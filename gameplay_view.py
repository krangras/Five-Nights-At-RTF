import pygame
import random
import os

def _normalize_brightness(images, target=15):
    for img in images:
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
        _normalize_brightness([self.bg_off] + list(self.bg_blinks.values()) + self.bg_frames)

        self.max_offset = max(0, target_size[0] - screen_w)
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._brightness_overlay = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        self._brightness_overlay.fill((255, 255, 255, 13))
        self.font = pygame.font.Font("assets/fonts/OCR-A.ttf", 30)
        self.switch_timer = random.randint(60, 180)
        self.current_idx = 0
        self.scale = scale
        self.server_hotspot = pygame.Rect(1151, 163, 131, 244)

        # Кнопка TAB в офисе (изображение на столе)
        raw_tab = pygame.image.load("assets/cctv/tabbutton.png").convert_alpha()
        self.tabbutton_surf = pygame.transform.smoothscale(raw_tab, (int(600 * scale), int(60 * scale)))
        self.tab_button_rect = pygame.Rect(662, 758, 600, 60)  # оригинальные координаты (1923×818)
        self.tab_button_hovered = False

        # Область экрана планшета — отступаем от краёв, чтобы не задеть рамку
        self.screen_rect = pygame.Rect(2, 2, screen_w - 32, screen_h - 5)

        # Иконки камер из assets/cctv/ — загружаются, маппинг по номеру камеры
        self._cam_icons = {}
        icon_map = {1: "cam1.png", 2: "cam2.png", 3: "cam3.png", 4: "cam4.png", 5: "cam5.png", 6: "cam6.png", 7: "cam7.png"}
        for idx, fname in icon_map.items():
            img = pygame.image.load(f"assets/cctv/{fname}").convert_alpha()
            self._cam_icons[idx] = pygame.transform.smoothscale(img, (30, 25))

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
            1: (207, 334),  # MAIN HALL — самый низ
            2: (447, 303),  # ALGEM'S ROOM
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
            2: "algems' room_with_algem.png",
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

        # CRT curvature mask + deep vignette
        self.crt_mask = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        cx, cy = screen_w / 2, screen_h / 2
        max_dist = ((cx) ** 2 + (cy) ** 2) ** 0.5
        for y in range(screen_h):
            for x in range(screen_w):
                dx, dy = x - cx, y - cy
                r = ((dx * dx + dy * dy) ** 0.5) / max_dist
                a = int(min(255, r * r * 230))
                self.crt_mask.set_at((x, y), (0, 0, 0, a))

        # Индикаторы энергии
        self._power_icons = {}
        for name in ["veryhigh", "high", "premid", "mid", "low"]:
            try:
                img = pygame.image.load(f"assets/cctv/{name}.png").convert_alpha()
                self._power_icons[name] = pygame.transform.smoothscale(img, (32, 32))
            except pygame.error:
                self._power_icons[name] = None

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
        for fname in sorted(os.listdir("assets/cctv")):
            if fname.lower().startswith("noice") and (fname.lower().endswith(".png") or fname.lower().endswith(".jpg")):
                img = pygame.image.load(f"assets/cctv/{fname}").convert()
                s = pygame.transform.smoothscale(img, (screen_w, screen_h))
                self._glitch_frames.append(s)

        # Планшет — 10 отдельных картинок без фона
        self.cam_frames = []
        for i in range(1, 11):
            img = pygame.image.load(f"assets/office/tablet/tablet-{i}.png").convert_alpha()
            self.cam_frames.append(pygame.transform.smoothscale(img, (screen_w, screen_h)))

        # Кнопка Mute Call (на столе офиса)
        raw_mute = pygame.image.load("assets/office/mutecall.png").convert_alpha()
        mute_scale = 140 / raw_mute.get_width()
        self.mutecall_surf = pygame.transform.smoothscale(raw_mute, (140, int(raw_mute.get_height() * mute_scale)))
        self._mutecall_rect = pygame.Rect(0, 0, *self.mutecall_surf.get_size())

        # Кнопки BAIT и MAP — одинаковый размер
        self._btn_size = (64, 34)
        raw_bait = pygame.image.load("assets/cameras/playaudio.png").convert_alpha()
        raw_map = pygame.image.load("assets/cameras/maptoggle.png").convert_alpha()
        self._bait_btn_img = pygame.transform.smoothscale(raw_bait, self._btn_size)
        self._map_btn_img = pygame.transform.smoothscale(raw_map, self._btn_size)
        self._btn_bg = pygame.Surface(self._btn_size, pygame.SRCALPHA)
        self._btn_bg.fill((15, 15, 25, 200))
        self._bait_btn_rect = pygame.Rect(0, 0, *self._btn_size)
        self._map_btn_rect = pygame.Rect(0, 0, *self._btn_size)

        # Аудио-иконки для мини-карты (audio1-4.png)
        self._audio_icons = []
        for i in range(1, 5):
            img = pygame.image.load(f"assets/cameras/audio{i}.png").convert_alpha()
            self._audio_icons.append(pygame.transform.smoothscale(img, (60, 50)))

    def is_server_clicked(self, mouse_pos, offset):
        img_x = (mouse_pos[0] + offset) / self.scale
        img_y = mouse_pos[1] / self.scale
        return self.server_hotspot.collidepoint(img_x, img_y)

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

    def _draw_cctv_effects(self, camera_idx, model):
        # Шум/помехи
        self._noise_timer -= 1
        if self._noise_timer <= 0:
            self._noise_idx = (self._noise_idx + 1) % len(self._noise_frames)
            self._noise_timer = random.randint(1, 3)
        self.screen.blit(self._noise_frames[self._noise_idx], (0, 0))

        # Всплеск помех только на камере, с которой ушёл или на которую пришёл Алгем
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

        # Camera label
        label = f"CAM {display_id}  {cam_name}"
        label_surf = self.font.render(label, True, (180, 180, 190))
        self.screen.blit(label_surf, (15, 12))

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
                loc = model.algem_location
                cam_idx = model.camera_idx

                if cam_idx == 1 and loc == 1:
                    if model.algem_main_hall_sprite == 0 and self._algem_main_hall_surf:
                        cam_surf = self._algem_main_hall_surf
                    elif model.algem_main_hall_sprite == 1 and self._algem_mainhall_watching:
                        cam_surf = self._algem_mainhall_watching
                    else:
                        cam_surf = self.camera_surfaces.get(1)
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
                    if cam_idx == 2 and cam_surf is not None:
                        dark = pygame.Surface(cam_surf.get_size(), pygame.SRCALPHA)
                        dark.fill((0, 0, 0, 80))
                        cam_surf = cam_surf.copy()
                        cam_surf.blit(dark, (0, 0))
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

        if model.server_state != "OFF":
            # Выбор иконки энергии по уровню
            p = model.power
            if p >= 80:     icon_name = "veryhigh"
            elif p >= 60:   icon_name = "high"
            elif p >= 40:   icon_name = "premid"
            elif p >= 20:   icon_name = "mid"
            else:           icon_name = "low"
            icon = self._power_icons.get(icon_name)
            if icon:
                self.screen.blit(icon, (20, 20))
            status = f"Night {model.night} | Power: {int(p)}% | Time: {model.hour} AM"
            self.screen.blit(self.font.render(status, True, (255, 255, 255)), (60, 22))

        # ── Game over / Night complete ──────────────────────────
        if model.night_complete:
            overlay = pygame.Surface((self.screen_w, self.screen_h))
            overlay.fill((0, 0, 0))
            self.screen.blit(overlay, (0, 0))
            txt = self.font.render("6 AM", True, (30, 200, 30))
            self.screen.blit(txt, (self.screen_w // 2 - txt.get_width() // 2, self.screen_h // 2 - 30))

        self.screen.blit(self._brightness_overlay, (0, 0))