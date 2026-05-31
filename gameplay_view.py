import pygame
import random
import os

def _normalize_brightness(surfaces_with_paths, target=15):
    """
    Нормализует яркость изображений. Если в assets/.cache/norm/ есть
    кешированная версия — загружает её вместо пересчёта.
    Принимает список кортежей (surface, source_filepath).
    """
    cache_dir = "assets/.cache/norm"
    for img, src_path in surfaces_with_paths:
        if src_path:
            cache_path = f"{cache_dir}/{os.path.basename(src_path)}"
            if os.path.exists(cache_path):
                cached = pygame.image.load(cache_path).convert()
                img.blit(cached, (0, 0))
                continue
        w, h = img.get_size()
        total = 0
        count = 0
        for y in range(0, h, 4):
            for x in range(0, w, 4):
                r, g, b, _ = img.get_at((x, y))
                total += int(0.299 * r + 0.587 * g + 0.114 * b)
                count += 1
        avg = total / count if count else target
        if avg > 0:
            factor = target / avg
            for y in range(h):
                for x in range(w):
                    r, g, b, a = img.get_at((x, y))
                    img.set_at((x, y), (
                        min(255, int(r * factor)),
                        min(255, int(g * factor)),
                        min(255, int(b * factor)),
                        a
                    ))
        if src_path:
            os.makedirs(cache_dir, exist_ok=True)
            pygame.image.save(img, cache_path)

