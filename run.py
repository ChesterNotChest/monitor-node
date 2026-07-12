"""Entry point for running the Monitor Node application."""

import os

from dotenv import load_dotenv

load_dotenv()

from app import app

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("MONITOR_PORT", "5000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
