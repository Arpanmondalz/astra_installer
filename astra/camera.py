"""Picamera2 camera pipeline.

Design notes
------------
* One long-lived ``Picamera2`` object. Exposure, gain, EV, AWB, saturation and
  zoom are applied with ``set_controls()`` while the stream keeps running, so
  moving a slider no longer tears the pipeline down and blacks out the preview.
  Only a flip change needs a reconfigure, because Transform is baked into the
  stream configuration.
* ``FrameDurationLimits`` is set explicitly. ``rpicam-vid --framerate`` silently
  clamps exposure to the frame duration, which is why the old build could never
  actually reach its requested long exposures.
* A supervisor thread owns startup, retry-with-backoff and stall recovery, so a
  camera that is not ready at boot never turns into a systemd crash loop.
"""

from __future__ import annotations

import io
import logging
import threading
import time
from typing import Any, Mapping

from . import config, presets
from .framebuffer import FrameBuffer
from .geometry import centred_crop
from .settings import Limits, Settings

log = logging.getLogger(__name__)


def _import_picamera2():
    from libcamera import Transform, controls as libcontrols  # noqa: PLC0415
    from picamera2 import Picamera2  # noqa: PLC0415
    from picamera2.encoders import MJPEGEncoder  # noqa: PLC0415
    from picamera2.outputs import FileOutput  # noqa: PLC0415

    return Picamera2, MJPEGEncoder, FileOutput, Transform, libcontrols


def limits_from_controls(controls: Mapping[str, Any]) -> Limits:
    """Derive slider ranges from what the sensor actually reports."""
    defaults = Limits()

    def span(name, fallback, cast):
        info = controls.get(name)
        try:
            low, high = cast(info[0]), cast(info[1])
        except (TypeError, ValueError, IndexError, KeyError):
            return fallback
        return (low, high) if high > low else fallback

    gain_low, gain_high = span("AnalogueGain", defaults.gain, float)
    return Limits(
        exposure_us=span("ExposureTime", defaults.exposure_us, int),
        # Beyond roughly 32x the OV5647 returns noise, not signal.
        gain=(gain_low, min(gain_high, 32.0)),
        ev=span("ExposureValue", defaults.ev, float),
        zoom=defaults.zoom,
        colour_gain=defaults.colour_gain,
    )


class CameraUnavailable(RuntimeError):
    pass


