from __future__ import annotations

import itertools
import time

import pytest

from astra import config
from astra.web import create_app
from conftest import FakeCamera


def test_index_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"ASTRA" in response.data


def test_state_payload_shape(client):
    payload = client.get("/api/state").get_json()
    assert set(payload) == {"settings", "limits", "status", "presets"}
    assert "exposure_us" in payload["settings"]
    assert payload["limits"]["gain"] == [1.0, 16.0]


def test_controls_rejects_non_object_body(client):
    assert client.post("/api/controls", json=["gain", 4]).status_code == 400
    assert client.post("/api/controls", data="junk").status_code == 400


def test_controls_applies_and_clamps(client, camera):
    payload = client.post("/api/controls", json={"gain": 999, "mono": True}).get_json()
    assert payload["settings"]["gain"] == camera.limits.gain[1]
    assert payload["settings"]["mono"] is True


def test_controls_ignores_unknown_keys(client):
    response = client.post("/api/controls", json={"__class__": "boom"})
    assert response.status_code == 200


def test_preset_applies(client):
    payload = client.post("/api/preset/moon").get_json()
    assert payload["settings"]["metering"] == "spot"
    assert payload["settings"]["auto_exposure"] is True


@pytest.mark.parametrize("name", ["nope", "../secrets", "__init__"])
def test_unknown_preset_is_rejected(client, name):
    assert client.post(f"/api/preset/{name}").status_code in (404, 405)


def test_frame_endpoint(client, camera):
    assert client.get("/frame.jpg").status_code == 503
    camera.frames.write(b"jpegbytes")
    response = client.get("/frame.jpg")
    assert response.status_code == 200
    assert response.data == b"jpegbytes"
    assert "no-store" in response.headers["Cache-Control"]


def test_capture_requires_a_frame(client, camera):
    assert client.get("/capture").status_code == 503
    camera.frames.write(b"jpegbytes")
    response = client.get("/capture")
    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    assert ".jpg" in response.headers["Content-Disposition"]


def test_full_capture_uses_the_still_path(client, camera):
    camera.frames.write(b"jpegbytes")
    assert client.get("/capture?full=1").status_code == 200
    assert camera.full_captures == 1


def test_healthz_reflects_camera_state(client, camera):
    assert client.get("/healthz").status_code == 200
    camera.state = "error"
    assert client.get("/healthz").status_code == 503


def test_stream_never_blocks_silently(monkeypatch, camera):
    """Regression guard for the bug that wedged the old server.

    With no frames at all the generator must still emit output so the WSGI
    layer can notice a disconnected client, and it must terminate on its own.
    """
    monkeypatch.setattr(config, "MJPEG_MAX_SECONDS", 2)
    client = create_app(camera).test_client()

    started = time.monotonic()
    response = client.get("/stream.mjpg")
    chunks = list(response.response)
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert chunks, "generator produced nothing"
    assert elapsed < 10, "generator did not terminate"
    response.close()


def test_stream_emits_frames(monkeypatch, camera):
    monkeypatch.setattr(config, "MJPEG_MAX_SECONDS", 3)
    client = create_app(camera).test_client()
    camera.frames.write(b"\xff\xd8payload\xff\xd9")

    response = client.get("/stream.mjpg")
    chunk = next(itertools.islice(iter(response.response), 1))
    response.close()

    assert b"Content-Type: image/jpeg" in chunk
    assert b"\xff\xd8payload\xff\xd9" in chunk


def test_concurrent_streams_are_capped(monkeypatch, camera):
    monkeypatch.setattr(config, "MAX_MJPEG_CLIENTS", 1)
    monkeypatch.setattr(config, "MJPEG_MAX_SECONDS", 2)
    client = create_app(camera).test_client()

    first = client.get("/stream.mjpg")
    next(iter(first.response))  # force the generator to start
    second = client.get("/stream.mjpg")

    assert second.status_code == 503
    first.close()
