"""Единая система масштабирования окна игры.

Игра всегда рисует кадр в фиксированном виртуальном разрешении 1280x720.
Этот модуль растягивает такой кадр на реальный экран (с пренебрежением
небольшой разницей пропорций) и переводит координаты мыши обратно в
виртуальное пространство игры.
"""

from __future__ import annotations

import pygame


VIRTUAL_SIZE = (1280, 720)
WINDOWED_FILL = 0.80


def compute_windowed_size(monitor_size: tuple[int, int]) -> tuple[int, int]:
    """Вычислить размер окна пропорционально монитору."""
    return (1360, 720)


def present_canvas(canvas: pygame.Surface, display: pygame.Surface) -> None:
    """Растянуть виртуальный кадр на весь экран без чёрных полос."""
    display_size = display.get_size()
    if display_size == canvas.get_size():
        display.blit(canvas, (0, 0))
    else:
        pygame.transform.smoothscale(canvas, display_size, display)


def screen_to_virtual(
    position: tuple[int, int],
    display_size: tuple[int, int],
    virtual_size: tuple[int, int] = VIRTUAL_SIZE,
) -> tuple[int, int]:
    """Переводит координаты мыши из окна в координаты виртуального кадра."""
    vx, vy = virtual_size
    dx, dy = display_size
    if dx <= 0 or dy <= 0:
        return (-1, -1)
    x, y = position
    return (int(x * vx / dx), int(y * vy / dy))


def scale_mouse_event(
    event: pygame.event.Event,
    display: pygame.Surface,
) -> pygame.event.Event:
    """Возвращает копию mouse-event с координатами в виртуальном пространстве."""
    if event.type not in (
        pygame.MOUSEBUTTONDOWN,
        pygame.MOUSEMOTION,
        pygame.MOUSEBUTTONUP,
    ):
        return event

    data = getattr(event, "dict", {}).copy()
    data["pos"] = screen_to_virtual(event.pos, display.get_size())
    if "rel" in data:
        dx, dy = display.get_size()
        rel_x, rel_y = data["rel"]
        data["rel"] = (
            int(rel_x * VIRTUAL_SIZE[0] / dx) if dx > 0 else 0,
            int(rel_y * VIRTUAL_SIZE[1] / dy) if dy > 0 else 0,
        )
    return pygame.event.Event(event.type, data)
