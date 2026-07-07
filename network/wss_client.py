"""WSS Client — persistent WebSocket connection to remote Server.

Features:
- Exponential backoff reconnection (1s → 2s → 4s → … max 60s)
- Heartbeat every 30s
- Message dispatch by ``command`` field
- Aligns with ``ServerCommand`` enum

Usage::

    client = WssClient(server_url, message_handler)
    await client.start()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable, Optional

import websockets
import websockets.exceptions

from constant import ServerCommand

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HEARTBEAT_INTERVAL = 30     # seconds
_INITIAL_BACKOFF = 1.0       # seconds
_MAX_BACKOFF = 60.0          # seconds
_BACKOFF_MULTIPLIER = 2.0

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]

# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class WssClient:
    """WebSocket Secure client with reconnection and heartbeat."""

    def __init__(
        self,
        url: Optional[str] = None,
        message_handler: Optional[MessageHandler] = None,
    ) -> None:
        self._url = url or os.getenv("SERVER_WS_URL", "ws://127.0.0.1:8443/ws")
        self._handler = message_handler or self._default_handler

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._connected = False
        self._backoff = _INITIAL_BACKOFF

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch the WSS connection loop as a background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._connect_loop())
        logger.info("WSS client started, target: %s", self._url)

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
    # Connection loop
    # ------------------------------------------------------------------

    async def _connect_loop(self) -> None:
        """Main loop: connect, then run heartbeat + receive until disconnect."""
        while self._running:
            try:
                await self._connect()
                self._backoff = _INITIAL_BACKOFF  # reset on success
                # Run heartbeat concurrently with message receive
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
        logger.info("WSS connecting to %s", self._url)
        # Disable SSL verification for self-signed certs in dev
        ssl_context = None
        if "wss://" in self._url:
            import ssl
            ssl_context = ssl.create_default_context()
            # Allow self-signed certs in debug mode
            if os.getenv("DEBUG_INFO", "false").lower() in ("true", "1"):
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

        self._ws = await websockets.connect(
            self._url,
            ssl=ssl_context if ssl_context else None,
            ping_interval=None,  # we handle heartbeat ourselves
        )
        self._connected = True
        logger.info("WSS connected")

    async def _disconnect(self) -> None:
        """Close the WebSocket connection gracefully."""
        self._connected = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat pings."""
        while self._connected and self._running:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            if self._connected and self._ws:
                try:
                    await self._send({"type": "heartbeat"})
                except Exception:
                    logger.warning("Heartbeat send failed, connection may be dead")
                    break

    # ------------------------------------------------------------------
    # Receive & dispatch
    # ------------------------------------------------------------------

    async def _receive_loop(self) -> None:
        """Receive messages and dispatch to handler."""
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
        """Public send — returns False if not connected."""
        if not self._connected or self._ws is None:
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
        """Default message handler — logs and no-ops."""
        command = data.get("command", "unknown")
        logger.info("WSS message received (command=%s), no handler registered", command)

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
