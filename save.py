SAVE_PATH = "save.txt"

def load_save() -> int:
    try:
        with open(SAVE_PATH, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0

def save_progress(night: int) -> None:
    with open(SAVE_PATH, "w") as f:
        f.write(str(night))
