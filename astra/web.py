"""HTTP layer.

The previous build wedged itself because ``waitress`` defaults to four worker
threads and the MJPEG generator could loop forever without ever writing to the
socket - so a disconnect was never detected and the thread was never returned.
Three things prevent that here:

* the generator yields on *every* iteration, including timeouts;
* streams are capped in both count and duration;
* the default preview transport is plain snapshot polling, which uses only
  short-lived requests and degrades gracefully on a weak link.
"""

from __future__ import annotations

import io
import logging
import threading
import time
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

from . import config, presets
from .camera import CameraUnavailable

log = logging.getLogger(__name__)

_BOUNDARY = "astraframe"


def _keepalive_jpeg() -> bytes | None:
    """A tiny black JPEG used to keep an MJPEG socket writable while starved."""
    try:
        from PIL import Image  # noqa: PLC0415

        buffer = io.BytesIO()
        Image.new("L", (64, 48), 0).save(buffer, format="JPEG", quality=30)
        return buffer.getvalue()
    except Exception:  # noqa: BLE001
        return None


def create_app(camera) -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    stream_slots = threading.Semaphore(config.MAX_MJPEG_CLIENTS)
    placeholder = _keepalive_jpeg()

    def state_payload() -> dict:
        return {
            "settings": camera.settings.to_dict(),
            "limits": camera.limits.to_dict(),
            "status": camera.status(),
            "presets": presets.listing(),
        }

    def no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        return response

    @app.get("/")
    def index() -> Response:
        return Response(render_template("index.html"), mimetype="text/html")

    @app.get("/healthz")
    def healthz():
        status = camera.status()
        code = 200 if status["state"] in ("running", "starting") else 503
        return jsonify(status), code

    @app.get("/api/state")
    def api_state():
        return jsonify(state_payload())

    @app.post("/api/controls")
    def api_controls():
        patch = request.get_json(silent=True)
        if not isinstance(patch, dict):
            return jsonify({"error": "expected a JSON object"}), 400
        camera.apply(patch)
        return jsonify(state_payload())

    @app.post("/api/preset/<name>")
    def api_preset(name: str):
        try:
            camera.apply_preset(name)
        except KeyError:
            return jsonify({"error": "unknown preset"}), 404
        return jsonify(state_payload())

    @app.get("/frame.jpg")
    def frame():
        frame_bytes, _ = camera.latest_frame()
        if frame_bytes is None:
            return no_store(Response("no frame yet", status=503, mimetype="text/plain"))
        return no_store(Response(frame_bytes, mimetype="image/jpeg"))

    @app.get("/stream.mjpg")
    def stream():
        if not stream_slots.acquire(blocking=False):
            return Response("too many streams", status=503, mimetype="text/plain")

        def generate():
            try:
                last_id = -1
                last_sent = placeholder
                deadline = time.monotonic() + config.MJPEG_MAX_SECONDS
                while time.monotonic() < deadline:
                    frame_bytes, last_id = camera.wait_frame(last_id, timeout=1.0)
                    payload = frame_bytes or last_sent
                    if payload is None:
                        # Nothing to send yet; a bare CRLF is legal multipart
                        # filler and still proves the client is alive.
                        yield b"\r\n"
                        continue
                    last_sent = payload
                    yield (
                        f"--{_BOUNDARY}\r\n"
                        f"Content-Type: image/jpeg\r\n"
                        f"Content-Length: {len(payload)}\r\n\r\n"
                    ).encode("ascii") + payload + b"\r\n"
            finally:
                stream_slots.release()

        return no_store(
            Response(
                generate(),
                mimetype=f"multipart/x-mixed-replace; boundary={_BOUNDARY}",
            )
        )

    @app.get("/capture")
    def capture():
        full = request.args.get("full", "0") not in ("0", "", "false", "no")
        try:
            payload = camera.capture(full=full)
        except CameraUnavailable as exc:
            return jsonify({"error": str(exc)}), 503
        except Exception as exc:  # noqa: BLE001
            log.exception("capture failed")
            return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

        suffix = "full" if full else "live"
        name = datetime.now().strftime(f"astra_%Y%m%d_%H%M%S_{suffix}.jpg")
        response = Response(payload, mimetype="image/jpeg")
        response.headers["Content-Disposition"] = f'attachment; filename="{name}"'
        return no_store(response)

    return app
