from __future__ import annotations

import threading
import time

from astra.framebuffer import FrameBuffer


def test_empty_buffer_reports_no_frame():
    buffer = FrameBuffer()
    assert buffer.latest() == (None, 0)
    assert buffer.age() is None
    assert buffer.fps() == 0.0


def test_write_publishes_and_increments_id():
    buffer = FrameBuffer()
    buffer.write(b"abc")
    buffer.write(b"defg")
    frame, frame_id = buffer.latest()
    assert frame == b"defg"
    assert frame_id == 2
    assert buffer.age() < 1.0


def test_wait_returns_promptly_when_a_frame_is_already_newer():
    buffer = FrameBuffer()
    buffer.write(b"x")
    started = time.monotonic()
    frame, frame_id = buffer.wait(last_id=0, timeout=5.0)
    assert frame == b"x" and frame_id == 1
    assert time.monotonic() - started < 0.5


def test_wait_times_out_without_blocking_forever():
    """The old generator could spin here without ever producing output."""
    buffer = FrameBuffer()
    started = time.monotonic()
    frame, frame_id = buffer.wait(last_id=0, timeout=0.2)
    elapsed = time.monotonic() - started
    assert frame is None and frame_id == 0
    assert 0.15 < elapsed < 2.0


def test_wait_is_woken_by_a_writer():
    buffer = FrameBuffer()
    threading.Timer(0.1, buffer.write, args=(b"late",)).start()
    frame, frame_id = buffer.wait(last_id=0, timeout=3.0)
    assert frame == b"late" and frame_id == 1


def test_reset_clears_timing_but_keeps_last_frame():
    buffer = FrameBuffer()
    buffer.write(b"frame")
    buffer.reset()
    assert buffer.age() is None
    assert buffer.latest()[0] == b"frame"


def test_fps_estimate():
    buffer = FrameBuffer()
    for _ in range(5):
        buffer.write(b"f")
        time.sleep(0.02)
    assert buffer.fps() > 0
