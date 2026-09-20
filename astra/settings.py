"""Camera settings model.

Pure data and validation only - this module must stay importable on any machine
(no picamera2/libcamera imports) so the logic can be unit tested off-device.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping

METERING_MODES = ("spot", "centre", "matrix")

_TRUE = {"1", "true", "on", "yes", "y"}
_FALSE = {"0", "false", "off", "no", "n", ""}


def clamp_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number):
        return default
    return int(max(low, min(high, round(number))))


def clamp_float(value: Any, low: float, high: float, default: float, ndigits: int = 3) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number):
        return default
    return round(max(low, min(high, number)), ndigits)


def as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
    return default


def as_choice(value: Any, choices: tuple[str, ...], default: str) -> str:
    if isinstance(value, str) and value.strip().lower() in choices:
        return value.strip().lower()
    return default


@dataclass(frozen=True)
class Limits:
    """Control ranges. Replaced at runtime with values read from the sensor."""

    exposure_us: tuple[int, int] = (100, 1_000_000)
    gain: tuple[float, float] = (1.0, 16.0)
    ev: tuple[float, float] = (-4.0, 4.0)
    zoom: tuple[float, float] = (1.0, 8.0)
    colour_gain: tuple[float, float] = (0.5, 8.0)

    def to_dict(self) -> dict[str, list]:
        return {key: list(value) for key, value in asdict(self).items()}


@dataclass(frozen=True)
class Settings:
    """A complete, already-validated camera state."""

    auto_exposure: bool = True
    exposure_us: int = 5_000
    gain: float = 1.0
    ev: float = -0.5
    metering: str = "spot"
    mono: bool = False
    hflip: bool = False
    vflip: bool = True
    zoom: float = 1.0
    awb_auto: bool = False
    red_gain: float = 2.0
    blue_gain: float = 1.6

    def clamped(self, limits: Limits) -> "Settings":
        defaults = Settings()
        return Settings(
            auto_exposure=as_bool(self.auto_exposure, defaults.auto_exposure),
            exposure_us=clamp_int(self.exposure_us, *limits.exposure_us, defaults.exposure_us),
            gain=clamp_float(self.gain, *limits.gain, defaults.gain),
            ev=clamp_float(self.ev, *limits.ev, defaults.ev),
            metering=as_choice(self.metering, METERING_MODES, defaults.metering),
            mono=as_bool(self.mono, defaults.mono),
            hflip=as_bool(self.hflip, defaults.hflip),
            vflip=as_bool(self.vflip, defaults.vflip),
            zoom=clamp_float(self.zoom, *limits.zoom, defaults.zoom),
            awb_auto=as_bool(self.awb_auto, defaults.awb_auto),
            red_gain=clamp_float(self.red_gain, *limits.colour_gain, defaults.red_gain),
            blue_gain=clamp_float(self.blue_gain, *limits.colour_gain, defaults.blue_gain),
        )

    def merged(self, patch: Mapping[str, Any], limits: Limits) -> "Settings":
        """Apply a partial update. Unknown keys are ignored, bad values are clamped."""
        known = {key: value for key, value in patch.items() if key in _FIELDS}
        return replace(self, **known).clamped(limits)

    def needs_reconfigure(self, other: "Settings") -> bool:
        """Flips are baked into the stream configuration; everything else is live."""
        return (self.hflip, self.vflip) != (other.hflip, other.vflip)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_FIELDS = frozenset(Settings().to_dict())