class GameView:
    def __init__(self, screen):
        self.screen = screen
        screen_w, screen_h = screen.get_size()

        raw_off = pygame.image.load("assets/office/server_is_off.png").convert()
        scale = screen_h / raw_off.get_height()
        target_size = (int(raw_off.get_width() * scale), screen_h)

        self.bg_off = pygame.transform.smoothscale(raw_off, target_size)

        self.bg_blinks = {}
        for name, key in [("server_turning_on_red.png", "red"), ("server_turning_on_green.png", "green")]:
            raw = pygame.image.load(f"assets/office/{name}").convert()
            self.bg_blinks[key] = pygame.transform.smoothscale(raw, target_size)

        self.bg_frames = []
        for name in ["office1.png", "office2.png"]:
            raw = pygame.image.load(f"assets/office/{name}").convert()
            self.bg_frames.append(pygame.transform.smoothscale(raw, target_size))
        norm_list = [
            (self.bg_off, "assets/office/server_is_off.png"),
        ]
        for key, name in [("red", "server_turning_on_red.png"), ("green", "server_turning_on_green.png")]:
            norm_list.append((self.bg_blinks[key], f"assets/office/{name}"))
        for i, name in enumerate(["office1.png", "office2.png"]):
            norm_list.append((self.bg_frames[i], f"assets/office/{name}"))
        _normalize_brightness(norm_list)

        self.max_offset = max(0, target_size[0] - screen_w)
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._brightness_overlay = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        self._brightness_overlay.fill((255, 255, 255, 13))
        self.font = pygame.font.Font("assets/fonts/OCR-A.ttf", 30)
        self._ui_font = pygame.font.SysFont("tahoma", 16)
        self._ui_font_bold = pygame.font.SysFont("tahoma", 16, bold=True)
        self._ui_font_sm = pygame.font.SysFont("tahoma", 13)
        self._ui_font_title = pygame.font.SysFont("tahoma", 14, bold=True)
        self.scale = scale
        self.server_hotspot = pygame.Rect(1151, 163, 131, 244)
        self.laptop_hotspot = pygame.Rect(380, 400, 280, 220)
        self.switch_timer = random.randint(60, 180)
        self.current_idx = 0

        # Кнопка TAB в офисе (изображение на столе)
        raw_tab = pygame.image.load("assets/cctv/tabbutton.png").convert_alpha()
        self.tabbutton_surf = pygame.transform.scale(raw_tab, (int(600 * scale), int(60 * scale)))
        self.tab_button_rect = pygame.Rect(662, 758, 600, 60)  # оригинальные координаты (1923×818)
        self.tab_button_hovered = False

        raw_wallpaper = pygame.image.load("assets/laptop/wallpaper.png").convert()
        self.laptop_wallpaper = pygame.transform.smoothscale(raw_wallpaper, (screen_w, screen_h - 40))

        self._ad_images = {}
        for key in ["ad_hhru", "ad_kontur", "ad_sber"]:
            raw = pygame.image.load(f"assets/laptop/{key}.png").convert()
            rw, rh = raw.get_size()
            scale = min((screen_w - 40) / rw, (screen_h - 80) / rh)
            self._ad_images[key] = pygame.transform.smoothscale(raw, (int(rw * scale), int(rh * scale)))

        # Область экрана планшета — отступаем от краёв, чтобы не задеть рамку
        self.screen_rect = pygame.Rect(0, 0, screen_w, screen_h)

        # Иконки камер из assets/cctv/ — загружаются, маппинг по номеру камеры
        self._cam_icons = {}
        icon_map = {1: "cam1.png", 2: "cam2.png", 3: "cam3.png", 4: "cam4.png", 5: "cam5.png", 6: "cam6.png", 7: "cam7.png"}
        for idx, fname in icon_map.items():
            img = pygame.image.load(f"assets/cctv/{fname}").convert_alpha()
            self._cam_icons[idx] = pygame.transform.scale(img, (30, 25))

        # Мини-карта (справа в планшете, uniform scale)
        raw_map = pygame.image.load("assets/cameras/camera_map.png").convert_alpha()
        mm_map_w, mm_map_h = raw_map.get_size()  # 595×550
        self._mm_scale = 500 / mm_map_w  # uniform scale ≈ 0.84
        mm_w, mm_h = 500, int(mm_map_h * self._mm_scale)
        self._minimap_bg = pygame.transform.smoothscale(raw_map, (mm_w, mm_h))
        self._minimap_bg.set_alpha(150)
        self._minimap_pos = (self.screen_rect.right - mm_w - 5, self.screen_rect.bottom - mm_h - 5)
        self._minimap_size = (mm_w, mm_h)

        self._cam_blink_start = 0
        self._prev_camera_idx = 1

        # Координаты центров иконок в пространстве мини-карты (500×462)
        # Кроме коворкинга — у него координата левого верхнего угла
        self._minimap_icon_positions = {
            1: (447, 303),  # ALGEM'S ROOM
            2: (207, 334),  # MAIN HALL — самый низ
            3: (270, 279),  # TOILETS
            4: (88,  213),  # WEST HALL
            5: (331, 120),  # CANTEEN — чуть правее и ниже в углу
            6: (32,  116),  # COWORKING
            7: (148,  65),  # SERVICE ROOM — самый верх
        }

        # Камеры — каждая грузится, масштабируется под высоту screen_rect, затемняется и тонируется
        from gameplay_model import CAMERAS, CAMERA_COUNT
        self.camera_surfaces = {}
        self.camera_max_offsets = {}
        cam_h = self.screen_rect.h
        for idx, _display_id, name, fname in CAMERAS:
            raw = pygame.image.load(f"assets/cameras/{fname}").convert()
            scale = cam_h / raw.get_height()
            cw = int(raw.get_width() * scale)
            surf = pygame.transform.smoothscale(raw, (cw, cam_h))
            dark = pygame.Surface((cw, cam_h))
            dark.fill((170, 170, 170))
            surf.blit(dark, (0, 0), special_flags=pygame.BLEND_MULT)
            purple = pygame.Surface((cw, cam_h), pygame.SRCALPHA)
            purple.fill((40, 15, 60, 55))
            surf.blit(purple, (0, 0))
            self.camera_surfaces[idx] = surf
            self.camera_max_offsets[idx] = max(0, cw - self.screen_rect.w)

        # Альтернативные фоны для камер
        self._algem_room_surf = None

        def _load_cam(path):
            try:
                raw = pygame.image.load(path).convert()
                s = cam_h / raw.get_height()
                cw = int(raw.get_width() * s)
                surf = pygame.transform.smoothscale(raw, (cw, cam_h))
                dark = pygame.Surface((cw, cam_h))
                dark.fill((170, 170, 170))
                surf.blit(dark, (0, 0), special_flags=pygame.BLEND_MULT)
                purple = pygame.Surface((cw, cam_h), pygame.SRCALPHA)
                purple.fill((40, 15, 60, 55))
                surf.blit(purple, (0, 0))
                return surf
            except pygame.error:
                return None

        # Алгем-спрайты для каждой камеры
        self._algem_surfaces: dict[int, pygame.Surface] = {}
        self._algem_main_hall_surf = _load_cam("assets/cameras/main_hall_with_algem.png")
        self._algem_mainhall_watching = _load_cam("assets/cameras/algem_mainhall_is_watching_you.png")
        algem_files = {
            1: "algems' room_with_algem.png",
            3: "toilets_algem.png",
            4: "westhall_algem.png",
            5: "canteen_algem.png",
            6: "coworking_algem.png",
            7: "service_room_algem.png",
        }
        for cam_idx, fname in algem_files.items():
            s = _load_cam(f"assets/cameras/{fname}")
            if s:
                self._algem_surfaces[cam_idx] = s

        # CRT curvature mask + deep vignette (кешируется в PNG)
        self.crt_mask = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        crt_path = "assets/crt_mask.png"
        if os.path.exists(crt_path):
            self.crt_mask = pygame.image.load(crt_path).convert_alpha()
        else:
            cx, cy = screen_w / 2, screen_h / 2
            max_dist = ((cx) ** 2 + (cy) ** 2) ** 0.5
            for y in range(screen_h):
                for x in range(screen_w):
                    dx, dy = x - cx, y - cy
                    r = ((dx * dx + dy * dy) ** 0.5) / max_dist
                    a = int(min(255, r * r * 230))
                    self.crt_mask.set_at((x, y), (0, 0, 0, a))
            pygame.image.save(self.crt_mask, crt_path)

        # Шум/помехи камер (noice*.jpg, noice*.png)
        self._noise_frames = []
        for fname in sorted(os.listdir("assets/cctv")):
            if fname.lower().startswith("noice") and (fname.lower().endswith(".png") or fname.lower().endswith(".jpg")):
                img = pygame.image.load(f"assets/cctv/{fname}").convert()
                s = pygame.transform.smoothscale(img, (screen_w, screen_h))
                s.set_alpha(45)
                self._noise_frames.append(s)
        self._noise_idx = 0
        self._noise_timer = 0

        # Те же помехи на полную непрозрачность для глитча при уходе Алгема
        self._glitch_frames = []
        for s in self._noise_frames:
            copy = s.copy()
            copy.set_alpha(255)
            self._glitch_frames.append(copy)

        # Планшет — 10 отдельных картинок без фона
        self.cam_frames = []
        for i in range(1, 11):
            img = pygame.image.load(f"assets/office/tablet/tablet-{i}.png").convert_alpha()
            self.cam_frames.append(pygame.transform.smoothscale(img, (screen_w, screen_h)))

        # Кнопка Mute Call (на столе офиса)
        raw_mute = pygame.image.load("assets/office/mutecall.png").convert_alpha()
        mute_scale = 140 / raw_mute.get_width()
        self.mutecall_surf = pygame.transform.scale(raw_mute, (140, int(raw_mute.get_height() * mute_scale)))
        self._mutecall_rect = pygame.Rect(0, 0, *self.mutecall_surf.get_size())

        # Кнопки BAIT и MAP — одинаковый размер
        self._btn_size = (64, 34)
        raw_bait = pygame.image.load("assets/cameras/playaudio.png").convert_alpha()
        raw_map = pygame.image.load("assets/cameras/maptoggle.png").convert_alpha()
        self._bait_btn_img = pygame.transform.scale(raw_bait, self._btn_size)
        self._map_btn_img = pygame.transform.scale(raw_map, self._btn_size)
        self._btn_bg = pygame.Surface(self._btn_size, pygame.SRCALPHA)
        self._btn_bg.fill((15, 15, 25, 200))
        self._bait_btn_rect = pygame.Rect(0, 0, *self._btn_size)
        self._map_btn_rect = pygame.Rect(0, 0, *self._btn_size)

        # Аудио-иконки для мини-карты (audio1-4.png)
        self._audio_icons = []
        for i in range(1, 5):
            img = pygame.image.load(f"assets/cameras/audio{i}.png").convert_alpha()
            self._audio_icons.append(pygame.transform.scale(img, (60, 50)))

    def is_server_clicked(self, mouse_pos, offset):
        img_x = (mouse_pos[0] + offset) / self.scale
        img_y = mouse_pos[1] / self.scale
        return self.server_hotspot.collidepoint(img_x, img_y)

    def is_laptop_clicked(self, mouse_pos, offset):
        img_x = (mouse_pos[0] + offset) / self.scale
        img_y = mouse_pos[1] / self.scale
        return self.laptop_hotspot.collidepoint(img_x, img_y)

    def is_tabbutton_clicked(self, mouse_pos):
        if mouse_pos is None:
            return False
        tx = self.screen_rect.centerx - self.tabbutton_surf.get_width() // 2
        ty = self.screen_rect.bottom - self.tabbutton_surf.get_height() - 5
        rect = pygame.Rect(tx, ty, *self.tabbutton_surf.get_size())
        return rect.collidepoint(mouse_pos)

    def is_mutecall_clicked(self, mouse_pos):
        if mouse_pos is None:
            return False
        return self._mutecall_rect.collidepoint(mouse_pos)

    def is_bait_clicked(self, mouse_pos):
        if mouse_pos is None:
            return False
        return self._bait_btn_rect.collidepoint(mouse_pos)

    def is_map_clicked(self, mouse_pos):
        if mouse_pos is None:
            return False
        return self._map_btn_rect.collidepoint(mouse_pos)

    def get_vent_reset_clicked(self, mouse_pos):
        return None

    def is_laptop_icon_clicked(self, mouse_pos):
        if not hasattr(self, '_laptop_icons'):
            return None
        for rect, key in self._laptop_icons:
            if rect.collidepoint(mouse_pos):
                return key
        return None

    def is_laptop_start_clicked(self, mouse_pos):
        return hasattr(self, '_laptop_start_rect') and self._laptop_start_rect.collidepoint(mouse_pos)

    def is_laptop_menu_item_clicked(self, mouse_pos):
        if not hasattr(self, '_laptop_menu_items'):
            return None
        for rect, key in self._laptop_menu_items:
            if rect.collidepoint(mouse_pos):
                return key
        return None

    def is_laptop_close_clicked(self, mouse_pos):
        return hasattr(self, '_laptop_close_btn') and self._laptop_close_btn.collidepoint(mouse_pos)

    def is_laptop_server_btn_clicked(self, mouse_pos):
        return hasattr(self, '_laptop_server_btn') and self._laptop_server_btn.collidepoint(mouse_pos)

    def is_laptop_reboot_btn_clicked(self, mouse_pos):
        return hasattr(self, '_laptop_reboot_btn') and self._laptop_reboot_btn.collidepoint(mouse_pos)

    def _draw_hack_bar(self, model) -> None:
        bar_w, bar_h = 300, 20
        x = (self.screen_w - bar_w) // 2
        y = self.screen_h - 80
        fill_w = int(bar_w * model.hack_progress)

        pygame.draw.rect(self.screen, (30, 30, 40), (x, y, bar_w, bar_h))
        if fill_w > 0:
            color = (40, 200, 40) if model.hack_active else (40, 140, 40)
            pygame.draw.rect(self.screen, color, (x, y, fill_w, bar_h))
        pygame.draw.rect(self.screen, (180, 180, 200), (x, y, bar_w, bar_h), 2)

        label = self.font.render("HACK", True, (200, 200, 200))
        self.screen.blit(label, (x - label.get_width() - 10, y + bar_h // 2 - label.get_height() // 2))

        pct = self.font.render(f"{int(model.hack_progress * 100)}%", True, (200, 200, 200))
        self.screen.blit(pct, (x + bar_w + 10, y + bar_h // 2 - pct.get_height() // 2))

    # ── Ноутбук ──────────────────────────────────────────────────────

    def _draw_xp_icon(self, ix: int, iy: int, key: str, hovered: bool) -> None:
        """Нарисовать одну иконку рабочего стола в стиле XP."""
        icon_s = 48
        pad = 2

        # Фон иконки
        if hovered:
            sel = pygame.Surface((icon_s + pad * 2, icon_s + pad * 2), pygame.SRCALPHA)
            sel.fill((80, 120, 200, 80))
            self.screen.blit(sel, (ix - pad, iy - pad))

        if key == "mycomputer":
            # Монитор
            pygame.draw.rect(self.screen, (180, 180, 180), (ix + 4, iy + 2, 40, 30), border_radius=3)
            pygame.draw.rect(self.screen, (50, 50, 50), (ix + 4, iy + 2, 40, 30), 2, border_radius=3)
            # Экран
            pygame.draw.rect(self.screen, (40, 80, 160), (ix + 8, iy + 6, 32, 20))
            pygame.draw.rect(self.screen, (30, 30, 30), (ix + 8, iy + 6, 32, 20), 1)
            # Подставка
            pygame.draw.rect(self.screen, (140, 140, 140), (ix + 18, iy + 32, 12, 4))
            pygame.draw.rect(self.screen, (120, 120, 120), (ix + 12, iy + 36, 24, 3), border_radius=2)

        elif key == "claude":
            # Скрин-иконка — череп / хакер
            cx, cy = ix + icon_s // 2, iy + 16
            pygame.draw.circle(self.screen, (60, 20, 80), (cx, cy), 16)
            pygame.draw.circle(self.screen, (100, 40, 140), (cx, cy), 16, 2)
            # Глаза
            pygame.draw.circle(self.screen, (200, 50, 50), (cx - 6, cy - 3), 4)
            pygame.draw.circle(self.screen, (200, 50, 50), (cx + 6, cy - 3), 4)
            pygame.draw.circle(self.screen, (255, 200, 200), (cx - 5, cy - 4), 1)
            pygame.draw.circle(self.screen, (255, 200, 200), (cx + 7, cy - 4), 1)
            # Нижняя часть
            pygame.draw.rect(self.screen, (60, 20, 80), (cx - 10, cy + 12, 20, 6), border_radius=2)

        elif key == "recycle":
            # Корзина
            bx, by = ix + 12, iy + 10
            pygame.draw.rect(self.screen, (180, 180, 180), (bx, by + 6, 24, 26), border_radius=2)
            pygame.draw.rect(self.screen, (140, 140, 140), (bx, by + 6, 24, 26), 2, border_radius=2)
            # Ручка
            pygame.draw.rect(self.screen, (160, 160, 160), (bx + 6, by, 12, 8), border_radius=2)
            pygame.draw.rect(self.screen, (120, 120, 120), (bx + 6, by, 12, 8), 1, border_radius=2)
            # Полоски
            for lx in (bx + 6, bx + 12, bx + 18):
                pygame.draw.line(self.screen, (120, 120, 120), (lx, by + 10), (lx, by + 30))

        # Подпись под иконкой
        label_lines = {"mycomputer": "My Computer", "claude": ["Claude", "Mythos"], "recycle": "Recycle Bin"}
        lines = label_lines.get(key, [key])
        if isinstance(lines, str):
            lines = [lines]
        for j, line in enumerate(lines):
            rendered = self._ui_font_sm.render(line, True, (0, 0, 0))
            self.screen.blit(rendered, (ix + 1 + icon_s // 2 - rendered.get_width() // 2 + 1, iy + icon_s + 4 + j * 16 + 1))
            rendered = self._ui_font_sm.render(line, True, (255, 255, 255))
            self.screen.blit(rendered, (ix + icon_s // 2 - rendered.get_width() // 2, iy + icon_s + 4 + j * 16))

    def _draw_laptop_screen(self, model) -> None:
        sw, sh = self.screen_w, self.screen_h
        mx, my = model.laptop_cursor

        # ── Фон — обои ─────────────────────────────────────────────
        self.screen.blit(self.laptop_wallpaper, (0, 0))

        # ── Taskbar ──────────────────────────────────────────────────
        tb_h = 40
        tb_top = sh - tb_h

        for y in range(tb_top, sh):
            t = (y - tb_top) / tb_h
            r = int(20 + t * 20)
            g = int(60 + t * 40)
            b = int(180 + t * 40)
            pygame.draw.line(self.screen, (r, g, b), (0, y), (sw, y))

        pygame.draw.line(self.screen, (100, 160, 255), (0, tb_top), (sw, tb_top))

        # Кнопка Start — зелёный градиент как в XP
        start_rect = pygame.Rect(2, tb_top + 2, 86, tb_h - 4)
        for y in range(start_rect.y, start_rect.bottom):
            t = (y - start_rect.y) / start_rect.h
            r = int(40 + t * 30)
            g = int(160 - t * 20)
            b = int(40 + t * 20)
            pygame.draw.line(self.screen, (r, g, b), (start_rect.x, y), (start_rect.right, y))
        pygame.draw.rect(self.screen, (20, 100, 20), start_rect, 1, border_radius=4)

        # Текст Start
        start_label = self._ui_font_bold.render("start", True, (255, 255, 255))
        self.screen.blit(start_label, (start_rect.x + 12, start_rect.y + 11))
        self._laptop_start_rect = start_rect

        # Сепаратор после Start
        pygame.draw.line(self.screen, (60, 100, 180), (start_rect.right + 4, tb_top + 6),
                         (start_rect.right + 4, sh - 6))

        # Системный трей
        tray_rect = pygame.Rect(sw - 120, tb_top, 120, tb_h)
        pygame.draw.rect(self.screen, (30, 80, 160), tray_rect)
        pygame.draw.line(self.screen, (80, 130, 210), (tray_rect.x, tb_top), (tray_rect.x, sh))

        # Часы — игровое время
        display_h = 12 if model.hour == 0 else model.hour
        display_m = model.timer // 60
        clock_str = f"{display_h}:{display_m:02d}"
        clock_label = self._ui_font_bold.render(clock_str, True, (255, 255, 255))
        self.screen.blit(clock_label, (sw - clock_label.get_width() - 10, sh - tb_h + 11))

        # ── Иконки на рабочем столе ──────────────────────────────────
        icon_defs = [
            ("My Computer", 30, 30, "mycomputer"),
            ("Claude Mythos", 30, 130, "claude"),
            ("Recycle Bin", 30, 240, "recycle"),
        ]
        self._laptop_icons = []
        icon_s = 48
        for label, ix, iy, key in icon_defs:
            icon_rect = pygame.Rect(ix - 2, iy - 2, icon_s + 4, icon_s + 40)
            hovered = icon_rect.collidepoint(mx, my)
            self._draw_xp_icon(ix, iy, key, hovered)
            self._laptop_icons.append((icon_rect, key))

        # ── Меню Start ───────────────────────────────────────────────
        if model.laptop_start_menu:
            menu_w, menu_h = 220, 260
            menu_x = 2
            menu_y = tb_top - menu_h

            # Фон меню — с градиентом
            menu_surf = pygame.Surface((menu_w, menu_h), pygame.SRCALPHA)
            for y in range(menu_h):
                t = y / menu_h
                r = int(30 + t * 20)
                g = int(60 + t * 30)
                b = int(180 + t * 40)
                pygame.draw.line(menu_surf, (r, g, b, 240), (0, y), (menu_w, y))
            self.screen.blit(menu_surf, (menu_x, menu_y))
            pygame.draw.rect(self.screen, (80, 140, 255), (menu_x, menu_y, menu_w, menu_h), 2)

            # Шапка — полоса с именем пользователя
            head_h = 50
            head_rect = pygame.Rect(menu_x, menu_y, menu_w, head_h)
            pygame.draw.rect(self.screen, (50, 100, 200), head_rect)
            pygame.draw.line(self.screen, (100, 160, 255), (menu_x, menu_y + head_h), (menu_x + menu_w, menu_y + head_h))

            # Аватарка
            pygame.draw.circle(self.screen, (200, 200, 200), (menu_x + 24, menu_y + 25), 16)
            pygame.draw.circle(self.screen, (100, 100, 100), (menu_x + 24, menu_y + 25), 16, 1)
            pygame.draw.circle(self.screen, (60, 60, 60), (menu_x + 24, menu_y + 22), 5)
            pygame.draw.ellipse(self.screen, (60, 60, 60), (menu_x + 14, menu_y + 28, 20, 14))
            user_label = self._ui_font_bold.render("Admin", True, (255, 255, 255))
            self.screen.blit(user_label, (menu_x + 48, menu_y + 18))

            # Сепаратор
            sep_y = menu_y + head_h
            pygame.draw.line(self.screen, (100, 160, 255), (menu_x + 4, sep_y + 4),
                             (menu_x + menu_w - 4, sep_y + 4))

            menu_items = [
                ("Claude Mythos", "claude"),
                ("My Computer", "mycomputer"),
                ("", None),
                ("Shutdown", "shutdown"),
            ]
            self._laptop_menu_items = []
            for i, (item_label, item_key) in enumerate(menu_items):
                iy = sep_y + 8 + i * 34
                item_rect = pygame.Rect(menu_x + 2, iy, menu_w - 4, 30)
                item_hovered = item_rect.collidepoint(mx, my) and item_key is not None

                if item_hovered:
                    pygame.draw.rect(self.screen, (40, 80, 200), item_rect, border_radius=3)
                elif item_key is None:
                    pygame.draw.line(self.screen, (60, 100, 180),
                                     (menu_x + 8, iy + 16), (menu_x + menu_w - 8, iy + 16))
                    self._laptop_menu_items.append((item_rect, item_key))
                    continue

                if item_label:
                    txt = self._ui_font.render(item_label, True, (255, 255, 255))
                    self.screen.blit(txt, (menu_x + 12, iy + 7))
                self._laptop_menu_items.append((item_rect, item_key))

        # ── Claude Mythos — окно ─────────────────────────────────────
        if model.laptop_app == "claude_mythos":
            win_w, win_h = 620, 440
            win_x = sw // 2 - win_w // 2
            win_y = sh // 2 - win_h // 2 - 20
            win_rect = pygame.Rect(win_x, win_y, win_w, win_h)

            # Тень
            shadow = pygame.Surface((win_w + 4, win_h + 4), pygame.SRCALPHA)
            for i in range(4, 0, -1):
                shadow.fill((0, 0, 0, 15 * i))
                self.screen.blit(shadow, (win_x + i, win_y + i))

            # Фон окна
            pygame.draw.rect(self.screen, (236, 233, 216), win_rect)

            # Title bar — XP-градиент
            title_h = 26
            title_rect = pygame.Rect(win_x, win_y, win_w, title_h)
            for y in range(title_h):
                t = y / title_h
                r = int(0 + t * 30)
                g = int(80 + t * 40)
                b = int(180 + t * 40)
                pygame.draw.line(self.screen, (r, g, b),
                                 (win_x, win_y + y), (win_x + win_w, win_y + y))
            pygame.draw.rect(self.screen, (0, 0, 100), title_rect, 1)

            title_txt = self._ui_font_bold.render("Claude Mythos v2.1 — Neural Hack Engine", True, (255, 255, 255))
            self.screen.blit(title_txt, (win_x + 8, win_y + 5))

            # Кнопки управления — XP стиль
            btn_y = win_y + 3
            btn_w, btn_h = 21, 19

            # Свернуть
            min_btn = pygame.Rect(win_x + win_w - 68, btn_y, btn_w, btn_h)
            pygame.draw.rect(self.screen, (40, 100, 180), min_btn, border_radius=2)
            pygame.draw.rect(self.screen, (20, 60, 140), min_btn, 1, border_radius=2)
            pygame.draw.line(self.screen, (255, 255, 255),
                             (min_btn.x + 4, min_btn.y + 14), (min_btn.x + 16, min_btn.y + 14), 2)

            # Развернуть
            max_btn = pygame.Rect(win_x + win_w - 45, btn_y, btn_w, btn_h)
            pygame.draw.rect(self.screen, (40, 100, 180), max_btn, border_radius=2)
            pygame.draw.rect(self.screen, (20, 60, 140), max_btn, 1, border_radius=2)
            pygame.draw.rect(self.screen, (255, 255, 255),
                             (max_btn.x + 4, max_btn.y + 4, 13, 11), 2)

            # Закрыть
            close_btn = pygame.Rect(win_x + win_w - 22, btn_y, btn_w, btn_h)
            pygame.draw.rect(self.screen, (180, 60, 40), close_btn, border_radius=2)
            pygame.draw.rect(self.screen, (120, 30, 20), close_btn, 1, border_radius=2)
            close_x = self._ui_font_bold.render("X", True, (255, 255, 255))
            self.screen.blit(close_x, (close_btn.x + 4, close_btn.y + 2))
            self._laptop_close_btn = close_btn

            # Линия под title bar
            pygame.draw.line(self.screen, (10, 60, 140),
                             (win_x, win_y + title_h), (win_x + win_w, win_y + title_h))

            content_y = win_y + title_h + 8

            # ── Строка статуса ─────────────────────────────────────────
            is_on = model.server_state == "ON"
            is_overload = model.server_overload
            is_rebooting = model.server_rebooting

            if is_on and not is_overload:
                status_txt = "SERVER: ONLINE"
                status_clr = (40, 180, 40)
            elif is_overload:
                status_txt = "SERVER: OVERLOAD!"
                status_clr = (220, 50, 30)
            elif is_rebooting:
                dots = "." * ((pygame.time.get_ticks() // 500) % 3 + 1)
                status_txt = f"SERVER: REBOOTING{dots}"
                status_clr = (200, 160, 40)
            else:
                status_txt = "SERVER: OFFLINE"
                status_clr = (160, 40, 40)

            lbl_server = self._ui_font_bold.render(status_txt, True, status_clr)
            self.screen.blit(lbl_server, (win_x + 15, content_y))

            # ── Кнопки сервера ─────────────────────────────────────────
            btn_server_y = content_y + 22

            if model.server_state in ("OFF", "ON") and not is_overload:
                srv_label = "STOP SERVER" if is_on else "START SERVER"
                srv_clr = (180, 50, 30) if is_on else (40, 160, 40)
            else:
                srv_label = "START SERVER"
                srv_clr = (120, 120, 120)

            srv_btn = pygame.Rect(win_x + 15, btn_server_y, 130, 24)
            srv_enabled = model.server_state in ("OFF", "ON") and not is_overload
            pygame.draw.rect(self.screen, srv_clr if srv_enabled else (160, 160, 160), srv_btn, border_radius=3)
            pygame.draw.rect(self.screen, (30, 30, 30), srv_btn, 1, border_radius=3)
            srv_txt = self._ui_font_bold.render(srv_label, True, (255, 255, 255))
            self.screen.blit(srv_txt, (srv_btn.x + srv_btn.w // 2 - srv_txt.get_width() // 2,
                                       srv_btn.y + 4))
            self._laptop_server_btn = srv_btn

            # Кнопка Reboot
            rebtn = pygame.Rect(win_x + 155, btn_server_y, 100, 24)
            re_enabled = is_overload or is_rebooting
            re_clr = (200, 140, 30) if re_enabled else (160, 160, 160)
            pygame.draw.rect(self.screen, re_clr, rebtn, border_radius=3)
            pygame.draw.rect(self.screen, (30, 30, 30), rebtn, 1, border_radius=3)
            re_txt = self._ui_font_bold.render("REBOOT", True, (255, 255, 255) if re_enabled else (120, 120, 120))
            self.screen.blit(re_txt, (rebtn.x + rebtn.w // 2 - re_txt.get_width() // 2,
                                      rebtn.y + 4))
            self._laptop_reboot_btn = rebtn

            # ── Прогресс-бар ──────────────────────────────────────────
            bar_x = win_x + 15
            bar_y = btn_server_y + 32
            bar_w = win_w - 30
            bar_h = 18
            pygame.draw.rect(self.screen, (220, 220, 220), (bar_x, bar_y, bar_w, bar_h))
            pygame.draw.rect(self.screen, (160, 160, 160), (bar_x, bar_y, bar_w, bar_h), 1)
            fill = int(bar_w * model.hack_progress)
            if fill > 0:
                clr = (40, 200, 40) if model.hack_active else (40, 140, 40)
                pygame.draw.rect(self.screen, clr, (bar_x + 1, bar_y + 1, fill - 2, bar_h - 2))
            pct = self._ui_font_sm.render(f"{int(model.hack_progress * 100)}%", True, (30, 30, 30))
            self.screen.blit(pct, (bar_x + bar_w - pct.get_width() - 4, bar_y + 1))

            # ── Терминал — логи ───────────────────────────────────────
            term_x = win_x + 15
            term_y = bar_y + bar_h + 8
            term_w = win_w - 30
            term_h = win_h - (term_y - win_y) - 12

            # Фон терминала
            pygame.draw.rect(self.screen, (12, 12, 12), (term_x, term_y, term_w, term_h))
            pygame.draw.rect(self.screen, (60, 60, 60), (term_x, term_y, term_w, term_h), 1)

            # Полоска заголовка терминала
            pygame.draw.rect(self.screen, (30, 30, 30), (term_x, term_y, term_w, 18))
            term_hdr = self._ui_font_sm.render("Claude Mythos — Terminal Output", True, (120, 200, 120))
            self.screen.blit(term_hdr, (term_x + 6, term_y + 2))

            # Логи
            logs = model.hack_logs
            line_h = 14
            max_lines = (term_h - 22) // line_h
            visible = logs[-max_lines:] if len(logs) > max_lines else logs

            for i, log_line in enumerate(visible):
                clr = (180, 220, 180) if log_line.startswith("[") else (140, 180, 140)
                if "ERROR" in log_line or "OVERLOAD" in log_line:
                    clr = (220, 80, 60)
                elif "COMPLETE" in log_line or "SUCCESS" in log_line:
                    clr = (80, 220, 80)
                rendered = self._ui_font_sm.render(log_line, True, clr)
                self.screen.blit(rendered, (term_x + 6, term_y + 20 + i * line_h))

            # Мигающий курсор
            if pygame.time.get_ticks() % 1000 < 600:
                cur_y = term_y + 20 + len(visible) * line_h
                if cur_y < term_y + term_h - 4:
                    pygame.draw.rect(self.screen, (180, 220, 180),
                                     (term_x + 6, cur_y, 8, line_h - 2))

        # ── Реклама — поверх всего ──────────────────────────────────
        if model.ad_active and model.ad_image_key in self._ad_images:
            ad_img = self._ad_images[model.ad_image_key]
            ax = (sw - ad_img.get_width()) // 2
            ay = (sh - 40 - ad_img.get_height()) // 2
            self.screen.blit(ad_img, (ax, ay))

            btn_size = 28
            bx = ax + ad_img.get_width() - btn_size - 4
            by = ay + 4
            self._ad_close_rect = pygame.Rect(bx, by, btn_size, btn_size)
            pygame.draw.rect(self.screen, (60, 60, 60), self._ad_close_rect)
            pygame.draw.rect(self.screen, (200, 200, 200), self._ad_close_rect, 1)
            cross_cx, cross_cy = bx + btn_size // 2, by + btn_size // 2
            pygame.draw.line(self.screen, (255, 255, 255), (cross_cx - 6, cross_cy - 6), (cross_cx + 6, cross_cy + 6), 2)
            pygame.draw.line(self.screen, (255, 255, 255), (cross_cx + 6, cross_cy - 6), (cross_cx - 6, cross_cy + 6), 2)
        else:
            self._ad_close_rect = None

        # ── XP-курсор ────────────────────────────────────────────────
        cx, cy = mx, my
        cursor_pts = [
            (cx, cy), (cx, cy + 18), (cx + 5, cy + 14),
            (cx + 9, cy + 21), (cx + 12, cy + 19), (cx + 8, cy + 12),
            (cx + 15, cy + 10),
        ]
        # Тень
        shadow_pts = [(x + 1, y + 1) for x, y in cursor_pts]
        pygame.draw.polygon(self.screen, (40, 40, 40), shadow_pts)
        # Основной курсор
        pygame.draw.polygon(self.screen, (255, 255, 255), cursor_pts)
        pygame.draw.polygon(self.screen, (0, 0, 0), cursor_pts, 1)

    def _draw_cctv_effects(self, camera_idx, model):
        # Шум/помехи
        self._noise_timer -= 1
        if self._noise_timer <= 0:
            self._noise_idx = (self._noise_idx + 1) % len(self._noise_frames)
            self._noise_timer = random.randint(1, 3)
        self.screen.blit(self._noise_frames[self._noise_idx], (0, 0))

        # Всплеск помех только на камере, с которой ушёл или на которую пришёл Алгем
        if model.night > 1:
            on_target_cam = camera_idx in (model.algem_prev_location, model.algem_location)
            if model.algem_trigger > 0 and on_target_cam and self._glitch_frames:
                idx = (pygame.time.get_ticks() // 50) % len(self._glitch_frames)
                self.screen.blit(self._glitch_frames[idx], (0, 0))

        # CRT curvature mask
        self.screen.blit(self.crt_mask, (0, 0))

        from gameplay_model import CAMERAS
        cam_info = next(((d, n) for i, d, n, _ in CAMERAS if i == camera_idx), ("??", "???"))
        self._draw_camera_ui(*cam_info)

    def _draw_camera_ui(self, display_id, cam_name):
        # RECORD light (blinking)
        blink = (pygame.time.get_ticks() // 600) % 2 == 0
        if blink:
            pygame.draw.circle(self.screen, (255, 0, 0), (self.screen_w - 78, 28), 5)
            glow = pygame.Surface((24, 24), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 0, 0, 50), (12, 12), 12)
            self.screen.blit(glow, (self.screen_w - 90, 16), special_flags=pygame.BLEND_ADD)

        # REC text
        rec_surf = self.font.render("REC", True, (200, 30, 30))
        self.screen.blit(rec_surf, (self.screen_w - 70, 36))

        # Camera label — левый нижний угол
        label = f"CAM {display_id}  {cam_name}"
        label_surf = self.font.render(label, True, (180, 180, 190))
        self.screen.blit(label_surf, (self.screen_rect.x + 15, self.screen_rect.bottom - 35))

        # Corruption on UI text (static interference)
        if random.random() < 0.15:
            for _ in range(random.randint(1, 4)):
                cx = random.randint(self.screen_w - 90, self.screen_w - 30)
                cy = random.randint(15, 50)
                c = random.choice([(255, 255, 255), (0, 0, 0), (100, 100, 100)])
                self.screen.set_at((cx, cy), c)

    def _draw_minimap(self, model):
        mx, my = self._minimap_pos
        self.screen.blit(self._minimap_bg, (mx, my))

        if model.camera_idx != self._prev_camera_idx:
            self._cam_blink_start = pygame.time.get_ticks()
            self._prev_camera_idx = model.camera_idx

        blink_green = ((pygame.time.get_ticks() - self._cam_blink_start) // 1000) % 2 == 0

        for cidx, (cx, cy) in self._minimap_icon_positions.items():
            icon = self._cam_icons[cidx]
            ix = mx + cx - icon.get_width() // 2
            iy = my + cy - icon.get_height() // 2

            self.screen.blit(icon, (ix, iy))

            if cidx == model.camera_idx:
                color = (40, 220, 40) if blink_green else (100, 100, 100)
            else:
                color = (80, 80, 80)
            tint = pygame.Surface(icon.get_size(), pygame.SRCALPHA)
            tint.fill((*color, 140))
            self.screen.blit(tint, (ix, iy))

            if model.bait_active and cidx == model.bait_target_node and model.bait_cam_step < 3:
                audio_idx = min(model.bait_cam_step, 3)
                ax = ix + icon.get_width() // 2 - 30
                ay = iy + icon.get_height() // 2 - 25
                self.screen.blit(self._audio_icons[audio_idx], (ax, ay))

            pygame.draw.rect(self.screen, (255, 255, 255),
                             (ix - 3, iy - 3, icon.get_width() + 6, icon.get_height() + 6), 1)

    def get_minimap_hotspot(self, screen_pos):
        mx, my = self._minimap_pos
        rx, ry = screen_pos
        pad = 6
        for cidx, (cx, cy) in self._minimap_icon_positions.items():
            icon = self._cam_icons[cidx]
            iw, ih = icon.get_size()
            ix = mx + cx - iw // 2
            iy = my + cy - ih // 2
            if ix - pad <= rx <= ix + iw + pad and iy - pad <= ry <= iy + ih + pad:
                return (cidx, f"CAM {cidx:02d}")
        return None

    def draw(self, model):
        offset = int((model.current_look + 1) / 2 * self.max_offset)

        # ── Зум на ноутбук ──────────────────────────────────────────
        if model.laptop_zoom >= 0.95:
            self._draw_laptop_screen(model)
            return

        if model.laptop_zoom > 0:
            # Рисуем офис с затемнением
            if model.server_state == "OFF":
                self.screen.blit(self.bg_off, (-offset, 0))
            elif model.server_state == "TURNING_ON":
                img = self.bg_blinks.get(model.server_blink, self.bg_off)
                self.screen.blit(img, (-offset, 0))
            elif model.server_state == "TURNING_OFF":
                self.screen.blit(self.bg_off, (-offset, 0))
            elif model.server_state == "ON":
                self.screen.blit(self.bg_frames[self.current_idx], (-offset, 0))

            # Затемнение пропорционально зуму
            dark_alpha = int(model.laptop_zoom * 180)
            dark = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
            dark.fill((0, 0, 0, dark_alpha))
            self.screen.blit(dark, (0, 0))

            # Зуммированная область ноутбука
            lx = int(self.laptop_hotspot.x * self.scale) - offset
            ly = int(self.laptop_hotspot.y * self.scale)
            lw = int(self.laptop_hotspot.w * self.scale)
            lh = int(self.laptop_hotspot.h * self.scale)

            zoom = 1.0 + model.laptop_zoom * 2.0
            zw = int(lw * zoom)
            zh = int(lh * zoom)
            zx = self.screen_w // 2 - zw // 2
            zy = self.screen_h // 2 - zh // 2

            # Клипаем область ноутбука из офиса
            src_rect = pygame.Rect(
                max(0, lx), max(0, ly),
                min(lw, self.bg_off.get_width() - max(0, lx)),
                min(lh, self.bg_off.get_height() - max(0, ly))
            )
            if src_rect.w > 0 and src_rect.h > 0:
                if model.server_state == "ON":
                    src = self.bg_frames[self.current_idx].subsurface(src_rect)
                else:
                    src = self.bg_off.subsurface(src_rect)
                zoomed = pygame.transform.smoothscale(src, (zw, zh))
                self.screen.blit(zoomed, (zx, zy))
                pygame.draw.rect(self.screen, (100, 100, 100), (zx, zy, zw, zh), 2)

            pygame.display.flip()
            return

        if model.server_state == "OFF":
            self.screen.blit(self.bg_off, (-offset, 0))
        elif model.server_state == "TURNING_ON":
            img = self.bg_blinks.get(model.server_blink, self.bg_off)
            self.screen.blit(img, (-offset, 0))
        elif model.server_state == "TURNING_OFF":
            self.screen.blit(self.bg_off, (-offset, 0))
        elif model.server_state == "ON":
            self.switch_timer -= 1
            if self.switch_timer <= 0:
                self.current_idx = 1 - self.current_idx
                self.switch_timer = random.randint(60, 180)
            self.screen.blit(self.bg_frames[self.current_idx], (-offset, 0))

        if model.hack_active or model.hack_progress > 0:
            self._draw_hack_bar(model)

        if model.server_state != "OFF":
            pass  # двери нет

        if model.tablet_open or model.tablet_animating:
            if model.tablet_animating:
                self.screen.blit(self.cam_frames[model.tablet_anim_frame], (0, 0))
            else:
                # Планшет полностью открыт — рамка + контент камеры
                self.screen.blit(self.cam_frames[9], (0, 0))
                old_clip = self.screen.get_clip()
                self.screen.set_clip(self.screen_rect)

                # Прямой эфир камеры с панорамированием
                loc = model.algem_location if model.night > 1 else -1
                cam_idx = model.camera_idx

                if cam_idx == 2 and loc == 2:
                    if model.algem_main_hall_sprite == 0 and self._algem_main_hall_surf:
                        cam_surf = self._algem_main_hall_surf
                    elif model.algem_main_hall_sprite == 1 and self._algem_mainhall_watching:
                        cam_surf = self._algem_mainhall_watching
                    else:
                        cam_surf = self.camera_surfaces.get(2)
                elif loc == cam_idx:
                    cam_surf = self._algem_surfaces.get(cam_idx)
                    if cam_surf is None:
                        cam_surf = self.camera_surfaces.get(cam_idx)
                        if cam_surf is not None:
                            dark = pygame.Surface(cam_surf.get_size(), pygame.SRCALPHA)
                            dark.fill((0, 0, 0, 80))
                            cam_surf = cam_surf.copy()
                            cam_surf.blit(dark, (0, 0))
                else:
                    cam_surf = self.camera_surfaces.get(cam_idx)
                cam_max_off = self.camera_max_offsets.get(model.camera_idx, 0)
                if cam_surf is not None:
                    off = int((model.cam_look + 1) / 2 * cam_max_off)
                    self.screen.blit(cam_surf, (self.screen_rect.x - off, self.screen_rect.y))
                self._draw_cctv_effects(model.camera_idx, model)
                # Мини-карта внутри планшета
                self._draw_minimap(model)

                # Кнопки BAIT (сверху) и MAP (снизу) — слева от мини-карты
                mmx, mmy = self._minimap_pos
                bw, bh = self._btn_size
                gap = 20
                bx = mmx - bw + 4
                by = mmy + int(self._minimap_size[1] * 0.6)

                if not model.bait_active:
                    self.screen.blit(self._btn_bg, (bx, by))
                    self.screen.blit(self._bait_btn_img, (bx, by))
                    pygame.draw.rect(self.screen, (255, 255, 255), (bx, by, bw, bh), 1)
                else:
                    dot_y = by + bh // 2
                    dot_r = 3
                    dot_gap = 12
                    total_w = 5 * dot_gap
                    start_x = bx + bw // 2 - total_w // 2
                    for i in range(6):
                        if i <= model.bait_step:
                            pygame.draw.circle(self.screen, (255, 255, 255), (start_x + i * dot_gap, dot_y), dot_r)
                self._bait_btn_rect.topleft = (bx, by)
                my = by + bh + gap
                self.screen.blit(self._btn_bg, (bx, my))
                self.screen.blit(self._map_btn_img, (bx, my))
                pygame.draw.rect(self.screen, (255, 255, 255), (bx, my, bw, bh), 1)
                self._map_btn_rect.topleft = (bx, my)

                self.screen.set_clip(old_clip)

        # Кнопка TAB — на столе
        tx = self.screen_rect.centerx - self.tabbutton_surf.get_width() // 2
        ty = self.screen_rect.bottom - self.tabbutton_surf.get_height() - 5
        self.screen.blit(self.tabbutton_surf, (tx, ty))

        # Кнопка Mute Call — на столе, справа от TAB (только когда звонит)
        phone_on = model.phone_call_active
        if phone_on and not model.phone_muted:
            mx = tx + self.tabbutton_surf.get_width() + 8
            my = self.screen_rect.bottom - self.mutecall_surf.get_height() - 5
            self._mutecall_rect.topleft = (mx, my)
            self.screen.blit(self.mutecall_surf, (mx, my))

        display_hour = 12 if model.hour == 0 else model.hour
        time_str = f"{display_hour} AM"
        night_str = f"Night {model.night}"
        self.screen.blit(self.font.render(time_str, True, (255, 255, 255)), (20, 22))
        self.screen.blit(self.font.render(night_str, True, (200, 200, 200)), (20, 54))

        # ── Стартовый экран ночи ─────────────────────────────────
        if model.night_start_ticks > 0:
            overlay = pygame.Surface((self.screen_w, self.screen_h))
            overlay.fill((0, 0, 0))
            self.screen.blit(overlay, (0, 0))
            display_hour = 12 if model.hour == 0 else model.hour
            title = self.font.render(f"Night {model.night}", True, (200, 200, 200))
            sub = self.font.render(f"{display_hour} AM", True, (180, 180, 190))
            self.screen.blit(title, (self.screen_w // 2 - title.get_width() // 2, self.screen_h // 2 - 40))
            self.screen.blit(sub, (self.screen_w // 2 - sub.get_width() // 2, self.screen_h // 2 + 10))

        # ── Перегрузка / перезагрузка сервера ───────────────────
        if model.server_overload or model.server_rebooting:
            panel_w, panel_h = 360, 48
            px = (self.screen_w - panel_w) // 2
            py = 90
            panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 180))
            self.screen.blit(panel, (px, py))
            color = (255, 60, 60) if model.server_overload else (60, 255, 60)
            if model.server_overload and (pygame.time.get_ticks() // 300) % 2 == 0:
                overlay = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
                overlay.fill((255, 0, 0, 20))
                self.screen.blit(overlay, (0, 0))
            if model.server_overload:
                txt = self.font.render("OVERLOAD! OPEN LAPTOP TO REBOOT", True, color)
            else:
                dots = "." * ((pygame.time.get_ticks() // 600) % 4)
                txt = self.font.render(f"REBOOTING{dots}", True, color)
            self.screen.blit(txt, (px + (panel_w - txt.get_width()) // 2,
                                   py + (panel_h - txt.get_height()) // 2))

        # ── Game over / Night complete ──────────────────────────
        if model.night_complete:
            overlay = pygame.Surface((self.screen_w, self.screen_h))
            overlay.fill((0, 0, 0))
            self.screen.blit(overlay, (0, 0))
            txt = self.font.render("6 AM", True, (30, 200, 30))
            self.screen.blit(txt, (self.screen_w // 2 - txt.get_width() // 2, self.screen_h // 2 - 30))

        self.screen.blit(self._brightness_overlay, (0, 0))