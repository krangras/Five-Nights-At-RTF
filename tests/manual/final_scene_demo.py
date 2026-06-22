"""
final_scene_demo.py — Тест финальной сцены (ночь 5).

Запуск: python tests/manual/final_scene_demo.py

Сценарий:
  1. Картинка плавно появляется (fade-in ~1 сек).
  2. Бесконечная музыка + речь Алгема (разово).
  3. После окончания речи — по нажатию клавиши погасание и выход.
  ESC — принудительный выход на любом этапе.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
os.chdir(str(_ROOT))

import pygame


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    pygame.init()
    pygame.mixer.set_num_channels(16)
    screen = pygame.display.set_mode((1280, 720))
    pygame.display.set_caption("Final Scene Demo — ESC=quit")
    surface = pygame.Surface((1280, 720))

    GAME_SIZE = (1280, 720)

    final_img_path = _ROOT / "assets" / "final_scene" / "dfa83ef3-a181-4a77-8216-f80b0834de0a.png"
    final_img = None
    if final_img_path.exists():
        try:
            raw = pygame.image.load(str(final_img_path)).convert()
            final_img = pygame.transform.smoothscale(raw, GAME_SIZE)
        except pygame.error as exc:
            print(f"[WARN] Картинка не загружена: {exc}")

    music_path = _ROOT / "sounds" / "final_scene" / "mb2.wav"
    if music_path.exists():
        try:
            snd = pygame.mixer.Sound(str(music_path))
            snd.set_volume(0.5)
            snd.play(loops=-1)
            print("Музыка: playing (loop)")
        except pygame.error as exc:
            print(f"[WARN] Музыка не загружена: {exc}")

    speech_path = _ROOT / "sounds" / "final_scene" / "algems' final speech.mp3"
    speech_chan = None
    if speech_path.exists():
        try:
            snd = pygame.mixer.Sound(str(speech_path))
            snd.set_volume(1.0)
            speech_chan = snd.play()
            print("Речь Алгема: playing")
        except pygame.error as exc:
            print(f"[WARN] Речь не загружена: {exc}")

    phase = "FADE_IN"
    tick = 0
    speech_done = False

    clock = pygame.time.Clock()
    print("Финальная сцена запущена. ESC — выход.\n")

    running = True
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                print("ESC — принудительный выход")
                running = False
            if e.type == pygame.KEYDOWN and speech_done and phase == "SHOWING":
                phase = "FADE_OUT"
                tick = 0
                print("Клавиша — начало fade-out")

        if not running:
            break

        surface.fill((0, 0, 0))
        tick += 1

        if phase == "FADE_IN":
            if final_img is not None:
                alpha = min(255, tick * 4)
                final_img.set_alpha(alpha)
                surface.blit(final_img, (0, 0))
            if tick % 30 == 0:
                print(f"  fade-in: alpha={min(255, tick * 4)}")
            if tick >= 64:
                phase = "SHOWING"
                tick = 0
                print("-> SHOWING (fade-in завершён)")

        elif phase == "SHOWING":
            if final_img is not None:
                final_img.set_alpha(255)
                surface.blit(final_img, (0, 0))
            if not speech_done and (speech_chan is None or not speech_chan.get_busy()):
                speech_done = True
                print("-> Речь Алгема завершена. Нажмите любую клавишу.")

        elif phase == "FADE_OUT":
            if final_img is not None:
                alpha = max(0, 255 - tick * 8)
                final_img.set_alpha(alpha)
                surface.blit(final_img, (0, 0))
            if tick % 10 == 0:
                print(f"  fade-out: alpha={max(0, 255 - tick * 8)}")
            if tick >= 32:
                phase = "DONE"
                print("-> DONE (финальная сцена завершена)")

        pygame.transform.smoothscale(surface, screen.get_size(), screen)
        pygame.display.flip()
        clock.tick(60)

    pygame.mixer.stop()
    pygame.quit()
    print("\nТест пройден успешно.")


if __name__ == "__main__":
    main()
