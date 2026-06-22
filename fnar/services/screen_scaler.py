"""Единая система масштабирования окна игры.

Игра всегда рисует кадр в фиксированном виртуальном разрешении 1280x720.
Этот модуль аккуратно показывает такой кадр в любом оконном или полноэкранном
режиме без растяжения картинки и переводит координаты мыши обратно в
виртуальное пространство игры.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame


VIRTUAL_SIZE = (1280, 720)
WINDOWED_FILL = 0.80


@dataclass(frozen=True)
class Viewport:
    """Область экрана, в которую вписан виртуальный кадр игры."""

    rect: pygame.Rect
    scale: float


def compute_windowed_size(monitor_size: tuple[int, int]) -> tuple[int, int]:
    """Вычислить размер окна пропорционально монитору с сохранением пропорций виртуального холста."""
    mw, mh = monitor_size
    vw, vh = VIRTUAL_SIZE
    target_h = int(mh * WINDOWED_FILL)
    target_w = int(target_h * vw / vh)
    if target_w > mw:
        target_w = int(mw * WINDOWED_FILL)
        target_h = int(target_w * vh / vw)
    return (target_w, target_h)


def get_viewport(display_size: tuple[int, int], virtual_size: tuple[int, int] = VIRTUAL_SIZE) -> Viewport:
    """Возвращает letterbox-область вывода без искажения пропорций."""
    display_w, display_h = display_size
    virtual_w, virtual_h = virtual_size
    if display_w <= 0 or display_h <= 0:
        return Viewport(pygame.Rect(0, 0, virtual_w, virtual_h), 1.0)

    scale = min(display_w / virtual_w, display_h / virtual_h)
    view_w = max(1, round(virtual_w * scale))
    view_h = max(1, round(virtual_h * scale))
    rect = pygame.Rect((display_w - view_w) // 2, (display_h - view_h) // 2, view_w, view_h)
    return Viewport(rect, scale)


def present_canvas(canvas: pygame.Surface, display: pygame.Surface) -> None:
    """Показывает виртуальный кадр на реальном экране с сохранением пропорций."""
    if display.get_size() == canvas.get_size():
        display.blit(canvas, (0, 0))
        return

    viewport = get_viewport(display.get_size(), canvas.get_size()).rect
    display.fill((0, 0, 0))
    scaled = pygame.transform.smoothscale(canvas, viewport.size)
    display.blit(scaled, viewport.topleft)


def screen_to_virtual(
    position: tuple[int, int],
    display_size: tuple[int, int],
    virtual_size: tuple[int, int] = VIRTUAL_SIZE,
) -> tuple[int, int]:
    """Переводит координаты мыши из окна в координаты виртуального кадра."""
    viewport = get_viewport(display_size, virtual_size).rect
    x, y = position
    if not viewport.collidepoint(x, y):
        return (-1, -1)

    virtual_w, virtual_h = virtual_size
    return (
        int((x - viewport.x) * virtual_w / viewport.width),
        int((y - viewport.y) * virtual_h / viewport.height),
    )


def scale_mouse_event(event: pygame.event.Event, display: pygame.Surface) -> pygame.event.Event:
    """Возвращает копию mouse-event с координатами в виртуальном пространстве."""
    if event.type not in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
        return event

    data = getattr(event, "dict", {}).copy()
    data["pos"] = screen_to_virtual(event.pos, display.get_size())
    if "rel" in data:
        viewport = get_viewport(display.get_size()).rect
        if viewport.width > 0 and viewport.height > 0:
            rel_x, rel_y = data["rel"]
            data["rel"] = (
                int(rel_x * VIRTUAL_SIZE[0] / viewport.width),
                int(rel_y * VIRTUAL_SIZE[1] / viewport.height),
            )
    return pygame.event.Event(event.type, data)
