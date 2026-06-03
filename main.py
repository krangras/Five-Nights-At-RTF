import os
import math
import random
import threading
import pygame
from model import MenuModel
from presenter import MenuPresenter
from view import MenuView
from gameplay_model import GameModel
from gameplay_view import GameView
from gameplay_presenter import GamePresenter
from save import load_save, save_progress
from settings import load_settings, save_settings
from screamer import ScreamerPlayer

LOADING_FONT_CACHE: dict[int, pygame.font.Font] = {}
LECTURE_SOUNDS: list[str] = [
    f"sounds/lectures/lecture{i}.mp3" for i in range(1, 7)
]

def _get_loading_font(size=30):
    if size not in LOADING_FONT_CACHE:
        path = "assets/fonts/OCR-A.ttf"
        if os.path.exists(path):
            LOADING_FONT_CACHE[size] = pygame.font.Font(path, size)
        else:
            LOADING_FONT_CACHE[size] = pygame.font.Font(None, size)
    return LOADING_FONT_CACHE[size]

def draw_loading(screen, elapsed_ms):
    screen.fill((0, 0, 0))
    font = _get_loading_font()
    dots = "." * ((elapsed_ms // 300) % 4)
    txt = font.render(f"LOADING{dots}", True, (100, 100, 100))
    sw, sh = screen.get_size()
    screen.blit(txt, (sw // 2 - txt.get_width() // 2, sh // 2 - txt.get_height() // 2))
    pygame.display.flip()

GAME_SIZE = (1280, 720)

WINDOWED_SIZE = (1280, 720)

def _scale_event(event, screen):
    sw, sh = screen.get_size()
    if sw == GAME_SIZE[0] and sh == GAME_SIZE[1]:
        return event
    if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
        mx, my = event.pos
        gx = int(mx * GAME_SIZE[0] / sw)
        gy = int(my * GAME_SIZE[1] / sh)
        event.pos = (gx, gy)
    return event

_monitor_size = None
_settings = None

def toggle_fullscreen(screen, is_fullscreen):
    global _settings
    if is_fullscreen:
        screen = pygame.display.set_mode(WINDOWED_SIZE)
        _settings["fullscreen"] = False
    else:
        screen = pygame.display.set_mode(_monitor_size, pygame.FULLSCREEN)
        _settings["fullscreen"] = True
    save_settings(_settings)
    return screen, not is_fullscreen

def main():
    global _monitor_size, _settings
    pygame.init()
    pygame.mixer.set_num_channels(16)
    _settings = load_settings()
    _monitor_size = pygame.display.list_modes()[0]
    if _settings.get("fullscreen", True):
        screen = pygame.display.set_mode(_monitor_size, pygame.FULLSCREEN)
        is_fullscreen = True
    else:
        screen = pygame.display.set_mode(WINDOWED_SIZE)
        is_fullscreen = False
    clock = pygame.time.Clock()
    try:
        snd_scream = pygame.mixer.Sound("sounds/screamer.mp3")
        snd_scream.set_volume(0.5)
    except pygame.error:
        pass

    menu_m, menu_v = MenuModel(), MenuView(screen)
    menu_p = MenuPresenter(menu_m, menu_v)

    game_m, game_v, game_p = None, None, None
    load_start = 0
    lecture_sound = None
    game_over_tick = 0
    night_complete_tick = 0
    night_end_sound = None
    screamer = None

    game_surface = pygame.Surface(GAME_SIZE)

    def start_game(night=1):
        m = GameModel(night=night)
        v = GameView(game_surface)
        p = GamePresenter(m, v)
        return m, v, p

    state = "MENU"
    while True:
        if state == "MENU":
            state = menu_p.handle_events()
            if state == "TOGGLE_FULLSCREEN":
                screen, is_fullscreen = toggle_fullscreen(screen, is_fullscreen)
                menu_v = MenuView(screen)
                menu_p = MenuPresenter(menu_m, menu_v)
                state = "MENU"
            menu_m.update()
            menu_v.draw_menu(menu_m)
            clock.tick(60)
        elif state == "START_GAME":
            load_start = pygame.time.get_ticks()
            state = "LOADING"
            _continue_night = 1
        elif state == "START_CONTINUE":
            load_start = pygame.time.get_ticks()
            _continue_night = load_save()
            state = "LOADING"
        elif state == "LOADING":
            draw_loading(screen, pygame.time.get_ticks() - load_start)
            clock.tick(60)
            game_m, game_v, game_p = start_game(_continue_night)
            screamer = ScreamerPlayer(screen_size=GAME_SIZE)
            state = "GAME"
        elif state == "GAME":
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    pygame.mixer.stop()
                    return
                if e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                    screen, is_fullscreen = toggle_fullscreen(screen, is_fullscreen)
                    continue
                game_p.handle_event(_scale_event(e, screen))

            game_m.update()
            game_p.update()

            game_v.draw(game_m)
            pygame.transform.smoothscale(game_surface, screen.get_size(), screen)
            pygame.display.flip()

            if game_m.game_over:
                pygame.mixer.stop()
                save_progress(game_m.night)
                screamer.reset()
                try:
                    snd_scream.play()
                except pygame.error:
                    pass
                state = "SCREAMER"
                game_over_tick = 0
                continue
            elif game_m.night_complete:
                save_progress(game_m.night + 1)
                pygame.mixer.stop()
                night_complete_tick = 0
                night_end_sound = None
                try:
                    night_end_sound = pygame.mixer.Sound("sounds/night_ends.wav")
                    night_end_sound.play()
                except pygame.error:
                    pass
                state = "NIGHT_COMPLETE"
            clock.tick(60)
        elif state == "SCREAMER":
            dt = clock.tick(60) / 1000.0
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    pygame.mixer.stop()
                    return
                if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    pygame.mixer.stop()
                    screamer = None
                    lecture_sound = None
                    menu_m.saved_night = load_save()
                    menu_m.continue_available = menu_m.saved_night > 1
                    state = "MENU"

            screamer.update(dt)
            screamer.draw(game_surface)
            pygame.transform.smoothscale(game_surface, screen.get_size(), screen)
            pygame.display.flip()

            if screamer.done:
                screamer = None
                state = "GAME_OVER"
                try:
                    path = random.choice(LECTURE_SOUNDS)
                    lecture_sound = pygame.mixer.Sound(path)
                    lecture_sound.set_volume(1.5)
                    lecture_sound.play()
                    def _echo():
                        try:
                            snd = pygame.mixer.Sound(path)
                            snd.set_volume(0.4)
                            snd.play()
                        except pygame.error:
                            pass
                    threading.Timer(0.3, _echo).start()
                except pygame.error:
                    lecture_sound = None
        elif state == "GAME_OVER":
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    pygame.mixer.stop()
                    return
                if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    pygame.mixer.stop()
                    lecture_sound = None
                    menu_m.saved_night = load_save()
                    menu_m.continue_available = menu_m.saved_night > 1
                    state = "MENU"

            game_surface.fill((0, 0, 0))

            total_ticks = game_m.hour * 3600 + game_m.timer
            total_seconds = total_ticks // 60
            display_minutes = total_seconds // 60
            display_seconds = total_seconds % 60

            font_big = _get_loading_font(60)
            font_small = _get_loading_font(24)

            game_over_tick += 1
            pulse = (math.sin(game_over_tick * 0.05) + 1) / 2
            r = int(100 + pulse * 60)
            go_surf = font_big.render("GAME OVER", True, (r, 0, 0))
            game_surface.blit(go_surf, (640 - go_surf.get_width() // 2, 360 - 50))

            time_str = f"{display_minutes}:{display_seconds:02d}"
            time_text = font_small.render(time_str, True, (100, 100, 100))
            game_surface.blit(time_text, (640 - time_text.get_width() // 2, 360 + 30))

            pygame.transform.smoothscale(game_surface, screen.get_size(), screen)
            pygame.display.flip()
            clock.tick(60)
        elif state == "NIGHT_COMPLETE":
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    pygame.mixer.stop()
                    return

            game_surface.fill((0, 0, 0))

            font_big = _get_loading_font(80)
            font_sub = _get_loading_font(30)

            night_complete_tick += 1

            if night_complete_tick < 60:
                alpha = min(255, night_complete_tick * 12)
                am_surf = font_big.render("6 AM", True, (255, 255, 255))
                am_surf.set_alpha(alpha)
                game_surface.blit(am_surf, (640 - am_surf.get_width() // 2, 360 - am_surf.get_height() // 2))

                completed_night = game_m.night
                if completed_night >= 5:
                    sub = font_sub.render("You survived all nights!", True, (200, 200, 200))
                else:
                    sub = font_sub.render(f"Night {completed_night} Complete", True, (200, 200, 200))
                sub.set_alpha(alpha)
                game_surface.blit(sub, (640 - sub.get_width() // 2, 360 + 60))
            else:
                am_surf = font_big.render("6 AM", True, (255, 255, 255))
                game_surface.blit(am_surf, (640 - am_surf.get_width() // 2, 360 - am_surf.get_height() // 2))

                completed_night = game_m.night
                if completed_night >= 5:
                    sub = font_sub.render("You survived all nights!", True, (200, 200, 200))
                else:
                    sub = font_sub.render(f"Night {completed_night} Complete", True, (200, 200, 200))
                game_surface.blit(sub, (640 - sub.get_width() // 2, 360 + 60))

            sound_done = night_end_sound is None or not pygame.mixer.get_busy()
            if sound_done:
                menu_m.saved_night = load_save()
                menu_m.continue_available = menu_m.saved_night > 1
                if completed_night >= 5:
                    state = "MENU"
                else:
                    game_m, game_v, game_p = start_game(completed_night + 1)
                    state = "GAME"

            pygame.transform.smoothscale(game_surface, screen.get_size(), screen)
            pygame.display.flip()
            clock.tick(60)

if __name__ == "__main__":
    main()
