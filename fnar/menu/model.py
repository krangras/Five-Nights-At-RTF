from __future__ import annotations

import random

from fnar.services.save import load_save


class MenuModel:
    def __init__(self) -> None:
        """Выполнить ``init``.
        
        Args:
            Нет аргументов.
        
        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта.
        """
        self._hovered_button: str | None = None

        raw = load_save()
        self._game_completed = raw > 5
        self._saved_night = min(raw, 5)
        self._continue_available = self._saved_night > 0

        self._algem_state = "NORMAL"
        self._glitch_cooldown = random.randint(180, 420)
        self._glitch_burst_left = 0
        self._glitch_frame_idx = 0
        self._prev_glitch_idx = -1
        self._noise_frame = 0

    @property
    def hovered_button(self) -> str | None:
        """Выполнить ``hovered button``.
        
        Args:
            Нет аргументов.
        
        Returns:
            Значение типа ``str | None``.
        """
        return self._hovered_button

    @property
    def game_completed(self) -> bool:
        """Выполнить ``game completed``.
        
        Args:
            Нет аргументов.
        
        Returns:
            Значение типа ``bool``.
        """
        return self._game_completed

    @property
    def saved_night(self) -> int:
        """Выполнить ``saved night``.
        
        Args:
            Нет аргументов.
        
        Returns:
            Значение типа ``int``.
        """
        return self._saved_night

    @property
    def continue_available(self) -> bool:
        """Выполнить ``continue available``.
        
        Args:
            Нет аргументов.
        
        Returns:
            Значение типа ``bool``.
        """
        return self._continue_available

    @property
    def algem_state(self) -> str:
        """Выполнить ``algem state``.
        
        Args:
            Нет аргументов.
        
        Returns:
            Значение типа ``str``.
        """
        return self._algem_state

    @property
    def glitch_frame_idx(self) -> int:
        """Выполнить ``glitch frame idx``.
        
        Args:
            Нет аргументов.
        
        Returns:
            Значение типа ``int``.
        """
        return self._glitch_frame_idx

    @property
    def noise_frame(self) -> int:
        """Выполнить ``noise frame``.
        
        Args:
            Нет аргументов.
        
        Returns:
            Значение типа ``int``.
        """
        return self._noise_frame

    def set_hovered_button(self, button: str | None) -> None:
        """Выполнить ``set hovered button``.
        
        Args:
            button: Входной параметр метода ``set_hovered_button``.
        
        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта.
        """
        allowed = {None, "new_game", "continue", "settings", "exit"}
        self._hovered_button = button if button in allowed else None

    def update(self) -> None:
        """Выполнить ``update``.
        
        Args:
            Нет аргументов.
        
        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта.
        """
        if self._algem_state == "NORMAL":
            self._glitch_cooldown -= 1
            if self._glitch_cooldown <= 0:
                self._algem_state = "GLITCH"
                self._glitch_burst_left = random.randint(8, 24)
                idx = random.randint(0, 3)
                self._glitch_frame_idx = idx
                self._prev_glitch_idx = idx
        else:
            self._glitch_burst_left -= 1
            if self._glitch_burst_left <= 0:
                self._algem_state = "NORMAL"
                self._glitch_cooldown = random.randint(180, 420)
            else:
                choices = [i for i in range(4) if i != self._prev_glitch_idx]
                idx = random.choice(choices)
                self._glitch_frame_idx = idx
                self._prev_glitch_idx = idx

        self._noise_frame = (self._noise_frame + 1) % 3
