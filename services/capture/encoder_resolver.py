"""Dynamic ffmpeg encoder detection.

Runs ``ffmpeg -encoders`` once at module load, caches results.
Every ``capture_command()`` calls ``get_video_encoder()`` and
``get_audio_encoder()`` instead of hardcoding codec names.
"""

from __future__ import annotations

import functools
import logging
import subprocess

logger = logging.getLogger(__name__)

# Fallbacks — always available in any ffmpeg build
_FALLBACK_VIDEO = "mpeg4"
_FALLBACK_AUDIO = "aac"

# Priority order (first found wins)
_VIDEO_PRIORITY = ("libx264", "libopenh264", "h264_mf", "mpeg4")
_AUDIO_PRIORITY = ("aac", "libmp3lame")


@functools.lru_cache(maxsize=1)
def _detect_encoders() -> str:
    """Run ``ffmpeg -encoders`` and return stdout.  Cached after first call."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-encoders"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout
    except Exception:
        logger.warning("Cannot run 'ffmpeg -encoders' — using fallback encoders")
        return ""


def _pick_encoder(priority: tuple[str, ...], fallback: str) -> str:
    """Return the first encoder from *priority* found in ffmpeg output."""
    output = _detect_encoders()
    for codec in priority:
        if codec in output:
            logger.debug("Selected encoder: %s", codec)
            return codec
    logger.debug("No preferred encoder found — using fallback: %s", fallback)
    return fallback


def get_video_encoder() -> str:
    """Return the best available video encoder name."""
    return _pick_encoder(_VIDEO_PRIORITY, _FALLBACK_VIDEO)


def get_audio_encoder() -> str:
    """Return the best available audio encoder name."""
    return _pick_encoder(_AUDIO_PRIORITY, _FALLBACK_AUDIO)
