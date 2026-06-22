"""Rendering and interaction helpers for CCTV and ventilation cameras."""

import math
import random

import numpy as np
import pygame

from .camera_graph import is_vent_detour_away_from_office


class CameraRendererMixin:
    """Render CCTV effects, camera UI, maps, and ventilation seals."""

    def _draw_cctv_effects(self, camera_idx, model, suppress_algem_glitch: bool = False):
        sw, sh = self.screen_w, self.screen_h

        # ── 1. Процедурный шум (numpy, low-res) ───────────────────────
        self._noise_timer -= 1
        if self._noise_timer <= 0:
            self._noise_timer = random.randint(1, 3)
            # Генерируем шум на маленькой surface
            arr = np.random.randint(0, 255, (self._noise_h, self._noise_w, 3), dtype=np.uint8)
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
                not suppress_algem_glitch
                and model.algem_trigger > 0
                and on_target_cam
                and self._glitch_frames
            ):
                idx = (pygame.time.get_ticks() // 50) % len(self._glitch_frames)
                self.screen.blit(self._glitch_frames[idx], (0, 0))

        # ── 7. CRT curvature mask ─────────────────────────────────────
        self.screen.blit(self.crt_mask, (0, 0))

        from .model import CAMERAS

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
        """Карта вентиляции: camera_map + duct-линии + камеры + seal-точки.

        Args:
            model: Входной параметр метода ``_draw_vent_map``.
            mx: Входной параметр метода ``_draw_vent_map``.
            my: Входной параметр метода ``_draw_vent_map``.

        Returns:
            Результат выполнения метода; для процедурных методов — ``None``."""
        from .model import SealState

        # Основа — карта камер + duct-линии
        self.screen.blit(self._minimap_bg, (mx, my))
        self.screen.blit(self._vent_overlay, (mx, my))

        # Иконки вент-камер (8–11) — старые спрайты, но переставлены по новым позициям.
        for cidx, (cx, cy) in self._vent_cam_positions.items():
            icon = self._cam_icons.get(cidx)
            if icon is None:
                continue
            iw, ih = icon.get_width(), icon.get_height()
            ix = mx + cx - iw // 2
            iy = my + cy - ih // 2

            is_active = (cidx == model.camera_idx)
            if is_active:
                blink_green = ((pygame.time.get_ticks() - self._cam_blink_start) // 1000) % 2 == 0
                tint_color = (40, 220, 40) if blink_green else (90, 90, 90)
                border_color = (40, 220, 40) if blink_green else (180, 180, 180)
            else:
                tint_color = (60, 60, 60)
                border_color = (140, 140, 140)

            bg = self._minimap_tint_cache.get("vent_bg")
            if bg is None:
                bg = pygame.Surface((iw, ih), pygame.SRCALPHA)
                bg.fill((10, 10, 10, 180))
                self._minimap_tint_cache["vent_bg"] = bg
            self.screen.blit(bg, (ix, iy))

            self.screen.blit(icon, (ix, iy))
            tint_key = (tint_color, 150)
            tint = self._minimap_tint_cache.get(tint_key)
            if tint is None:
                tint = pygame.Surface((iw, ih), pygame.SRCALPHA)
                tint.fill((*tint_color, 150))
                self._minimap_tint_cache[tint_key] = tint
            self.screen.blit(tint, (ix, iy))

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
        """Возвращает seal_id, если клик попал на seal-точку, иначе None.

        Args:
            mouse_pos: Входной параметр метода ``get_seal_clicked``.

        Returns:
            Результат выполнения метода; для процедурных методов — ``None``."""
        if mouse_pos is None:
            return None
        for sid, rect in self._seal_rects.items():
            if rect.collidepoint(mouse_pos):
                return sid
        return None

    def get_minimap_hotspot(self, screen_pos):
        from .model import CAMERAS

        display_ids = {idx: disp for idx, disp, _name, _fname in CAMERAS}
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
                return (cidx, f"CAM {display_ids.get(cidx, f'{cidx:02d}')}")
        return None
    def _should_show_directional_vent_leave(self, model, cam_idx: int) -> bool:
        if cam_idx not in (8, 9, 10, 11):
            return False
        if model.algem_location != cam_idx or model.algem_trigger <= 0:
            return False
        source, target = model.algem_last_vent_move
        if target != cam_idx or source == target or source not in (8, 9, 10, 11):
            return False
        if target == 0:
            return False
        return is_vent_detour_away_from_office(source, target)
