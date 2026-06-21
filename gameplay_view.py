import math
import os
import json
import random

import cv2
import numpy as np
import pygame

from gameplay_model import SEAL_CAMERA_MAP


DEFAULT_LAPTOP_PROJECTION_CORNERS = [
    [419, 494],
    [567, 474],
    [593, 576],
    [445, 610],
]
LAPTOP_PROJECTION_CONFIG_PATH = "laptop_projection.json"
LAPTOP_BOOT_TICKS = 180
LAPTOP_SHUTDOWN_TICKS = 150


def get_laptop_power_sequence(power_state: str, power_timer: int) -> tuple[str, float]:
    """Map laptop power timers to a visual phase and normalized progress."""
    if power_state == "BOOTING":
        progress = max(0.0, min(1.0, 1.0 - power_timer / LAPTOP_BOOT_TICKS))
        if progress < 0.18:
            return "boot_wake", progress / 0.18
        if progress < 0.62:
            return "boot_post", (progress - 0.18) / 0.44
        return "boot_loading", (progress - 0.62) / 0.38

    if power_state == "SHUTTING_DOWN":
        progress = max(
            0.0, min(1.0, 1.0 - power_timer / LAPTOP_SHUTDOWN_TICKS)
        )
        if progress < 0.48:
            return "shutdown_msg", progress / 0.48
        return "shutdown_fade", (progress - 0.48) / 0.52

    return "off_idle", 0.0


def _normalize_brightness(surfaces_with_paths, target=25):
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
                    img.set_at(
                        (x, y),
                        (
                            min(255, int(r * factor)),
                            min(255, int(g * factor)),
                            min(255, int(b * factor)),
                            a,
                        ),
                    )
        if src_path:
            os.makedirs(cache_dir, exist_ok=True)
            pygame.image.save(img, cache_path)


