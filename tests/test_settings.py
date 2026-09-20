from __future__ import annotations

import pytest

from astra.settings import Limits, Settings, as_bool, clamp_float, clamp_int


def test_clamp_int_rejects_garbage():
    assert clamp_int("not a number", 0, 10, 5) == 5
    assert clamp_int(None, 0, 10, 5) == 5
    assert clamp_int(float("nan"), 0, 10, 5) == 5


def test_clamp_int_bounds():
    assert clamp_int(-100, 0, 10, 5) == 0
    assert clamp_int(100, 0, 10, 5) == 10
    assert clamp_int("7", 0, 10, 5) == 7


def test_clamp_float_rounds_and_bounds():
    assert clamp_float(3.14159, 0.0, 10.0, 1.0) == 3.142
    assert clamp_float(99, 0.0, 10.0, 1.0) == 10.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [("on", True), ("off", False), ("true", True), ("0", False), (1, True), ("", False)],
)
def test_as_bool(value, expected):
    assert as_bool(value, default=None) is expected


def test_merged_ignores_unknown_keys():
    limits = Limits()
    updated = Settings().merged({"gain": 4.0, "rm -rf": "/"}, limits)
    assert updated.gain == 4.0
    assert not hasattr(updated, "rm -rf")


def test_merged_clamps_to_sensor_limits():
    limits = Limits(exposure_us=(100, 800_000), gain=(1.0, 8.0))
    updated = Settings().merged({"exposure_us": 10_000_000, "gain": 500}, limits)
    assert updated.exposure_us == 800_000
    assert updated.gain == 8.0


def test_bad_metering_falls_back_to_default():
    assert Settings().merged({"metering": "wat"}, Limits()).metering == "spot"


def test_only_flips_require_a_reconfigure():
    base = Settings()
    assert base.merged({"gain": 9.0}, Limits()).needs_reconfigure(base) is False
    assert base.merged({"hflip": True}, Limits()).needs_reconfigure(base) is True
    assert base.merged({"vflip": False}, Limits()).needs_reconfigure(base) is True


def test_settings_round_trip_through_dict():
    original = Settings(gain=3.5, zoom=2.0, mono=True)
    assert Settings(**original.to_dict()) == original
