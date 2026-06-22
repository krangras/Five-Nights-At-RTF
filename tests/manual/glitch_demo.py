"""
glitch_demo.py — Визуальная демонстрация глитча.

Запуск:  python tests/manual/glitch_demo.py

Управление:
  G — запустить глитч
  ESC — выход
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

GAME_SIZE = (1280, 720)
FONT_PATH = Path("assets/fonts/OCR-A.ttf")


def force_glitch(model: GameModel, presenter: GamePresenter) -> None:
    model.start_glitch(90)
    if presenter._glitch_sounds:
        snd = presenter._glitch_sounds[0]
        chan = pygame.mixer.find_channel(True)
        if chan:
            chan.set_volume(0.7)
            chan.play(snd)
            presenter._glitch_channel = chan


def main() -> None:
    pygame.init()
    pygame.mixer.set_num_channels(16)
    screen = pygame.display.set_mode(GAME_SIZE)
    pygame.display.set_caption("Glitch Demo — G = glitch, ESC = quit")

    _fp = str(FONT_PATH) if FONT_PATH.exists() else None
    font = pygame.font.Font(_fp, 28)

    model = GameModel(night=1)
    view = GameView(screen)
    presenter = GamePresenter(model, view)

    model.tablet_open = True
    model.tablet_anim_frame = 1

    clock = pygame.time.Clock()
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_g and not model.glitch_active:
                    force_glitch(model, presenter)
            presenter.handle_event(event)

        presenter.update()
        view.draw(model)

        hint = "[G] glitch" if not model.glitch_active else "GLITCH ACTIVE"
        color = (255, 50, 50) if model.glitch_active else (120, 120, 120)
        hud = font.render(hint, True, color)
        screen.blit(hud, (10, 690))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
