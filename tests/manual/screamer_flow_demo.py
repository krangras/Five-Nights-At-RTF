"""
screamer_flow_demo.py — Тест game_over через 5 секунд: игра -> скример -> game_over экран.

Запуск: python tests/manual/screamer_flow_demo.py

ESC — пропустить скример / выйти с game_over экрана.
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
os.chdir(str(_ROOT))

import pygame

from fnar.gameplay.model import GameModel
from fnar.gameplay.presenter import GamePresenter
from fnar.gameplay.screamer import ScreamerPlayer
from fnar.gameplay.view import GameView


def _load_font(size: int = 30) -> pygame.font.Font:
    path = "assets/fonts/OCR-A.ttf"
    if Path(path).exists():
        return pygame.font.Font(path, size)
    return pygame.font.SysFont("consolas", size)


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    pygame.display.set_caption("Screamer Flow Demo — ESC=skip, ESC again=quit")
    clock = pygame.time.Clock()

    m = GameModel(night=1)
    v = GameView(screen)
    p = GamePresenter(m, v)

    LECTURE_SOUNDS = [f"sounds/lectures/lecture{i}.mp3" for i in range(1, 4)]

    ticks = 0
    state = "GAME"
    screamer: ScreamerPlayer | None = None
    lecture_sound: pygame.mixer.Sound | None = None

    print("Game started. game_over in 5 seconds...")

    running = True
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
                break
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                if state == "GAME_OVER":
                    pygame.mixer.stop()
                    print("ESC — exit")
                    running = False
                elif state == "SCREAMER" and screamer:
                    screamer = None
                    state = "GAME_OVER"
                    pygame.mixer.stop()
                    path = random.choice(LECTURE_SOUNDS)
                    if Path(path).exists():
                        lecture_sound = pygame.mixer.Sound(path)
                        lecture_sound.play()
                        print(f"Lecture: {path}")
                    else:
                        print(f"Lecture not found: {path}")
                        lecture_sound = None
                break

        if not running:
            break

        if state == "GAME":
            m.update()
            p.update()
            v.draw(m)
            pygame.display.flip()

            ticks += 1
            if ticks >= 300:
                pygame.mixer.stop()
                m.game_over = True
                screamer = ScreamerPlayer(
                    frames_dir="assets/screamer/office_screamer",
                    screen_size=(1280, 720),
                    scream_frame=20,
                    red_start=52,
                    red_duration=0.5,
                )
                screamer.reset()
                state = "SCREAMER"
                print("SCREAMER!")
                continue

            clock.tick(60)

        elif state == "SCREAMER":
            if screamer:
                dt = clock.tick(60) / 1000.0
                screamer.update(dt)
                screamer.draw(screen)
                pygame.display.flip()
                if screamer.done:
                    screamer = None
                    state = "GAME_OVER"
                    pygame.mixer.stop()
                    path = random.choice(LECTURE_SOUNDS)
                    if Path(path).exists():
                        lecture_sound = pygame.mixer.Sound(path)
                        lecture_sound.play()
                        print(f"Lecture: {path}")
                    else:
                        print(f"Lecture not found: {path}")
                        lecture_sound = None

        elif state == "GAME_OVER":
            sw, sh = screen.get_size()
            screen.fill((0, 0, 0))

            total_seconds = (m.hour * 3600 + m.timer) // 60
            display_minutes = total_seconds // 60
            display_seconds = total_seconds % 60

            font_big = _load_font(60)
            font_small = _load_font(24)

            go_text = font_big.render("GAME OVER", True, (160, 0, 0))
            screen.blit(go_text, (sw // 2 - go_text.get_width() // 2, sh // 2 - 50))

            time_str = f"{display_minutes}:{display_seconds:02d}"
            time_text = font_small.render(time_str, True, (100, 100, 100))
            screen.blit(time_text, (sw // 2 - time_text.get_width() // 2, sh // 2 + 20))

            esc_text = font_small.render("ESC — exit", True, (60, 60, 60))
            screen.blit(esc_text, (sw // 2 - esc_text.get_width() // 2, sh // 2 + 60))

            pygame.display.flip()
            clock.tick(60)

    pygame.mixer.stop()
    pygame.quit()


if __name__ == "__main__":
    main()
