import json
import os

from audio_mix import default_audio_mix, normalize_audio_mix

SETTINGS_PATH = "settings.json"

_defaults = {
    "fullscreen": True,
}


def _default_settings() -> dict:
    return {
        "fullscreen": _defaults["fullscreen"],
        "audio_mix": default_audio_mix(),
    }

def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r") as f:
            data = json.load(f)
        for k, v in _default_settings().items():
            data.setdefault(k, v)
        data["audio_mix"] = normalize_audio_mix(data.get("audio_mix"))
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return _default_settings()

def save_settings(data: dict) -> None:
    data = dict(data)
    data["audio_mix"] = normalize_audio_mix(data.get("audio_mix"))
    with open(SETTINGS_PATH, "w") as f:
        json.dump(data, f, indent=2)
