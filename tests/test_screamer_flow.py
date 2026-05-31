"""
Тест скримера: game_over через 5 секунд.
Запуск: python test_screamer_flow.py
"""
import os
import pygame

os.environ["SDL_VIDEODRIVER"] = "dummy"

pygame.init()
screen = pygame.display.set_mode((1280, 720))

from model import MenuModel
from presenter import MenuPresenter
from view import MenuView
from gameplay_model import GameModel
from gameplay_view import GameView
from gameplay_presenter import GamePresenter
from screamer import ScreamerPlayer
import random

LOADING_FONT_CACHE: dict[int, pygame.font.Font] = {}
LECTURE_SOUNDS = [f"sounds/lectures/lecture{i}.mp3" for i in range(1, 4)]

def _get_loading_font(size=30):
    if size not in LOADING_FONT_CACHE:
        path = "assets/fonts/OCR-A.ttf"
        if os.path.exists(path):
            LOADING_FONT_CACHE[size] = pygame.font.Font(path, size)
        else:
            LOADING_FONT_CACHE[size] = pygame.font.Font(None, size)
    return LOADING_FONT_CACHE[size]

def main():
    clock = pygame.time.Clock()

    m = GameModel(night=1)
    v = GameView(screen)
    p = GamePresenter(m, v)

    ticks = 0
    state = "GAME"
    screamer = None
    lecture_sound = None

    print("Игра запущена. game_over через 5 секунд...")

    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                if screamer:
                    screamer.close()
                return
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                if state == "GAME_OVER":
                    pygame.mixer.stop()
                    lecture_sound = None
                    print("ESC — возврат в меню (выход из теста)")
                    return
                if state == "SCREAMER" and screamer:
                    screamer.close()
                    state = "GAME_OVER"
                    pygame.mixer.stop()
                    try:
                        path = random.choice(LECTURE_SOUNDS)
                        lecture_sound = pygame.mixer.Sound(path)
                        lecture_sound.play()
                        print(f"Лекция: {path}")
                    except pygame.error:
                        lecture_sound = None

        if state == "GAME":
            p.handle_event(e) if False else None
            m.update()
            p.update()
            v.draw(m)
            pygame.display.flip()

            ticks += 1
            if ticks >= 300:  # 5 секунд при 60 FPS
                pygame.mixer.stop()
                m.game_over = True
                screamer = ScreamerPlayer("assets/office/screamer.mp4")
                screamer.extract_audio()
                screamer.play_audio()
                state = "SCREAMER"
                print("SCREAMER!")
                continue

            clock.tick(60)

        elif state == "SCREAMER":
            if screamer:
                frame = screamer.get_frame()
                if frame is None:
                    screamer.close()
                    screamer = None
                    state = "GAME_OVER"
                    pygame.mixer.stop()
                    try:
                        path = random.choice(LECTURE_SOUNDS)
                        lecture_sound = pygame.mixer.Sound(path)
                        lecture_sound.play()
                        print(f"Лекция: {path}")
                    except pygame.error:
                        lecture_sound = None
                else:
                    screen.blit(frame, (0, 0))
                    pygame.display.flip()
            clock.tick(60)

        elif state == "GAME_OVER":
            sw, sh = screen.get_size()
            screen.fill((0, 0, 0))

            total_ticks = m.hour * 3600 + m.timer
            total_seconds = total_ticks // 60
            display_minutes = total_seconds // 60
            display_seconds = total_seconds % 60

            font_big = _get_loading_font(60)
            font_small = _get_loading_font(24)

            go_text = font_big.render("GAME OVER", True, (160, 0, 0))
            screen.blit(go_text, (sw // 2 - go_text.get_width() // 2, sh // 2 - 50))

            time_str = f"{display_minutes}:{display_seconds:02d}"
            time_text = font_small.render(time_str, True, (100, 100, 100))
            screen.blit(time_text, (sw // 2 - time_text.get_width() // 2, sh // 2 + 20))

            pygame.display.flip()
            clock.tick(60)

if __name__ == "__main__":
    main()
