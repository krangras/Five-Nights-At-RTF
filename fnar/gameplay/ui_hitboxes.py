"""Hit testing and small shared UI helpers for the gameplay view."""

import pygame


class UiHitboxesMixin:
    """Expose hit tests without mixing them into the main renderer module."""

    def _build_status_button(
        self,
        lines: list[str],
    ) -> pygame.Surface:
        """Build status button from the current game data."""
        surf = pygame.Surface(self._btn_size, pygame.SRCALPHA)
        surf.fill(self._seal_btn_fill)
        pygame.draw.rect(surf, (255, 255, 255), (0, 0, *self._btn_size), 1)

        rendered = [self.font_very_small.render(line, False, (245, 245, 245)) for line in lines]
        total_h = sum(s.get_height() for s in rendered) + 1 * (len(rendered) - 1)
        y = (self._btn_size[1] - total_h) // 2 - 1
        for text_surf in rendered:
            x = (self._btn_size[0] - text_surf.get_width()) // 2
            surf.blit(text_surf, (x, y))
            y += text_surf.get_height() + 1
        return surf

    def _ctext(self, font, text, color):
        """Возвращает текст из UI-словаря с безопасным fallback-значением."""
        key = (id(font), text, color)
        cached = self._text_cache.get(key)
        if cached is None:
            cached = font.render(text, True, color)
            self._text_cache[key] = cached
        return cached

    def is_server_clicked(self, mouse_pos, offset):
        """Return whether server clicked is true for the current gameplay state."""
        img_x = (mouse_pos[0] + offset) / self.scale
        img_y = mouse_pos[1] / self.scale
        return self.server_hotspot.collidepoint(img_x, img_y)

    def is_laptop_clicked(self, mouse_pos, offset):
        """Return whether laptop clicked is true for the current gameplay state."""
        img_x = (mouse_pos[0] + offset) / self.scale
        img_y = mouse_pos[1] / self.scale
        return self.laptop_hotspot.collidepoint(img_x, img_y)

    def is_tabbutton_clicked(self, mouse_pos):
        """Return whether tabbutton clicked is true for the current gameplay state."""
        if mouse_pos is None:
            return False
        tx = self.screen_rect.right - self.tabbutton_surf.get_width() - self._tab_button_margin_right
        ty = self.screen_rect.bottom - self.tabbutton_surf.get_height() - self._tab_button_margin_bottom
        rect = pygame.Rect(tx, ty, *self.tabbutton_surf.get_size())
        return rect.collidepoint(mouse_pos)

    def is_mutecall_clicked(self, mouse_pos):
        """Return whether mutecall clicked is true for the current gameplay state."""
        if mouse_pos is None:
            return False
        return self._mutecall_rect.collidepoint(mouse_pos)

    def is_bait_clicked(self, mouse_pos):
        """Return whether bait clicked is true for the current gameplay state."""
        if mouse_pos is None:
            return False
        return self._bait_btn_rect.collidepoint(mouse_pos)

    def is_map_clicked(self, mouse_pos):
        """Return whether map clicked is true for the current gameplay state."""
        if mouse_pos is None:
            return False
        return self._map_btn_rect.collidepoint(mouse_pos)

    def is_laptop_icon_clicked(self, mouse_pos):
        """Return whether laptop icon clicked is true for the current gameplay state."""
        if not hasattr(self, "_laptop_icons"):
            return None
        for rect, key in self._laptop_icons:
            if rect.collidepoint(mouse_pos):
                return key
        return None

    def is_laptop_start_clicked(self, mouse_pos):
        """Return whether laptop start clicked is true for the current gameplay state."""
        return hasattr(self, "_laptop_start_rect") and self._laptop_start_rect.collidepoint(mouse_pos)

    def is_laptop_menu_item_clicked(self, mouse_pos):
        """Return whether laptop menu item clicked is true for the current gameplay state."""
        if not hasattr(self, "_laptop_menu_items"):
            return None
        for rect, key in self._laptop_menu_items:
            if rect.collidepoint(mouse_pos):
                return key
        return None

    def is_laptop_close_clicked(self, mouse_pos):
        """Return whether laptop close clicked is true for the current gameplay state."""
        return hasattr(self, "_laptop_close_btn") and self._laptop_close_btn.collidepoint(mouse_pos)

    def is_laptop_server_btn_clicked(self, mouse_pos):
        """Return whether laptop server btn clicked is true for the current gameplay state."""
        return hasattr(self, "_laptop_server_btn") and self._laptop_server_btn.collidepoint(mouse_pos)

    def is_laptop_reboot_btn_clicked(self, mouse_pos):
        """Return whether laptop reboot btn clicked is true for the current gameplay state."""
        return hasattr(self, "_laptop_reboot_btn") and self._laptop_reboot_btn.collidepoint(mouse_pos)

    def is_laptop_power_clicked(self, mouse_pos):
        """Return whether laptop power clicked is true for the current gameplay state."""
        return hasattr(self, "_laptop_power_btn") and self._laptop_power_btn.collidepoint(mouse_pos)

    def is_ad_close_clicked(self, mouse_pos) -> bool:
        """Return whether a click hit the active advertisement close button."""
        close_rect = getattr(self, "_ad_close_rect", None)
        return bool(close_rect and close_rect.collidepoint(mouse_pos))
