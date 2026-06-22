"""
demo_algem_audio.py — Демо: distance-based audio Алгема.

Запуск:  python tests/manual/demo_algem_audio.py

Автоматически:
  1. Открывает планшет
  2. Ставит Алгема на камеру 7 (Service Room)
  3. Проигрывает случайные цитаты
  4. Переключает камеры 7 → 4 → 1 → 2 → 3 → 5 → 6 → 7
  5. Показывает текущую громкость и расстояние на экране

Нажми ESC чтобы выйти.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pygame

pygame.init()
pygame.mixer.set_num_channels(16)
screen = pygame.display.set_mode((1280, 720))
pygame.display.set_caption("Five Nights At RTF")
_icon_path = Path(__file__).resolve().parents[2] / "assets" / "logo" / "logo_32_rgb.png"
if _icon_path.exists():
    try:
        _icon = pygame.image.load(str(_icon_path))
        pygame.display.set_icon(_icon)
    except pygame.error:
        pass
clock = pygame.time.Clock()

from fnar.gameplay.model import GameModel  # noqa: E402
from fnar.gameplay.view import GameView  # noqa: E402
from fnar.gameplay.presenter import GamePresenter  # noqa: E402

m = GameModel(night=1)
v = GameView(screen)
p = GamePresenter(m, v)

from fnar.gameplay.algem_ai import bfs_path  # noqa: E402
from fnar.gameplay.model import BASE_GRAPH  # noqa: E402

NODE_NAMES = {
    1: "Algem's Room",
    2: "Canteen",
    3: "Toilets",
    4: "Main Hall",
    5: "West Hall",
    6: "Coworking",
    7: "Service Room",
}

CAM_SEQUENCE = [7, 4, 1, 2, 3, 5, 6, 7]
SWITCH_INTERVAL = 180  # 3 сек при 60 FPS
TALK_INTERVAL = 120  # новая цитата каждые 2 сек

cam_step = 0
switch_timer = 0
phase = "WAIT"  # WAIT → OPEN_TAB → TALK → SWITCH → DONE
phase_timer = 0
debug_font = pygame.font.Font(None, 36)

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False
        p.handle_event(event)

    phase_timer += 1

    if phase == "WAIT" and phase_timer >= 60:
        phase = "OPEN_TAB"
        phase_timer = 0
        tab_event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB)
        pygame.event.post(tab_event)

    elif phase == "OPEN_TAB" and phase_timer >= 30:
        m._ai.location = 7
        m._ai.prev_location = 7
        phase = "TALK"
        phase_timer = 0
        p._algem_talk_timer = 0

    elif phase == "TALK" and phase_timer >= 30:
        phase = "SWITCH"
        phase_timer = 0
        switch_timer = 0
        cam_step = 0

    elif phase == "SWITCH":
        if not p._algem_talk_channel.get_busy():
            p._algem_talk_timer = 0

        switch_timer += 1
        if switch_timer >= SWITCH_INTERVAL:
            switch_timer = 0
            cam_step += 1
            if cam_step >= len(CAM_SEQUENCE):
                cam_step = 0
            cam_idx = CAM_SEQUENCE[cam_step]
            cam_event = pygame.event.Event(pygame.KEYDOWN, key=getattr(pygame, f"K_{cam_idx}"))
            pygame.event.post(cam_event)

    m.update()
    p.update()
    v.draw(m)

    if m.tablet_open and not m.tablet_animating:
        algem_loc = m.algem_location
        cam = m.camera_idx
        if cam == algem_loc:
            dist = 0
        else:
            path = bfs_path(cam, algem_loc, BASE_GRAPH)
            dist = len(path) - 1 if path else 4
        vol = p._algem_talk_channel.get_volume()
        busy = p._algem_talk_channel.get_busy()

        lines = [
            f"Phase: {phase}",
            f"Algem: node {algem_loc} ({NODE_NAMES.get(algem_loc, '?')})",
            f"Camera: {cam} ({NODE_NAMES.get(cam, '?')})",
            f"Distance (cam->algem): {dist}",
            f"Volume: {vol:.3f}",
            f"Playing: {'YES' if busy else 'NO'}",
            f"Talk timer: {p._algem_talk_timer}",
        ]
        y = 10
        for line in lines:
            bg = debug_font.render(line, True, (0, 0, 0))
            fg = debug_font.render(line, True, (255, 255, 0))
            screen.blit(bg, (12, y + 1))
            screen.blit(fg, (10, y))
            y += 30

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
