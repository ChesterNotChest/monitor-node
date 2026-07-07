"""Monitor Node - FastAPI Application."""

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

app = FastAPI(
    title="Monitor Node API",
    docs_url="/docs",
    redoc_url=None,
)


# ------------------------------------------------------------------
# HTTP Routes
# ------------------------------------------------------------------


@app.get("/")
def index():
    """Root endpoint returning service status."""
    return {"service": "monitor-node", "status": "running"}


@app.get("/health")
def health():
    """Health-check endpoint."""
    return {"status": "ok"}


# ------------------------------------------------------------------
# Device API (WebSocket + REST)
# ------------------------------------------------------------------

from network.api import router as device_router

app.include_router(device_router, prefix="/api")
