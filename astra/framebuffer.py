"""Latest-frame buffer shared between the encoder thread and HTTP workers.

Picamera2's ``FileOutput`` calls ``write()`` once per complete JPEG, so this
doubles as the encoder sink. Readers block on a condition variable rather than
polling, and always learn the frame id so they can detect "nothing new yet"
without spinning.
"""

from __future__ import annotations

import io
import threading
import time
from collections import deque


class FrameBuffer(io.BufferedIOBase):
    def __init__(self, fps_window: int = 30) -> None:
        self._cond = threading.Condition()
        self._frame: bytes | None = None
        self._frame_id = 0
        self._stamp: float | None = None
        self._recent: deque[float] = deque(maxlen=fps_window)

    # -- writer side ---------------------------------------------------------
    def writable(self) -> bool:
        return True

    def write(self, data) -> int:  # noqa: D102 - file-like protocol
        payload = bytes(data)
        now = time.monotonic()
        with self._cond:
            self._frame = payload
            self._frame_id += 1
            self._stamp = now
            self._recent.append(now)
            self._cond.notify_all()
        return len(payload)

    def reset(self) -> None:
        """Forget the current frame, e.g. while the pipeline is reconfiguring."""
        with self._cond:
            self._stamp = None
            self._recent.clear()
            self._cond.notify_all()

    # -- reader side ---------------------------------------------------------
    def latest(self) -> tuple[bytes | None, int]:
        with self._cond:
            return self._frame, self._frame_id

    def wait(self, last_id: int, timeout: float) -> tuple[bytes | None, int]:
        """Block until a frame newer than ``last_id`` arrives, or ``timeout``.

        Always returns; callers must treat an unchanged id as "no new frame"
        rather than looping without producing output.
        """
        with self._cond:
            if self._frame_id == last_id:
                self._cond.wait(timeout)
            return self._frame, self._frame_id

    def age(self) -> float | None:
        """Seconds since the last frame, or None if none has arrived."""
        with self._cond:
            if self._stamp is None:
                return None
            return time.monotonic() - self._stamp

    def fps(self) -> float:
        with self._cond:
            if len(self._recent) < 2:
                return 0.0
            span = self._recent[-1] - self._recent[0]
            if span <= 0:
                return 0.0
            return round((len(self._recent) - 1) / span, 1)
