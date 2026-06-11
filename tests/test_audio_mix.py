"""
test_audio_mix.py - Tests for audio mix normalization and effective volume.

Run:
  python -m pytest tests/test_audio_mix.py -v
  python tests/test_audio_mix.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from audio_mix import ALL_SOUND_PATHS, default_audio_mix, effective_volume, normalize_audio_mix


def test_default_mix_has_master_categories_and_sounds() -> None:
    mix = default_audio_mix()
    assert mix["master"] == pytest.approx(1.0)
    assert "sounds/ui/blip3.mp3" in mix["sounds"]
    assert len(mix["sounds"]) == len(ALL_SOUND_PATHS)


def test_normalize_fills_missing_fields() -> None:
    mix = normalize_audio_mix({"master": 0.75})
    assert mix["master"] == pytest.approx(0.75)
    assert "sounds/final_scene/algems' final speech.mp3" in mix["sounds"]


def test_normalize_clamps_out_of_range_values() -> None:
    mix = normalize_audio_mix(
        {
            "master": 3.0,
            "sounds": {"menu_music": 2.7, "sounds/menu/Faulty_Ventilation.mp3": -1.0},
        }
    )
    assert mix["master"] == pytest.approx(2.0)
    assert mix["sounds"]["sounds/menu/Faulty_Ventilation.mp3"] == pytest.approx(0.0)


def test_effective_volume_applies_master_category_and_sound_multipliers() -> None:
    settings_data = {
        "audio_mix": {
            "master": 0.5,
            "sounds": {"sounds/ambience/ambience.wav": 0.25},
        }
    }
    result = effective_volume(settings_data, "sounds/ambience/ambience.wav", 1.0)
    assert result == pytest.approx(0.125)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
