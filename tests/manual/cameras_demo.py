"""
cameras_demo.py — Демонстрация переключения камер и перемещения Алгема.

Запуск:  python tests/manual/cameras_demo.py

Алгем автоматически перемещается между камерами 3 и 4 каждые 10 секунд.
Используй WASD/стрелки для панорамирования, TAB для планшета.
ESC — выход.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
os.chdir(str(_ROOT))

import pygame

from fnar.gameplay.model import GameModel
from fnar.gameplay.presenter import GamePresenter
from fnar.gameplay.view import GameView

pygame.init()
screen = pygame.display.set_mode((1280, 720))
pygame.display.set_caption("Cameras Demo — TAB=tablet, arrows=pan, ESC=quit")
clock = pygame.time.Clock()

model = GameModel(night=1)
view = GameView(screen)
presenter = GamePresenter(model, view)

model.server_state = "ON"
model.tablet_open = True
model.camera_idx = 3

frame = 0
running = True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False
        presenter.handle_event(event)

    model.update()
    presenter.update()

    algem_node = 3 if (frame // 600) % 2 == 0 else 4
    model._ai.location = algem_node
    model._ai.prev_location = 1 if algem_node == 3 else 3

    view.draw(model)
    pygame.display.flip()
    clock.tick(60)
    frame += 1

pygame.quit()