class GameView:
    def __init__(self, screen):
        self.screen = screen
        screen_w, screen_h = screen.get_size()

        raw_off = pygame.image.load(
            "assets/office/server_is_off.png"
        ).convert()
        scale = screen_h / raw_off.get_height()
        target_size = (int(raw_off.get_width() * scale), screen_h)

        self.bg_off = pygame.transform.smoothscale(raw_off, target_size)

        self.bg_blinks = {}
        for name, key in [
            ("server_all_four_lights_are_red.png", "red"),
            ("server_all_four_lights_are_green.png", "green"),
        ]:
            raw = pygame.image.load(f"assets/office/{name}").convert()
            self.bg_blinks[key] = pygame.transform.smoothscale(
                raw, target_size
            )

        self.bg_frames = []
        for name in [
            "server_all_four_lights_are_green.png",
            "server_all_four_lights_are_green.png",
        ]:
            raw = pygame.image.load(f"assets/office/{name}").convert()
            self.bg_frames.append(
                pygame.transform.smoothscale(raw, target_size)
            )

        raw_hack = pygame.image.load(
            "assets/office/server_all_four_lights_are_green+hack_is_going.png"
        ).convert()
        self.bg_hack = pygame.transform.smoothscale(raw_hack, target_size)
        norm_list = [
            (self.bg_off, "assets/office/server_is_off.png"),
        ]
        for key, name in [
            ("red", "server_all_four_lights_are_red.png"),
            ("green", "server_all_four_lights_are_green.png"),
        ]:
            norm_list.append((self.bg_blinks[key], f"assets/office/{name}"))
        for i, name in enumerate(
            [
                "server_all_four_lights_are_green.png",
                "server_all_four_lights_are_green.png",
            ]
        ):
            norm_list.append((self.bg_frames[i], f"assets/office/{name}"))
        norm_list.append(
            (
                self.bg_hack,
                "assets/office/server_all_four_lights_are_green+hack_is_going.png",
            )
        )
        _normalize_brightness(norm_list)

        self.max_offset = max(0, target_size[0] - screen_w)
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._brightness_overlay = pygame.Surface(
            (screen_w, screen_h), pygame.SRCALPHA
        )
        self._brightness_overlay.fill((255, 255, 255, 13))
        self.font = pygame.font.Font("assets/fonts/OCR-A.ttf", 30)
        self.font_small = pygame.font.Font("assets/fonts/OCR-A.ttf", 18)
        self.font_very_small = pygame.font.Font("assets/fonts/OCR-A.ttf", 11)
        self._ui_font = pygame.font.SysFont("tahoma", 16)
        self._ui_font_bold = pygame.font.SysFont("tahoma", 16, bold=True)
        self._ui_font_sm = pygame.font.SysFont("tahoma", 13)
        self._ui_font_title = pygame.font.SysFont("tahoma", 14, bold=True)
        self.scale = scale
        self.server_hotspot = pygame.Rect(1151, 163, 131, 244)
        self.laptop_hotspot = pygame.Rect(350, 390, 340, 255)
        self.switch_timer = random.randint(60, 180)
        self.current_idx = 0

        # ── Offscreen для рендеринга ноутбука + перспектива ─────────
        self._laptop_offscreen = pygame.Surface((screen_w, screen_h))

        self._projection_config_path = LAPTOP_PROJECTION_CONFIG_PATH
        self._lp_base_corners = np.float32(DEFAULT_LAPTOP_PROJECTION_CORNERS)
        self.load_laptop_projection()
        self._rebuild_laptop_projection()

        # Кнопка TAB в офисе (изображение на столе)
        raw_tab = pygame.image.load(
            "assets/cctv/tabbutton.png"
        ).convert_alpha()
        self.tabbutton_surf = pygame.transform.scale(
            raw_tab, (int(600 * scale), int(60 * scale))
        )
        self._tab_button_dx = 28
        self.tab_button_rect = pygame.Rect(
            662, 758, 600, 60
        )  # оригинальные координаты (1923×818)
        self.tab_button_hovered = False

        raw_wallpaper = pygame.image.load(
            "assets/laptop/wallpaper.png"
        ).convert()
        self.laptop_wallpaper = pygame.transform.smoothscale(
            raw_wallpaper, (screen_w, screen_h - 40)
        )

        self._ad_images = {}
        for key in ["ad_hhru", "ad_kontur", "ad_sber"]:
            raw = pygame.image.load(f"assets/laptop/{key}.png").convert()
            rw, rh = raw.get_size()
            scale = min((screen_w - 40) / rw, (screen_h - 80) / rh)
            self._ad_images[key] = pygame.transform.smoothscale(
                raw, (int(rw * scale), int(rh * scale))
            )

        self._ad_office_images = {}
        for key in ["ad_hhru", "ad_kontur", "ad_sber"]:
            raw = pygame.image.load(
                f"assets/office/server_all_four_lights_are_green+{key}.png"
            ).convert()
            self._ad_office_images[key] = pygame.transform.smoothscale(
                raw, target_size
            )

        # Область экрана планшета — отступаем от краёв, чтобы не задеть рамку
        self.screen_rect = pygame.Rect(0, 0, screen_w, screen_h)

        # Иконки камер из assets/cctv/ — загружаются, маппинг по номеру камеры
        self._cam_icons = {}
        icon_map = {
            1: "cam1.png",
            2: "cam2.png",
            3: "cam3.png",
            4: "cam4.png",
            5: "cam5.png",
            6: "cam6.png",
            7: "cam7.png",
            8: "cam8.png",
            9: "cam9.png",
            10: "cam10.png",
            11: "cam11.png",
            12: "cam10.png",
        }
        for idx, fname in icon_map.items():
            img = pygame.image.load(f"assets/cctv/{fname}").convert_alpha()
            self._cam_icons[idx] = pygame.transform.scale(img, (30, 25))

        # Мини-карта (справа в планшете, uniform scale)
        raw_map = pygame.image.load(
            "assets/cameras/camera_map.png"
        ).convert_alpha()
        mm_map_w, mm_map_h = raw_map.get_size()  # 595×550
        self._mm_scale = 500 / mm_map_w  # uniform scale ≈ 0.84
        mm_w, mm_h = 500, int(mm_map_h * self._mm_scale)
        self._minimap_bg = pygame.transform.smoothscale(raw_map, (mm_w, mm_h))
        self._minimap_bg.set_alpha(220)
        self._minimap_pos = (
            self.screen_rect.right - mm_w - 5,
            self.screen_rect.bottom - mm_h - 5,
        )
        self._minimap_size = (mm_w, mm_h)

        # Карта вентиляции: прозрачный оверлей (белые контуры + синие duct-линии)
        raw_vent = pygame.image.load(
            "assets/cameras/vent_map.png"
        ).convert_alpha()
        vw, vh = raw_vent.get_size()
        self._vent_overlay = pygame.transform.smoothscale(
            raw_vent, (mm_w, mm_h)
        )
        self.vent_map_mode = False  # False = камеры, True = вентиляция

        self._cam_blink_start = 0
        self._prev_camera_idx = 1

        # Координаты индикаторов вентов (в координатах scaled vent map = mm_w × mm_h)
        vent_sx = mm_w / vw
        vent_sy = mm_h / vh
        self._vent_indicator_pos = {
            "VENT_A": (int(740 * vent_sx), int(520 * vent_sy)),
            "VENT_B": (int(560 * vent_sx), int(520 * vent_sy)),
        }
        self._vent_reset_rects: dict[str, pygame.Rect] = {}

        # Иконки вент-камер (8–11) — внутри duct-проходов, рядом с seal'ами
        # Реальные duct'ы в vent_map.png (1306x1204):
        #   Горизонт. верхний:  y≈45,  x: 16–1127
        #   Горизонт. средний:  y≈560, x: 16–1127
        #   Горизонт. нижний:   y≈903, x: 16–170
        #   Вертик. левый:      x≈18,  y: 43–906
        #   Вертик. средний:    x≈339, y: 43–541
        #   Вертик. правый:     x≈1124,y: 43–746
        self._vent_cam_positions = {
            8:  (int(900 * vent_sx),  int(45 * vent_sy)),   # верхний горизонт. duct, правая часть
            9:  (int(18 * vent_sx),   int(145 * vent_sy)),  # левый вертик. duct, верхняя часть
            10: (int(18 * vent_sx),   int(750 * vent_sy)),  # левый вертик. duct, нижняя часть
            11: (int(1124 * vent_sx), int(620 * vent_sy)),  # правый вертик. duct, нижняя часть (НОВАЯ)
        }

        # Точки блокировки (SEAL) — (sx, sy, direction) в координатах vent overlay
        # direction: "V" = вертикальная полоска поперёк горизонт. duct'а
        #            "H" = горизонтальная полоска поперёк вертик. duct'а
        # Точные центры duct-линий из vent_map.png (по пикселям):
        #   верхний горизонт: y=45    левый вертик: x=18
        #   правый вертик: x=1124   нижний горизонт: y=903
        self._seal_positions = {
            "SEAL_TOP_RIGHT":   (int(1050 * vent_sx), int(45 * vent_sy),   "V"),  # верхн. duct, левее перекрёстия
            "SEAL_CENTER":      (int(18 * vent_sx),   int(200 * vent_sy),  "H"),  # левый duct, под CAM09
            "SEAL_MID_RIGHT":   (int(1124 * vent_sx), int(700 * vent_sy),  "H"),  # правый duct, ниже CAM11
            "SEAL_BOTTOM_LEFT": (int(18 * vent_sx),  int(845 * vent_sy),  "H"),  # по центру короткого правого участка у CAM10
        }
        self._seal_rects: dict[str, pygame.Rect] = {}

        # Координаты центров иконок в пространстве мини-карты (500×462)
        # Кроме коворкинга — у него координата левого верхнего угла
        self._minimap_icon_positions = {
            1: (447, 303),  # ALGEM'S ROOM
            2: (331, 120),  # CANTEEN
            3: (270, 279),  # TOILETS
            4: (207, 334),  # MAIN HALL
            5: (148, 65),  # SERVICE ROOM
            6: (88, 213),  # WEST HALL
            7: (32, 116),  # COWORKING
        }
        self._office_me_pos = (245, 76)

        # Камеры — каждая грузится, масштабируется под высоту screen_rect, затемняется и тонируется
        from gameplay_model import CAMERAS

        self.camera_surfaces = {}
        self._closed_vent_surfaces: dict[int, pygame.Surface] = {}
        self.camera_max_offsets = {}
        cam_h = self.screen_rect.h
        for idx, _display_id, name, fname in CAMERAS:
            path = f"assets/cameras/{fname}"
            if not os.path.exists(path):
                path = f"assets/vents_cameras/{fname}"
            raw = pygame.image.load(path).convert()
            if path.startswith("assets/vents_cameras"):
                target_w = int(raw.get_height() * 16 / 9)
                offset = (raw.get_width() - target_w) // 2
                raw = raw.subsurface((offset, 0, target_w, raw.get_height()))
            scale = cam_h / raw.get_height()
            cw = int(raw.get_width() * scale)
            surf = pygame.transform.smoothscale(raw, (cw, cam_h))
            dark = pygame.Surface((cw, cam_h))
            dark.fill((195, 195, 195))
            surf.blit(dark, (0, 0), special_flags=pygame.BLEND_MULT)
            purple = pygame.Surface((cw, cam_h), pygame.SRCALPHA)
            purple.fill((20, 30, 60, 40))
            surf.blit(purple, (0, 0))
            self.camera_surfaces[idx] = surf
            self.camera_max_offsets[idx] = max(0, cw - self.screen_rect.w)

        # Альтернативные фоны для камер
        self._algem_room_surf = None

        def _load_cam(path):
            try:
                raw = pygame.image.load(path).convert()
                if path.startswith("assets/vents_cameras"):
                    target_w = int(raw.get_height() * 16 / 9)
                    offset = (raw.get_width() - target_w) // 2
                    raw = raw.subsurface((offset, 0, target_w, raw.get_height()))
                s = cam_h / raw.get_height()
                cw = int(raw.get_width() * s)
                surf = pygame.transform.smoothscale(raw, (cw, cam_h))
                dark = pygame.Surface((cw, cam_h))
                dark.fill((195, 195, 195))
                surf.blit(dark, (0, 0), special_flags=pygame.BLEND_MULT)
                purple = pygame.Surface((cw, cam_h), pygame.SRCALPHA)
                purple.fill((20, 30, 60, 40))
                surf.blit(purple, (0, 0))
                return surf
            except pygame.error:
                return None

        def _cache_laptop_gradients():
            sw, sh = self.screen_w, self.screen_h
            tb_h = 40
            tb_top = sh - tb_h

            tb_surf = pygame.Surface((sw, tb_h))
            for y in range(tb_h):
                t = y / tb_h
                r = int(20 + t * 20)
                g = int(60 + t * 40)
                b = int(180 + t * 40)
                pygame.draw.line(tb_surf, (r, g, b), (0, y), (sw, y))
            self._tb_surf = tb_surf
            self._tb_top = tb_top

            start_w, start_h = 86, tb_h - 4
            start_surf = pygame.Surface((start_w, start_h))
            for y in range(start_h):
                t = y / start_h
                r = int(40 + t * 30)
                g = int(160 - t * 20)
                b = int(40 + t * 20)
                pygame.draw.line(start_surf, (r, g, b), (0, y), (start_w, y))
            self._start_btn_surf = start_surf

            menu_w, menu_h = 220, 260
            menu_surf = pygame.Surface((menu_w, menu_h), pygame.SRCALPHA)
            for y in range(menu_h):
                t = y / menu_h
                r = int(30 + t * 20)
                g = int(60 + t * 30)
                b = int(180 + t * 40)
                pygame.draw.line(menu_surf, (r, g, b, 240), (0, y), (menu_w, y))
            self._menu_bg_surf = menu_surf

            title_w = 620
            title_h = 26
            title_surf = pygame.Surface((title_w, title_h))
            for y in range(title_h):
                t = y / title_h
                r = int(0 + t * 30)
                g = int(80 + t * 40)
                b = int(180 + t * 40)
                pygame.draw.line(title_surf, (r, g, b), (0, y), (title_w, y))
            self._title_bar_surf = title_surf

            shadow_w, shadow_h = 624, 444
            shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
            for i in range(4, 0, -1):
                inner = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
                inner.fill((0, 0, 0, 15 * i))
                shadow.blit(inner, (i, i))
            self._shadow_surface = shadow

            self._sel_highlight = pygame.Surface((52, 52), pygame.SRCALPHA)
            self._sel_highlight.fill((80, 120, 200, 80))

            self._rec_glow = pygame.Surface((24, 24), pygame.SRCALPHA)
            pygame.draw.circle(self._rec_glow, (255, 0, 0, 50), (12, 12), 12)

            self._dark_overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)

            self._laptop_scanlines = pygame.Surface((sw, sh), pygame.SRCALPHA)
            for y in range(0, sh, 2):
                alpha = 10 if (y // 2) % 2 == 0 else 18
                pygame.draw.line(
                    self._laptop_scanlines,
                    (0, 0, 0, alpha),
                    (0, y),
                    (sw, y),
                )

            self._laptop_crt_vignette = pygame.Surface(
                (sw, sh), pygame.SRCALPHA
            )
            for i in range(24):
                inset = i * 8
                alpha = min(110, 4 + i * 4)
                pygame.draw.rect(
                    self._laptop_crt_vignette,
                    (0, 0, 0, alpha),
                    pygame.Rect(inset, inset, sw - inset * 2, sh - inset * 2),
                    8,
                    border_radius=18,
                )

            self._laptop_panel_noise = pygame.Surface(
                (sw, sh), pygame.SRCALPHA
            )
            rng = random.Random(17)
            for _ in range(260):
                x = rng.randrange(sw)
                y = rng.randrange(sh)
                w = rng.randint(6, 28)
                h = rng.randint(1, 3)
                alpha = rng.randint(5, 12)
                tone = rng.randint(26, 40)
                pygame.draw.rect(
                    self._laptop_panel_noise,
                    (tone, tone, tone + 2, alpha),
                    pygame.Rect(x, y, w, h),
                )
            for _ in range(120):
                y = rng.randrange(sh)
                alpha = rng.randint(3, 8)
                pygame.draw.line(
                    self._laptop_panel_noise,
                    (255, 255, 255, alpha),
                    (0, y),
                    (sw, y),
                )

            self._text_cache = {}

            self._minimap_tint_cache = {}
            self._seal_bg_cache = {}
            self._cam_dark_cache = {}

        _cache_laptop_gradients()

        # Алгем-спрайты для каждой камеры
        self._algem_surfaces: dict[int, pygame.Surface] = {}
        self._algem_main_hall_surf = _load_cam(
            "assets/cameras/main_hall_with_algem.png"
        )
        self._algem_mainhall_watching = _load_cam(
            "assets/cameras/algem_mainhall_is_watching_you.png"
        )
        closed_cam_files = {
            8: "cam_8_closed.png",
            9: "cam_9_closed.png",
            10: "cam_10_closed.png",
            11: "cam_11_closed.png",
        }
        for cam_idx, fname in closed_cam_files.items():
            path = f"assets/vents_cameras/{fname}"
            if os.path.exists(path):
                surf = _load_cam(path)
                if surf is not None:
                    self._closed_vent_surfaces[cam_idx] = surf

        algem_files = {
            1: "algems' room_with_algem.png",
            2: "canteen_algem.png",
            3: "toilets_algem.png",
            4: "main_hall_with_algem.png",
            5: "service_room_algem.png",
            6: "westhall_algem.png",
            7: "coworking_algem.png",
            8: "cam8_with_algem.png",
            9: "cam9_with_algem.png",
            10: "cam10_with_algem.png",
            11: "cam11_with_algem.png",
        }
        for cam_idx, fname in algem_files.items():
            path = f"assets/cameras/{fname}"
            if not os.path.exists(path):
                path = f"assets/vents_cameras/{fname}"
            s = _load_cam(path)
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

        # ── Процедурный шум (numpy) ────────────────────────────────────
        self._noise_w = screen_w // 3
        self._noise_h = screen_h // 3
        self._noise_surf = pygame.Surface((self._noise_w, self._noise_h), pygame.SRCALPHA)
        self._noise_timer = 0
        self._noise_alpha = 25
        self._noise_burst_timer = 0

        # Сканлинии (crt scanlines) — кэшируются, скроллятся
        self._scanline_surf = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        for y in range(0, screen_h, 3):
            pygame.draw.line(self._scanline_surf, (0, 0, 0, 22), (0, y), (screen_w, y))
        self._scanline_offset = 0

        # Glitch frames для Алгема (старые noice*.png)
        self._glitch_frames = []
        for fname in sorted(os.listdir("assets/cctv")):
            if fname.lower().startswith("noice") and (
                fname.lower().endswith(".png")
                or fname.lower().endswith(".jpg")
            ):
                img = pygame.image.load(f"assets/cctv/{fname}").convert()
                s = pygame.transform.smoothscale(img, (screen_w, screen_h))
                s.set_alpha(255)
                self._glitch_frames.append(s)

        # Планшет — 10 отдельных картинок без фона
        self.cam_frames = []
        for i in range(1, 11):
            img = pygame.image.load(
                f"assets/office/tablet/tablet-{i}.png"
            ).convert_alpha()
            self.cam_frames.append(
                pygame.transform.smoothscale(img, (screen_w, screen_h))
            )

        # Кнопка Mute Call (на столе офиса)
        raw_mute = pygame.image.load(
            "assets/office/mutecall.png"
        ).convert_alpha()
        mute_scale = 140 / raw_mute.get_width()
        self.mutecall_surf = pygame.transform.scale(
            raw_mute, (140, int(raw_mute.get_height() * mute_scale))
        )
        self._mutecall_rect = pygame.Rect(0, 0, *self.mutecall_surf.get_size())

        # Кнопки BAIT и MAP — одинаковый размер
        self._btn_size = (64, 34)
        self._bait_btn_icon_size = (56, 28)
        self._map_btn_icon_size = (52, 26)
        raw_bait = pygame.image.load(
            "assets/cameras/playaudio.png"
        ).convert_alpha()
        raw_map = pygame.image.load(
            "assets/cameras/maptoggle.png"
        ).convert_alpha()
        self._btn_bg = pygame.Surface(self._btn_size, pygame.SRCALPHA)
        self._btn_bg.fill((15, 15, 25, 200))
        self._bait_btn_img = pygame.Surface(self._btn_size, pygame.SRCALPHA)
        self._map_btn_img = pygame.Surface(self._btn_size, pygame.SRCALPHA)
        bait_fill = raw_bait.get_at(
            (raw_bait.get_width() // 2, raw_bait.get_height() // 2)
        )
        map_fill = raw_map.get_at(
            (raw_map.get_width() // 2, raw_map.get_height() // 2)
        )
        self._seal_btn_fill = bait_fill
        self._bait_btn_img.fill(bait_fill)
        self._map_btn_img.fill(map_fill)
        bait_scaled = pygame.transform.scale(raw_bait, self._bait_btn_icon_size)
        map_scaled = pygame.transform.scale(raw_map, self._map_btn_icon_size)
        bait_x = (self._btn_size[0] - self._bait_btn_icon_size[0]) // 2
        bait_y = (self._btn_size[1] - self._bait_btn_icon_size[1]) // 2
        map_x = (self._btn_size[0] - self._map_btn_icon_size[0]) // 2 - 1
        map_y = (self._btn_size[1] - self._map_btn_icon_size[1]) // 2 - 1
        self._bait_btn_img.blit(bait_scaled, (bait_x, bait_y))
        self._map_btn_img.blit(map_scaled, (map_x, map_y))
        self._bait_btn_rect = pygame.Rect(0, 0, *self._btn_size)
        self._map_btn_rect = pygame.Rect(0, 0, *self._btn_size)
        self._seal_btn_frames = [
            self._build_status_button(["SEALING", dots])
            for dots in (".", "..", "...")
        ]

        # Аудио-иконки для мини-карты (audio1-4.png)
        self._audio_icons = []
        for i in range(1, 5):
            img = pygame.image.load(
                f"assets/cameras/audio{i}.png"
            ).convert_alpha()
            self._audio_icons.append(pygame.transform.scale(img, (60, 50)))

        # ── Глитч-картинки ─────────────────────────────────────────────
        self._glitch_surfs = []
        for fname in ("glitch1.png", "glitch2.png"):
            try:
                raw = pygame.image.load(f"assets/glithces/{fname}").convert()
                self._glitch_surfs.append(
                    pygame.transform.smoothscale(raw, (screen_w, screen_h))
                )
            except pygame.error:
                pass

    def load_laptop_projection(self) -> None:
        """Load laptop projection corners from a JSON config if it exists."""
        if not os.path.exists(self._projection_config_path):
            return
        try:
            with open(self._projection_config_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            corners = data.get("corners")
            if not isinstance(corners, list) or len(corners) != 4:
                return
            parsed = []
            for pair in corners:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    return
                parsed.append([float(pair[0]), float(pair[1])])
            self._lp_base_corners = np.float32(parsed)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    def save_laptop_projection(self) -> None:
        """Save current laptop projection corners to disk."""
        data = {
            "corners": [
                [int(round(x)), int(round(y))]
                for x, y in self._lp_base_corners.tolist()
            ]
        }
        with open(self._projection_config_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=True, indent=2)

    def reset_laptop_projection(self) -> None:
        """Reset the laptop projection to the default tuned trapezoid."""
        self._lp_base_corners = np.float32(DEFAULT_LAPTOP_PROJECTION_CORNERS)
        self._rebuild_laptop_projection()

    def _rebuild_laptop_projection(self) -> None:
        """Recompute the perspective transform after any corner edit."""
        dst = self._lp_base_corners * self.scale
        x_min, y_min = dst.min(axis=0).astype(int)
        x_max, y_max = dst.max(axis=0).astype(int)
        self._lp_out_w = max(1, int(x_max - x_min))
        self._lp_out_h = max(1, int(y_max - y_min))
        self._lp_blit_origin = (int(x_min), int(y_min))

        src_c = np.float32(
            [
                [0, 0],
                [self._lp_out_w, 0],
                [self._lp_out_w, self._lp_out_h],
                [0, self._lp_out_h],
            ]
        )
        dst_c = (dst - np.array([x_min, y_min])).astype(np.float32)
        self._lp_M = cv2.getPerspectiveTransform(src_c, dst_c)

    def get_laptop_projection_corners_screen(
        self, offset: int = 0
    ) -> list[tuple[int, int]]:
        """Return projection corners in active screen coordinates."""
        return [
            (int(round(x * self.scale)) - offset, int(round(y * self.scale)))
            for x, y in self._lp_base_corners.tolist()
        ]

    def get_laptop_projection_corner_hit(
        self, mouse_pos: tuple[int, int], offset: int = 0, radius: int = 18
    ) -> int | None:
        """Return the nearest projection corner index under the mouse."""
        mx, my = mouse_pos
        best_idx = None
        best_dist_sq = radius * radius
        for idx, (cx, cy) in enumerate(
            self.get_laptop_projection_corners_screen(offset)
        ):
            dx = mx - cx
            dy = my - cy
            dist_sq = dx * dx + dy * dy
            if dist_sq <= best_dist_sq:
                best_idx = idx
                best_dist_sq = dist_sq
        return best_idx

    def move_laptop_projection_corner(
        self, corner_idx: int, mouse_pos: tuple[int, int], offset: int = 0
    ) -> None:
        """Move one projection corner using current screen coordinates."""
        x = (mouse_pos[0] + offset) / self.scale
        y = mouse_pos[1] / self.scale
        self._lp_base_corners[corner_idx] = [x, y]
        self._rebuild_laptop_projection()

    def nudge_laptop_projection_corner(
        self, corner_idx: int, dx: float, dy: float
    ) -> None:
        """Fine-tune one projection corner in source-image pixels."""
        self._lp_base_corners[corner_idx][0] += dx
        self._lp_base_corners[corner_idx][1] += dy
        self._rebuild_laptop_projection()

    def draw_laptop_projection_editor(
        self,
        surface: pygame.Surface,
        offset: int,
        active_corner: int | None,
        dragging: bool,
    ) -> None:
        """Draw an in-game overlay for live laptop projection editing."""
        corners = self.get_laptop_projection_corners_screen(offset)
        if len(corners) == 4:
            pygame.draw.lines(surface, (70, 220, 255), True, corners, 2)

        labels = ["TL", "TR", "BR", "BL"]
        for idx, (cx, cy) in enumerate(corners):
            color = (255, 210, 60) if idx == active_corner else (255, 110, 110)
            radius = 7 if idx == active_corner else 5
            pygame.draw.circle(surface, color, (cx, cy), radius)
            pygame.draw.circle(surface, (20, 20, 20), (cx, cy), radius, 2)
            tag = self._ctext(self._ui_font_bold, labels[idx], (255, 255, 255))
            surface.blit(tag, (cx + 12, cy - 10))

        panel = pygame.Rect(18, 18, 355, 178)
        panel_bg = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
        panel_bg.fill((8, 12, 18, 210))
        surface.blit(panel_bg, panel.topleft)
        pygame.draw.rect(surface, (70, 220, 255), panel, 2, border_radius=8)

        title = self._ctext(
            self._ui_font_bold, "Laptop Projection Editor [F8]", (255, 255, 255)
        )
        surface.blit(title, (panel.x + 12, panel.y + 10))

        status = "Drag corners with mouse"
        if dragging:
            status = "Dragging selected corner"
        status_surf = self._ctext(self._ui_font_sm, status, (180, 220, 235))
        surface.blit(status_surf, (panel.x + 12, panel.y + 34))

        hint = self._ctext(
            self._ui_font_sm,
            "1-4 select, arrows move, Shift=faster, S save, R reset",
            (160, 185, 200),
        )
        surface.blit(hint, (panel.x + 12, panel.y + 54))

        for idx, (x, y) in enumerate(self._lp_base_corners.tolist()):
            line_color = (255, 225, 130) if idx == active_corner else (210, 210, 210)
            text = self._ctext(
                self._ui_font_sm,
                f"{idx + 1}. {labels[idx]}  x={int(round(x))}  y={int(round(y))}",
                line_color,
            )
            surface.blit(text, (panel.x + 12, panel.y + 82 + idx * 20))

    def _build_status_button(
        self,
        lines: list[str],
    ) -> pygame.Surface:
        """Собрать маленькую UI-плашку в том же духе, что и остальные кнопки."""
        surf = pygame.Surface(self._btn_size, pygame.SRCALPHA)
        surf.fill(self._seal_btn_fill)
        pygame.draw.rect(surf, (255, 255, 255), (0, 0, *self._btn_size), 1)

        rendered = [
            self.font_very_small.render(line, False, (245, 245, 245))
            for line in lines
        ]
        total_h = sum(s.get_height() for s in rendered) + 1 * (len(rendered) - 1)
        y = (self._btn_size[1] - total_h) // 2 - 1
        for text_surf in rendered:
            x = (self._btn_size[0] - text_surf.get_width()) // 2
            surf.blit(text_surf, (x, y))
            y += text_surf.get_height() + 1
        return surf

    def _ctext(self, font, text, color):
        key = (id(font), text, color)
        cached = self._text_cache.get(key)
        if cached is None:
            cached = font.render(text, True, color)
            self._text_cache[key] = cached
        return cached

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
        tx = (
            self.screen_rect.centerx
            - self.tabbutton_surf.get_width() // 2
            + self._tab_button_dx
        )
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
        if not hasattr(self, "_laptop_icons"):
            return None
        for rect, key in self._laptop_icons:
            if rect.collidepoint(mouse_pos):
                return key
        return None

    def is_laptop_start_clicked(self, mouse_pos):
        return hasattr(
            self, "_laptop_start_rect"
        ) and self._laptop_start_rect.collidepoint(mouse_pos)

    def is_laptop_menu_item_clicked(self, mouse_pos):
        if not hasattr(self, "_laptop_menu_items"):
            return None
        for rect, key in self._laptop_menu_items:
            if rect.collidepoint(mouse_pos):
                return key
        return None

    def is_laptop_close_clicked(self, mouse_pos):
        return hasattr(
            self, "_laptop_close_btn"
        ) and self._laptop_close_btn.collidepoint(mouse_pos)

    def is_laptop_server_btn_clicked(self, mouse_pos):
        return hasattr(
            self, "_laptop_server_btn"
        ) and self._laptop_server_btn.collidepoint(mouse_pos)

    def is_laptop_reboot_btn_clicked(self, mouse_pos):
        return hasattr(
            self, "_laptop_reboot_btn"
        ) and self._laptop_reboot_btn.collidepoint(mouse_pos)

    def is_laptop_power_clicked(self, mouse_pos):
        return hasattr(
            self, "_laptop_power_btn"
        ) and self._laptop_power_btn.collidepoint(mouse_pos)

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

        label = self._ctext(self.font, "HACK", (200, 200, 200))
        self.screen.blit(
            label,
            (
                x - label.get_width() - 10,
                y + bar_h // 2 - label.get_height() // 2,
            ),
        )

        pct = self._ctext(self.font, f"{int(model.hack_progress * 100)}%", (200, 200, 200))
        self.screen.blit(
            pct, (x + bar_w + 10, y + bar_h // 2 - pct.get_height() // 2)
        )

    # ── Ноутбук ──────────────────────────────────────────────────────

    def _draw_xp_icon(
        self,
        ix: int,
        iy: int,
        key: str,
        hovered: bool,
        surface: pygame.Surface | None = None,
    ) -> None:
        """Нарисовать одну иконку рабочего стола в стиле XP."""
        target = surface if surface is not None else self.screen
        icon_s = 48
        pad = 2

        # Фон иконки
        if hovered:
            sel = pygame.Surface(
                (icon_s + pad * 2, icon_s + pad * 2), pygame.SRCALPHA
            )
            sel.fill((80, 120, 200, 80))
            target.blit(sel, (ix - pad, iy - pad))

        if key == "mycomputer":
            # Монитор
            pygame.draw.rect(
                target,
                (180, 180, 180),
                (ix + 4, iy + 2, 40, 30),
                border_radius=3,
            )
            pygame.draw.rect(
                target,
                (50, 50, 50),
                (ix + 4, iy + 2, 40, 30),
                2,
                border_radius=3,
            )
            # Экран
            pygame.draw.rect(
                target, (40, 80, 160), (ix + 8, iy + 6, 32, 20)
            )
            pygame.draw.rect(
                target, (30, 30, 30), (ix + 8, iy + 6, 32, 20), 1
            )
            # Подставка
            pygame.draw.rect(
                target, (140, 140, 140), (ix + 18, iy + 32, 12, 4)
            )
            pygame.draw.rect(
                target,
                (120, 120, 120),
                (ix + 12, iy + 36, 24, 3),
                border_radius=2,
            )

        elif key == "claude":
            # Скрин-иконка — череп / хакер
            cx, cy = ix + icon_s // 2, iy + 16
            pygame.draw.circle(target, (60, 20, 80), (cx, cy), 16)
            pygame.draw.circle(target, (100, 40, 140), (cx, cy), 16, 2)
            # Глаза
            pygame.draw.circle(target, (200, 50, 50), (cx - 6, cy - 3), 4)
            pygame.draw.circle(target, (200, 50, 50), (cx + 6, cy - 3), 4)
            pygame.draw.circle(
                target, (255, 200, 200), (cx - 5, cy - 4), 1
            )
            pygame.draw.circle(
                target, (255, 200, 200), (cx + 7, cy - 4), 1
            )
            # Нижняя часть
            pygame.draw.rect(
                target,
                (60, 20, 80),
                (cx - 10, cy + 12, 20, 6),
                border_radius=2,
            )

        elif key == "recycle":
            # Корзина
            bx, by = ix + 12, iy + 10
            pygame.draw.rect(
                target,
                (180, 180, 180),
                (bx, by + 6, 24, 26),
                border_radius=2,
            )
            pygame.draw.rect(
                target,
                (140, 140, 140),
                (bx, by + 6, 24, 26),
                2,
                border_radius=2,
            )
            # Ручка
            pygame.draw.rect(
                target,
                (160, 160, 160),
                (bx + 6, by, 12, 8),
                border_radius=2,
            )
            pygame.draw.rect(
                target,
                (120, 120, 120),
                (bx + 6, by, 12, 8),
                1,
                border_radius=2,
            )
            # Полоски
            for lx in (bx + 6, bx + 12, bx + 18):
                pygame.draw.line(
                    target, (120, 120, 120), (lx, by + 10), (lx, by + 30)
                )

        # Подпись под иконкой
        label_lines = {
            "mycomputer": "My Computer",
            "claude": ["Claude", "Mythos"],
            "recycle": "Recycle Bin",
        }
        lines = label_lines.get(key, [key])
        if isinstance(lines, str):
            lines = [lines]
        for j, line in enumerate(lines):
            rendered = self._ctext(self._ui_font_sm, line, (0, 0, 0))
            target.blit(
                rendered,
                (
                    ix + 1 + icon_s // 2 - rendered.get_width() // 2 + 1,
                    iy + icon_s + 4 + j * 16 + 1,
                ),
            )
            rendered = self._ctext(self._ui_font_sm, line, (255, 255, 255))
            target.blit(
                rendered,
                (
                    ix + icon_s // 2 - rendered.get_width() // 2,
                    iy + icon_s + 4 + j * 16,
                ),
            )

    def _draw_laptop_power_transition(self, model) -> None:
        sw, sh = self.screen_w, self.screen_h
        phase, phase_t = get_laptop_power_sequence(
            model.laptop_power_state, model.laptop_power_timer
        )

        layer = self._render_laptop_phase_surface(phase, phase_t, model)
        self.screen.blit(layer, (0, 0))

        if model.laptop_power_state in ("BOOTING", "SHUTTING_DOWN"):
            scanlines = self._laptop_scanlines.copy()
            scanlines.set_alpha(12)
            self.screen.blit(scanlines, (0, 0))

        boot_progress = 0.0
        if model.laptop_power_state == "BOOTING":
            boot_progress = self._clamp01(
                1.0 - model.laptop_power_timer / LAPTOP_BOOT_TICKS
            )

        draw_power_button = model.laptop_power_state != "BOOTING" or boot_progress < 0.84
        if draw_power_button:
            power_btn = pygame.Rect(sw // 2 - 28, int(sh * 0.83), 56, 24)
            self._laptop_power_btn = power_btn
            self._draw_laptop_power_button(model.laptop_power_state, power_btn)
        else:
            self._laptop_power_btn = pygame.Rect(0, 0, 0, 0)

    def _render_laptop_phase_surface(
        self, phase: str, phase_t: float, model=None
    ) -> pygame.Surface:
        surface = pygame.Surface((self.screen_w, self.screen_h))

        if phase == "boot_wake":
            self._draw_boot_animation(surface, phase_t * 0.18, model)
            return surface
        if phase == "boot_post":
            self._draw_boot_animation(surface, 0.18 + phase_t * 0.44, model)
            return surface
        if phase == "boot_loading":
            self._draw_boot_animation(surface, 0.62 + phase_t * 0.38, model)
            return surface
        if phase == "shutdown_msg":
            self._draw_shutdown_animation(surface, phase_t * 0.48)
            return surface
        if phase == "shutdown_fade":
            self._draw_shutdown_animation(surface, 0.48 + phase_t * 0.52)
            return surface

        self._draw_powered_off_screen(surface)
        return surface

    def _draw_laptop_power_button(
        self, power_state: str, rect: pygame.Rect
    ) -> None:
        pulse = {
            "OFF": 0.10,
            "BOOTING": 0.28,
            "SHUTTING_DOWN": 0.05,
        }.get(power_state, 0.0)
        fill = (10, 10, 11)
        rim = (
            58 + int(48 * pulse),
            58 + int(48 * pulse),
            60 + int(52 * pulse),
        )
        pygame.draw.rect(self.screen, fill, rect, border_radius=6)
        pygame.draw.rect(self.screen, rim, rect, 1, border_radius=6)
        highlight = pygame.Surface((rect.w - 4, max(4, rect.h // 2)), pygame.SRCALPHA)
        pygame.draw.rect(
            highlight,
            (255, 255, 255, 10 + int(18 * pulse)),
            highlight.get_rect(),
            border_radius=5,
        )
        self.screen.blit(highlight, (rect.x + 2, rect.y + 2))
        symbol_color = (
            108 + int(78 * pulse),
            108 + int(78 * pulse),
            112 + int(82 * pulse),
        )
        cx, cy = rect.center
        pygame.draw.circle(self.screen, symbol_color, (cx, cy + 1), 6, 2)
        pygame.draw.line(self.screen, symbol_color, (cx, cy - 8), (cx, cy + 1), 2)

    def _clamp01(self, value: float) -> float:
        return max(0.0, min(1.0, value))

    def _ease_out_cubic(self, value: float) -> float:
        t = self._clamp01(value)
        return 1.0 - (1.0 - t) ** 3

    def _ease_in_out(self, value: float) -> float:
        t = self._clamp01(value)
        return t * t * (3.0 - 2.0 * t)

    def _draw_power_scan_line(
        self,
        surface: pygame.Surface,
        y: int,
        width: int,
        height: int,
        alpha: int,
    ) -> None:
        sw, _sh = surface.get_size()
        line = pygame.Surface((max(1, width), max(1, height)), pygame.SRCALPHA)
        line.fill((96, 132, 154, alpha))
        surface.blit(line, (sw // 2 - width // 2, y - height // 2))

    def _draw_laptop_desktop_preview(
        self,
        surface: pygame.Surface,
        model=None,
        alpha: int = 255,
    ) -> None:
        """Draw a non-interactive copy of the normal desktop for boot fade-in."""
        sw, sh = surface.get_size()
        alpha = max(0, min(255, int(alpha)))
        if alpha <= 0:
            return

        desktop = pygame.Surface((sw, sh), pygame.SRCALPHA)
        desktop.blit(self.laptop_wallpaper, (0, 0))

        tb_h = 40
        tb_top = self._tb_top
        desktop.blit(self._tb_surf, (0, tb_top))

        line_alpha = 220
        pygame.draw.line(
            desktop,
            (100, 160, 255, line_alpha),
            (0, tb_top),
            (sw, tb_top),
        )

        start_rect = pygame.Rect(2, tb_top + 2, 86, 36)
        desktop.blit(self._start_btn_surf, start_rect.topleft)
        pygame.draw.rect(
            desktop,
            (20, 100, 20, line_alpha),
            start_rect,
            1,
            border_radius=4,
        )
        start_label = self._ctext(self._ui_font_bold, "start", (255, 255, 255))
        desktop.blit(start_label, (start_rect.x + 12, start_rect.y + 11))

        pygame.draw.line(
            desktop,
            (60, 100, 180, line_alpha),
            (start_rect.right + 4, tb_top + 6),
            (start_rect.right + 4, sh - 6),
        )

        tray_rect = pygame.Rect(sw - 120, tb_top, 120, tb_h)
        pygame.draw.rect(desktop, (30, 80, 160), tray_rect)
        pygame.draw.line(
            desktop,
            (80, 130, 210, line_alpha),
            (tray_rect.x, tb_top),
            (tray_rect.x, sh),
        )

        if model is not None:
            display_h = 12 if getattr(model, "hour", 0) == 0 else model.hour
            display_m = getattr(model, "timer", 0) // 60
            clock_str = f"{display_h}:{display_m:02d}"
        else:
            clock_str = "12:00"
        clock_label = self._ctext(self._ui_font_bold, clock_str, (255, 255, 255))
        desktop.blit(
            clock_label,
            (sw - clock_label.get_width() - 10, sh - tb_h + 11),
        )

        self._draw_xp_icon(30, 30, "claude", False, surface=desktop)
        desktop.set_alpha(alpha)
        surface.blit(desktop, (0, 0))

    def _draw_boot_status_panel(
        self,
        surface: pygame.Surface,
        progress: float,
        alpha: int,
    ) -> None:
        sw, sh = surface.get_size()
        p = self._clamp01(progress)
        alpha = max(0, min(255, int(alpha)))
        if alpha <= 0:
            return

        cx, cy = sw // 2, sh // 2
        layer = pygame.Surface((sw, sh), pygame.SRCALPHA)

        appear = self._ease_in_out(max(0.0, (p - 0.28) / 0.26))
        local_alpha = int(alpha * appear)
        if local_alpha <= 0:
            return

        title = self._ctext(self.font, "RTF OS", (210, 236, 246)).copy()
        title.set_alpha(local_alpha)
        layer.blit(title, (cx - title.get_width() // 2, cy - 74))

        subtitle = self._ctext(
            self._ui_font_sm, "secure workstation", (126, 158, 174)
        ).copy()
        subtitle.set_alpha(int(local_alpha * 0.86))
        layer.blit(subtitle, (cx - subtitle.get_width() // 2, cy - 34))

        line_t = self._ease_in_out((p - 0.36) / 0.46)
        line_w = int(sw * (0.10 + 0.24 * line_t))
        line_alpha = int(local_alpha * (0.46 + 0.18 * math.sin(p * math.tau * 2.0)))
        if line_w > 8 and line_alpha > 0:
            self._draw_power_scan_line(layer, cy + 2, line_w, 1, line_alpha)

        boot_lines = [
            (0.40, "checking cameras"),
            (0.52, "mounting local server"),
            (0.64, "loading night profile"),
            (0.76, "opening session"),
            (0.88, "starting desktop"),
        ]
        status_text = "starting services"
        for threshold, text in boot_lines:
            if p >= threshold:
                status_text = text
        dots = "." * (1 + int((p * 20) % 3))
        status = self._ctext(
            self._ui_font_sm,
            status_text + dots,
            (144, 176, 190),
        ).copy()
        status.set_alpha(int(local_alpha * 0.9))
        layer.blit(status, (cx - status.get_width() // 2, cy + 24))

        surface.blit(layer, (0, 0))

    def _draw_plain_boot_screen(
        self,
        surface: pygame.Surface,
        title: str,
        lines: list[str],
    ) -> None:
        sw, sh = surface.get_size()
        surface.fill((0, 0, 0))

        header_rect = pygame.Rect(28, 26, sw - 56, 34)
        pygame.draw.rect(surface, (7, 18, 24), header_rect)
        pygame.draw.rect(surface, (68, 112, 128), header_rect, 1)
        title_surf = self._ctext(self._ui_font_bold, title, (218, 238, 244))
        surface.blit(title_surf, (header_rect.x + 12, header_rect.y + 8))

        build = self._ctext(
            self._ui_font_sm,
            "RTF BOARD / NIGHT SHIFT TERMINAL",
            (98, 140, 154),
        )
        surface.blit(build, (header_rect.right - build.get_width() - 12, header_rect.y + 9))

        panel = pygame.Rect(28, 76, sw - 56, sh - 150)
        pygame.draw.rect(surface, (3, 8, 11), panel)
        pygame.draw.rect(surface, (46, 82, 94), panel, 1)

        left_w = min(300, panel.w // 2 - 20)
        left = pygame.Rect(panel.x + 14, panel.y + 14, left_w, panel.h - 28)
        right = pygame.Rect(left.right + 18, left.y, panel.right - left.right - 32, left.h)
        pygame.draw.rect(surface, (5, 13, 17), left)
        pygame.draw.rect(surface, (5, 13, 17), right)
        pygame.draw.rect(surface, (38, 76, 88), left, 1)
        pygame.draw.rect(surface, (38, 76, 88), right, 1)

        logo_lines = [
            "+-- R T F --+",
            "|  LAB-17  |",
            "+----------+",
        ]
        y = left.y + 18
        for line in logo_lines:
            txt = self._ctext(self._ui_font_sm, line, (162, 214, 226))
            surface.blit(txt, (left.x + 18, y))
            y += 24

        spec_lines = [
            "CPU      I386 COMPATIBLE",
            "RAM      262144 KB",
            "VIDEO    VGA TEXT MODE",
            "DISK 0   LOCAL SERVER",
            "CCTV     11 CHANNELS",
            "VENT     SEAL BUS READY",
        ]
        y += 14
        for line in spec_lines:
            key, value = line[:8], line[9:]
            k = self._ctext(self._ui_font_sm, key, (96, 132, 142))
            v = self._ctext(self._ui_font_sm, value, (188, 210, 214))
            surface.blit(k, (left.x + 18, y))
            surface.blit(v, (left.x + 104, y))
            y += 22

        right_title = self._ctext(self._ui_font_bold, "POST CHECK", (218, 238, 244))
        surface.blit(right_title, (right.x + 14, right.y + 14))
        y = right.y + 48
        visible = max(1, min(len(lines), int((pygame.time.get_ticks() // 170) % (len(lines) + 1))))
        if title != "RTF BIOS 1.04":
            visible = len(lines)
        for i, line in enumerate(lines[:visible]):
            color = (156, 204, 172) if "OK" in line or "READY" in line else (174, 194, 202)
            marker = "[OK]" if "OK" in line or "READY" in line else ">>"
            m = self._ctext(self._ui_font_sm, marker, (84, 172, 108) if marker == "[OK]" else (102, 150, 166))
            t = self._ctext(self._ui_font_sm, line, color)
            surface.blit(m, (right.x + 16, y))
            surface.blit(t, (right.x + 66, y))
            y += 24

        if visible < len(lines):
            cursor = "█" if (pygame.time.get_ticks() // 250) % 2 == 0 else " "
            cur = self._ctext(self._ui_font_sm, cursor, (184, 224, 232))
            surface.blit(cur, (right.x + 16, y))

        footer = pygame.Rect(28, sh - 58, sw - 56, 28)
        pygame.draw.rect(surface, (7, 18, 24), footer)
        pygame.draw.rect(surface, (46, 82, 94), footer, 1)
        footer_text = self._ctext(
            self._ui_font_sm,
            "DEL Setup   F8 Boot Menu   CTRL+ALT+DEL Restart",
            (128, 172, 184),
        )
        surface.blit(footer_text, (footer.x + 12, footer.y + 7))

    def _draw_plain_center_screen(
        self,
        surface: pygame.Surface,
        title: str,
        subtitle: str,
    ) -> None:
        sw, sh = surface.get_size()
        surface.fill((0, 0, 0))
        cx = sw // 2
        cy = sh // 2

        title_surf = self._ctext(self.font, title, (224, 238, 244))
        surface.blit(title_surf, (cx - title_surf.get_width() // 2, cy - 48))

        subtitle_surf = self._ctext(self._ui_font_sm, subtitle, (136, 158, 170))
        surface.blit(subtitle_surf, (cx - subtitle_surf.get_width() // 2, cy + 2))

    def _draw_boot_animation(
        self,
        surface: pygame.Surface,
        progress: float,
        model=None,
    ) -> None:
        sw, sh = surface.get_size()
        p = self._clamp01(progress)

        if p >= 0.88:
            self._draw_laptop_desktop_preview(surface, model=model, alpha=255)
            return

        surface.fill((0, 0, 0))

        if p < 0.22:
            self._draw_plain_boot_screen(
                surface,
                "RTF BIOS 1.04",
                [
                    "CPU CLOCK SYNC OK",
                    "MEMORY MAP OK",
                    "VIDEO ADAPTER OK",
                    "FIXED DISK OK",
                    "CCTV BUS READY",
                    "VENT CONTROL READY",
                    "BOOT DEVICE SELECTED",
                ],
            )
            return

        if p < 0.52:
            self._draw_plain_boot_screen(
                surface,
                "Starting RTF OS",
                [
                    "KERNEL IMAGE OK",
                    "LOCAL SERVER READY",
                    "CAMERA MATRIX READY",
                    "VENT SEAL DRIVER READY",
                    "NIGHT PROFILE LOADED",
                    "SESSION MANAGER STARTING",
                ],
            )
            return

        if p < 0.74:
            self._draw_plain_center_screen(
                surface,
                "RTF OS",
                "Please wait while the system starts",
            )
            return

        self._draw_plain_center_screen(
            surface,
            "Welcome",
            "Loading your personal settings",
        )

    def _draw_shutdown_animation(self, surface: pygame.Surface, progress: float) -> None:
        p = self._clamp01(progress)

        if p < 0.62:
            self._draw_plain_center_screen(
                surface,
                "RTF OS",
                "Saving your settings",
            )
            return

        self._draw_powered_off_screen(surface)

    def _fill_power_background(
        self,
        surface: pygame.Surface,
        top_color: tuple[int, int, int],
        bottom_color: tuple[int, int, int],
    ) -> None:
        sw, sh = surface.get_size()
        for y in range(sh):
            t = y / max(1, sh - 1)
            color = (
                int(top_color[0] + (bottom_color[0] - top_color[0]) * t),
                int(top_color[1] + (bottom_color[1] - top_color[1]) * t),
                int(top_color[2] + (bottom_color[2] - top_color[2]) * t),
            )
            pygame.draw.line(surface, color, (0, y), (sw, y))

    def _draw_panel_sheen(
        self,
        surface: pygame.Surface,
        alpha: int,
        width: int = 480,
        height: int = 220,
    ) -> None:
        # Старый метод оставлен для совместимости, но он больше не используется
        # в анимациях питания.
        sw, sh = surface.get_size()
        sheen = pygame.Surface((sw, sh), pygame.SRCALPHA)
        rect = pygame.Rect(sw // 2 - width // 2, sh // 2 - height // 2, width, height)
        band_h = max(18, height // 8)
        top_band = pygame.Rect(rect.x, rect.y + height // 5, rect.w, band_h)
        mid_band = pygame.Rect(rect.x, rect.centery - band_h // 2, rect.w, band_h)
        pygame.draw.rect(sheen, (172, 174, 178, alpha), top_band, border_radius=3)
        pygame.draw.rect(sheen, (58, 60, 64, alpha // 2), mid_band, border_radius=3)
        surface.blit(sheen, (0, 0), special_flags=pygame.BLEND_ADD)

    def _draw_boot_wake_screen(
        self, surface: pygame.Surface, phase_t: float
    ) -> None:
        self._draw_boot_animation(surface, phase_t * 0.18)

    def _draw_boot_post_screen(
        self, surface: pygame.Surface, phase_t: float
    ) -> None:
        self._draw_boot_animation(surface, 0.18 + phase_t * 0.44)

    def _draw_boot_loading_screen(
        self, surface: pygame.Surface, phase_t: float
    ) -> None:
        self._draw_boot_animation(surface, 0.62 + phase_t * 0.38)

    def _draw_shutdown_message_screen(
        self, surface: pygame.Surface, phase_t: float
    ) -> None:
        self._draw_shutdown_animation(surface, phase_t * 0.48)

    def _draw_shutdown_fade_screen(
        self, surface: pygame.Surface, phase_t: float
    ) -> None:
        self._draw_shutdown_animation(surface, 0.48 + phase_t * 0.52)

    def _draw_powered_off_screen(self, surface: pygame.Surface) -> None:
        surface.fill((0, 0, 0))
        sw, sh = surface.get_size()
        message = "It is now safe to turn on your computer"

        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 850.0)
        font = pygame.font.SysFont("tahoma", 22, bold=True)
        glow_alpha = int(28 + 22 * pulse)
        text_alpha = int(232 + 23 * pulse)

        glow = self._ctext(font, message, (82, 176, 214)).copy()
        glow.set_alpha(glow_alpha)
        x = sw // 2 - glow.get_width() // 2
        y = sh // 2 - glow.get_height() // 2 - 6
        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2)):
            surface.blit(glow, (x + dx, y + dy))

        shadow = self._ctext(font, message, (4, 8, 10)).copy()
        shadow.set_alpha(220)
        surface.blit(shadow, (x + 2, y + 2))

        text = self._ctext(font, message, (218, 246, 255)).copy()
        text.set_alpha(text_alpha)
        surface.blit(text, (x, y))

    def _draw_laptop_screen(self, model) -> None:
        sw, sh = self.screen_w, self.screen_h
        mx, my = (-100, -100)

        power_btn = pygame.Rect(sw - 112, sh - 78, 84, 34)
        self._laptop_power_btn = power_btn
        if model.laptop_power_state != "ON":
            self._draw_laptop_power_transition(model)

            self._laptop_icons = []
            self._laptop_menu_items = []
            self._laptop_start_rect = pygame.Rect(0, 0, 0, 0)
            return

        # ── Фон — обои ─────────────────────────────────────────────
        self.screen.blit(self.laptop_wallpaper, (0, 0))

        # ── Taskbar ──────────────────────────────────────────────────
        tb_h = 40
        tb_top = self._tb_top
        self.screen.blit(self._tb_surf, (0, tb_top))

        pygame.draw.line(
            self.screen, (100, 160, 255), (0, tb_top), (sw, tb_top)
        )

        # Кнопка Start — зелёный градиент как в XP
        start_rect = pygame.Rect(2, tb_top + 2, 86, 36)
        self.screen.blit(self._start_btn_surf, (start_rect.x, start_rect.y))
        pygame.draw.rect(
            self.screen, (20, 100, 20), start_rect, 1, border_radius=4
        )

        # Текст Start
        start_label = self._ctext(self._ui_font_bold, "start", (255, 255, 255))
        self.screen.blit(start_label, (start_rect.x + 12, start_rect.y + 11))
        self._laptop_start_rect = start_rect

        # Сепаратор после Start
        pygame.draw.line(
            self.screen,
            (60, 100, 180),
            (start_rect.right + 4, tb_top + 6),
            (start_rect.right + 4, sh - 6),
        )

        # Системный трей
        tray_rect = pygame.Rect(sw - 120, tb_top, 120, tb_h)
        pygame.draw.rect(self.screen, (30, 80, 160), tray_rect)
        pygame.draw.line(
            self.screen,
            (80, 130, 210),
            (tray_rect.x, tb_top),
            (tray_rect.x, sh),
        )

        # Часы — игровое время
        display_h = 12 if model.hour == 0 else model.hour
        display_m = model.timer // 60
        clock_str = f"{display_h}:{display_m:02d}"
        clock_label = self._ctext(self._ui_font_bold, clock_str, (255, 255, 255))
        self.screen.blit(
            clock_label, (sw - clock_label.get_width() - 10, sh - tb_h + 11)
        )

        # ── Иконки на рабочем столе ──────────────────────────────────
        icon_defs = [
            ("Claude Mythos", 30, 30, "claude"),
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
            self.screen.blit(self._menu_bg_surf, (menu_x, menu_y))
            pygame.draw.rect(
                self.screen,
                (80, 140, 255),
                (menu_x, menu_y, menu_w, menu_h),
                2,
            )

            # Шапка — полоса с именем пользователя
            head_h = 50
            head_rect = pygame.Rect(menu_x, menu_y, menu_w, head_h)
            pygame.draw.rect(self.screen, (50, 100, 200), head_rect)
            pygame.draw.line(
                self.screen,
                (100, 160, 255),
                (menu_x, menu_y + head_h),
                (menu_x + menu_w, menu_y + head_h),
            )

            # Аватарка
            pygame.draw.circle(
                self.screen, (200, 200, 200), (menu_x + 24, menu_y + 25), 16
            )
            pygame.draw.circle(
                self.screen, (100, 100, 100), (menu_x + 24, menu_y + 25), 16, 1
            )
            pygame.draw.circle(
                self.screen, (60, 60, 60), (menu_x + 24, menu_y + 22), 5
            )
            pygame.draw.ellipse(
                self.screen, (60, 60, 60), (menu_x + 14, menu_y + 28, 20, 14)
            )
            user_label = self._ctext(self._ui_font_bold, "Admin", (255, 255, 255))
            self.screen.blit(user_label, (menu_x + 48, menu_y + 18))

            # Сепаратор
            sep_y = menu_y + head_h
            pygame.draw.line(
                self.screen,
                (100, 160, 255),
                (menu_x + 4, sep_y + 4),
                (menu_x + menu_w - 4, sep_y + 4),
            )

            menu_items = [
                ("Claude Mythos", "claude"),
                ("Shutdown", "shutdown"),
            ]
            self._laptop_menu_items = []
            for i, (item_label, item_key) in enumerate(menu_items):
                iy = sep_y + 8 + i * 34
                item_rect = pygame.Rect(menu_x + 2, iy, menu_w - 4, 30)
                item_hovered = (
                    item_rect.collidepoint(mx, my) and item_key is not None
                )

                if item_hovered:
                    pygame.draw.rect(
                        self.screen, (40, 80, 200), item_rect, border_radius=3
                    )
                elif item_key is None:
                    pygame.draw.line(
                        self.screen,
                        (60, 100, 180),
                        (menu_x + 8, iy + 16),
                        (menu_x + menu_w - 8, iy + 16),
                    )
                    self._laptop_menu_items.append((item_rect, item_key))
                    continue

                if item_label:
                    txt = self._ctext(self._ui_font, item_label, (255, 255, 255))
                    self.screen.blit(txt, (menu_x + 12, iy + 7))
                self._laptop_menu_items.append((item_rect, item_key))

        # ── Claude Mythos — окно ─────────────────────────────────────
        if model.laptop_power_state == "ON" and model.laptop_app == "claude_mythos":
            win_w, win_h = 620, 440
            win_x = sw // 2 - win_w // 2
            win_y = sh // 2 - win_h // 2 - 20
            win_rect = pygame.Rect(win_x, win_y, win_w, win_h)

            # Тень — предзаготовленная
            self.screen.blit(self._shadow_surface, (win_x, win_y))

            # Фон окна
            pygame.draw.rect(self.screen, (236, 233, 216), win_rect)

            # Title bar — предзаготовленный градиент
            title_h = 26
            title_rect = pygame.Rect(win_x, win_y, win_w, title_h)
            self.screen.blit(self._title_bar_surf, (win_x, win_y))
            pygame.draw.rect(self.screen, (0, 0, 100), title_rect, 1)

            title_txt = self._ctext(self._ui_font_bold, model.night_app["title"], (255, 255, 255))
            self.screen.blit(title_txt, (win_x + 8, win_y + 5))

            # Кнопки управления — XP стиль
            btn_y = win_y + 3
            btn_w, btn_h = 21, 19

            # Свернуть
            min_btn = pygame.Rect(win_x + win_w - 68, btn_y, btn_w, btn_h)
            pygame.draw.rect(
                self.screen, (40, 100, 180), min_btn, border_radius=2
            )
            pygame.draw.rect(
                self.screen, (20, 60, 140), min_btn, 1, border_radius=2
            )
            pygame.draw.line(
                self.screen,
                (255, 255, 255),
                (min_btn.x + 4, min_btn.y + 14),
                (min_btn.x + 16, min_btn.y + 14),
                2,
            )

            # Развернуть
            max_btn = pygame.Rect(win_x + win_w - 45, btn_y, btn_w, btn_h)
            pygame.draw.rect(
                self.screen, (40, 100, 180), max_btn, border_radius=2
            )
            pygame.draw.rect(
                self.screen, (20, 60, 140), max_btn, 1, border_radius=2
            )
            pygame.draw.rect(
                self.screen,
                (255, 255, 255),
                (max_btn.x + 4, max_btn.y + 4, 13, 11),
                2,
            )

            # Закрыть
            close_btn = pygame.Rect(win_x + win_w - 22, btn_y, btn_w, btn_h)
            pygame.draw.rect(
                self.screen, (180, 60, 40), close_btn, border_radius=2
            )
            pygame.draw.rect(
                self.screen, (120, 30, 20), close_btn, 1, border_radius=2
            )
            close_x = self._ctext(self._ui_font_bold, "X", (255, 255, 255))
            self.screen.blit(close_x, (close_btn.x + 4, close_btn.y + 2))
            self._laptop_close_btn = close_btn

            # Линия под title bar
            pygame.draw.line(
                self.screen,
                (10, 60, 140),
                (win_x, win_y + title_h),
                (win_x + win_w, win_y + title_h),
            )

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

            lbl_server = self._ctext(self._ui_font_bold, status_txt, status_clr)
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
            srv_enabled = (
                model.server_state in ("OFF", "ON") and not is_overload
            )
            pygame.draw.rect(
                self.screen,
                srv_clr if srv_enabled else (160, 160, 160),
                srv_btn,
                border_radius=3,
            )
            pygame.draw.rect(
                self.screen, (30, 30, 30), srv_btn, 1, border_radius=3
            )
            srv_txt = self._ctext(self._ui_font_bold, srv_label, (255, 255, 255))
            self.screen.blit(
                srv_txt,
                (
                    srv_btn.x + srv_btn.w // 2 - srv_txt.get_width() // 2,
                    srv_btn.y + 4,
                ),
            )
            self._laptop_server_btn = srv_btn

            # Кнопка Reboot
            rebtn = pygame.Rect(win_x + 155, btn_server_y, 100, 24)
            re_enabled = is_overload or is_rebooting
            re_clr = (200, 140, 30) if re_enabled else (160, 160, 160)
            pygame.draw.rect(self.screen, re_clr, rebtn, border_radius=3)
            pygame.draw.rect(
                self.screen, (30, 30, 30), rebtn, 1, border_radius=3
            )
            re_txt = self._ctext(
                self._ui_font_bold,
                "REBOOT",
                (255, 255, 255) if re_enabled else (120, 120, 120),
            )
            self.screen.blit(
                re_txt,
                (
                    rebtn.x + rebtn.w // 2 - re_txt.get_width() // 2,
                    rebtn.y + 4,
                ),
            )
            self._laptop_reboot_btn = rebtn

            # ── Прогресс-бар ──────────────────────────────────────────
            term_x = win_x + 15
            if model.server_state == "ON":
                bar_x = win_x + 15
                bar_y = btn_server_y + 32
                bar_w = win_w - 30
                bar_h = 18
                pygame.draw.rect(
                    self.screen, (220, 220, 220), (bar_x, bar_y, bar_w, bar_h)
                )
                pygame.draw.rect(
                    self.screen, (160, 160, 160), (bar_x, bar_y, bar_w, bar_h), 1
                )
                fill = int(bar_w * model.hack_progress)
                if fill > 0:
                    clr = (40, 200, 40) if model.hack_active else (40, 140, 40)
                    pygame.draw.rect(
                        self.screen,
                        clr,
                        (bar_x + 1, bar_y + 1, fill - 2, bar_h - 2),
                    )
                pct = self._ctext(
                    self._ui_font_sm,
                    f"{int(model.hack_progress * 100)}%",
                    (30, 30, 30),
                )
                self.screen.blit(
                    pct, (bar_x + bar_w - pct.get_width() - 4, bar_y + 1)
                )
                term_y = bar_y + bar_h + 8
            else:
                offline_note = self._ctext(
                    self._ui_font_sm,
                    f"HACK PROGRESS SAVED: {int(model.hack_progress * 100)}%",
                    (150, 150, 150),
                )
                self.screen.blit(offline_note, (win_x + 15, btn_server_y + 35))
                term_y = btn_server_y + 58

            # ── Терминал — логи ───────────────────────────────────────
            term_w = win_w - 30
            term_h = win_h - (term_y - win_y) - 12

            # Фон терминала
            pygame.draw.rect(
                self.screen, (12, 12, 12), (term_x, term_y, term_w, term_h)
            )
            pygame.draw.rect(
                self.screen, (60, 60, 60), (term_x, term_y, term_w, term_h), 1
            )

            # Полоска заголовка терминала
            pygame.draw.rect(
                self.screen, (30, 30, 30), (term_x, term_y, term_w, 18)
            )
            term_hdr = self._ctext(self._ui_font_sm, model.night_app["header"], (120, 200, 120))
            self.screen.blit(term_hdr, (term_x + 6, term_y + 2))

            # Логи
            logs = model.hack_logs
            line_h = 14
            max_lines = (term_h - 22) // line_h
            visible = logs[-max_lines:] if len(logs) > max_lines else logs

            for i, log_line in enumerate(visible):
                clr = (
                    (180, 220, 180)
                    if log_line.startswith("[")
                    else (140, 180, 140)
                )
                if "ERROR" in log_line or "OVERLOAD" in log_line:
                    clr = (220, 80, 60)
                elif "COMPLETE" in log_line or "SUCCESS" in log_line:
                    clr = (80, 220, 80)
                rendered = self._ctext(self._ui_font_sm, log_line, clr)
                self.screen.blit(
                    rendered, (term_x + 6, term_y + 20 + i * line_h)
                )

            # Мигающий курсор
            if pygame.time.get_ticks() % 1000 < 600:
                cur_y = term_y + 20 + len(visible) * line_h
                if cur_y < term_y + term_h - 4:
                    pygame.draw.rect(
                        self.screen,
                        (180, 220, 180),
                        (term_x + 6, cur_y, 8, line_h - 2),
                    )

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
            pygame.draw.rect(
                self.screen, (200, 200, 200), self._ad_close_rect, 1
            )
            cross_cx, cross_cy = bx + btn_size // 2, by + btn_size // 2
            pygame.draw.line(
                self.screen,
                (255, 255, 255),
                (cross_cx - 6, cross_cy - 6),
                (cross_cx + 6, cross_cy + 6),
                2,
            )
            pygame.draw.line(
                self.screen,
                (255, 255, 255),
                (cross_cx + 6, cross_cy - 6),
                (cross_cx - 6, cross_cy + 6),
                2,
            )
        else:
            self._ad_close_rect = None

        # ── XP-курсор ────────────────────────────────────────────────
        cx, cy = mx, my
        cursor_pts = [
            (cx, cy),
            (cx, cy + 18),
            (cx + 5, cy + 14),
            (cx + 9, cy + 21),
            (cx + 12, cy + 19),
            (cx + 8, cy + 12),
            (cx + 15, cy + 10),
        ]
        # Тень
        shadow_pts = [(x + 1, y + 1) for x, y in cursor_pts]
        pygame.draw.polygon(self.screen, (40, 40, 40), shadow_pts)
        # Основной курсор
        pygame.draw.polygon(self.screen, (255, 255, 255), cursor_pts)
        pygame.draw.polygon(self.screen, (0, 0, 0), cursor_pts, 1)

    def _draw_cctv_effects(self, camera_idx, model):
        sw, sh = self.screen_w, self.screen_h

        # ── 1. Процедурный шум (numpy, low-res) ───────────────────────
        self._noise_timer -= 1
        if self._noise_timer <= 0:
            self._noise_timer = random.randint(1, 3)
            # Генерируем шум на маленькой surface
            arr = np.random.randint(0, 255, (self._noise_h, self._noise_w, 3), dtype=np.uint8)
            # Альфа: тихий шум normal, иногда burst
            self._noise_burst_timer -= 1
            if self._noise_burst_timer <= 0:
                self._noise_alpha = random.choice([25, 25, 25, 60, 80])
                self._noise_burst_timer = random.randint(120, 400)
            alpha_arr = np.full((self._noise_h, self._noise_w, 1), self._noise_alpha, dtype=np.uint8)
            rgba = np.concatenate([arr, alpha_arr], axis=2)
            raw = pygame.image.frombuffer(rgba.tobytes(), (self._noise_w, self._noise_h), "RGBA")
            self._noise_surf = pygame.transform.smoothscale(raw, (sw, sh))
        self.screen.blit(self._noise_surf, (0, 0))

        # ── 2. CRT сканлинии (скролл вниз) ───────────────────────────
        self._scanline_offset = (self._scanline_offset + 0.7) % 3
        self.screen.blit(self._scanline_surf, (0, int(self._scanline_offset)))

        # ── 3. Glitch Алгема (старые noice*.png) ──────────────────────
        if model.night > 1:
            on_target_cam = camera_idx in (
                model.algem_prev_location,
                model.algem_location,
            )
            if (
                model.algem_trigger > 0
                and on_target_cam
                and self._glitch_frames
            ):
                idx = (pygame.time.get_ticks() // 50) % len(self._glitch_frames)
                self.screen.blit(self._glitch_frames[idx], (0, 0))

        # ── 7. CRT curvature mask ─────────────────────────────────────
        self.screen.blit(self.crt_mask, (0, 0))

        from gameplay_model import CAMERAS

        cam_info = next(
            ((d, n) for i, d, n, _ in CAMERAS if i == camera_idx),
            ("??", "???"),
        )
        self._draw_camera_ui(*cam_info)

    def _draw_camera_ui(self, display_id, cam_name):
        # RECORD light (blinking)
        blink = (pygame.time.get_ticks() // 600) % 2 == 0
        if blink:
            pygame.draw.circle(
                self.screen, (255, 0, 0), (self.screen_w - 78, 28), 5
            )
            glow = self._rec_glow
            self.screen.blit(
                glow, (self.screen_w - 90, 16), special_flags=pygame.BLEND_ADD
            )

        # REC text
        rec_surf = self._ctext(self.font, "REC", (200, 30, 30))
        self.screen.blit(rec_surf, (self.screen_w - 70, 36))

        # Camera label — левый нижний угол
        label = f"CAM {display_id}  {cam_name}"
        label_surf = self._ctext(self.font, label, (180, 180, 190))
        self.screen.blit(
            label_surf,
            (self.screen_rect.x + 15, self.screen_rect.bottom - 35),
        )

        # Corruption on UI text (static interference)
        if random.random() < 0.15:
            for _ in range(random.randint(1, 4)):
                cx = random.randint(self.screen_w - 90, self.screen_w - 30)
                cy = random.randint(15, 50)
                c = random.choice(
                    [(255, 255, 255), (0, 0, 0), (100, 100, 100)]
                )
                self.screen.set_at((cx, cy), c)

    def _draw_minimap(self, model):
        mx, my = self._minimap_pos

        if self.vent_map_mode:
            self._draw_vent_map(model, mx, my)
            return

        self.screen.blit(self._minimap_bg, (mx, my))

        if model.camera_idx != self._prev_camera_idx:
            self._cam_blink_start = pygame.time.get_ticks()
            self._prev_camera_idx = model.camera_idx

        blink_green = (
            (pygame.time.get_ticks() - self._cam_blink_start) // 1000
        ) % 2 == 0

        for cidx, (cx, cy) in self._minimap_icon_positions.items():
            icon = self._cam_icons[cidx]
            ix = mx + cx - icon.get_width() // 2
            iy = my + cy - icon.get_height() // 2

            self.screen.blit(icon, (ix, iy))

            if cidx == model.camera_idx:
                color = (40, 220, 40) if blink_green else (100, 100, 100)
            else:
                color = (80, 80, 80)
            tint_key = (color, 140)
            tint = self._minimap_tint_cache.get(tint_key)
            if tint is None:
                tint = pygame.Surface(icon.get_size(), pygame.SRCALPHA)
                tint.fill((*color, 140))
                self._minimap_tint_cache[tint_key] = tint
            self.screen.blit(tint, (ix, iy))

            if (
                model.bait_active
                and cidx == model.bait_target_node
                and model.bait_cam_step < 3
            ):
                audio_idx = min(model.bait_cam_step, 3)
                ax = ix + icon.get_width() // 2 - 30
                ay = iy + icon.get_height() // 2 - 25
                self.screen.blit(self._audio_icons[audio_idx], (ax, ay))

            pygame.draw.rect(
                self.screen,
                (255, 255, 255),
                (ix - 3, iy - 3, icon.get_width() + 6, icon.get_height() + 6),
                1,
            )

        me_x, me_y = self._office_me_pos
        dot_x = mx + me_x
        dot_y = my + me_y
        pulse = (math.sin(pygame.time.get_ticks() * 0.004) + 1) / 2
        r = 4 + pulse * 2
        pygame.draw.circle(self.screen, (255, 255, 255), (dot_x, dot_y), int(r))
        pygame.draw.circle(self.screen, (120, 120, 120), (dot_x, dot_y), int(r), 1)
        me_label = self._ctext(self.font_small, "ME", (230, 230, 230))
        self.screen.blit(
            me_label,
            (dot_x - me_label.get_width() // 2, dot_y + 10),
        )

    def _draw_vent_map(self, model, mx, my):
        """Карта вентиляции: camera_map + duct-линии + камеры + seal-точки."""
        from gameplay_model import SealState

        # Основа — карта камер + duct-линии
        self.screen.blit(self._minimap_bg, (mx, my))
        self.screen.blit(self._vent_overlay, (mx, my))

        # Иконки вент-камер (8–11) — стиль FNAF3: серый прямоугольник + "CAM XX"
        for cidx, (cx, cy) in self._vent_cam_positions.items():
            icon = self._cam_icons.get(cidx)
            if icon is None:
                continue
            iw, ih = icon.get_width(), icon.get_height()
            ix = mx + cx - iw // 2
            iy = my + cy - ih // 2

            # Определяем активность
            is_active = (cidx == model.camera_idx)
            if is_active:
                blink_green = ((pygame.time.get_ticks() - self._cam_blink_start) // 1000) % 2 == 0
                tint_color = (40, 220, 40) if blink_green else (90, 90, 90)
                border_color = (40, 220, 40) if blink_green else (180, 180, 180)
            else:
                tint_color = (60, 60, 60)
                border_color = (140, 140, 140)

            # Фон иконки (полупрозрачный тёмный)
            bg = self._minimap_tint_cache.get("vent_bg")
            if bg is None:
                bg = pygame.Surface((iw, ih), pygame.SRCALPHA)
                bg.fill((10, 10, 10, 180))
                self._minimap_tint_cache["vent_bg"] = bg
            self.screen.blit(bg, (ix, iy))

            # Tint поверх иконки
            self.screen.blit(icon, (ix, iy))
            tint_key = (tint_color, 150)
            tint = self._minimap_tint_cache.get(tint_key)
            if tint is None:
                tint = pygame.Surface((iw, ih), pygame.SRCALPHA)
                tint.fill((*tint_color, 150))
                self._minimap_tint_cache[tint_key] = tint
            self.screen.blit(tint, (ix, iy))

            # Рамка
            pygame.draw.rect(self.screen, border_color, (ix - 2, iy - 2, iw + 4, ih + 4), 1)

        # Seal-точки — аутентичный стиль FNAF 3:
        # зелёная горизонтальная полоска + текст "SEAL" над ней
        self._seal_rects.clear()

        for sid, (sx, sy, direction) in self._seal_positions.items():
            state = model.seals.get(sid, SealState.OPEN)
            ix = mx + sx
            iy = my + sy

            if state == SealState.OPEN:
                bar_color = (40, 210, 40)  # зелёный
            elif state == SealState.SEALING:
                bar_color = (220, 180, 40)  # жёлтый — процесс закрывания
            else:  # CLOSED
                bar_color = (200, 50, 50)  # красный — полностью закрыта

            # FNAF3-style seal: полоска, ориентация зависит от direction
            # "H" = горизонтальная (22×5), "V" = вертикальная (5×22)
            if direction == "V":
                BAR_W, BAR_H = 5, 22
            else:
                BAR_W, BAR_H = 22, 5

            rx = ix - BAR_W // 2
            ry = iy - BAR_H // 2

            # Кликабельная зона
            click_rect = pygame.Rect(rx - 4, ry - 4, BAR_W + 8, BAR_H + 8)
            self._seal_rects[sid] = click_rect

            # Тёмный фон-подложка для читаемости
            seal_bg_key = (BAR_W, BAR_H)
            bg_surf = self._seal_bg_cache.get(seal_bg_key)
            if bg_surf is None:
                bg_surf = pygame.Surface((BAR_W + 2, BAR_H + 2), pygame.SRCALPHA)
                bg_surf.fill((0, 0, 0, 120))
                self._seal_bg_cache[seal_bg_key] = bg_surf
            self.screen.blit(bg_surf, (rx - 1, ry - 1))

            # Основная полоска
            pygame.draw.rect(self.screen, bar_color, (rx, ry, BAR_W, BAR_H))

            # Блик (светлая полоска по краю)
            highlight = (
                min(bar_color[0] + 80, 255),
                min(bar_color[1] + 80, 255),
                min(bar_color[2] + 80, 255),
            )
            if direction == "V":
                pygame.draw.line(self.screen, highlight, (rx + 1, ry + 1), (rx + 1, ry + BAR_H - 2))
            else:
                pygame.draw.line(self.screen, highlight, (rx + 1, ry + 1), (rx + BAR_W - 2, ry + 1))

            # Тонкая рамка
            pygame.draw.rect(self.screen, (200, 200, 200), (rx, ry, BAR_W, BAR_H), 1)

            # Glow (мягкое свечение вокруг)
            gw, gh = BAR_W + 10, BAR_H + 10
            glow = pygame.Surface((gw, gh), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*bar_color, 35), (5, 5, BAR_W, BAR_H))
            self.screen.blit(glow, (rx - 5, ry - 5), special_flags=pygame.BLEND_ADD)

        me_x, me_y = self._office_me_pos
        dot_x = mx + me_x
        dot_y = my + me_y
        pulse = (math.sin(pygame.time.get_ticks() * 0.004) + 1) / 2
        r = 4 + pulse * 2
        pygame.draw.circle(self.screen, (255, 255, 255), (dot_x, dot_y), int(r))
        pygame.draw.circle(self.screen, (120, 120, 120), (dot_x, dot_y), int(r), 1)
        me_label = self._ctext(self.font_small, "ME", (230, 230, 230))
        self.screen.blit(
            me_label,
            (dot_x - me_label.get_width() // 2, dot_y + 10),
        )

    def get_seal_clicked(self, mouse_pos):
        """Возвращает seal_id, если клик попал на seal-точку, иначе None."""
        if mouse_pos is None:
            return None
        for sid, rect in self._seal_rects.items():
            if rect.collidepoint(mouse_pos):
                return sid
        return None

    def get_vent_reset_clicked(self, mouse_pos):
        """Возвращает vent_id, если клик попал на кнопку RESET, иначе None."""
        if mouse_pos is None:
            return None
        for vid, rect in self._vent_reset_rects.items():
            if rect.collidepoint(mouse_pos):
                return vid
        return None

    def get_minimap_hotspot(self, screen_pos):
        mx, my = self._minimap_pos
        rx, ry = screen_pos
        pad = 6
        positions = self._vent_cam_positions if self.vent_map_mode else self._minimap_icon_positions
        for cidx, (cx, cy) in positions.items():
            icon = self._cam_icons.get(cidx)
            if icon is None:
                continue
            iw, ih = icon.get_size()
            ix = mx + cx - iw // 2
            iy = my + cy - ih // 2
            if (
                ix - pad <= rx <= ix + iw + pad
                and iy - pad <= ry <= iy + ih + pad
            ):
                return (cidx, f"CAM {cidx:02d}")
        return None

    def draw(self, model):
        offset = int((model.current_look + 1) / 2 * self.max_offset)

        # ── Зум на ноутбук ──────────────────────────────────────────
        if model.laptop_open:
            self._draw_laptop_screen(model)
            return

        if model.ad_active and model.ad_image_key in self._ad_office_images:
            self.screen.blit(
                self._ad_office_images[model.ad_image_key], (-offset, 0)
            )
        elif model.server_rebooting:
            self.screen.blit(self.bg_blinks.get("red", self.bg_off), (-offset, 0))
        elif model.hack_active and model.server_state == "ON":
            self.screen.blit(self.bg_hack, (-offset, 0))
        elif model.server_state == "OFF":
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

        if model.server_state == "ON" and (model.hack_active or model.hack_progress > 0):
            self._draw_hack_bar(model)

        if model.server_state != "OFF":
            pass  # двери нет

        # ── Экран ноутбука на столе (перспективный рендеринг) ───────
        if model.show_real_screen and not model.laptop_open:
            old_screen = self.screen
            self.screen = self._laptop_offscreen
            self._laptop_offscreen.fill((0, 0, 0))
            self._draw_laptop_screen(model)
            self.screen = old_screen

            small = pygame.transform.smoothscale(
                self._laptop_offscreen, (self._lp_out_w, self._lp_out_h)
            )
            rgb_src = pygame.surfarray.array3d(small).transpose(1, 0, 2)
            alpha_src = np.full((self._lp_out_h, self._lp_out_w), 255, dtype=np.uint8)

            bgr = cv2.cvtColor(rgb_src, cv2.COLOR_RGB2BGR)
            warped_rgb = cv2.warpPerspective(
                bgr, self._lp_M, (self._lp_out_w, self._lp_out_h)
            )
            warped_alpha = cv2.warpPerspective(
                alpha_src, self._lp_M, (self._lp_out_w, self._lp_out_h)
            )
            rgb = cv2.cvtColor(warped_rgb, cv2.COLOR_BGR2RGB)
            rgba = np.dstack([rgb, warped_alpha])
            surf = pygame.image.frombuffer(
                rgba.tobytes(), (self._lp_out_w, self._lp_out_h), "RGBA"
            )
            ox, oy = self._lp_blit_origin
            self.screen.blit(surf, (ox - offset, oy))

        if model.tablet_open or model.tablet_animating:
            if model.tablet_animating:
                self.screen.blit(
                    self.cam_frames[model.tablet_anim_frame], (0, 0)
                )
            else:
                # Планшет полностью открыт — рамка + контент камеры
                self.screen.blit(self.cam_frames[9], (0, 0))
                old_clip = self.screen.get_clip()
                self.screen.set_clip(self.screen_rect)

                # Прямой эфир камеры с панорамированием
                loc = model.algem_location if model.night > 1 else -1
                cam_idx = model.camera_idx

                if cam_idx == 4 and loc == 4:
                    if (
                        model.algem_main_hall_sprite == 0
                        and self._algem_main_hall_surf
                    ):
                        cam_surf = self._algem_main_hall_surf
                    elif (
                        model.algem_main_hall_sprite == 1
                        and self._algem_mainhall_watching
                    ):
                        cam_surf = self._algem_mainhall_watching
                    else:
                        cam_surf = self.camera_surfaces.get(4)
                elif loc == cam_idx:
                    cam_surf = self._algem_surfaces.get(cam_idx)
                    if cam_surf is None:
                        cam_surf = self.camera_surfaces.get(cam_idx)
                        if cam_surf is not None:
                            dark = pygame.Surface(
                                cam_surf.get_size(), pygame.SRCALPHA
                            )
                            dark.fill((0, 0, 0, 80))
                            cam_surf = cam_surf.copy()
                            cam_surf.blit(dark, (0, 0))
                else:
                    cam_surf = self.camera_surfaces.get(cam_idx)

                seal_id = SEAL_CAMERA_MAP.get(cam_idx)
                seal_state = model.seals.get(seal_id) if seal_id is not None else None
                if seal_state is not None and seal_state.name == "CLOSED":
                    cam_surf = self._closed_vent_surfaces.get(cam_idx, cam_surf)
                cam_max_off = self.camera_max_offsets.get(model.camera_idx, 0)
                if cam_surf is not None:
                    off = int((model.cam_look + 1) / 2 * cam_max_off)
                    self.screen.blit(
                        cam_surf,
                        (self.screen_rect.x - off, self.screen_rect.y),
                    )
                self._draw_cctv_effects(model.camera_idx, model)
                # Мини-карта внутри планшета
                self._draw_minimap(model)

                # Кнопки BAIT (сверху) и MAP (снизу) — слева от мини-карты
                mmx, mmy = self._minimap_pos
                bw, bh = self._btn_size
                gap = 15
                bx = mmx - bw - 15
                by = mmy + int(self._minimap_size[1] * 0.6)

                if not self.vent_map_mode:
                    if not model.bait_active:
                        self.screen.blit(self._btn_bg, (bx, by))
                        self.screen.blit(self._bait_btn_img, (bx, by))
                        pygame.draw.rect(
                            self.screen, (255, 255, 255), (bx, by, bw, bh), 1
                        )
                    else:
                        dot_y = by + bh // 2
                        dot_r = 3
                        dot_gap = 12
                        total_w = 5 * dot_gap
                        start_x = bx + bw // 2 - total_w // 2
                        for i in range(6):
                            if i <= model.bait_step:
                                pygame.draw.circle(
                                    self.screen,
                                    (255, 255, 255),
                                    (start_x + i * dot_gap, dot_y),
                                    dot_r,
                                )
                    self._bait_btn_rect.topleft = (bx, by)
                else:
                    self._bait_btn_rect.topleft = (-1000, -1000)
                    if model.currently_sealing_id is not None:
                        frame_idx = (pygame.time.get_ticks() // 300) % 3
                        self.screen.blit(self._seal_btn_frames[frame_idx], (bx, by))

                my = by + bh + gap
                self.screen.blit(self._btn_bg, (bx, my))
                self.screen.blit(self._map_btn_img, (bx, my))
                pygame.draw.rect(
                    self.screen, (255, 255, 255), (bx, my, bw, bh), 1
                )
                self._map_btn_rect.topleft = (bx, my)

                self.screen.set_clip(old_clip)

        # Кнопка TAB — на столе
        tx = (
            self.screen_rect.centerx
            - self.tabbutton_surf.get_width() // 2
            + self._tab_button_dx
        )
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
        self.screen.blit(
            self._ctext(self.font, time_str, (255, 255, 255)), (20, 22)
        )
        self.screen.blit(
            self._ctext(self.font, night_str, (200, 200, 200)), (20, 54)
        )

        # ── Стартовый экран ночи ─────────────────────────────────
        if model.night_start_ticks > 0:
            overlay = pygame.Surface((self.screen_w, self.screen_h))
            overlay.fill((0, 0, 0))
            self.screen.blit(overlay, (0, 0))
            display_hour = 12 if model.hour == 0 else model.hour
            title = self._ctext(
                self.font, f"Night {model.night}", (200, 200, 200)
            )
            sub = self._ctext(self.font, f"{display_hour} AM", (180, 180, 190))
            self.screen.blit(
                title,
                (
                    self.screen_w // 2 - title.get_width() // 2,
                    self.screen_h // 2 - 40,
                ),
            )
            self.screen.blit(
                sub,
                (
                    self.screen_w // 2 - sub.get_width() // 2,
                    self.screen_h // 2 + 10,
                ),
            )

        # ── Перегрузка / перезагрузка сервера ───────────────────
        if model.server_overload or model.server_rebooting:
            panel_w, panel_h = 360, 48
            px = (self.screen_w - panel_w) // 2
            py = 90
            color = (255, 60, 60) if model.server_overload else (60, 255, 60)
            if (
                model.server_overload
                and (pygame.time.get_ticks() // 300) % 2 == 0
            ):
                overlay = pygame.Surface(
                    (self.screen_w, self.screen_h), pygame.SRCALPHA
                )
                overlay.fill((255, 0, 0, 20))
                self.screen.blit(overlay, (0, 0))
            if model.server_overload:
                txt = self._ctext(
                    self.font,
                    "OVERLOAD! OPEN LAPTOP TO REBOOT", color
                )
            else:
                dots = "." * ((pygame.time.get_ticks() // 600) % 4)
                txt = self._ctext(self.font, f"REBOOTING{dots}", color)
            self.screen.blit(
                txt,
                (
                    px + (panel_w - txt.get_width()) // 2,
                    py + (panel_h - txt.get_height()) // 2,
                ),
            )

        self.screen.blit(self._brightness_overlay, (0, 0))

        # ── Глитч: мерцание — офис, картинка, офис, картинка... ────────
        if model._glitch_active and self._glitch_surfs:
            if model._glitch_frame == 1:
                idx = (model._glitch_timer // 2) % len(self._glitch_surfs)
                self.screen.blit(self._glitch_surfs[idx], (0, 0))
