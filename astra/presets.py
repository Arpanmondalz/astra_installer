"""Observing presets.

Values are deliberately physical rather than arbitrary. For a 114 mm f/6-f/8
Newtonian with a bare sensor at the focal plane, the Looney-11 rule puts correct
lunar exposure near 5 ms at unity gain - roughly 2.5 stops brighter than the
1000 us the original build used, which is why Moon and Planets rendered black.

Moon and Planets run on auto exposure with *spot* metering. A small bright disc
on a black field is exactly the case that defeats matrix metering, and spot
metering fixes it without the observer touching a slider.

Out-of-range values (notably the deep sky exposure) are intentional sentinels:
they get clamped to whatever the sensor actually supports.
"""

from __future__ import annotations

from typing import Any, Mapping

PRESETS: dict[str, dict[str, Any]] = {
    "moon": {
        "auto_exposure": True,
        "metering": "spot",
        "ev": -0.5,
        "exposure_us": 5_000,
        "gain": 1.0,
        "mono": False,
        "awb_auto": False,
    },
    "planets": {
        "auto_exposure": True,
        "metering": "spot",
        "ev": -0.7,
        "exposure_us": 12_000,
        "gain": 4.0,
        "mono": False,
        "awb_auto": False,
    },
    "deepsky": {
        "auto_exposure": False,
        "metering": "matrix",
        "ev": 0.0,
        "exposure_us": 10_000_000,  # clamped to the sensor maximum
        "gain": 12.0,
        "mono": True,
        "awb_auto": False,
    },
    "daylight": {
        "auto_exposure": True,
        "metering": "centre",
        "ev": 0.0,
        "exposure_us": 2_000,
        "gain": 1.0,
        "mono": False,
        "awb_auto": True,
    },
    "reset": {
        "auto_exposure": True,
        "metering": "spot",
        "ev": -0.5,
        "exposure_us": 5_000,
        "gain": 1.0,
        "mono": False,
        "awb_auto": False,
        "zoom": 1.0,
        "red_gain": 2.0,
        "blue_gain": 1.6,
    },
}

LABELS: dict[str, str] = {
    "moon": "Moon",
    "planets": "Planets",
    "deepsky": "Deep Sky",
    "daylight": "Daylight",
    "reset": "Reset",
}


def patch_for(name: str) -> Mapping[str, Any]:
    """Return the settings patch for a preset. Raises KeyError for unknown names."""
    return dict(PRESETS[name])


def listing() -> list[dict[str, str]]:
    return [{"id": name, "label": LABELS[name]} for name in PRESETS]
