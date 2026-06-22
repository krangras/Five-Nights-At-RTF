"""Безопасное чтение и запись прогресса прохождения."""

import os

_APP_DIR = os.path.join(os.environ.get("APPDATA", "."), "FiveNightsAtRTF")
os.makedirs(_APP_DIR, exist_ok=True)

SAVE_PATH = os.path.join(_APP_DIR, "save.txt")


def load_save() -> int:
    """Load the highest unlocked night from the local save file."""
    try:
        with open(SAVE_PATH, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def save_progress(night: int) -> None:
    """Atomically persist the highest unlocked night after a completed run."""
    progress = max(load_save(), int(night))
    temporary_path = f"{SAVE_PATH}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as save_file:
        save_file.write(str(progress))
    os.replace(temporary_path, SAVE_PATH)
