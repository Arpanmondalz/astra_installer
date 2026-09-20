"""Runtime configuration. Everything is overridable via environment variables."""

from __future__ import annotations

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _size(name: str, default: tuple[int, int]) -> tuple[int, int]:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        w, h = (int(part) for part in raw.lower().split("x", 1))
        return (w, h)
    except ValueError:
        return default


# --- Network -----------------------------------------------------------------
HOST = os.environ.get("ASTRA_HOST", "0.0.0.0")
PORT = _int("ASTRA_PORT", 80)

# Waitress needs far more threads than its default of 4, because every in-flight
# MJPEG stream pins one for its entire lifetime.
SERVER_THREADS = _int("ASTRA_THREADS", 16)
SERVER_CHANNEL_TIMEOUT = _int("ASTRA_CHANNEL_TIMEOUT", 30)

# --- Camera ------------------------------------------------------------------
# OV5647 mode 1296x972 is 2x2 binned: full field of view and 4x the light per
# pixel compared with the 1920x1080 mode, which is a centre crop of the sensor.
STREAM_SIZE = _size("ASTRA_STREAM_SIZE", (1296, 972))
STILL_SIZE = _size("ASTRA_STILL_SIZE", (2592, 1944))

# 10 fps keeps the stream inside the ~10-20 Mbit/s a Pi Zero 2 W access point
# can actually deliver. Higher rates stall the link rather than looking smoother.
STREAM_FPS = _int("ASTRA_STREAM_FPS", 10)
STREAM_BITRATE = _int("ASTRA_STREAM_BITRATE", 6_000_000)
STILL_QUALITY = _int("ASTRA_STILL_QUALITY", 92)

# --- Reliability -------------------------------------------------------------
# Restart the pipeline if the encoder goes this long without producing a frame.
STALL_TIMEOUT = _int("ASTRA_STALL_TIMEOUT", 8)
RESTART_BACKOFF_MAX = _int("ASTRA_RESTART_BACKOFF_MAX", 30)

# Bound both the number and the lifetime of MJPEG streams so a misbehaving
# client can never accumulate stuck worker threads.
MAX_MJPEG_CLIENTS = _int("ASTRA_MAX_MJPEG_CLIENTS", 3)
MJPEG_MAX_SECONDS = _int("ASTRA_MJPEG_MAX_SECONDS", 300)
