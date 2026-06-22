import random

import pygame

from .assets import load_menu_backgrounds, load_menu_fonts, load_menu_star
from .effects import (
    create_scanlines,
    create_vignette,
    draw_glitch_bars,
    generate_static_noise,
)


class MenuView:
    def __init__(self, screen):
        self.screen = screen
        self.btn_fullscreen_rect = pygame.Rect(0, 0, 0, 0)
        self.btn_back_rect = pygame.Rect(0, 0, 0, 0)
        self._configure_screen_metrics()
        self._load_visual_state()
        self._update_button_rects()

    def update_screen(self, screen):
        self.screen = screen
        self._configure_screen_metrics()
        self._load_visual_state()
        self._update_button_rects()

    def _configure_screen_metrics(self):
        info = pygame.display.Info()
        self.w = info.current_w
        self.h = info.current_h
        self.scale_x = self.w / 1024
        self.scale_y = self.h / 768

    def _load_visual_state(self):
        fonts = load_menu_fonts(self.scale_y)
        backgrounds = load_menu_backgrounds((self.w, self.h))
        self.title_font = fonts.title
        self.button_font = fonts.button
        self.bg_images = {"NORMAL": backgrounds.normal}
        self.glitch_images = backgrounds.glitch
        self.noise_frames = generate_static_noise((self.w, self.h), self.scale_x, self.scale_y)
        self.scanlines = create_scanlines((self.w, self.h))
        self.vignette = create_vignette((self.w, self.h))
        self.star_image = load_menu_star(self.scale_x, self.scale_y)

    def _update_button_rects(self):
        sx, sy = self.scale_x, self.scale_y
        btn_x = int(100 * sx)
        surf_ng = self.button_font.render(">> New Game", True, (255, 255, 255))
        surf_cont = self.button_font.render(">> Continue", True, (255, 255, 255))
        surf_set = self.button_font.render(">> Settings", True, (255, 255, 255))
        surf_ex = self.button_font.render(">> Exit", True, (255, 255, 255))
        self.btn_new_game_rect = pygame.Rect(btn_x, int(360 * sy), surf_ng.get_width(), surf_ng.get_height())
        self.btn_continue_rect = pygame.Rect(btn_x, int(410 * sy), surf_cont.get_width(), surf_cont.get_height())
        self.btn_settings_rect = pygame.Rect(btn_x, int(460 * sy), surf_set.get_width(), surf_set.get_height())
        self.btn_exit_rect = pygame.Rect(btn_x, int(510 * sy), surf_ex.get_width(), surf_ex.get_height())

    def _draw_menu_bg(self, model, draw_star=True):
        sx, sy = self.scale_x, self.scale_y

        if model.algem_state == "NORMAL":
            self.screen.blit(self.bg_images["NORMAL"], (0, 0))
        else:
            shake_x = random.randint(int(-12 * sx), int(12 * sx))
            shake_y = random.randint(int(-5 * sy), int(5 * sy))
            frame_idx = model.glitch_frame_idx % len(self.glitch_images)
            self.screen.blit(self.glitch_images[frame_idx], (shake_x, shake_y))

        if draw_star and model.game_completed and self.star_image is not None:
            star_x = self.w - self.star_image.get_width() - int(30 * sx)
            star_y = int(30 * sy)
            self.screen.blit(self.star_image, (star_x, star_y))

        self.screen.blit(self.noise_frames[model.noise_frame % len(self.noise_frames)], (0, 0))
        self.screen.blit(self.scanlines, (0, 0))
        draw_glitch_bars(self.screen)
        self.screen.blit(self.vignette, (0, 0))

    def draw_menu(self, model):
        self._draw_menu_bg(model)
        sx, sy = self.scale_x, self.scale_y
        title_x = int(100 * sx)

        title_top = self.title_font.render("FIVE NIGHTS", True, (255, 255, 255))
        title_bot = self.title_font.render("AT RTF", True, (255, 255, 255))
        self.screen.blit(title_top, (title_x, int(120 * sy)))
        self.screen.blit(title_bot, (title_x, int(195 * sy)))

        btn_x = int(100 * sx)
        color_new = (255, 255, 255) if model.hovered_button != "new_game" else (140, 140, 140)
        text_new = ">> New Game" if model.hovered_button == "new_game" else "   New Game"
        surf_new = self.button_font.render(text_new, True, color_new)
        self.screen.blit(surf_new, (btn_x, int(360 * sy)))

        if model.continue_available:
            color_cont = (255, 255, 255) if model.hovered_button != "continue" else (140, 140, 140)
            text_cont = ">> Continue" if model.hovered_button == "continue" else "   Continue"
            night_label = f" (Night {model.saved_night})"
            surf_cont = self.button_font.render(text_cont, True, color_cont)
            self.screen.blit(surf_cont, (btn_x, int(410 * sy)))
            surf_night = self.button_font.render(night_label, True, color_cont)
            self.screen.blit(surf_night, (btn_x + surf_cont.get_width(), int(410 * sy)))
            total_w = surf_cont.get_width() + surf_night.get_width()
            self.btn_continue_rect = pygame.Rect(btn_x, int(410 * sy), total_w, surf_cont.get_height())
        else:
            surf_cont = self.button_font.render("   Continue", True, (80, 80, 80))
            self.screen.blit(surf_cont, (btn_x, int(410 * sy)))

        color_set = (255, 255, 255) if model.hovered_button != "settings" else (140, 140, 140)
        text_set = ">> Settings" if model.hovered_button == "settings" else "   Settings"
        surf_set = self.button_font.render(text_set, True, color_set)
        self.screen.blit(surf_set, (btn_x, int(460 * sy)))

        color_exit = (255, 255, 255) if model.hovered_button != "exit" else (140, 140, 140)
        text_exit = ">> Exit" if model.hovered_button == "exit" else "   Exit"
        surf_exit = self.button_font.render(text_exit, True, color_exit)
        self.screen.blit(surf_exit, (btn_x, int(510 * sy)))

        pygame.display.flip()

    def draw_settings(self, is_fullscreen: bool, hovered: str | None = None, model=None):
        if model:
            self._draw_menu_bg(model, draw_star=False)
        else:
            self.screen.fill((10, 10, 15))
        sx, sy = self.scale_x, self.scale_y

        title = self.title_font.render("SETTINGS", True, (255, 255, 255))
        self.screen.blit(title, (int(100 * sx), int(100 * sy)))

        btn_x = int(100 * sx)
        fs_label = "ON" if is_fullscreen else "OFF"
        color_fs = (255, 255, 255) if hovered != "fullscreen" else (140, 140, 140)
        text_fs = f">> Fullscreen: {fs_label}" if hovered == "fullscreen" else f"   Fullscreen: {fs_label}"
        surf_fs = self.button_font.render(text_fs, True, color_fs)
        self.screen.blit(surf_fs, (btn_x, int(280 * sy)))
        self.btn_fullscreen_rect = pygame.Rect(btn_x, int(280 * sy), surf_fs.get_width(), surf_fs.get_height())

        color_back = (255, 255, 255) if hovered != "back" else (140, 140, 140)
        text_back = ">> Back" if hovered == "back" else "   Back"
        surf_back = self.button_font.render(text_back, True, color_back)
        self.screen.blit(surf_back, (btn_x, int(360 * sy)))
        self.btn_back_rect = pygame.Rect(btn_x, int(360 * sy), surf_back.get_width(), surf_back.get_height())

        pygame.display.flip()
