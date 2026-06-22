"""
test_ad_demo.py — Визуальная демонстрация рекламы на ноутбуке и в офисе.

Запуск:  python test_ad_demo.py

Управление:
  A — принудительно показать рекламу
  C — закрыть рекламу
  V — переключить вид офис/ноутбук
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


def main():
    pygame.init()
    pygame.mixer.set_num_channels(16)
    screen = pygame.display.set_mode(GAME_SIZE)
    pygame.display.set_caption("Ad Demo — A = show, C = close, V = office view, ESC = quit")

    _fp = FONT_PATH if os.path.exists(FONT_PATH) else None
    font = pygame.font.Font(_fp, 28)

    game_surface = pygame.Surface(GAME_SIZE)

    model = GameModel(night=1)
    view = GameView(game_surface)
    presenter = GamePresenter(model, view)

    model.laptop_power_state = "ON"
    model.laptop_open = True
    model.laptop_app = "claude_mythos"
    model.hack_active = True
    model.server_state = "ON"
    model.hack_progress = 0.0
    model.tablet_open = False
    model.tablet_anim_frame = 1

    model.ad_spawn_timer = 300
    show_office = False

    clock = pygame.time.Clock()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_a and not model.ad_active:
                    model.ad_active = True
                    model.ad_image_key = "ad_hhru"
                    model.ad_timer = 0
                elif event.key == pygame.K_c and model.ad_active:
                    presenter._close_ad()
                elif event.key == pygame.K_v:
                    show_office = not show_office
            presenter.handle_event(event)

        if show_office and model.laptop_open:
            model.laptop_open = False
        elif not show_office and not model.laptop_open and model.laptop_power_state == "ON":
            model.laptop_open = True

        presenter.update()
        view.draw(model)

        if model.ad_active:
            mode = "OFFICE" if show_office else "LAPTOP"
            hint = f"AD ACTIVE  [{mode}]"
            color = (255, 200, 50)
        else:
            mode = "OFFICE" if show_office else "LAPTOP"
            hint = f"[A] show ad  [V] {mode}  (spawn {model.ad_spawn_timer})"
            color = (120, 120, 120)
        hud = font.render(hint, True, color)
        game_surface.blit(hud, (10, 690))

        screen.blit(game_surface, (0, 0))
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
