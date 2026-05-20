import pygame
import random

class MenuView:
    def __init__(self, screen):
        self.screen = screen
        
        info = pygame.display.Info()
        self.w = info.current_w
        self.h = info.current_h

        self.scale_x = self.w / 1024
        self.scale_y = self.h / 768

        # Загрузка идентичного FNAF-шрифта OCR-A
        font_size_title = int(65 * self.scale_y)
        font_size_btn = int(28 * self.scale_y)
        try:
            self.title_font = pygame.font.Font("OCR-A.ttf", font_size_title)
            self.button_font = pygame.font.Font("OCR-A.ttf", font_size_btn)
        except IOError:
            print("Шрифт OCR-A.ttf не найден в корне! Включаю системный Arial.")
            self.title_font = pygame.font.SysFont("Arial", font_size_title, bold=True)
            self.button_font = pygame.font.SysFont("Arial", font_size_btn)

        # Хитбоксы для кнопок меню (левый нижний угол)
        self.btn_new_game_rect = pygame.Rect(
            int(80 * self.scale_x), int(480 * self.scale_y),
            int(250 * self.scale_x), int(40 * self.scale_y)
        )
        self.btn_exit_rect = pygame.Rect(
            int(80 * self.scale_x), int(550 * self.scale_y),
            int(150 * self.scale_x), int(40 * self.scale_y)
        )

        # Словарь для хранения двух состояний Алгема
        self.bg_images = {}
        self._load_assets()
        
        # Текстуры телевизионных помех
        self.noise_frames = self._generate_static_noise()

    def _load_assets(self):
        """Загрузка твоих кастомных картинок Алгема"""
        size = (self.w, self.h)
        try:
            img_normal = pygame.image.load("assets/menu/algem_normal.png").convert()
            self.bg_images["NORMAL"] = pygame.transform.smoothscale(img_normal, size)
        except pygame.error:
            print("Ошибка: assets/menu/algem_normal.png не найден!")
            self.bg_images["NORMAL"] = pygame.Surface(size)
            self.bg_images["NORMAL"].fill((10, 10, 15))

        try:
            img_glitch = pygame.image.load("assets/menu/algem_glitch.png").convert()
            self.bg_images["GLITCH"] = pygame.transform.smoothscale(img_glitch, size)
        except pygame.error:
            print("Ошибка: assets/menu/algem_glitch.png не найден! Использую базовую подложку.")
            self.bg_images["GLITCH"] = self.bg_images["NORMAL"]

    def _generate_static_noise(self):
        """Процедурный ТВ-шум для атмосферы старого монитора"""
        frames = []
        density = int(4500 * self.scale_x * self.scale_y)
        for _ in range(3):
            noise_surface = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            for _ in range(density):
                x = random.randint(0, self.w - 1)
                y = random.randint(0, self.h - 1)
                gray = random.randint(100, 200)
                alpha = random.randint(20, 55)
                noise_surface.set_at((x, y), (gray, gray, gray, alpha))
            frames.append(noise_surface)
        return frames

    def draw_menu(self, model):
        sx, sy = self.scale_x, self.scale_y

        # 1. Отрисовка фона с эффектом 25-го кадра (стробоскоп)
        if model.algem_state == "NORMAL":
            self.screen.blit(self.bg_images["NORMAL"], (0, 0))
        else:
            if model.glitch_timer % 2 == 0:
                shake_x = random.randint(int(-15 * sx), int(15 * sx))
                shake_y = random.randint(int(-6 * sy), int(6 * sy))
                self.screen.blit(self.bg_images["GLITCH"], (shake_x, shake_y))
            else:
                self.screen.blit(self.bg_images["NORMAL"], (0, 0))

        # 2. Накладываем слой анимированного ТВ-шума поверх картинки
        self.screen.blit(self.noise_frames[model.noise_frame], (0, 0))
        
        # Горизонтальные полосы искажения
        if model.algem_state == "GLITCH" or random.random() < 0.1:
            for _ in range(random.randint(1, 2)):
                h_y = random.randint(0, self.h - 1)
                h_h = random.randint(int(4 * sy), int(15 * sy))
                line_surf = pygame.Surface((self.w, h_h), pygame.SRCALPHA)
                line_surf.fill((255, 255, 255, 35))
                self.screen.blit(line_surf, (0, h_y))

        # 3. Название игры аутентичным шрифтом
        title_top = self.title_font.render("FIVE NIGHTS", True, (255, 255, 255))
        title_bot = self.title_font.render("AT RTF", True, (255, 255, 255))
        self.screen.blit(title_top, (int(80 * sx), int(120 * sy)))
        self.screen.blit(title_bot, (int(80 * sx), int(200 * sy)))
        
        # 4. Кнопка "New Game"
        color_new = (255, 255, 255) if model.hovered_button != "new_game" else (140, 140, 140)
        text_new = ">> New Game" if model.hovered_button == "new_game" else "   New Game"
        surf_new = self.button_font.render(text_new, True, color_new)
        self.screen.blit(surf_new, (self.btn_new_game_rect.x, self.btn_new_game_rect.y))
        
        # 5. Кнопка "Exit"
        color_exit = (255, 255, 255) if model.hovered_button != "exit" else (140, 140, 140)
        text_exit = ">> Exit" if model.hovered_button == "exit" else "   Exit"
        surf_exit = self.button_font.render(text_exit, True, color_exit)
        self.screen.blit(surf_exit, (self.btn_exit_rect.x, self.btn_exit_rect.y))
        
        pygame.display.flip()