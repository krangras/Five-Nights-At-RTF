"""Keyboard and mouse translation for gameplay."""

import pygame

from .camera_graph import VENT_CAMERAS
from .vent_seal import SealState


class InputControllerMixin:
    """Translate Pygame events into model and presenter commands."""

    def handle_event(self, event: pygame.event.Event) -> None:
        """Route one Pygame event to the correct gameplay interaction handler."""
        if self.model.night_start_ticks > 0:
            return

        if self.audio_overlay.handle_event(event):
            return

        if self._handle_projection_overlay_event(event):
            return

        # Блокировка ввода во время глитча
        if self.model.glitch_active:
            return

        if event.type == pygame.KEYDOWN:
            self._keys_held.add(event.key)
            self._handle_keydown(event)

        elif event.type == pygame.KEYUP:
            self._keys_held.discard(event.key)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._handle_click(event.pos)

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._projection_dragging = False

        elif event.type == pygame.MOUSEMOTION:
            self._handle_mouse_motion(event.pos)

    def _handle_keydown(self, event: pygame.event.Event) -> None:
        """Handle gameplay hotkeys: laptop close, tablet toggle, and server shutdown."""
        key = event.key

        if key == pygame.K_ESCAPE:
            if self.model.laptop_open and not self.model.server_rebooting:
                self._close_laptop()

        # Переключение планшета по TAB — блокировано при ноутбуке
        elif key == pygame.K_TAB and not self.model.laptop_open:
            self._toggle_tablet()

        elif key == pygame.K_s:
            self._shutdown_server_hotkey()

    def _handle_projection_overlay_event(self, event: pygame.event.Event) -> bool:
        """Handle the F8 live editor for laptop perspective calibration."""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F8:
            self._projection_overlay_active = not self._projection_overlay_active
            self._projection_dragging = False
            if not self._projection_overlay_active:
                self.view.save_laptop_projection()
            return True

        if not self._projection_overlay_active:
            return False

        if event.type == pygame.KEYDOWN:
            mods = pygame.key.get_mods()
            step = 5 if mods & pygame.KMOD_SHIFT else 1
            key_to_corner = {
                pygame.K_1: 0,
                pygame.K_2: 1,
                pygame.K_3: 2,
                pygame.K_4: 3,
            }
            if event.key in key_to_corner:
                self._projection_corner_idx = key_to_corner[event.key]
                return True
            if event.key == pygame.K_s:
                self.view.save_laptop_projection()
                return True
            if event.key == pygame.K_r:
                self.view.reset_laptop_projection()
                self._projection_corner_idx = 0
                self.view.save_laptop_projection()
                return True

            dx = 0
            dy = 0
            if event.key == pygame.K_LEFT:
                dx = -step
            elif event.key == pygame.K_RIGHT:
                dx = step
            elif event.key == pygame.K_UP:
                dy = -step
            elif event.key == pygame.K_DOWN:
                dy = step
            if dx or dy:
                self.view.nudge_laptop_projection_corner(self._projection_corner_idx, dx, dy)
                return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.model.laptop_open:
                return True
            offset = int((self.model.current_look + 1) / 2 * self.view.max_offset)
            hit = self.view.get_laptop_projection_corner_hit(event.pos, offset)
            if hit is not None:
                self._projection_corner_idx = hit
                self._projection_dragging = True
            return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._projection_dragging:
                self._projection_dragging = False
                self.view.save_laptop_projection()
            return True

        if event.type == pygame.MOUSEMOTION:
            if self._projection_dragging and not self.model.laptop_open:
                offset = int((self.model.current_look + 1) / 2 * self.view.max_offset)
                self.view.move_laptop_projection_corner(self._projection_corner_idx, event.pos, offset)
            return True

        return False

    def _handle_click(self, pos: tuple[int, int]) -> None:
        """Dispatch a left click between office, tablet, laptop, map, and seal UI."""

        # 0. Ноутбук открыт — обработка кликов внутри
        if self.model.laptop_open:
            self._handle_laptop_click(pos)
            return

        # 1. Клик по иконке камеры на мини-карте
        hit = self.view.get_minimap_hotspot(pos)
        if hit is not None:
            cam_idx, _ = hit
            if not self.model.tablet_open:
                self._open_tablet()
            self._switch_camera(cam_idx)
            return

        # 2. Кнопка Mute Call
        if (self.model.phone_call_active or self._phone_channel) and not self.model.phone_muted:
            if self.view.is_mutecall_clicked(pos):
                self.model.phone_muted = True
                self.model.phone_call_active = False
                if self.snd_phone_call:
                    self.snd_phone_call.stop()
                self._phone_channel = None
                return

        # 3. Кнопки внутри открытого планшета
        if self.model.tablet_open and not self.model.tablet_animating:
            # PLAY AUDIO (аудио-приманка)
            if not self.view.vent_map_mode and self.view.is_bait_clicked(pos):
                if not self.model.bait_active and self.model.camera_idx not in self.model.bait_cooldown:
                    self._activate_bait()
                return

            # MAP TOGGLE — переключение между камерами и вентиляцией
            if self.view.is_map_clicked(pos):
                if any(state == SealState.SEALING for state in self.model.seals.values()):
                    return
                going_vent = not self.view.vent_map_mode
                self.view.vent_map_mode = going_vent
                if going_vent:
                    # Возвращаем игрока на последнюю просмотренную вент-камеру.
                    if self.model.camera_idx not in VENT_CAMERAS:
                        self._last_regular_cam = self.model.camera_idx
                    self._switch_camera(self._last_vent_cam)
                else:
                    # Возврат на последнюю просмотренную обычную камеру.
                    self._switch_camera(self._last_regular_cam)
                return

            # Seal-точки на карте вентиляции
            if self.view.vent_map_mode:
                seal_hit = self.view.get_seal_clicked(pos)
                if seal_hit is not None:
                    self.model.start_seal(seal_hit)
                    self._play_seal_sound()
                    return

            # Остальные клики внутри планшета поглощаем
            if self.view.screen_rect.collidepoint(pos):
                return

        # 4. Клик по ноутбуку (в офисе) — открыть
        if not self.model.laptop_open:
            offset = int((self.model.current_look + 1) / 2 * self.view.max_offset)
            if self.view.is_laptop_clicked(pos, offset):
                self.model.laptop_open = True
                self.model.laptop_app = self._laptop_saved_app
                self.model.laptop_start_menu = self._laptop_saved_menu

    def _handle_laptop_click(self, pos: tuple[int, int]) -> None:
        """Handle laptop click and translate it into game actions."""
        # Клик по крестику рекламы — закрыть
        if self.model.ad_active:
            if self.view.is_ad_close_clicked(pos):
                self._close_ad()
            return

        if self.view.is_laptop_power_clicked(pos):
            if self.model.laptop_power_state == "OFF":
                self._start_laptop_boot()
            elif self.model.laptop_power_state == "ON":
                self._start_laptop_shutdown()
            return

        if self.model.laptop_power_state != "ON":
            self.model.laptop_start_menu = False
            return

        # Клик по кнопке закрытия окна
        if self.model.laptop_app and self.view.is_laptop_close_clicked(pos) and not self.model.server_rebooting:
            self.model.laptop_app = None
            return

        # Кнопка Start/Stop Server
        if self.model.laptop_app == "claude_mythos" and self.view.is_laptop_server_btn_clicked(pos):
            if self.model.server_state in ("OFF", "ON") and not self.model.server_overload:
                self._toggle_server()
            return

        # Кнопка Reboot
        if self.model.laptop_app == "claude_mythos" and self.view.is_laptop_reboot_btn_clicked(pos):
            if self.model.server_overload or self.model.server_rebooting:
                self._check_node5_attack()
                if self.model.game_over:
                    return
                self.model.server_rebooting = True
                self.model.server_reboot_timer = 300
                self.model.server_overload_warn = 0
                self.model.hack_active = False
                self.model.hack_logs.append(f"[{self.model.hour}:00] > Rebooting server...")
            return

        # Клик по Start
        if self.view.is_laptop_start_clicked(pos):
            self.model.laptop_start_menu = not self.model.laptop_start_menu
            return

        # Клик по пункту меню Start
        if self.model.laptop_start_menu:
            item = self.view.is_laptop_menu_item_clicked(pos)
            if item == "claude":
                self.model.laptop_app = "claude_mythos"
                self.model.laptop_start_menu = False
            elif item == "shutdown" and not self.model.server_rebooting:
                self._start_laptop_shutdown()
            elif item is not None:
                self.model.laptop_start_menu = False
            return

        # Клик по иконке на рабочем столе
        icon = self.view.is_laptop_icon_clicked(pos)
        if icon == "claude":
            self.model.laptop_app = "claude_mythos"

        # Закрыть меню если кликнул мимо
        self.model.laptop_start_menu = False

    def _close_laptop(self) -> None:
        """Close the laptop view and restore the app/menu state for the next open."""
        self._laptop_saved_app = self.model.laptop_app
        self._laptop_saved_menu = self.model.laptop_start_menu
        self.model.laptop_open = False
        self.model.laptop_start_menu = False

    def _handle_mouse_motion(self, pos: tuple[int, int]) -> None:
        """Update office camera pan, laptop cursor, and TAB hover auto-open behavior."""
        w = self.view.screen_w
        self.model.target_look = max(-1.0, min(1.0, (pos[0] / w) * 2 - 1))

        if self.model.laptop_open:
            self.model.laptop_cursor = pos

        if self.model.tablet_animating or self.model.laptop_open:
            self.view.tab_button_hovered = False
            self._tab_prev_hovered = False
            return

        hovered = self.view.is_tabbutton_clicked(pos)
        self.view.tab_button_hovered = hovered

        # Edge-trigger: только при входе в зону ховера (с кулдауном)
        if hovered and not self._tab_prev_hovered and self._tab_hover_cooldown <= 0:
            self._toggle_tablet()
            self._tab_hover_cooldown = 30  # 0.5 сек при 60 FPS

        self._tab_prev_hovered = hovered
