import sys

import pygame

from .audio import MenuAudio


class MenuPresenter:
    def __init__(self, model, view, settings_data=None):
        self.model = model
        self.view = view
        self.audio = MenuAudio(settings_data)
        self._prev_hover = None

    def handle_events(self, global_event_handler=None):
        self.audio.ensure_music()
        self._update_menu_hover()
        self._play_hover_if_changed()

        for event in pygame.event.get():
            if global_event_handler is not None and global_event_handler(event):
                continue
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.model.hovered_button == "new_game":
                    self.audio.stop_music()
                    return "START_GAME"
                if self.model.hovered_button == "continue":
                    self.audio.stop_music()
                    return "START_CONTINUE"
                if self.model.hovered_button == "settings":
                    return "SETTINGS"
                if self.model.hovered_button == "exit":
                    pygame.quit()
                    sys.exit()

        return "MENU"

    def handle_settings_events(self, is_fullscreen: bool, global_event_handler=None):
        hovered = self._get_settings_hover()
        if hovered != self._prev_hover and hovered is not None:
            self.audio.play_hover()
        self._prev_hover = hovered

        for event in pygame.event.get():
            if global_event_handler is not None and global_event_handler(event):
                continue
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return "BACK", is_fullscreen, hovered
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if hovered == "fullscreen":
                    return "TOGGLE_FS", is_fullscreen, hovered
                if hovered == "back":
                    return "BACK", is_fullscreen, hovered

        return None, is_fullscreen, hovered

    def _update_menu_hover(self):
        mouse_pos = pygame.mouse.get_pos()
        if self.view.btn_new_game_rect.collidepoint(mouse_pos):
            self.model.hovered_button = "new_game"
        elif self.model.continue_available and self.view.btn_continue_rect.collidepoint(mouse_pos):
            self.model.hovered_button = "continue"
        elif self.view.btn_settings_rect.collidepoint(mouse_pos):
            self.model.hovered_button = "settings"
        elif self.view.btn_exit_rect.collidepoint(mouse_pos):
            self.model.hovered_button = "exit"
        else:
            self.model.hovered_button = None

    def _get_settings_hover(self):
        mouse_pos = pygame.mouse.get_pos()
        if self.view.btn_fullscreen_rect.collidepoint(mouse_pos):
            return "fullscreen"
        if self.view.btn_back_rect.collidepoint(mouse_pos):
            return "back"
        return None

    def _play_hover_if_changed(self):
        if self.model.hovered_button != self._prev_hover and self.model.hovered_button is not None:
            self.audio.play_hover()
        self._prev_hover = self.model.hovered_button
