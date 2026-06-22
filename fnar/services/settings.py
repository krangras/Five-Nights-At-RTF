"""Чтение, нормализация и сохранение пользовательских настроек игры."""

import json
import os

from .audio_mix import default_audio_mix, normalize_audio_mix

_APP_DIR = os.path.join(os.environ.get("APPDATA", "."), "FiveNightsAtRTF")
os.makedirs(_APP_DIR, exist_ok=True)

SETTINGS_PATH = os.path.join(_APP_DIR, "settings.json")

_defaults = {
    "fullscreen": True,
}


def _default_settings() -> dict:
    """Создаёт полный набор настроек по умолчанию, включая аудиомикшер."""
    return {
        "fullscreen": _defaults["fullscreen"],
        "audio_mix": default_audio_mix(),
    }


def load_settings() -> dict:
    """Load user settings and audio calibration from disk."""
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in _default_settings().items():
            data.setdefault(k, v)
        data["audio_mix"] = normalize_audio_mix(data.get("audio_mix"))
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return _default_settings()


def save_settings(data: dict) -> None:
    """Atomically persist user settings and audio calibration to disk."""
    data = dict(data)
    data["audio_mix"] = normalize_audio_mix(data.get("audio_mix"))
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
