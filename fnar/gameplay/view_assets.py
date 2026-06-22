"""Load and precompute all surfaces used by the gameplay view."""

import glob
import os
import random

import numpy as np
import pygame

from .laptop_projection import (
    DEFAULT_LAPTOP_PROJECTION_CORNERS,
    LAPTOP_PROJECTION_CONFIG_PATH,
)
from fnar.services.visual_assets import (
    normalize_brightness as _normalize_brightness,
    safe_font as _safe_font,
    safe_load_image as _safe_load_image,
)


class ViewAssetsMixin:
    """Initialize immutable assets and reusable rendering surfaces."""

    def __init__(self, screen):
        """Выполняет специализированную операцию «init» в подсистеме view assets."""
        self.screen = screen
        try:
            screen_w, screen_h = screen.get_size()
        except pygame.error:
            pygame.display.init()
            screen = pygame.display.set_mode((1280, 720))
            self.screen = screen
            screen_w, screen_h = screen.get_size()

        raw_off = _safe_load_image(
            "assets/office/server_is_off.png"
        )
        scale = screen_h / raw_off.get_height()
        target_size = (int(raw_off.get_width() * scale), screen_h)

        self.bg_off = pygame.transform.smoothscale(raw_off, target_size)

        self.bg_blinks = {}
        for name, key in [
            ("server_all_four_lights_are_red.png", "red"),
            ("server_all_four_lights_are_green.png", "green"),
        ]:
            raw = _safe_load_image(f"assets/office/{name}")
            self.bg_blinks[key] = pygame.transform.smoothscale(
                raw, target_size
            )

        self.bg_frames = []
        for name in [
            "server_all_four_lights_are_green.png",
            "server_all_four_lights_are_green.png",
        ]:
            raw = _safe_load_image(f"assets/office/{name}")
            self.bg_frames.append(
                pygame.transform.smoothscale(raw, target_size)
            )

        raw_hack = _safe_load_image(
            "assets/office/server_all_four_lights_are_green+hack_is_going.png"
        )
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
        self.font = _safe_font("assets/fonts/OCR-A.ttf", 30)
        self.font_small = _safe_font("assets/fonts/OCR-A.ttf", 18)
        self.font_very_small = _safe_font("assets/fonts/OCR-A.ttf", 11)
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
        raw_tab = _safe_load_image(
            "assets/cctv/tabbutton.png", alpha=True
        )
        self.tabbutton_surf = pygame.transform.scale(
            raw_tab, (int(600 * scale), int(60 * scale))
        )
        self._tab_button_margin_right = 120
        self._tab_button_margin_bottom = 8
        self.tab_button_rect = pygame.Rect(
            662, 758, 600, 60
        )  # оригинальные координаты (1923×818)
        self.tab_button_hovered = False

        raw_wallpaper = _safe_load_image(
            "assets/laptop/wallpaper.png"
        )
        self.laptop_wallpaper = pygame.transform.smoothscale(
            raw_wallpaper, (screen_w, screen_h - 40)
        )

        self._ad_images = {}
        for key in ["ad_hhru", "ad_kontur", "ad_sber"]:
            raw = _safe_load_image(f"assets/laptop/{key}.png")
            rw, rh = raw.get_size()
            scale = min((screen_w - 40) / rw, (screen_h - 80) / rh)
            self._ad_images[key] = pygame.transform.smoothscale(
                raw, (int(rw * scale), int(rh * scale))
            )

        self._ad_office_images = {}
        for key in ["ad_hhru", "ad_kontur", "ad_sber"]:
            raw = _safe_load_image(
                f"assets/office/server_all_four_lights_are_green+{key}.png"
            )
            self._ad_office_images[key] = pygame.transform.smoothscale(
                raw, target_size
            )
        _normalize_brightness(
            [
                (
                    self._ad_office_images[key],
                    f"assets/office/server_all_four_lights_are_green+{key}.png",
                )
                for key in ["ad_hhru", "ad_kontur", "ad_sber"]
            ]
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
            img = _safe_load_image(f"assets/cctv/{fname}", alpha=True)
            self._cam_icons[idx] = pygame.transform.scale(img, (30, 25))

        # Мини-карта (справа в планшете, uniform scale)
        raw_map = _safe_load_image(
            "assets/cameras/camera_map.png", alpha=True
        )
        mm_map_w, mm_map_h = raw_map.get_size()  # 595×550
        self._mm_scale = 500 / mm_map_w  # uniform scale ≈ 0.84
        mm_w, mm_h = 500, int(mm_map_h * self._mm_scale)
        self._minimap_bg = pygame.transform.smoothscale(raw_map, (mm_w, mm_h))
        self._minimap_bg.set_alpha(220)
        self._minimap_pos = (
            self.screen_rect.right - mm_w - 5,
            self.screen_rect.bottom - mm_h - 34,
        )
        self._minimap_size = (mm_w, mm_h)

        # Карта вентиляции: прозрачный оверлей (белые контуры + синие duct-линии)
        raw_vent = _safe_load_image(
            "assets/cameras/vent_map.png", alpha=True
        )
        vw, vh = raw_vent.get_size()
        self._vent_overlay = pygame.transform.smoothscale(
            raw_vent, (mm_w, mm_h)
        )
        self.vent_map_mode = False  # False = камеры, True = вентиляция

        self._cam_blink_start = 0
        self._prev_camera_idx = 1

        vent_sx = mm_w / vw
        vent_sy = mm_h / vh

        # Иконки вент-камер (8–11) — внутри duct-проходов.
        # Порядок по запросу: 8 = низ-право, 9 = верх-право, 10 = верх-лево, 11 = низ-лево.
        # Реальные duct'ы в vent_map.png (1306x1204):
        #   Горизонт. верхний:  y≈45,  x: 16–1127
        #   Горизонт. средний:  y≈560, x: 16–1127
        #   Горизонт. нижний:   y≈903, x: 16–170
        #   Вертик. левый:      x≈18,  y: 43–906
        #   Вертик. средний:    x≈339, y: 43–541
        #   Вертик. правый:     x≈1124,y: 43–746
        self._vent_cam_positions = {
            8:  (int(1124 * vent_sx), int(620 * vent_sy)),  # правый вертик. duct, нижняя часть
            9:  (int(900 * vent_sx),  int(45 * vent_sy)),   # верхний горизонт. duct, правая часть
            10: (int(18 * vent_sx),   int(145 * vent_sy)),  # левый вертик. duct, верхняя часть
            11: (int(18 * vent_sx),   int(750 * vent_sy)),  # левый вертик. duct, нижняя часть
        }

        # Точки блокировки (SEAL) — (sx, sy, direction) в координатах vent overlay
        # direction: "V" = вертикальная полоска поперёк горизонт. duct'а
        #            "H" = горизонтальная полоска поперёк вертик. duct'а
        # Точные центры duct-линий из vent_map.png (по пикселям):
        #   верхний горизонт: y=45    левый вертик: x=18
        #   правый вертик: x=1124   нижний горизонт: y=903
        self._seal_positions = {
            "SEAL_TOP_RIGHT":   (int(1050 * vent_sx), int(45 * vent_sy),   "V"),  # верхн. duct, левее перекрёстия
            "SEAL_CENTER":      (int(18 * vent_sx),   int(200 * vent_sy),  "H"),  # левый duct, под CAM10
            "SEAL_MID_RIGHT":   (int(1124 * vent_sx), int(700 * vent_sy),  "H"),  # правый duct, ниже CAM08
            "SEAL_BOTTOM_LEFT": (int(18 * vent_sx),   int(845 * vent_sy),  "H"),  # нижний левый duct, ниже CAM11
        }
        self._seal_rects: dict[str, pygame.Rect] = {}

        # Координаты центров иконок в пространстве мини-карты (500×462)
        # Кроме коворкинга — у него координата левого верхнего угла
        self._minimap_icon_positions = {
            1: (447, 303),  # ALGEM'S ROOM
            2: (331, 120),  # CANTEEN
            3: (270, 279),  # TOILETS
            4: (207, 334),  # MAIN HALL
            5: (88, 213),  # WEST HALL
            6: (32, 116),  # COWORKING
            7: (148, 65),  # SERVICE ROOM
        }
        self._office_me_pos = (245, 76)

        # Камеры — каждая грузится, масштабируется под высоту screen_rect, затемняется и тонируется
        from .model import CAMERAS

        self.camera_surfaces = {}
        self._closed_vent_surfaces: dict[int, pygame.Surface] = {}
        self._algem_retreat_surfaces: dict[int, pygame.Surface] = {}
        self.camera_max_offsets = {}
        cam_h = self.screen_rect.h
        for idx, _display_id, name, fname in CAMERAS:
            path = f"assets/cameras/{fname}"
            if not os.path.exists(path):
                path = f"assets/vents_cameras/{fname}"
            raw = _safe_load_image(path)
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
            """Load one camera background and apply the CCTV dark-purple grade."""
            try:
                raw = _safe_load_image(path)
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
            """Pre-render Windows-like gradients reused by the laptop renderer."""
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
            8: "cam_11_closed.png",
            9: "cam_8_closed.png",
            10: "cam_9_closed.png",
            11: "cam_10_closed.png",
        }
        for cam_idx, fname in closed_cam_files.items():
            path = f"assets/vents_cameras/{fname}"
            surf = _load_cam(path)
            if surf is not None:
                self._closed_vent_surfaces[cam_idx] = surf

        retreat_name_roots = {
            8: ["cam_8", "cam8", "cam11"],
            9: ["cam_9", "cam9", "cam8"],
            10: ["cam_10", "cam10", "cam9"],
            11: ["cam_11", "cam11", "cam10"],
        }
        retreat_suffixes = (
            "_with_leaving_algem",
            "_with_algem_leaving",
            "_algem_leaving",
            "_leaving",
            "_with_algem_retreat",
            "_algem_retreat",
            "_retreat",
            "_backward",
            "_back",
        )
        retreat_search_dirs = ("assets/vents_cameras", "assets/cameras")
        for cam_idx, roots in retreat_name_roots.items():
            candidate_paths: list[str] = []
            for folder in retreat_search_dirs:
                for root in roots:
                    for suffix in retreat_suffixes:
                        candidate_paths.append(f"{folder}/{root}{suffix}.png")
                    candidate_paths.extend(sorted(glob.glob(f"{folder}/{root}*leaving*.png")))
                    candidate_paths.extend(sorted(glob.glob(f"{folder}/{root}*retreat*.png")))
                    candidate_paths.extend(sorted(glob.glob(f"{folder}/{root}*leav*.png")))
                    candidate_paths.extend(sorted(glob.glob(f"{folder}/{root}*back*.png")))
            seen: set[str] = set()
            for path in candidate_paths:
                if path in seen or not os.path.exists(path):
                    continue
                seen.add(path)
                surf = _load_cam(path)
                if surf is not None:
                    self._algem_retreat_surfaces[cam_idx] = surf
                    break

        algem_files = {
            1: "algems' room_with_algem.png",
            2: "canteen_algem.png",
            3: "toilets_algem.png",
            4: "main_hall_with_algem.png",
            5: "westhall_algem.png",
            6: "coworking_algem.png",
            7: "service_room_algem.png",
            8: "cam11_with_algem.png",
            9: "cam8_with_algem.png",
            10: "cam9_with_algem.png",
            11: "cam10_with_algem.png",
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
        crt_path = os.path.join(os.environ.get("APPDATA", "."), "FiveNightsAtRTF", "crt_mask.png")
        if os.path.exists(crt_path):
            self.crt_mask = _safe_load_image(crt_path, alpha=True)
        else:
            os.makedirs(os.path.dirname(crt_path), exist_ok=True)
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
        self._noise_alpha = 30

        # Сканлинии (crt scanlines) — кэшируются, скроллятся
        self._scanline_surf = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        for y in range(0, screen_h, 3):
            pygame.draw.line(self._scanline_surf, (0, 0, 0, 22), (0, y), (screen_w, y))
        self._scanline_offset = 0

        # Glitch frames для Алгема (старые noice*.png)
        self._glitch_frames = []
        for fname in sorted(os.listdir("assets/cctv") if os.path.isdir("assets/cctv") else ()):
            if fname.lower().startswith("noice") and (
                fname.lower().endswith(".png")
                or fname.lower().endswith(".jpg")
            ):
                img = _safe_load_image(f"assets/cctv/{fname}")
                s = pygame.transform.smoothscale(img, (screen_w, screen_h))
                s.set_alpha(255)
                self._glitch_frames.append(s)

        # Планшет — 10 отдельных картинок без фона
        self.cam_frames = []
        for i in range(1, 11):
            img = _safe_load_image(
                f"assets/office/tablet/tablet-{i}.png", alpha=True
            )
            self.cam_frames.append(
                pygame.transform.smoothscale(img, (screen_w, screen_h))
            )

        # Кнопка Mute Call (на столе офиса)
        raw_mute = _safe_load_image(
            "assets/office/mutecall.png", alpha=True
        )
        mute_scale = 112 / raw_mute.get_width()
        self.mutecall_surf = pygame.transform.scale(
            raw_mute, (112, int(raw_mute.get_height() * mute_scale))
        )
        self._mutecall_rect = pygame.Rect(0, 0, *self.mutecall_surf.get_size())

        # Кнопки BAIT и MAP — одинаковый размер
        self._btn_size = (64, 34)
        self._bait_btn_icon_size = (56, 28)
        self._map_btn_icon_size = (52, 26)
        raw_bait = _safe_load_image(
            "assets/cameras/playaudio.png", alpha=True
        )
        raw_map = _safe_load_image(
            "assets/cameras/maptoggle.png", alpha=True
        )
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
            img = _safe_load_image(
                f"assets/cameras/audio{i}.png", alpha=True
            )
            self._audio_icons.append(pygame.transform.scale(img, (60, 50)))

        # ── Глитч-картинки ─────────────────────────────────────────────
        self._glitch_surfs = []
        for fname in ("glitch1.png", "glitch2.png"):
            try:
                raw = _safe_load_image(f"assets/glithces/{fname}")
                self._glitch_surfs.append(
                    pygame.transform.smoothscale(raw, (screen_w, screen_h))
                )
            except pygame.error:
                pass
