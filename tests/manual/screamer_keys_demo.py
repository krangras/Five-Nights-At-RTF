"""
screamer_keys_demo.py — Тест скримеров: O — офисный, V — вентиляционный.

Запуск: python tests/manual/screamer_keys_demo.py
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
    pygame.display.set_caption("Screamer Test — O=office, V=vent, ESC=quit")
    clock = pygame.time.Clock()

    screamer_office = ScreamerPlayer(
        frames_dir=str(Path("assets/screamer/office_screamer")),
        screen_size=SCREEN_SIZE,
        scream_frame=20,
        red_start=52,
        red_duration=0.5,
    )
    screamer_vent = ScreamerPlayer(
        frames_dir=str(Path("assets/screamer/vent_screamer")),
        screen_size=SCREEN_SIZE,
        scream_frame=40,
        red_start=62,
        red_duration=0.5,
        hold_last=0.8,
    )

    snd_screamer = None
    snd_path = Path("sounds/screamer/screamer.mp3")
    if snd_path.exists():
        snd_screamer = pygame.mixer.Sound(str(snd_path))
        snd_screamer.set_volume(0.7)

    print(f"Office screamer frames: {len(screamer_office._frames)}")
    print(f"Vent screamer frames:   {len(screamer_vent._frames)}")
    print("O — office screamer | V — vent screamer | ESC — quit")

    active_screamer: ScreamerPlayer | None = None
    state = "IDLE"
    font = pygame.font.Font(None, 36)

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
                break
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                    break
                if state == "IDLE":
                    if e.key == pygame.K_o:
                        active_screamer = screamer_office
                        active_screamer.reset()
                        state = "SCREAMER"
                        print("Playing office screamer...")
                    elif e.key == pygame.K_v:
                        active_screamer = screamer_vent
                        active_screamer.reset()
                        state = "SCREAMER"
                        print("Playing vent screamer...")

        if state == "SCREAMER" and active_screamer:
            active_screamer.update(dt)
            if active_screamer.scream_triggered and snd_screamer:
                snd_screamer.play()
                active_screamer.scream_triggered = False
                active_screamer.scream_frame = 999999
            active_screamer.draw(screen)
            pygame.display.flip()
            if active_screamer.done:
                state = "IDLE"
                active_screamer = None
                print("Done. Press O or V.")

        elif state == "IDLE":
            screen.fill((20, 20, 30))
            t1 = font.render("Press O — office screamer", True, (255, 255, 255))
            t2 = font.render("Press V — vent screamer", True, (255, 255, 255))
            screen.blit(t1, (640 - t1.get_width() // 2, 320))
            screen.blit(t2, (640 - t2.get_width() // 2, 370))
            pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
