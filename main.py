import os
import pygame
from model import MenuModel
from presenter import MenuPresenter
from view import MenuView
from gameplay_model import GameModel
from gameplay_view import GameView
from gameplay_presenter import GamePresenter
from screamer import ScreamerPlayer

LOADING_FONT_CACHE = None

def _get_loading_font(size=30):
    global LOADING_FONT_CACHE
    if LOADING_FONT_CACHE is None:
        path = "assets/fonts/OCR-A.ttf"
        if os.path.exists(path):
            LOADING_FONT_CACHE = pygame.font.Font(path, size)
        else:
            LOADING_FONT_CACHE = pygame.font.Font(None, size)
    return LOADING_FONT_CACHE

def draw_loading(screen, elapsed_ms):
    screen.fill((0, 0, 0))
    font = _get_loading_font()
    dots = "." * ((elapsed_ms // 300) % 4)
    txt = font.render(f"LOADING{dots}", True, (100, 100, 100))
    sw, sh = screen.get_size()
    screen.blit(txt, (sw // 2 - txt.get_width() // 2, sh // 2 - txt.get_height() // 2))
    pygame.display.flip()

def main():
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    clock = pygame.time.Clock()

    menu_m, menu_v = MenuModel(), MenuView(screen)
    menu_p = MenuPresenter(menu_m, menu_v)

    def start_game(night=1):
        m = GameModel(night=night)
        v = GameView(screen)
        p = GamePresenter(m, v)
        return m, v, p

    game_m = game_v = game_p = None
    load_start = 0

    state = "MENU"
    while True:
        if state == "MENU":
            state = menu_p.handle_events()
            menu_m.update()
            menu_v.draw_menu(menu_m)
            clock.tick(60)
        elif state == "START_GAME":
            load_start = pygame.time.get_ticks()
            state = "LOADING"
        elif state == "LOADING":
            draw_loading(screen, pygame.time.get_ticks() - load_start)
            clock.tick(60)
            game_m, game_v, game_p = start_game(1)
            state = "GAME"
        elif state == "GAME":
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return
                game_p.handle_event(e)

            game_m.update()
            game_p.update()

            game_v.draw(game_m)
            pygame.display.flip()

            if game_m.game_over:
                pygame.mixer.stop()
                screamer = ScreamerPlayer("assets/office/screamer.mp4")
                screamer.extract_audio()
                screamer.play_audio()
                state = "SCREAMER"
                continue
            elif game_m.night_complete:
                if game_m.night >= 5:
                    state = "MENU"
                else:
                    game_m, game_v, game_p = start_game(game_m.night + 1)
            clock.tick(60)
        elif state == "SCREAMER":
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    screamer.close()
                    return
                if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    screamer.close()
                    state = "MENU"

            if state == "SCREAMER":
                frame = screamer.get_frame()
                if frame is None:
                    screamer.close()
                    state = "MENU"
                else:
                    screen.blit(frame, (0, 0))
                    pygame.display.flip()

            clock.tick(screamer.fps)

if __name__ == "__main__":
    main()
