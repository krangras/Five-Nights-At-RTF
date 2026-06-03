import json
import os

SETTINGS_PATH = "settings.json"

_defaults = {
    "fullscreen": True,
}

def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r") as f:
            data = json.load(f)
        for k, v in _defaults.items():
            data.setdefault(k, v)
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_defaults)

def save_settings(data: dict) -> None:
    with open(SETTINGS_PATH, "w") as f:
        json.dump(data, f)
