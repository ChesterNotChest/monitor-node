"""Monitor Node - FastAPI Application.

On startup:
  1. Kills leftover zombie ffmpeg processes
  2. Enumerates all capture devices via ffmpeg
  3. (STREAM_DEBUG) Starts embedded RTMP server on :1935
  4. Starts the WSS client (persistent connection to Server)
  5. Starts the stream state machine (reconciliation loop)

On shutdown:
  1. Stops the state machine (terminates all ffmpeg subprocesses)
  2. Stops the WSS client
  3. (STREAM_DEBUG) Stops the RTMP server
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

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


# ---------------------------------------------------------------------------
# RTMP server helpers
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


async def _start_rtmp_server() -> None:
    """Launch the embedded Node.js RTMP server."""
    global _RTMP_SERVER_PROC
    node = _find_node()
    if node is None:
        logger.error("[STREAM_DEBUG] Node.js 未找到，RTMP 服务器无法启动")
        return
    try:
        _RTMP_SERVER_PROC = await asyncio.create_subprocess_exec(
            node, str(_RTMP_SERVER_DIR / "index.js"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(_RTMP_SERVER_DIR),
        )
    except Exception:
        logger.exception("[STREAM_DEBUG] RTMP 服务器启动失败")
        return
    try:
        line = await asyncio.wait_for(
            _RTMP_SERVER_PROC.stdout.readline(), timeout=5.0,
        )
    except asyncio.TimeoutError:
        pass
    await asyncio.sleep(0.5)
    if _RTMP_SERVER_PROC.returncode is not None:
        logger.error("[STREAM_DEBUG] RTMP 服务器异常退出，可能端口 1935 被占用")
        _RTMP_SERVER_PROC = None
        return
    if line:
        logger.info("[STREAM_DEBUG] %s", line.decode().strip())


async def _stop_rtmp_server() -> None:
    """Terminate the RTMP server."""
    global _RTMP_SERVER_PROC
    if _RTMP_SERVER_PROC is None:
        return
    try:
        _RTMP_SERVER_PROC.terminate()
        try:
            await asyncio.wait_for(_RTMP_SERVER_PROC.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            _RTMP_SERVER_PROC.kill()
            await _RTMP_SERVER_PROC.wait()
    except ProcessLookupError:
        pass
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
    from network.api import set_cached_devices
    from services.device_registry import device_registry

    # 1. Clean up leftover ffmpeg zombie processes from a previous crash
    await ffmpeg_runner.kill_zombies()

    # 2. Enumerate devices once at startup, cache for API use
    devices = await enumerate_devices()
    set_cached_devices(devices)
    logger.info("Startup device enumeration: %d device(s) found", len(devices))

    # 3. STREAM_DEBUG: start RTMP server + push ALL devices
    stream_debug = os.getenv("STREAM_DEBUG", "false").lower() in ("true", "1", "yes")
    if stream_debug and devices:
        await _start_rtmp_server()
        if _RTMP_SERVER_PROC is not None:
            logger.info(
                "[STREAM_DEBUG] RTMP 服务器已启动: rtmp://127.0.0.1:1935/live"
            )
            for device in devices:
                await device_registry.add(device)
                logger.info(
                    "[STREAM_DEBUG] 拉流地址: rtmp://127.0.0.1:1935/live/%s",
                    device.device_id,
                )
        else:
            logger.warning(
                "[STREAM_DEBUG] RTMP 服务器未能启动，跳过设备推流"
            )
    elif stream_debug:
        logger.warning("[STREAM_DEBUG] 未发现设备，无法推流")

    # 4. Start the WSS client (persistent connection to Server)
    wss_enabled = os.getenv("WSS_ENABLED", "true").lower() in ("true", "1", "yes")
    if wss_enabled:
        await wss_client.start()
        logger.info("WSS client enabled, connecting to %s", os.getenv("SERVER_WS_URL", ""))
    else:
        logger.info("WSS client disabled (WSS_ENABLED=false)")

    # 5. Start the stream state machine (reconciliation loop)
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

    logger.info("Monitor Node stopped.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Monitor Node API",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# HTTP Routes
# ---------------------------------------------------------------------------


@app.get("/")
def index():
    """Root endpoint returning service status."""
    return {"service": "monitor-node", "status": "running"}


@app.get("/health")
def health():
    """Health-check endpoint."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Device API (WebSocket + REST)
# ---------------------------------------------------------------------------

from network.api import router as device_router

app.include_router(device_router, prefix="/api")
