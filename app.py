"""Monitor Node - FastAPI Application.

On startup:
  1. Kills leftover zombie ffmpeg processes
  2. Enumerates all capture devices via ffmpeg
  3. (DEBUG_WSS) Starts embedded mock WSS server
  4. (RTMP_DEBUG) Starts embedded RTMP server on :1935, pushes all devices
  5. Starts the WSS client with CommandHandler (persistent connection + auth)
  6. Starts the stream state machine (reconciliation loop)

On shutdown:
  1. Stops the state machine (terminates all ffmpeg subprocesses)
  2. Stops the WSS client
  3. (RTMP_DEBUG) Stops the RTMP server
  4. (DEBUG_WSS) Stops the mock WSS server

WSS is the sole Server→Node command channel.
REST and local WS endpoints have been removed.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("monitor-node")

_RTMP_SERVER_DIR = Path(__file__).parent / "rtmp_server"
_RTMP_SERVER_PROC: Optional[asyncio.subprocess.Process] = None

_MOCK_WSS_SERVER_DIR = Path(__file__).parent / "tests" / "mock_server"
_MOCK_WSS_SERVER_PROC: Optional[asyncio.subprocess.Process] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_node() -> Optional[str]:
    """Locate Node.js binary."""
    node = shutil.which("node") or shutil.which("node.exe")
    if node:
        return node
    for candidate in (
        r"C:\Program Files\nodejs\node.exe",
        r"C:\Program Files (x86)\nodejs\node.exe",
    ):
        if os.path.isfile(candidate):
            return candidate
    return None


async def _kill_subprocess(
    proc: Optional[asyncio.subprocess.Process],
    label: str = "",
) -> None:
    """Gracefully terminate a subprocess, force-kill after 5s timeout."""
    if proc is None or proc.returncode is not None:
        return
    try:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
    except ProcessLookupError:
        pass


# ---------------------------------------------------------------------------
# Mock WSS server (DEBUG_WSS)
# ---------------------------------------------------------------------------


async def _start_mock_wss_server() -> None:
    """Launch the embedded mock WSS server for DEBUG_WSS mode."""
    global _MOCK_WSS_SERVER_PROC
    node = _find_node()
    if node is None:
        logger.error("[DEBUG_WSS] Node.js 未找到，假 WSS 服务器无法启动")
        return

    script = _MOCK_WSS_SERVER_DIR / "mock_server.js"
    if not script.is_file():
        logger.error("[DEBUG_WSS] 假 WSS 服务器脚本不存在: %s", script)
        return

    try:
        _MOCK_WSS_SERVER_PROC = await asyncio.create_subprocess_exec(
            node, str(script),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(_MOCK_WSS_SERVER_DIR),
            env={**os.environ, "WSS_PORT": os.getenv("WSS_PORT", "8443")},
        )
    except Exception:
        logger.exception("[DEBUG_WSS] 假 WSS 服务器启动失败")
        return

    # 等一小段时间检查是否立即崩溃，同时收集启动输出
    await asyncio.sleep(1.5)
    if _MOCK_WSS_SERVER_PROC.returncode is not None:
        # 进程已退出 — 读取所有 stdout/stderr 输出并打印
        exit_code = _MOCK_WSS_SERVER_PROC.returncode
        output_lines: list[str] = []
        if _MOCK_WSS_SERVER_PROC.stdout:
            try:
                while True:
                    line = await asyncio.wait_for(
                        _MOCK_WSS_SERVER_PROC.stdout.readline(), timeout=0.5,
                    )
                    if not line:
                        break
                    output_lines.append(line.decode(errors="replace").rstrip())
            except asyncio.TimeoutError:
                pass
        logger.error(
            "[DEBUG_WSS] 假 WSS 服务器异常退出 (exit_code=%d, port=%s)",
            exit_code,
            os.getenv("WSS_PORT", "8443"),
        )
        if output_lines:
            for line in output_lines:
                logger.error("[DEBUG_WSS]   | %s", line)
        else:
            logger.error("[DEBUG_WSS]   (无输出)")
        # 额外排查线索
        logger.error("[DEBUG_WSS]   排查: node=%s, script=%s, cwd=%s",
                     _find_node(), str(script), str(_MOCK_WSS_SERVER_DIR))
        _MOCK_WSS_SERVER_PROC = None
        return

    logger.info(
        "[DEBUG_WSS] 假 WSS 服务器已启动: ws://127.0.0.1:%s/ws",
        os.getenv("WSS_PORT", "8443"),
    )

    # 启动后台任务持续读取 stdout，避免管道阻塞
    asyncio.create_task(_drain_stdout(_MOCK_WSS_SERVER_PROC, "[WSS mock]"))


async def _stop_mock_wss_server() -> None:
    """Terminate the mock WSS server."""
    global _MOCK_WSS_SERVER_PROC
    if _MOCK_WSS_SERVER_PROC is not None:
        await _kill_subprocess(_MOCK_WSS_SERVER_PROC, "mock WSS server")
    _MOCK_WSS_SERVER_PROC = None


# ---------------------------------------------------------------------------
# RTMP server (RTMP_DEBUG)
# ---------------------------------------------------------------------------


async def _drain_stdout(
    proc: asyncio.subprocess.Process,
    prefix: str = "",
) -> None:
    """持续读取子进程 stdout 并打日志，防止管道缓冲区阻塞。"""
    try:
        while proc.stdout and proc.returncode is None:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode(errors="replace").rstrip()
            if text:
                logger.info("%s %s", prefix, text)
    except Exception:
        pass


async def _start_rtmp_server() -> None:
    """Launch the embedded Node.js RTMP server."""
    global _RTMP_SERVER_PROC
    node = _find_node()
    if node is None:
        logger.error("[RTMP_DEBUG] Node.js 未找到，RTMP 服务器无法启动")
        return
    try:
        _RTMP_SERVER_PROC = await asyncio.create_subprocess_exec(
            node, str(_RTMP_SERVER_DIR / "index.js"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(_RTMP_SERVER_DIR),
        )
    except Exception:
        logger.exception("[RTMP_DEBUG] RTMP 服务器启动失败")
        return
    try:
        line = await asyncio.wait_for(
            _RTMP_SERVER_PROC.stdout.readline(), timeout=5.0,
        )
    except asyncio.TimeoutError:
        pass
    await asyncio.sleep(0.5)
    if _RTMP_SERVER_PROC.returncode is not None:
        logger.error("[RTMP_DEBUG] RTMP 服务器异常退出，可能端口 1935 被占用")
        _RTMP_SERVER_PROC = None
        return
    if line:
        logger.info("[RTMP_DEBUG] %s", line.decode(errors="replace").strip())

    # 后台持续读取 stdout
    asyncio.create_task(_drain_stdout(_RTMP_SERVER_PROC, "[RTMP server]"))


async def _stop_rtmp_server() -> None:
    """Terminate the RTMP server."""
    global _RTMP_SERVER_PROC
    if _RTMP_SERVER_PROC is not None:
        await _kill_subprocess(_RTMP_SERVER_PROC, "RTMP server")
    _RTMP_SERVER_PROC = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle for background tasks."""
    # ---- STARTUP ----
    logger.info("Monitor Node starting up …")

    # Lazy imports so services can import `app` if needed
    from services.device_enumerator import enumerate_devices
    from services.ffmpeg_runner import ffmpeg_runner
    from services.state_machine import state_machine
    from network.wss_client import wss_client
    from network.command_handler import CommandHandler
    from network.models import set_cached_devices
    from services.device_registry import device_registry

    # 1. Clean up leftover ffmpeg zombie processes from a previous crash
    await ffmpeg_runner.kill_zombies()

    # 2. Enumerate devices once at startup, cache for CommandHandler use
    devices = await enumerate_devices()
    set_cached_devices(devices)
    logger.info("Startup device enumeration: %d device(s) found", len(devices))

    # 3. DEBUG_WSS: start embedded mock WSS server (before WSS client)
    debug_wss = os.getenv("DEBUG_WSS", "false").lower() in ("true", "1", "yes")
    if debug_wss:
        await _start_mock_wss_server()

    # 4. RTMP_DEBUG: start RTMP server + push ALL devices
    rtmp_debug = os.getenv("RTMP_DEBUG", "false").lower() in ("true", "1", "yes")
    if rtmp_debug and devices:
        await _start_rtmp_server()
        if _RTMP_SERVER_PROC is not None:
            logger.info(
                "[RTMP_DEBUG] RTMP 服务器已启动: rtmp://127.0.0.1:1935/live"
            )
            from services.ffmpeg_runner import _build_rtmp_url
            for device in devices:
                await device_registry.add(device)
                # 使用与实际推流一致的 URL 格式打印拉流地址
                actual_url = _build_rtmp_url(device)
                logger.info(
                    "[RTMP_DEBUG] 拉流地址: %s",
                    actual_url,
                )
        else:
            logger.warning(
                "[RTMP_DEBUG] RTMP 服务器未能启动，跳过设备推流"
            )
    elif rtmp_debug:
        logger.warning("[RTMP_DEBUG] 未发现设备，无法推流")

    # 5. Start the WSS client with CommandHandler
    #    WSS is always enabled now — it's the sole command channel
    handler = CommandHandler(wss_client)
    wss_client.set_message_handler(handler.dispatch)

    # 认证成功后自动重启所有运行中的流，使 NodeID 从 "unauthenticated" 更新为真实值
    async def _on_auth_restart_streams(node_id: str) -> None:
        running = ffmpeg_runner.list_running()
        if running:
            logger.info(
                "WSS 认证完成 (NodeID=%s)，重启 %d 个运行中的流以更新 RTMP URL",
                node_id, len(running),
            )
            for device_id in list(running):
                await ffmpeg_runner.stop_stream(device_id)
            # 状态机在下一个 tick 会自动重启它们，届时 URL 将包含正确的 NodeID

    wss_client.set_on_auth_complete(_on_auth_restart_streams)
    await wss_client.start()
    logger.info(
        "WSS client started (DEBUG_WSS=%s, target=%s)",
        os.getenv("DEBUG_WSS", "false"),
        wss_client._resolve_url(),
    )

    # 6. Start the stream state machine (reconciliation loop)
    await state_machine.start()

    # ---- YIELD (app runs here) ----
    yield

    # ---- SHUTDOWN ----
    logger.info("Monitor Node shutting down …")

    # 1. Stop the state machine (terminates all ffmpeg processes)
    await state_machine.shutdown()

    # 2. Stop the WSS client
    await wss_client.stop()

    # 3. Stop the RTMP server
    await _stop_rtmp_server()

    # 4. Stop the mock WSS server
    await _stop_mock_wss_server()

    logger.info("Monitor Node stopped.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Monitor Node API",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# HTTP Routes (minimal — health only)
# ---------------------------------------------------------------------------


@app.get("/")
def index():
    """Root endpoint returning service status."""
    return {"service": "monitor-node", "status": "running"}


@app.get("/health")
def health():
    """Health-check endpoint."""
    return {"status": "ok"}
