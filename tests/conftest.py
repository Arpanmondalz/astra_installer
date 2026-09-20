"""Shared fixtures. These tests run anywhere - no Pi or picamera2 required."""

from __future__ import annotations

import pytest

from astra import presets
from astra.camera import CameraUnavailable
from astra.framebuffer import FrameBuffer
from astra.settings import Limits, Settings
from astra.web import create_app


class FakeCamera:
    """Implements the surface area that :func:`astra.web.create_app` consumes."""

    def __init__(self, limits: Limits | None = None) -> None:
        self.frames = FrameBuffer()
        self.limits = limits or Limits()
        self.settings = Settings().clamped(self.limits)
        self.state = "running"
        self.full_captures = 0

    def status(self) -> dict:
        return {
            "state": self.state,
            "error": None,
            "fps": self.frames.fps(),
            "frame_age": self.frames.age(),
            "stream_size": [1296, 972],
            "still_size": [2592, 1944],
        }

    def apply(self, patch) -> Settings:
        self.settings = self.settings.merged(patch, self.limits)
        return self.settings

    def apply_preset(self, name: str) -> Settings:
        return self.apply(presets.patch_for(name))

    def latest_frame(self):
        return self.frames.latest()

    def wait_frame(self, last_id, timeout):
        return self.frames.wait(last_id, timeout)

    def capture(self, full: bool = False) -> bytes:
        frame, _ = self.frames.latest()
        if frame is None:
            raise CameraUnavailable("no frame available yet")
        if full:
            self.full_captures += 1
        return frame


@pytest.fixture()
def camera() -> FakeCamera:
    return FakeCamera()


@pytest.fixture()
def client(camera):
    app = create_app(camera)
    app.config.update(TESTING=True)
    return app.test_client()
