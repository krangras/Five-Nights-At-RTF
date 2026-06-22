"""Rendering for the in-game laptop, boot flow, and desktop applications."""

import math

import pygame

from fnar.services.laptop_power import get_laptop_power_sequence


class LaptopRendererMixin:
    """Render every visual state of the office laptop."""

    def _draw_hack_bar(self, model) -> None:
        """Render hack bar for the current frame."""
        bar_w, bar_h = 300, 20
        x = self.screen_w - bar_w - 88
        y = 16
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
        self.screen.blit(pct, (x + bar_w + 10, y + bar_h // 2 - pct.get_height() // 2))

        if getattr(model, "post_hack_active", False):
            if getattr(model, "post_hack_shutdown_ready", False):
                msg = "SURVIVE UNTIL 6 AM"
                color = (230, 180, 70)
            else:
                msg = "SHUT DOWN SERVER + LAPTOP"
                color = (230, 70, 50)
            note = self._ctext(self._ui_font_bold, msg, color)
            self.screen.blit(note, (x, y + bar_h + 6))

    # ── Ноутбук ──────────────────────────────────────────────────────

    def _draw_xp_icon(
        self,
        ix: int,
        iy: int,
        key: str,
        hovered: bool,
        surface: pygame.Surface | None = None,
    ) -> None:
        """Render xp icon for the current frame."""
        target = surface if surface is not None else self.screen
        icon_s = 48
        pad = 2

        # Фон иконки
        if hovered:
            sel = pygame.Surface((icon_s + pad * 2, icon_s + pad * 2), pygame.SRCALPHA)
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
            pygame.draw.rect(target, (40, 80, 160), (ix + 8, iy + 6, 32, 20))
            pygame.draw.rect(target, (30, 30, 30), (ix + 8, iy + 6, 32, 20), 1)
            # Подставка
            pygame.draw.rect(target, (140, 140, 140), (ix + 18, iy + 32, 12, 4))
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
            pygame.draw.circle(target, (255, 200, 200), (cx - 5, cy - 4), 1)
            pygame.draw.circle(target, (255, 200, 200), (cx + 7, cy - 4), 1)
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
                pygame.draw.line(target, (120, 120, 120), (lx, by + 10), (lx, by + 30))

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
        """Render laptop power transition for the current frame."""
        sw, sh = self.screen_w, self.screen_h
        phase, phase_t = get_laptop_power_sequence(model.laptop_power_state, model.laptop_power_timer)

        layer = self._render_laptop_phase_surface(phase, phase_t, model)
        self.screen.blit(layer, (0, 0))

        if model.laptop_power_state in ("BOOTING", "SHUTTING_DOWN"):
            scanlines = self._laptop_scanlines.copy()
            scanlines.set_alpha(12)
            self.screen.blit(scanlines, (0, 0))

        draw_power_button = model.laptop_power_state == "OFF"
        if draw_power_button:
            power_btn = pygame.Rect(sw // 2 - 28, int(sh * 0.83), 56, 24)
            self._laptop_power_btn = power_btn
            self._draw_laptop_power_button(model.laptop_power_state, power_btn)
        else:
            self._laptop_power_btn = pygame.Rect(0, 0, 0, 0)

    def _render_laptop_phase_surface(self, phase: str, phase_t: float, model=None) -> pygame.Surface:
        """Рисует кадр текущей фазы включения или выключения ноутбука."""
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

    def _draw_laptop_power_button(self, power_state: str, rect: pygame.Rect) -> None:
        """Render laptop power button for the current frame."""
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
        """Ограничивает число диапазоном от нуля до единицы."""
        return max(0.0, min(1.0, value))

    def _ease_out_cubic(self, value: float) -> float:
        """Возвращает плавную ease-out кривую для визуальных переходов."""
        t = self._clamp01(value)
        return 1.0 - (1.0 - t) ** 3

    def _ease_in_out(self, value: float) -> float:
        """Возвращает симметричную ease-in-out кривую для анимаций."""
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
        """Render power scan line for the current frame."""
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
        """Render laptop desktop preview for the current frame."""
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
            display_m = getattr(model, "clock_minute", getattr(model, "timer", 0) // 60)
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
        """Render boot status panel for the current frame."""
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

        subtitle = self._ctext(self._ui_font_sm, "secure workstation", (126, 158, 174)).copy()
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
        """Render plain boot screen for the current frame."""
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
            m = self._ctext(
                self._ui_font_sm,
                marker,
                (84, 172, 108) if marker == "[OK]" else (102, 150, 166),
            )
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
        """Render plain center screen for the current frame."""
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
        """Render boot animation for the current frame."""
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
        """Render shutdown animation for the current frame."""
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
        """Заполняет фон экрана ноутбука цветом текущего power-состояния."""
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
        """Render panel sheen for the current frame."""
        sw, sh = surface.get_size()
        sheen = pygame.Surface((sw, sh), pygame.SRCALPHA)
        rect = pygame.Rect(sw // 2 - width // 2, sh // 2 - height // 2, width, height)
        band_h = max(18, height // 8)
        top_band = pygame.Rect(rect.x, rect.y + height // 5, rect.w, band_h)
        mid_band = pygame.Rect(rect.x, rect.centery - band_h // 2, rect.w, band_h)
        pygame.draw.rect(sheen, (172, 174, 178, alpha), top_band, border_radius=3)
        pygame.draw.rect(sheen, (58, 60, 64, alpha // 2), mid_band, border_radius=3)
        surface.blit(sheen, (0, 0), special_flags=pygame.BLEND_ADD)

    def _draw_boot_wake_screen(self, surface: pygame.Surface, phase_t: float) -> None:
        """Render boot wake screen for the current frame."""
        self._draw_boot_animation(surface, phase_t * 0.18)

    def _draw_boot_post_screen(self, surface: pygame.Surface, phase_t: float) -> None:
        """Render boot post screen for the current frame."""
        self._draw_boot_animation(surface, 0.18 + phase_t * 0.44)

    def _draw_boot_loading_screen(self, surface: pygame.Surface, phase_t: float) -> None:
        """Render boot loading screen for the current frame."""
        self._draw_boot_animation(surface, 0.62 + phase_t * 0.38)

    def _draw_shutdown_message_screen(self, surface: pygame.Surface, phase_t: float) -> None:
        """Render shutdown message screen for the current frame."""
        self._draw_shutdown_animation(surface, phase_t * 0.48)

    def _draw_shutdown_fade_screen(self, surface: pygame.Surface, phase_t: float) -> None:
        """Render shutdown fade screen for the current frame."""
        self._draw_shutdown_animation(surface, 0.48 + phase_t * 0.52)

    def _draw_powered_off_screen(self, surface: pygame.Surface) -> None:
        """Render powered off screen for the current frame."""
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
        """Render laptop screen for the current frame."""
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

        pygame.draw.line(self.screen, (100, 160, 255), (0, tb_top), (sw, tb_top))

        # Кнопка Start — зелёный градиент как в XP
        start_rect = pygame.Rect(2, tb_top + 2, 86, 36)
        self.screen.blit(self._start_btn_surf, (start_rect.x, start_rect.y))
        pygame.draw.rect(self.screen, (20, 100, 20), start_rect, 1, border_radius=4)

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
        display_m = getattr(model, "clock_minute", model.timer // 60)
        clock_str = f"{display_h}:{display_m:02d}"
        clock_label = self._ctext(self._ui_font_bold, clock_str, (255, 255, 255))
        self.screen.blit(clock_label, (sw - clock_label.get_width() - 10, sh - tb_h + 11))

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
            pygame.draw.circle(self.screen, (200, 200, 200), (menu_x + 24, menu_y + 25), 16)
            pygame.draw.circle(self.screen, (100, 100, 100), (menu_x + 24, menu_y + 25), 16, 1)
            pygame.draw.circle(self.screen, (60, 60, 60), (menu_x + 24, menu_y + 22), 5)
            pygame.draw.ellipse(self.screen, (60, 60, 60), (menu_x + 14, menu_y + 28, 20, 14))
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
                item_hovered = item_rect.collidepoint(mx, my) and item_key is not None

                if item_hovered:
                    pygame.draw.rect(self.screen, (40, 80, 200), item_rect, border_radius=3)
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
            pygame.draw.rect(self.screen, (40, 100, 180), min_btn, border_radius=2)
            pygame.draw.rect(self.screen, (20, 60, 140), min_btn, 1, border_radius=2)
            pygame.draw.line(
                self.screen,
                (255, 255, 255),
                (min_btn.x + 4, min_btn.y + 14),
                (min_btn.x + 16, min_btn.y + 14),
                2,
            )

            # Развернуть
            max_btn = pygame.Rect(win_x + win_w - 45, btn_y, btn_w, btn_h)
            pygame.draw.rect(self.screen, (40, 100, 180), max_btn, border_radius=2)
            pygame.draw.rect(self.screen, (20, 60, 140), max_btn, 1, border_radius=2)
            pygame.draw.rect(
                self.screen,
                (255, 255, 255),
                (max_btn.x + 4, max_btn.y + 4, 13, 11),
                2,
            )

            # Закрыть
            close_btn = pygame.Rect(win_x + win_w - 22, btn_y, btn_w, btn_h)
            pygame.draw.rect(self.screen, (180, 60, 40), close_btn, border_radius=2)
            pygame.draw.rect(self.screen, (120, 30, 20), close_btn, 1, border_radius=2)
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
            if getattr(model, "post_hack_active", False):
                if getattr(model, "post_hack_shutdown_ready", False):
                    post_txt = "SURVIVE UNTIL 6 AM"
                    post_clr = (180, 120, 20)
                else:
                    post_txt = "ALGEM ALERT: SHUTDOWN REQUIRED"
                    post_clr = (190, 40, 30)
                post_lbl = self._ctext(self._ui_font_sm, post_txt, post_clr)
                self.screen.blit(post_lbl, (win_x + 175, content_y + 2))

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
            pygame.draw.rect(
                self.screen,
                srv_clr if srv_enabled else (160, 160, 160),
                srv_btn,
                border_radius=3,
            )
            pygame.draw.rect(self.screen, (30, 30, 30), srv_btn, 1, border_radius=3)
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
            pygame.draw.rect(self.screen, (30, 30, 30), rebtn, 1, border_radius=3)
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
                pygame.draw.rect(self.screen, (220, 220, 220), (bar_x, bar_y, bar_w, bar_h))
                pygame.draw.rect(self.screen, (160, 160, 160), (bar_x, bar_y, bar_w, bar_h), 1)
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
                self.screen.blit(pct, (bar_x + bar_w - pct.get_width() - 4, bar_y + 1))
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
            pygame.draw.rect(self.screen, (12, 12, 12), (term_x, term_y, term_w, term_h))
            pygame.draw.rect(self.screen, (60, 60, 60), (term_x, term_y, term_w, term_h), 1)

            # Полоска заголовка терминала
            pygame.draw.rect(self.screen, (30, 30, 30), (term_x, term_y, term_w, 18))
            term_hdr = self._ctext(self._ui_font_sm, model.night_app["header"], (120, 200, 120))
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
                rendered = self._ctext(self._ui_font_sm, log_line, clr)
                self.screen.blit(rendered, (term_x + 6, term_y + 20 + i * line_h))

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
            pygame.draw.rect(self.screen, (200, 200, 200), self._ad_close_rect, 1)
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