class AstraCamera:
    """Owns the sensor and publishes JPEG frames into a :class:`FrameBuffer`."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.frames = FrameBuffer()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._supervisor: threading.Thread | None = None

        self._picam2 = None
        self._limits = Limits()
        self._settings = (settings or Settings()).clamped(self._limits)
        self._full_rect: tuple[int, int, int, int] | None = None
        self._state = "starting"
        self._error: str | None = None
        self._busy = False

    # -- public API ----------------------------------------------------------
    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def limits(self) -> Limits:
        return self._limits

    def status(self) -> dict[str, Any]:
        age = self.frames.age()
        return {
            "state": self._state,
            "error": self._error,
            "fps": self.frames.fps(),
            "frame_age": None if age is None else round(age, 2),
            "stream_size": list(config.STREAM_SIZE),
            "still_size": list(config.STILL_SIZE),
        }

    def start(self) -> None:
        if self._supervisor is not None:
            return
        self._supervisor = threading.Thread(
            target=self._supervise, name="astra-camera", daemon=True
        )
        self._supervisor.start()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        self._teardown()

    def apply(self, patch: Mapping[str, Any]) -> Settings:
        with self._lock:
            updated = self._settings.merged(patch, self._limits)
            reconfigure = updated.needs_reconfigure(self._settings)
            self._settings = updated
            if self._picam2 is not None:
                if reconfigure:
                    self._restart_stream()
                else:
                    self._push_controls()
            return updated

    def apply_preset(self, name: str) -> Settings:
        return self.apply(presets.patch_for(name))

    def latest_frame(self) -> tuple[bytes | None, int]:
        return self.frames.latest()

    def wait_frame(self, last_id: int, timeout: float) -> tuple[bytes | None, int]:
        return self.frames.wait(last_id, timeout)

    def capture(self, full: bool = False) -> bytes:
        """Return a JPEG. ``full`` switches the sensor to its full 5 MP mode."""
        if not full:
            frame, _ = self.frames.latest()
            if frame is None:
                raise CameraUnavailable("no frame available yet")
            return frame
        return self._capture_full()

    # -- supervisor ----------------------------------------------------------
    def _supervise(self) -> None:
        backoff = 2.0
        while not self._stop.is_set():
            try:
                self._open()
            except Exception as exc:  # noqa: BLE001 - surface anything to the UI
                self._error = f"{type(exc).__name__}: {exc}"
                self._state = "error"
                log.error("camera start failed: %s", self._error)
                self._teardown()
                self._stop.wait(backoff)
                backoff = min(backoff * 2, config.RESTART_BACKOFF_MAX)
                continue

            backoff = 2.0
            self._error = None
            self._state = "running"
            log.info("camera running at %sx%s", *config.STREAM_SIZE)

            self._watch()
            self._teardown()

        self._state = "stopped"

    def _watch(self) -> None:
        """Block until the pipeline stalls or shutdown is requested."""
        while not self._stop.is_set():
            self._wake.wait(2.0)
            self._wake.clear()
            if self._stop.is_set() or self._busy:
                continue
            age = self.frames.age()
            if age is None or age > config.STALL_TIMEOUT:
                self._state = "stalled"
                log.warning(
                    "no frames for %s s - restarting pipeline",
                    "never" if age is None else f"{age:.1f}",
                )
                return

    # -- pipeline ------------------------------------------------------------
    def _open(self) -> None:
        Picamera2, MJPEGEncoder, FileOutput, Transform, libcontrols = _import_picamera2()
        self._Transform = Transform
        self._libcontrols = libcontrols
        self._MJPEGEncoder = MJPEGEncoder
        self._FileOutput = FileOutput

        with self._lock:
            picam2 = Picamera2()
            self._picam2 = picam2
            self._limits = limits_from_controls(picam2.camera_controls)
            self._settings = self._settings.clamped(self._limits)
            picam2.options["quality"] = config.STILL_QUALITY

            picam2.configure(self._build_video_config())
            self._full_rect = self._resolve_full_rect()
            self._start_encoder()
            self._push_controls()

    def _build_video_config(self):
        picam2 = self._picam2
        # Allow frame durations long enough for the requested exposure; the lower
        # bound caps the frame rate so the Wi-Fi link is not oversubscribed.
        min_duration = int(1_000_000 / max(1, config.STREAM_FPS))
        max_duration = max(min_duration, self._limits.exposure_us[1] + 20_000)
        return picam2.create_video_configuration(
            main={"size": config.STREAM_SIZE, "format": "YUV420"},
            raw={"size": config.STREAM_SIZE},
            controls={"FrameDurationLimits": (min_duration, max_duration)},
            transform=self._Transform(
                hflip=int(self._settings.hflip), vflip=int(self._settings.vflip)
            ),
            buffer_count=4,
            queue=False,
        )

    def _start_encoder(self) -> None:
        self.frames.reset()
        self._picam2.start_recording(
            self._MJPEGEncoder(bitrate=config.STREAM_BITRATE),
            self._FileOutput(self.frames),
        )

    def _restart_stream(self) -> None:
        picam2 = self._picam2
        if picam2 is None:
            return
        self._busy = True
        try:
            picam2.stop_recording()
            picam2.configure(self._build_video_config())
            self._full_rect = self._resolve_full_rect()
            self._start_encoder()
            self._push_controls()
        finally:
            self._busy = False

    def _resolve_full_rect(self) -> tuple[int, int, int, int] | None:
        props = self._picam2.camera_properties
        rect = props.get("ScalerCropMaximum")
        if rect and len(rect) == 4 and rect[2] > 0 and rect[3] > 0:
            return tuple(int(v) for v in rect)
        areas = props.get("PixelArrayActiveAreas")
        if areas:
            first = areas[0]
            if len(first) == 4 and first[2] > 0:
                return tuple(int(v) for v in first)
        size = props.get("PixelArraySize")
        if size and len(size) == 2:
            return (0, 0, int(size[0]), int(size[1]))
        return None

    def _control_dict(self) -> dict[str, Any]:
        s = self._settings
        lc = self._libcontrols
        metering = {
            "centre": lc.AeMeteringModeEnum.CentreWeighted,
            "spot": lc.AeMeteringModeEnum.Spot,
            "matrix": lc.AeMeteringModeEnum.Matrix,
        }[s.metering]

        controls: dict[str, Any] = {
            "AeEnable": s.auto_exposure,
            "AeMeteringMode": metering,
            "ExposureValue": s.ev,
            "AwbEnable": s.awb_auto,
            "Saturation": 0.0 if s.mono else 1.0,
            # Denoise smears faint stars; keep it minimal.
            "NoiseReductionMode": lc.draft.NoiseReductionModeEnum.Minimal,
        }
        if not s.auto_exposure:
            controls["ExposureTime"] = s.exposure_us
            controls["AnalogueGain"] = s.gain
        if not s.awb_auto:
            # The lens removal also removed the IR filter, so leaving AWB to its
            # own devices produces the familiar pink cast.
            controls["ColourGains"] = (s.red_gain, s.blue_gain)
        if self._full_rect is not None:
            controls["ScalerCrop"] = centred_crop(self._full_rect, s.zoom)
        return controls

    def _push_controls(self) -> None:
        if self._picam2 is None:
            return
        try:
            self._picam2.set_controls(self._control_dict())
        except Exception as exc:  # noqa: BLE001
            log.warning("could not apply controls: %s", exc)

    def _capture_full(self) -> bytes:
        with self._lock:
            picam2 = self._picam2
            if picam2 is None:
                raise CameraUnavailable("camera is not running")
            self._busy = True
            buffer = io.BytesIO()
            try:
                picam2.stop_recording()
                still = picam2.create_still_configuration(
                    main={"size": config.STILL_SIZE, "format": "RGB888"},
                    buffer_count=1,
                    transform=self._Transform(
                        hflip=int(self._settings.hflip), vflip=int(self._settings.vflip)
                    ),
                )
                picam2.configure(still)
                picam2.start()
                picam2.set_controls(self._control_dict())
                time.sleep(0.6)  # let AE/AWB settle in the new mode
                picam2.capture_file(buffer, format="jpeg")
                picam2.stop()
            finally:
                try:
                    picam2.configure(self._build_video_config())
                    self._full_rect = self._resolve_full_rect()
                    self._start_encoder()
                    self._push_controls()
                except Exception as exc:  # noqa: BLE001
                    log.error("failed to resume streaming after capture: %s", exc)
                    self._wake.set()
                self._busy = False
            return buffer.getvalue()

    def _teardown(self) -> None:
        with self._lock:
            picam2, self._picam2 = self._picam2, None
        if picam2 is None:
            return
        for step in (picam2.stop_recording, picam2.stop, picam2.close):
            try:
                step()
            except Exception:  # noqa: BLE001 - teardown is best effort
                pass
        self.frames.reset()
