from __future__ import annotations

import pytest

from astra import presets
from astra.settings import Limits, Settings


def test_every_preset_applies_cleanly():
    limits = Limits(exposure_us=(100, 1_000_000), gain=(1.0, 16.0))
    for name in presets.PRESETS:
        result = Settings().merged(presets.patch_for(name), limits)
        assert limits.exposure_us[0] <= result.exposure_us <= limits.exposure_us[1]
        assert limits.gain[0] <= result.gain <= limits.gain[1]


def test_unknown_preset_raises():
    with pytest.raises(KeyError):
        presets.patch_for("../../etc/passwd")


def test_moon_is_bright_enough():
    """The original build used 1000 us at unity gain, ~2.5 stops underexposed."""
    moon = presets.PRESETS["moon"]
    assert moon["exposure_us"] >= 4_000
    assert moon["auto_exposure"] is True
    assert moon["metering"] == "spot"


def test_deepsky_requests_the_sensor_maximum():
    limits = Limits(exposure_us=(100, 760_000))
    result = Settings().merged(presets.patch_for("deepsky"), limits)
    assert result.exposure_us == 760_000
    assert result.auto_exposure is False


def test_presets_do_not_touch_physical_orientation():
    for name, patch in presets.PRESETS.items():
        if name == "reset":
            continue
        assert "hflip" not in patch
        assert "vflip" not in patch
        assert "zoom" not in patch


def test_every_preset_has_a_label():
    assert set(presets.PRESETS) == set(presets.LABELS)
    assert [item["id"] for item in presets.listing()] == list(presets.PRESETS)
