import sys
import pygame

class MenuPresenter:
    def __init__(self, model, view):
        self.model = model
        self.view = view
        self._prev_hover = None
        self._blip_sound = None
        try:
                self._blip_sound = pygame.mixer.Sound("sounds/ui/blip3.mp3")
        except pygame.error:
            pass
        self._menu_music_loaded = False

    def _ensure_music(self):
        if pygame.mixer.music.get_busy():
            return
        if not self._menu_music_loaded:
            try:
                pygame.mixer.music.load("sounds/menu/Faulty_Ventilation.mp3")
                self._menu_music_loaded = True
            except pygame.error:
                print("sounds/menu/Faulty_Ventilation.mp3 not found")
                return
        try:
            pygame.mixer.music.play(-1)
        except pygame.error:
            pass

    @property
    def blip_sound(self):
        if self._blip_sound is None:
            try:
                self._blip_sound = pygame.mixer.Sound("sounds/ui/blip3.mp3")
            except pygame.error:
                pass
        return self._blip_sound

    def handle_events(self):
        self._ensure_music()
        if not pygame.mixer.music.get_busy():
            self._ensure_music()

        mouse_pos = pygame.mouse.get_pos()
        
        # Проверяем, наведена ли мышь на кнопки (обновляем модель)
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

        # Звук при наведении на кнопку
        if self.model.hovered_button != self._prev_hover and self.model.hovered_button is not None:
            blip = self.blip_sound
            if blip:
                blip.play()
        self._prev_hover = self.model.hovered_button

        # Обработка кликов
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.model.hovered_button == "new_game":
                    pygame.mixer.music.stop()
                    print("Старт игры! Переключаемся на офис...")
                    return "START_GAME"
                elif self.model.hovered_button == "continue":
                    pygame.mixer.music.stop()
                    return "START_CONTINUE"
                elif self.model.hovered_button == "settings":
                    return "SETTINGS"
                elif self.model.hovered_button == "exit":
                    pygame.quit()
                    sys.exit()
                    
        return "MENU"

    def handle_settings_events(self, is_fullscreen: bool):
        mouse_pos = pygame.mouse.get_pos()
        hovered = None

        if self.view.btn_fullscreen_rect.collidepoint(mouse_pos):
            hovered = "fullscreen"
        elif self.view.btn_back_rect.collidepoint(mouse_pos):
            hovered = "back"

        if hovered != self._prev_hover and hovered is not None:
            blip = self.blip_sound
            if blip:
                blip.play()
        self._prev_hover = hovered

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return "BACK", is_fullscreen, hovered
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if hovered == "fullscreen":
                    return "TOGGLE_FS", is_fullscreen, hovered
                elif hovered == "back":
                    return "BACK", is_fullscreen, hovered

        return None, is_fullscreen, hovered