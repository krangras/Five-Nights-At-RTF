from __future__ import annotations

import random

from fnar.services.save import load_save


class MenuModel:
    """Модель состояния главного меню.

    Хранит выбранную ночь, текущий hover, таймеры шума и состояние фонового
    Алгема. Не зависит от PyGame и не выполняет отрисовку.
    """

    MAX_NIGHT = 5
    MIN_GLITCH_COOLDOWN = 180
    MAX_GLITCH_COOLDOWN = 420
    MIN_GLITCH_BURST = 8
    MAX_GLITCH_BURST = 24
    GLITCH_FRAME_COUNT = 4
    NOISE_FRAME_COUNT = 3
    STATE_NORMAL = "NORMAL"
    STATE_GLITCH = "GLITCH"
    ALLOWED_BUTTONS = {None, "new_game", "continue", "settings", "exit"}

    def __init__(self) -> None:
        self._hovered_button: str | None = None

        self.reload_progress()

        self._algem_state = self.STATE_NORMAL
        self._glitch_cooldown = random.randint(self.MIN_GLITCH_COOLDOWN, self.MAX_GLITCH_COOLDOWN)
        self._glitch_burst_left = 0
        self._glitch_frame_idx = 0
        self._prev_glitch_idx = -1
        self._noise_frame = 0

    @property
    def hovered_button(self) -> str | None:
        return self._hovered_button

    @property
    def game_completed(self) -> bool:
        return self._game_completed

    @property
    def saved_night(self) -> int:
        return self._saved_night

    @property
    def continue_available(self) -> bool:
        return self._continue_available

    @property
    def algem_state(self) -> str:
        return self._algem_state

    @property
    def glitch_frame_idx(self) -> int:
        return self._glitch_frame_idx

    @property
    def noise_frame(self) -> int:
        return self._noise_frame

    def set_hovered_button(self, button: str | None) -> None:
        self._hovered_button = button if button in self.ALLOWED_BUTTONS else None

    def reload_progress(self) -> None:
        """Refresh completion and Continue state from the save service."""
        raw = load_save()
        self._game_completed = raw > self.MAX_NIGHT
        self._saved_night = min(raw, self.MAX_NIGHT)
        self._continue_available = self._saved_night > 0

    def update(self) -> None:
        if self._algem_state == self.STATE_NORMAL:
            self._glitch_cooldown -= 1
            if self._glitch_cooldown <= 0:
                self._algem_state = self.STATE_GLITCH
                self._glitch_burst_left = random.randint(self.MIN_GLITCH_BURST, self.MAX_GLITCH_BURST)
                idx = random.randint(0, self.GLITCH_FRAME_COUNT - 1)
                self._glitch_frame_idx = idx
                self._prev_glitch_idx = idx
        else:
            self._glitch_burst_left -= 1
            if self._glitch_burst_left <= 0:
                self._algem_state = self.STATE_NORMAL
                self._glitch_cooldown = random.randint(self.MIN_GLITCH_COOLDOWN, self.MAX_GLITCH_COOLDOWN)
            else:
                choices = [i for i in range(self.GLITCH_FRAME_COUNT) if i != self._prev_glitch_idx]
                idx = random.choice(choices)
                self._glitch_frame_idx = idx
                self._prev_glitch_idx = idx

        self._noise_frame = (self._noise_frame + 1) % self.NOISE_FRAME_COUNT
