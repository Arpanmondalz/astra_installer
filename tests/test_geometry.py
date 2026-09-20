from __future__ import annotations

import pytest

from astra.geometry import centred_crop

FULL = (0, 0, 2592, 1944)


def test_zoom_one_returns_the_whole_sensor():
    assert centred_crop(FULL, 1.0) == FULL


def test_zoom_halves_each_axis_and_stays_centred():
    x, y, w, h = centred_crop(FULL, 2.0)
    assert (w, h) == (1296, 972)
    assert x == (2592 - w) // 2
    assert y == (1944 - h) // 2


def test_crop_stays_inside_the_sensor():
    for zoom in (1.0, 1.5, 3.3, 8.0):
        x, y, w, h = centred_crop(FULL, zoom)
        assert x >= 0 and y >= 0
        assert x + w <= 2592
        assert y + h <= 1944


def test_offset_origin_is_preserved():
    x, y, w, h = centred_crop((16, 8, 1000, 500), 2.0)
    assert (w, h) == (500, 250)
    assert x == 16 + 250
    assert y == 8 + 125


def test_dimensions_are_even():
    for zoom in (1.7, 2.3, 5.9, 7.1):
        _, _, w, h = centred_crop(FULL, zoom)
        assert w % 2 == 0 and h % 2 == 0


def test_zoom_below_one_is_ignored():
    assert centred_crop(FULL, 0.1) == FULL
    assert centred_crop(FULL, "nonsense") == FULL


def test_degenerate_rectangle_rejected():
    with pytest.raises(ValueError):
        centred_crop((0, 0, 0, 0), 2.0)
