"""
Тест финальной сцены (ночь 5).
Запуск: python tests/manual/final_scene_demo.py

Сценарий:
  1. Картинка плавно появляется (fade-in ~1 сек).
  2. Бесконечная музыка + речь Алгема (разово).
  3. После окончания речи — по нажатию клавиши погасание и выход.
  ESC — принудительный выход на любом этапе.
"""

import pygame


def main():
    pygame.init()
    pygame.mixer.set_num_channels(16)
    screen = pygame.display.set_mode((1280, 720), pygame.FULLSCREEN)
    surface = pygame.Surface((1280, 720))

    GAME_SIZE = (1280, 720)

    # ── Загрузка ассетов ────────────────────────────────────────────────
    try:
        raw = pygame.image.load("assets/final_scene/dfa83ef3-a181-4a77-8216-f80b0834de0a.png").convert()
        final_img = pygame.transform.smoothscale(raw, GAME_SIZE)
    except pygame.error as exc:
        print(f"[WARN] Картинка не загружена: {exc}")
        final_img = None

    try:
        snd = pygame.mixer.Sound("sounds/final_scene/mb2.wav")
        snd.set_volume(0.5)
        _music_chan = snd.play(loops=-1)
        print("Музыка: playing (loop)")
    except pygame.error as exc:
        print(f"[WARN] Музыка не загружена: {exc}")

    speech_chan = None
    try:
        snd = pygame.mixer.Sound("sounds/final_scene/algems' final speech.mp3")
        snd.set_volume(1.0)
        speech_chan = snd.play()
        print("Речь Алгема: playing")
    except pygame.error as exc:
        print(f"[WARN] Речь не загружена: {exc}")

    # ── Состояние ───────────────────────────────────────────────────────
    phase = "FADE_IN"  # FADE_IN → SHOWING → FADE_OUT → DONE
    tick = 0
    speech_done = False

    clock = pygame.time.Clock()
    print("Финальная сцена запущена. ESC — выход.\n")

    while phase != "DONE":
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.mixer.stop()
                pygame.quit()
                return
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                print("ESC — принудительный выход")
                pygame.mixer.stop()
                pygame.quit()
                return
            if e.type == pygame.KEYDOWN and speech_done and phase == "SHOWING":
                phase = "FADE_OUT"
                tick = 0
                print("Клавиша — начало fade-out")

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
                print("→ SHOWING (fade-in завершён)")

        elif phase == "SHOWING":
            if final_img is not None:
                final_img.set_alpha(255)
                surface.blit(final_img, (0, 0))
            if not speech_done and (speech_chan is None or not speech_chan.get_busy()):
                speech_done = True
                print("→ Речь Алгема завершена. Нажмите любую клавишу.")

        elif phase == "FADE_OUT":
            if final_img is not None:
                alpha = max(0, 255 - tick * 8)
                final_img.set_alpha(alpha)
                surface.blit(final_img, (0, 0))
            if tick % 10 == 0:
                print(f"  fade-out: alpha={max(0, 255 - tick * 8)}")
            if tick >= 32:
                phase = "DONE"
                print("→ DONE (финальная сцена завершена)")

        pygame.transform.smoothscale(surface, screen.get_size(), screen)
        pygame.display.flip()
        clock.tick(60)

    pygame.mixer.stop()
    pygame.quit()
    print("\nТест пройден успешно.")


if __name__ == "__main__":
    main()
