"""
ad_demo.py — Визуальная демонстрация рекламы на ноутбуке и в офисе.

Запуск:  python tests/manual/ad_demo.py

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

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
os.chdir(str(_ROOT))

import pygame

from fnar.gameplay.model import GameModel
from fnar.gameplay.presenter import GamePresenter
from fnar.gameplay.view import GameView

GAME_SIZE = (1280, 720)
FONT_PATH = Path("assets/fonts/OCR-A.ttf")


def main() -> None:
    pygame.init()
    pygame.mixer.set_num_channels(16)
    screen = pygame.display.set_mode(GAME_SIZE)
    pygame.display.set_caption("Ad Demo — A=show, C=close, V=toggle view, ESC=quit")

    _fp = str(FONT_PATH) if FONT_PATH.exists() else None
    font = pygame.font.Font(_fp, 28)

    model = GameModel(night=1)
    view = GameView(screen)
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

        mode = "OFFICE" if show_office else "LAPTOP"
        if model.ad_active:
            hint = f"AD ACTIVE  [{mode}]"
            color = (255, 200, 50)
        else:
            hint = f"[A] show ad  [V] {mode}  (spawn {model.ad_spawn_timer})"
            color = (120, 120, 120)
        hud = font.render(hint, True, color)
        screen.blit(hud, (10, 690))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
