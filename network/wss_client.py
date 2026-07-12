"""WSS Client — persistent WebSocket connection to remote Server.

Features:
- Token-based identity authentication (token → session_token + device maps)
- Exponential backoff reconnection (1s → 2s → 4s → … max 60s)
- Heartbeat every 30s (only after successful authentication)
- Message dispatch by ``command`` field after authentication
- DEBUG_WSS mode: fixed token, local non-encrypted WebSocket

Protocol (aligned with Server's node-wss-connection spec):
  Node → Server:  {"token": "xxx"}
  Server → Node:  {"session_token": "sess_xxx", "videos": [...], "audios": [...]}
  Server → Node:  {"command": "UPDATE_STREAM", "device_type": "video", "device_id": 1, "enable": true}
  Node → Server:  {"success": true, "message": null}

Usage::

    client = WssClient()
    await client.start()
    # After auth completes, client.session_token and device maps are available
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable, Optional

import websockets
import websockets.exceptions

from constant import AuthStatus
from network.models import clear_server_device_maps, set_server_device_maps

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HEARTBEAT_INTERVAL = 30     # seconds
_INITIAL_BACKOFF = 1.0       # seconds
_MAX_BACKOFF = 60.0          # seconds
_BACKOFF_MULTIPLIER = 2.0
_AUTH_TIMEOUT = 10.0         # seconds to wait for auth response

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]

# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class WssClient:
    """WebSocket Secure client with reconnection, auth, and heartbeat."""

    def __init__(
        self,
        url: Optional[str] = None,
        message_handler: Optional[MessageHandler] = None,
    ) -> None:
        self._url = url  # None → will be built from config in start()
        self._handler = message_handler or self._default_handler

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._connected = False
        self._backoff = _INITIAL_BACKOFF

        # 身份认证状态
        self._session_token: Optional[str] = None
        self._auth_status = AuthStatus.PENDING

        # 认证完成回调（auth 成功后触发，用于重启流等）
        self._on_auth_complete: Optional[Callable[[str], Awaitable[None]]] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_authenticated(self) -> bool:
        return self._auth_status == AuthStatus.AUTHENTICATED

    @property
    def session_token(self) -> Optional[str]:
        """Server 分配的 session_token，认证成功后方可用。"""
        return self._session_token

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch the WSS connection loop as a background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._connect_loop())
        logger.info("WSS client started, target: %s", self._resolve_url())

    async def stop(self) -> None:
        """Close the connection and stop the reconnect loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._disconnect()
        logger.info("WSS client stopped")

    # ------------------------------------------------------------------
    # URL resolution
    # ------------------------------------------------------------------

    def _resolve_url(self) -> str:
        """Build WSS URL from config fields.

        DEBUG_WSS=true → ws://127.0.0.1:{WSS_PORT}/ws
        否则           → {WSS_SCHEME}://{SERVER_BASE_URL}:{WSS_PORT}/ws
                        WSS_SCHEME defaults to ws for the current FastAPI
                        server; set it to wss when fronted by TLS/nginx.
        """
        if self._url:
            return self._url

        is_debug_wss = os.getenv("DEBUG_WSS", "false").lower() in ("true", "1", "yes")
        base = "127.0.0.1" if is_debug_wss else os.getenv("SERVER_BASE_URL", "127.0.0.1")
        port = os.getenv("WSS_PORT", "8443")
        protocol = "ws" if is_debug_wss else os.getenv("WSS_SCHEME", "ws").lower()
        if protocol not in ("ws", "wss"):
            logger.warning("Invalid WSS_SCHEME=%s, falling back to ws", protocol)
            protocol = "ws"
        return f"{protocol}://{base}:{port}/ws"

    def _resolve_token(self) -> str:
        """Resolve authentication token.

        DEBUG_WSS=true → 固定 Token "debug-token-fixed"
        否则           → 从 SECRET_KEY 环境变量读取
        """
        is_debug_wss = os.getenv("DEBUG_WSS", "false").lower() in ("true", "1", "yes")
        if is_debug_wss:
            return "debug-token-fixed"
        return os.getenv("SECRET_KEY", "")

    # ------------------------------------------------------------------
    # Connection loop
    # ------------------------------------------------------------------

    async def _connect_loop(self) -> None:
        """Main loop: connect, authenticate, then run heartbeat + receive until disconnect."""
        while self._running:
            try:
                await self._connect()
                self._backoff = _INITIAL_BACKOFF  # reset on success

                # 认证阶段
                authenticated = await self._authenticate()
                if not authenticated:
                    # 认证失败 — 断开并重连
                    await self._disconnect()
                    if self._running:
                        await asyncio.sleep(self._backoff)
                        self._backoff = min(
                            self._backoff * _BACKOFF_MULTIPLIER,
                            _MAX_BACKOFF,
                        )
                    continue

                # 认证成功 — 进入心跳 + 指令收发
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._heartbeat_loop())
                    tg.create_task(self._receive_loop())
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("WSS connection error")

            # Exponential backoff before reconnecting
            if self._running:
                logger.info(
                    "WSS reconnecting in %.1fs (backoff cap 60s)",
                    self._backoff,
                )
                await asyncio.sleep(self._backoff)
                self._backoff = min(
                    self._backoff * _BACKOFF_MULTIPLIER,
                    _MAX_BACKOFF,
                )

    async def _connect(self) -> None:
        """Establish a single WebSocket connection."""
        url = self._resolve_url()
        logger.info("WSS connecting to %s", url)
        # Disable SSL verification for self-signed certs in dev
        ssl_context = None
        if "wss://" in url:
            import ssl
            ssl_context = ssl.create_default_context()
            # Allow self-signed certs in debug mode
            if os.getenv("DEBUG_INFO", "false").lower() in ("true", "1"):
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

        self._ws = await websockets.connect(
            url,
            ssl=ssl_context if ssl_context else None,
            ping_interval=None,  # we handle heartbeat ourselves
        )
        self._connected = True
        logger.info("WSS connected")

    async def _disconnect(self) -> None:
        """Close the WebSocket connection and reset auth state."""
        self._connected = False
        self._auth_status = AuthStatus.PENDING
        self._session_token = None
        clear_server_device_maps()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def _authenticate(self) -> bool:
        """Send token and wait for session_token + device maps.

        Protocol (aligned with Server):
          Node → Server:  {"token": "xxx"}
          Server → Node:  {"session_token": "sess_xxx", "videos": [...], "audios": [...]}

        Reads from the websocket directly until response or timeout.
        Non-auth messages received during this phase are buffered.
        """
        self._auth_status = AuthStatus.PENDING
        self._session_token = None

        token = self._resolve_token()
        # 认证消息格式对齐 Server：{"token": "xxx"}（无 type 包装）
        await self._send({"token": token})
        logger.info("WSS auth sent (token: %s...)", token[:8] if len(token) > 8 else token)

        deadline = asyncio.get_event_loop().time() + _AUTH_TIMEOUT
        buffered: list[dict[str, Any]] = []

        while self._connected and self._ws:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                logger.error("WSS authentication timed out after %ss", _AUTH_TIMEOUT)
                self._auth_status = AuthStatus.REJECTED
                return False

            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=min(remaining, 1.0))
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WSS connection closed during authentication")
                self._auth_status = AuthStatus.REJECTED
                self._connected = False
                return False

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("WSS received invalid JSON during auth: %s", raw[:200])
                continue

            # Server 认证成功响应：{"session_token": "...", "videos": [...], "audios": [...]}
            if "session_token" in data:
                self._session_token = data["session_token"]
                self._auth_status = AuthStatus.AUTHENTICATED

                # 填充 Server 设备映射表
                videos = data.get("videos", [])
                audios = data.get("audios", [])
                set_server_device_maps(videos, audios)

                logger.info(
                    "WSS authenticated, session_token=%s, videos=%d, audios=%d",
                    self._session_token[:16] + "..." if len(self._session_token) > 16 else self._session_token,
                    len(videos),
                    len(audios),
                )

                # 将缓冲的非认证消息交给 handler 处理
                for buffered_msg in buffered:
                    try:
                        await self._handler(buffered_msg)
                    except Exception:
                        logger.exception("WSS handler failed for buffered message")
                # 通知认证完成（app.py 用此重启流）
                if self._on_auth_complete and self._session_token:
                    try:
                        await self._on_auth_complete(self._session_token)
                    except Exception:
                        logger.exception("on_auth_complete callback failed")
                return True

            # 非认证消息：缓冲起来，等认证成功后交给 handler
            logger.debug(
                "WSS buffering non-auth message during authentication: %s",
                data.get("command", data.get("type", "unknown")),
            )
            buffered.append(data)

        return False

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat pings with device list. Only runs after authentication."""
        from services.device_registry import device_registry
        from network.models import get_cached_devices

        while self._connected and self._running:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            if self._connected and self._ws and self._auth_status == AuthStatus.AUTHENTICATED:
                try:
                    # merge enabled + cached devices so Server knows all available devices
                    seen: set[tuple[str, str]] = set()
                    merged: list[dict[str, str]] = []
                    for d in await device_registry.list():
                        key = (d.device_type, d.device_name)
                        if key not in seen:
                            seen.add(key)
                            merged.append({"device_type": d.device_type, "device_name": d.device_name})
                    for d in get_cached_devices():
                        key = (d.device_type, d.device_name)
                        if key not in seen:
                            seen.add(key)
                            merged.append({"device_type": d.device_type, "device_name": d.device_name})
                    await self._send({
                        "type": "heartbeat",
                        "devices": merged,
                    })
                except Exception:
                    logger.warning("Heartbeat send failed, connection may be dead")
                    break

    # ------------------------------------------------------------------
    # Receive & dispatch
    # ------------------------------------------------------------------

    async def _receive_loop(self) -> None:
        """Receive messages and dispatch to the registered handler.

        Only runs after successful authentication — auth messages are handled
        directly by _authenticate().
        """
        while self._connected and self._running and self._ws:
            try:
                raw = await self._ws.recv()
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WSS connection closed by server")
                break
            except asyncio.CancelledError:
                break

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("WSS received invalid JSON: %s", raw[:200])
                continue

            command = data.get("command")
            if command:
                logger.debug("WSS received command: %s", command)
            try:
                await self._handler(data)
            except Exception:
                logger.exception("WSS message handler failed for: %s", data)

        self._connected = False

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    async def _send(self, data: dict[str, Any]) -> None:
        """Send a JSON message over the WebSocket."""
        if self._ws and self._connected:
            await self._ws.send(json.dumps(data))

    async def send(self, data: dict[str, Any]) -> bool:
        """Public send — returns False if not connected or not authenticated."""
        if not self._connected or self._ws is None:
            return False
        if self._auth_status != AuthStatus.AUTHENTICATED:
            logger.warning("WSS send blocked: not yet authenticated")
            return False
        try:
            await self._send(data)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Default handler
    # ------------------------------------------------------------------

    async def _default_handler(self, data: dict[str, Any]) -> None:
        """Default message handler — logs warning when no handler registered."""
        command = data.get("command", "unknown")
        logger.warning(
            "WSS received message but no handler registered (command=%s)", command
        )

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Replace the message handler at runtime."""
        self._handler = handler


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

wss_client = WssClient()
