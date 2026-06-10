"""
test_glitch_demo.py — Визуальная демонстрация глитча.

Запуск:  python test_glitch_demo.py

Управление:
  G — запустить глитч
  ESC — выход
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pygame

from gameplay_model import GameModel
from gameplay_view import GameView
from gameplay_presenter import GamePresenter

GAME_SIZE = (1280, 720)
FONT_PATH = "assets/fonts/OCR-A.ttf"


def force_glitch(model, presenter):
    """Принудительно запустить глитч."""
    model._glitch_delay = 0
    model._glitch_triggered = True
    model._glitch_active = True
    model._glitch_timer = 90
    model._glitch_frame = 0
    model._glitch_frame_timer = 0
    if presenter._glitch_sounds:
        snd = presenter._glitch_sounds[0]
        chan = pygame.mixer.find_channel(True)
        if chan:
            chan.set_volume(0.7)
            chan.play(snd)
            presenter._glitch_channel = chan


def main():
    pygame.init()
    pygame.mixer.set_num_channels(16)
    screen = pygame.display.set_mode(GAME_SIZE)
    pygame.display.set_caption("Glitch Demo — G = glitch, ESC = quit")

    _fp = FONT_PATH if os.path.exists(FONT_PATH) else None
    font = pygame.font.Font(_fp, 28)

    game_surface = pygame.Surface(GAME_SIZE)

    model = GameModel(night=1)
    view = GameView(game_surface)
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
                elif event.key == pygame.K_g and not model._glitch_active:
                    force_glitch(model, presenter)
            presenter.handle_event(event)

        presenter.update()
        view.draw(model)

        hint = "[G] glitch" if not model._glitch_active else "GLITCH ACTIVE"
        color = (255, 50, 50) if model._glitch_active else (120, 120, 120)
        hud = font.render(hint, True, color)
        game_surface.blit(hud, (10, 690))

        screen.blit(game_surface, (0, 0))
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
