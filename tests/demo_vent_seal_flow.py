"""
demo_vent_seal_flow.py - ручной demo-прогон seal-механики.

Запуск:
    python tests/demo_vent_seal_flow.py

Сценарий:
1. Скрипт сам открывает планшет и карту вентиляции
2. Ты сам кликаешь по seal на vent map
3. В момент старта закрытия Алгем появляется на связанной vent-камере
4. Камера автоматически показывается, пока seal закрывается
5. После закрытия ещё 2 секунды показывается закрытый вент
6. Затем demo возвращает тебя обратно на vent map для следующего клика

ESC - выход.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygame

from gameplay_model import GameModel, SEAL_CAMERA_MAP
from gameplay_presenter import GamePresenter
from gameplay_view import GameView

pygame.init()
pygame.mixer.set_num_channels(16)
screen = pygame.display.set_mode(
    pygame.display.list_modes()[0],
    pygame.FULLSCREEN,
)
clock = pygame.time.Clock()

model = GameModel(night=2)
model.night_start_ticks = 0
view = GameView(screen)
presenter = GamePresenter(model, view)

font = pygame.font.Font(None, 30)
small_font = pygame.font.Font(None, 24)

CAMERA_BY_SEAL = {seal_id: cam_idx for cam_idx, seal_id in SEAL_CAMERA_MAP.items()}

OPEN_TABLET_DELAY = 45
OPEN_MAP_DELAY = 20
CLOSED_VIEW_DELAY = 120

phase = "BOOT"
phase_timer = 0
active_seal: str | None = None
active_cam: int | None = None
prev_currently_sealing: str | None = None


def post_key(key: int) -> None:
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))


def click_at(pos: tuple[int, int]) -> None:
    pygame.event.post(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            button=1,
            pos=pos,
        )
    )


def rect_center(rect: pygame.Rect) -> tuple[int, int]:
    return (rect.centerx, rect.centery)


def teleport_algem_to_camera(cam_idx: int) -> None:
    prev = model._ai.location
    model._ai.prev_location = prev
    model._ai.location = cam_idx
    model._ai.trigger_timer = 0


def move_algem_offscreen() -> None:
    prev = model._ai.location
    model._ai.prev_location = prev
    model._ai.location = 1
    model._ai.trigger_timer = 0


def draw_debug() -> None:
    lines = [
        f"Phase: {phase}",
        "Click any seal on the vent map",
        f"Current camera: {model.camera_idx}",
        f"Active seal: {active_seal or '-'}",
        f"Algem node: {model.algem_location}",
        "Seal states:",
    ]
    for seal_id, state in model.seals.items():
        lines.append(f"  {seal_id}: {state.name}")

    y = 12
    for idx, line in enumerate(lines):
        text_font = font if idx < 5 else small_font
        shadow = text_font.render(line, True, (0, 0, 0))
        text = text_font.render(line, True, (255, 240, 120))
        screen.blit(shadow, (13, y + 1))
        screen.blit(text, (12, y))
        y += 28 if idx < 5 else 22


running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False
        presenter.handle_event(event)

    phase_timer += 1

    if phase == "BOOT" and phase_timer >= OPEN_TABLET_DELAY:
        post_key(pygame.K_TAB)
        phase = "OPENING_TABLET"
        phase_timer = 0

    elif phase == "OPENING_TABLET" and model.tablet_open and not model.tablet_animating:
        view.draw(model)
        click_at(rect_center(view._map_btn_rect))
        phase = "OPENING_MAP"
        phase_timer = 0

    elif phase == "OPENING_MAP" and view.vent_map_mode and phase_timer >= OPEN_MAP_DELAY:
        move_algem_offscreen()
        phase = "WAIT_FOR_USER"
        phase_timer = 0

    model.update()
    presenter.update()

    current_sealing = model.currently_sealing_id
    if prev_currently_sealing is None and current_sealing is not None:
        active_seal = current_sealing
        active_cam = CAMERA_BY_SEAL.get(current_sealing)
        if active_cam is not None:
            teleport_algem_to_camera(active_cam)
            presenter._switch_camera(active_cam)
            view.vent_map_mode = False
            phase = "SEALING_CAMERA"
            phase_timer = 0

    elif phase == "SEALING_CAMERA" and active_seal is not None:
        if model.currently_sealing_id is None and model.seals[active_seal].name == "CLOSED":
            phase = "SHOW_CLOSED_CAMERA"
            phase_timer = 0

    elif phase == "SHOW_CLOSED_CAMERA" and phase_timer >= CLOSED_VIEW_DELAY:
        if not view.vent_map_mode:
            view.vent_map_mode = True
            if active_cam is not None:
                presenter._switch_camera(active_cam)
        move_algem_offscreen()
        active_seal = None
        active_cam = None
        phase = "WAIT_FOR_USER"
        phase_timer = 0

    prev_currently_sealing = model.currently_sealing_id

    view.draw(model)
    draw_debug()
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
