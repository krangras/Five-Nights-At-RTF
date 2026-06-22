"""
screamer_demo.py — Тест скримера: показ офиса 5 секунд, затем скример.

Запуск: python tests/manual/screamer_demo.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
os.chdir(str(_ROOT))

import pygame

from fnar.gameplay.screamer import ScreamerPlayer

SCREEN_SIZE = (1280, 720)


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode(SCREEN_SIZE)
    pygame.display.set_caption("TEST SCREAMER — ждите 5 секунд, ESC=quit")
    clock = pygame.time.Clock()

    bg_path = Path("assets/office/server_is_off.png")
    if not bg_path.exists():
        print("ERROR: office background not found")
        pygame.quit()
        return
    bg = pygame.image.load(str(bg_path)).convert()
    scale = SCREEN_SIZE[1] / bg.get_height()
    bg = pygame.transform.smoothscale(bg, (int(bg.get_width() * scale), SCREEN_SIZE[1]))
    max_off = max(0, bg.get_width() - SCREEN_SIZE[0])

    screamer_path = Path("assets/screamer/office_screamer")
    if not screamer_path.is_dir():
        print(f"ERROR: screamer frames not found at {screamer_path}")
        pygame.quit()
        return
    screamer = ScreamerPlayer(
        frames_dir=str(screamer_path),
        screen_size=SCREEN_SIZE,
        scream_frame=20,
        red_start=52,
        red_duration=0.5,
    )

    timer = 0
    state = "OFFICE"
    font = pygame.font.Font("assets/fonts/OCR-A.ttf", 24)

    running = True
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                running = False

        if state == "OFFICE":
            offset = int((pygame.time.get_ticks() % 4000) / 4000 * max_off)
            screen.blit(bg, (-offset, 0))
            txt = font.render("SCREAMER IN 5...", True, (255, 255, 255))
            screen.blit(txt, (540, 680))
            pygame.display.flip()

            timer += 1
            if timer >= 300:
                state = "SCREAMER"
                screamer.reset()
                print("SCREAMER!")

            clock.tick(60)

        elif state == "SCREAMER":
            dt = clock.tick(60) / 1000.0
            screamer.update(dt)
            screamer.draw(screen)
            pygame.display.flip()
            if screamer.done:
                running = False

    pygame.quit()


if __name__ == "__main__":
    main()
