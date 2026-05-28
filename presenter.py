import sys
import pygame

class MenuPresenter:
    def __init__(self, model, view):
        self.model = model
        self.view = view
        self._prev_hover = None
        try:
            self.blip_sound = pygame.mixer.Sound("sounds/blip3.mp3")
        except pygame.error:
            print("sounds/blip3.mp3 не найден")
            self.blip_sound = None
        self._start_music()

    @staticmethod
    def _start_music():
        try:
            pygame.mixer.music.load("sounds/Faulty Ventilation.mp3")
            pygame.mixer.music.play(-1)
        except pygame.error:
            print("sounds/Faulty Ventilation.mp3 не найден")

    def handle_events(self):
        if not pygame.mixer.music.get_busy():
            self._start_music()

        mouse_pos = pygame.mouse.get_pos()
        
        # Проверяем, наведена ли мышь на кнопки (обновляем модель)
        if self.view.btn_new_game_rect.collidepoint(mouse_pos):
            self.model.hovered_button = "new_game"
        elif self.view.btn_exit_rect.collidepoint(mouse_pos):
            self.model.hovered_button = "exit"
        else:
            self.model.hovered_button = None

        # Звук при наведении на кнопку
        if self.model.hovered_button != self._prev_hover and self.model.hovered_button is not None:
            if self.blip_sound:
                self.blip_sound.play()
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
                elif self.model.hovered_button == "exit":
                    pygame.quit()
                    sys.exit()
                    
        return "MENU"