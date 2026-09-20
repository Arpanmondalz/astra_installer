"""Sensor crop maths for digital zoom.

Zoom is implemented as a real ScalerCrop on the sensor, not a CSS transform.
That gives genuine extra detail on planets and simultaneously *reduces* the
number of pixels being encoded and pushed over Wi-Fi.
"""

from __future__ import annotations

Rect = tuple[int, int, int, int]


def centred_crop(full: Rect, zoom: float) -> Rect:
    """Return a centred sub-rectangle of ``full`` that is ``zoom`` times smaller.

    ``full`` and the result are ``(x, y, width, height)`` in sensor coordinates.
    """
    x, y, width, height = (int(v) for v in full)
    if width <= 0 or height <= 0:
        raise ValueError("crop rectangle must have positive extent")

    try:
        factor = float(zoom)
    except (TypeError, ValueError):
        factor = 1.0
    factor = max(1.0, factor)

    crop_w = max(2, int(round(width / factor)) & ~1)
    crop_h = max(2, int(round(height / factor)) & ~1)
    return (
        x + (width - crop_w) // 2,
        y + (height - crop_h) // 2,
        crop_w,
        crop_h,
    )
