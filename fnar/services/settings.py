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
    """Выполнить ``default settings``.
    
    Args:
        Нет аргументов.
    
    Returns:
        Значение типа ``dict``.
    """
    return {
        "fullscreen": _defaults["fullscreen"],
        "audio_mix": default_audio_mix(),
    }


def load_settings() -> dict:
    """Выполнить ``load settings``.
    
    Args:
        Нет аргументов.
    
    Returns:
        Значение типа ``dict``.
    """
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
    """Выполнить ``save settings``.
    
    Args:
        data: Входной параметр метода ``save_settings``.
    
    Returns:
        ``None``. Метод выполняет действие или обновляет состояние объекта.
    """
    data = dict(data)
    data["audio_mix"] = normalize_audio_mix(data.get("audio_mix"))
    with open(SETTINGS_PATH, "w") as f:
        json.dump(data, f, indent=2)
