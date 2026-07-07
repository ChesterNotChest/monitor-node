"""Monitor Node - FastAPI Application.

On startup:
  1. Kills leftover zombie ffmpeg processes
  2. Enumerates all capture devices via ffmpeg
  3. Starts the WSS client (persistent connection to Server)
  4. Starts the stream state machine (reconciliation loop)

On shutdown:
  1. Stops the state machine (which terminates all ffmpeg subprocesses)
  2. Stops the WSS client
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

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

    # 1. Clean up leftover ffmpeg zombie processes from a previous crash
    await ffmpeg_runner.kill_zombies()

    # 2. Enumerate devices once at startup, cache for API use
    devices = await enumerate_devices()
    set_cached_devices(devices)
    logger.info("Startup device enumeration: %d device(s) found", len(devices))

    # 3. Start the WSS client (persistent connection to Server)
    wss_enabled = os.getenv("WSS_ENABLED", "true").lower() in ("true", "1", "yes")
    if wss_enabled:
        await wss_client.start()
        logger.info("WSS client enabled, connecting to %s", os.getenv("SERVER_WS_URL", ""))
    else:
        logger.info("WSS client disabled (WSS_ENABLED=false)")

    # 4. Start the stream state machine (reconciliation loop)
    await state_machine.start()

    # ---- YIELD (app runs here) ----
    yield

    # ---- SHUTDOWN ----
    logger.info("Monitor Node shutting down …")

    # 1. Stop the state machine (terminates all ffmpeg processes)
    await state_machine.shutdown()

    # 2. Stop the WSS client
    await wss_client.stop()

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
