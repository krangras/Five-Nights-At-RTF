import os
import math
import random
import threading
import pygame
import cv2
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
_native_size = None

def _blit_or_scale(src, dst):
    if _native_size and dst.get_size() == _native_size:
        dst.blit(src, (0, 0))
    else:
        pygame.transform.smoothscale(src, dst.get_size(), dst)

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
    pygame.display.set_caption("Five Nights At RTF")
    try:
        icon = pygame.image.load("assets/logo/icon.ico")
        pygame.display.set_icon(icon)
    except pygame.error:
        try:
            icon = pygame.image.load("assets/logo/logo_32_rgb.png")
            pygame.display.set_icon(icon)
        except pygame.error:
            pass
    # Принудительно ставим иконку на панель задач (Windows 10+)
    try:
        import ctypes
        hwnd = pygame.display.get_wm_info()["window"]
        ICON_small = 1
        ICON_big = 0
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        GCLP_HICONSM = -34
        GCLP_HICON = -14
        icon_path = os.path.abspath("assets/logo/icon.ico")
        user32 = ctypes.windll.user32
        hicon = user32.LoadImageW(None, icon_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        if hicon:
            user32.SetClassLongPtrW(hwnd, GCLP_HICONSM, hicon)
            user32.SetClassLongPtrW(hwnd, GCLP_HICON, hicon)
    except Exception:
        pass
    clock = pygame.time.Clock()

    _snd_cache: dict[str, pygame.mixer.Sound] = {}
    _snd_paths = [
        ("screamer", "sounds/screamer/screamer.mp3"),
        ("night_ends", "sounds/ui/night_ends.wav"),
        ("server_not_hacked", "sounds/screamer/server_is_not_hacked.mp3"),
    ]
    for _key, _path in _snd_paths:
        try:
            _snd_cache[_key] = pygame.mixer.Sound(_path)
            if _key == "screamer":
                _snd_cache[_key].set_volume(0.5)
            elif _key == "night_ends":
                _snd_cache[_key].set_volume(0.55)
        except pygame.error:
            pass
    _lecture_sounds_cache: list[pygame.mixer.Sound] = []
    for i in range(1, 7):
        try:
            _lecture_sounds_cache.append(pygame.mixer.Sound(f"sounds/lectures/lecture{i}.mp3"))
        except pygame.error:
            pass
    _final_scene_sounds: dict[str, pygame.mixer.Sound] = {}
    for _key, _path in [
        ("music", "sounds/final_scene/mb2.wav"),
        ("speech", "sounds/final_scene/algems' final speech.mp3"),
    ]:
        try:
            _final_scene_sounds[_key] = pygame.mixer.Sound(_path)
        except pygame.error:
            pass

    menu_m, menu_v = MenuModel(), MenuView(screen)
    menu_p = MenuPresenter(menu_m, menu_v, _settings)

    game_m, game_v, game_p = None, None, None
    load_start = 0
    lecture_sound = None
    game_over_tick = 0
    hack_timeout_sound = None
    night_complete_tick = 0
    night_end_sound = None
    screamer = None
    _nt_video_frames = []
    _nt_video_fps = 30.0

    def _preload_night_transfer():
        nonlocal _nt_video_frames, _nt_video_fps
        try:
            _nt_video_frames = []
            cap = cv2.VideoCapture("assets/night_transfer/night_transfer.mp4")
            _nt_video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            while True:
                ret, bgr = cap.read()
                if not ret:
                    break
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                h, w = rgb.shape[:2]
                surf = pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")
                if (w, h) != GAME_SIZE:
                    surf = pygame.transform.smoothscale(surf, GAME_SIZE)
                _nt_video_frames.append(surf)
            cap.release()
        except Exception:
            _nt_video_frames = []

    # ── Финальная сцена (ночь 5) ──────────────────────────────────────
    final_scene_img = None
    final_scene_music = None
    final_scene_speech = None
    final_scene_tick = 0
    final_scene_phase = ""  # FADE_IN | SHOWING | FADE_OUT
    final_scene_speech_played = False
    final_scene_music_chan = None
    final_scene_speech_chan = None

    game_surface = pygame.Surface(GAME_SIZE)
    _native_size = GAME_SIZE

    def start_game(night=1):
        m = GameModel(night=night)
        v = GameView(game_surface)
        p = GamePresenter(m, v, _settings)
        return m, v, p

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
            _continue_night = 1
        elif state == "SETTINGS":
            result, is_fullscreen, settings_hovered = menu_p.handle_settings_events(is_fullscreen)
            if result == "BACK":
                state = "MENU"
            elif result == "TOGGLE_FS":
                screen, is_fullscreen = toggle_fullscreen(screen, is_fullscreen)
                menu_v.update_screen(screen)
            menu_v.draw_settings(is_fullscreen, settings_hovered, menu_m)
            clock.tick(60)
        elif state == "START_CONTINUE":
            load_start = pygame.time.get_ticks()
            _continue_night = load_save()
            state = "LOADING"
        elif state == "LOADING":
            draw_loading(screen, pygame.time.get_ticks() - load_start)
            clock.tick(60)
            game_m, game_v, game_p = start_game(_continue_night)
            screamer = ScreamerPlayer(screen_size=GAME_SIZE)
            _preload_night_transfer()
            state = "GAME"
        elif state == "GAME":
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    pygame.mixer.stop()
                    return
                game_p.handle_event(_scale_event(e, screen))

            game_m.update()
            game_p.update()

            game_v.draw(game_m)
            game_p.draw_overlays(game_surface)
            _blit_or_scale(game_surface, screen)
            pygame.display.flip()

            if game_m.game_over:
                pygame.mixer.stop()
                save_progress(game_m.night)
                if game_m.hour >= 6 and game_m.hack_progress < 1.0:
                    game_over_tick = 0
                    hack_timeout_sound = _snd_cache.get("server_not_hacked")
                    if hack_timeout_sound is not None:
                        try:
                            hack_timeout_sound.set_volume(0.7)
                            hack_timeout_sound.play()
                        except pygame.error:
                            pass
                    state = "HACK_TIMEOUT"
                else:
                    screamer.reset()
                    try:
                        _snd_cache["screamer"].play()
                    except (pygame.error, KeyError):
                        pass
                    state = "SCREAMER"
                    game_over_tick = 0
                continue
            elif game_m.night_complete:
                save_progress(min(game_m.night + 1, 5))
                pygame.mixer.stop()
                night_complete_tick = 0
                if "night_ends" in _snd_cache:
                    night_end_sound = _snd_cache["night_ends"]
                    night_end_sound.play()
                else:
                    night_end_sound = None
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
            _blit_or_scale(game_surface, screen)
            pygame.display.flip()

            if screamer.done:
                screamer = None
                state = "GAME_OVER"
                if _lecture_sounds_cache:
                    lecture_sound = random.choice(_lecture_sounds_cache)
                    lecture_sound.set_volume(0.62)
                    lecture_sound.play()
                    def _echo():
                        lecture_sound.set_volume(0.28)
                        lecture_sound.play()
                    threading.Timer(0.3, _echo).start()
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

            _blit_or_scale(game_surface, screen)
            pygame.display.flip()
            clock.tick(60)
        elif state == "HACK_TIMEOUT":
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    pygame.mixer.stop()
                    return
                if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    pygame.mixer.stop()
                    hack_timeout_sound = None
                    menu_m.saved_night = load_save()
                    menu_m.continue_available = menu_m.saved_night > 1
                    state = "MENU"

            game_surface.fill((0, 0, 0))
            font_big = _get_loading_font(58)
            font_small = _get_loading_font(28)
            game_over_tick += 1

            pulse = (math.sin(game_over_tick * 0.04) + 1) / 2
            red = int(150 + pulse * 55)
            title_surf = font_big.render("GAME OVER", True, (red, 0, 0))
            game_surface.blit(
                title_surf,
                (640 - title_surf.get_width() // 2, 300 - title_surf.get_height() // 2),
            )

            msg = "You didn't hack the server in time"
            msg_surf = font_small.render(msg, True, (105, 105, 105))
            game_surface.blit(
                msg_surf,
                (640 - msg_surf.get_width() // 2, 400 - msg_surf.get_height() // 2),
            )

            _blit_or_scale(game_surface, screen)
            pygame.display.flip()
            clock.tick(60)
        elif state == "NIGHT_COMPLETE":
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    _nt_video_frames = []
                    pygame.mixer.stop()
                    return
                if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    _nt_video_frames = []
                    pygame.mixer.stop()
                    menu_m.saved_night = load_save()
                    menu_m.continue_available = menu_m.saved_night > 1
                    state = "MENU"
                    continue

            night_complete_tick += 1
            completed_night = game_m.night

            video_done = True
            if _nt_video_frames:
                frame_idx = min(
                    int(night_complete_tick * _nt_video_fps / 60.0),
                    len(_nt_video_frames) - 1,
                )
                game_surface.blit(_nt_video_frames[frame_idx], (0, 0))
                if frame_idx < len(_nt_video_frames) - 1:
                    video_done = False
            else:
                game_surface.fill((0, 0, 0))

            sound_done = night_end_sound is None or not pygame.mixer.get_busy()
            if video_done and sound_done:
                pygame.mixer.stop()
                menu_m.saved_night = load_save()
                menu_m.continue_available = menu_m.saved_night > 1
                if completed_night >= 5:
                    final_scene_tick = 0
                    final_scene_phase = "FADE_IN"
                    final_scene_speech_played = False
                    try:
                        raw = pygame.image.load(
                            "assets/final_scene/"
                            "dfa83ef3-a181-4a77-8216-f80b0834de0a.png"
                        ).convert()
                        final_scene_img = pygame.transform.smoothscale(
                            raw, GAME_SIZE
                        )
                    except pygame.error:
                        final_scene_img = None
                    final_scene_music_chan = None
                    final_scene_speech_chan = None
                    if "music" in _final_scene_sounds:
                        _final_scene_sounds["music"].set_volume(0.42)
                        final_scene_music_chan = _final_scene_sounds["music"].play(loops=-1)
                    if "speech" in _final_scene_sounds:
                        _final_scene_sounds["speech"].set_volume(0.72)
                        final_scene_speech_chan = _final_scene_sounds["speech"].play()
                    state = "FINAL_SCENE"
                else:
                    game_m, game_v, game_p = start_game(completed_night + 1)
                    state = "GAME"

            _blit_or_scale(game_surface, screen)
            pygame.display.flip()
            clock.tick(60)
        elif state == "FINAL_SCENE":
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    pygame.mixer.stop()
                    return
                if e.type == pygame.KEYDOWN and final_scene_speech_played:
                    final_scene_phase = "FADE_OUT"
                    final_scene_tick = 0

            game_surface.fill((0, 0, 0))
            final_scene_tick += 1

            if final_scene_phase == "FADE_IN":
                if final_scene_img is not None:
                    alpha = min(255, final_scene_tick * 4)
                    final_scene_img.set_alpha(alpha)
                    game_surface.blit(final_scene_img, (0, 0))
                if final_scene_tick >= 64:
                    final_scene_phase = "SHOWING"
                    final_scene_tick = 0

            elif final_scene_phase == "SHOWING":
                if final_scene_img is not None:
                    final_scene_img.set_alpha(255)
                    game_surface.blit(final_scene_img, (0, 0))
                if (
                    not final_scene_speech_played
                    and (
                        final_scene_speech_chan is None
                        or not final_scene_speech_chan.get_busy()
                    )
                ):
                    final_scene_speech_played = True

            elif final_scene_phase == "FADE_OUT":
                if final_scene_img is not None:
                    alpha = max(0, 255 - final_scene_tick * 8)
                    final_scene_img.set_alpha(alpha)
                    game_surface.blit(final_scene_img, (0, 0))
                if final_scene_tick >= 32:
                    pygame.mixer.stop()
                    final_scene_img = None
                    final_scene_music_chan = None
                    final_scene_speech_chan = None
                    menu_m.saved_night = load_save()
                    menu_m.continue_available = menu_m.saved_night > 1
                    state = "MENU"

            _blit_or_scale(game_surface, screen)
            pygame.display.flip()
            clock.tick(60)

if __name__ == "__main__":
    main()
