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

        font_size_title = int(65 * self.scale_y)
        font_size_btn = int(30 * self.scale_y)
        try:
            self.title_font = pygame.font.Font("assets/fonts/OCR-A.ttf", font_size_title)
            self.button_font = pygame.font.Font("assets/fonts/OCR-A.ttf", font_size_btn)
        except IOError:
            print("Шрифт OCR-A.ttf не найден! Использую Arial.")
            self.title_font = pygame.font.SysFont("Arial", font_size_title, bold=True)
            self.button_font = pygame.font.SysFont("Arial", font_size_btn)

        btn_x = int(100 * self.scale_x)

        surf_ng = self.button_font.render(">> New Game", True, (255, 255, 255))
        surf_ex = self.button_font.render(">> Exit", True, (255, 255, 255))

        self.btn_new_game_rect = pygame.Rect(btn_x, int(360 * self.scale_y),
                                             surf_ng.get_width(), surf_ng.get_height())
        self.btn_exit_rect = pygame.Rect(btn_x, int(460 * self.scale_y),
                                         surf_ex.get_width(), surf_ex.get_height())

        self.bg_images = {}
        self._load_assets()
        self.noise_frames = self._generate_static_noise()

    def _load_assets(self):
        size = (self.w, self.h)

        def load_and_scale(path):
            img = pygame.image.load(path).convert()
            return pygame.transform.smoothscale(img, size)

        try:
            normal = load_and_scale("assets/menu/algem_normal.png")
        except pygame.error:
            print("Ошибка: algem_normal.png")
            normal = pygame.Surface(size)
            normal.fill((10, 10, 15))

        glitch_paths = [
            "assets/menu/algem_is_trying_to_escape.jpg",
            "assets/menu/algem_is_watching_you.jpg",
            "assets/menu/empty_room.jpeg",
            "assets/menu/algem_normal.png",
        ]
        glitch_raw = []
        for path in glitch_paths:
            try:
                glitch_raw.append(load_and_scale(path))
            except pygame.error:
                print(f"Ошибка: {path}")
        if not glitch_raw:
            glitch_raw.append(normal)

        # Нормализация яркости всех изображений
        all_images = [normal] + glitch_raw
        target_brightness = 15
        
        for img in all_images:
            w, h = img.get_size()
            total = 0
            for y in range(0, h, 4):
                for x in range(0, w, 4):
                    r, g, b, _ = img.get_at((x, y))
                    total += int(0.299 * r + 0.587 * g + 0.114 * b)
            count = (w // 4) * (h // 4)
            avg = total / count if count > 0 else target_brightness
            
            if avg > 0:
                factor = target_brightness / avg
                for y in range(h):
                    for x in range(w):
                        r, g, b, a = img.get_at((x, y))
                        new_r = min(255, int(r * factor))
                        new_g = min(255, int(g * factor))
                        new_b = min(255, int(b * factor))
                        img.set_at((x, y), (new_r, new_g, new_b, a))

        self.bg_images["NORMAL"] = normal
        self.glitch_images = glitch_raw

    def _generate_static_noise(self):
        frames = []
        density = int(8000 * self.scale_x * self.scale_y)
        for _ in range(3):
            noise_surface = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            for _ in range(density):
                x = random.randint(0, self.w - 1)
                y = random.randint(0, self.h - 1)
                gray = random.randint(50, 180)
                alpha = random.randint(30, 80)
                noise_surface.set_at((x, y), (gray, gray, gray, alpha))
            frames.append(noise_surface)
        
        # Сканирующие линии (как на старом ТВ)
        self.scanlines = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        for y in range(0, self.h, 3):
            self.scanlines.fill((0, 0, 0, 40), (0, y, self.w, 1))
        
        # Виньетка (тёмные углы)
        self.vignette = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        for i in range(self.h):
            alpha = int(150 * (i / self.h))
            self.vignette.fill((0, 0, 0, alpha), (0, i, self.w, 1))
            self.vignette.fill((0, 0, 0, alpha), (0, self.h - i - 1, self.w, 1))
        
        return frames

    def draw_menu(self, model):
        sx, sy = self.scale_x, self.scale_y

        if model.algem_state == "NORMAL":
            self.screen.blit(self.bg_images["NORMAL"], (0, 0))
        else:
            shake_x = random.randint(int(-12 * sx), int(12 * sx))
            shake_y = random.randint(int(-5 * sy), int(5 * sy))
            self.screen.blit(self.glitch_images[model.glitch_frame_idx], (shake_x, shake_y))

        # ТВ-шум
        self.screen.blit(self.noise_frames[model.noise_frame], (0, 0))
        
        # Сканирующие линии (постоянно)
        self.screen.blit(self.scanlines, (0, 0))
        
        # Горизонтальные помехи (часто)
        for _ in range(random.randint(2, 5)):
            y = random.randint(0, self.h - 1)
            h_bar = random.randint(1, 4)
            bar = pygame.Surface((self.w, h_bar), pygame.SRCALPHA)
            bar.fill((255, 255, 255, random.randint(20, 60)))
            self.screen.blit(bar, (0, y))
        
        # Виньетка
        self.screen.blit(self.vignette, (0, 0))

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

        surf_cont = self.button_font.render("   Continue", True, (80, 80, 80))
        self.screen.blit(surf_cont, (btn_x, int(410 * sy)))

        color_exit = (255, 255, 255) if model.hovered_button != "exit" else (140, 140, 140)
        text_exit = ">> Exit" if model.hovered_button == "exit" else "   Exit"
        surf_exit = self.button_font.render(text_exit, True, color_exit)
        self.screen.blit(surf_exit, (btn_x, int(460 * sy)))

        pygame.display.flip()