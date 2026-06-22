"""Top-level office renderer and composition order for gameplay visuals."""

import random

import cv2
import numpy as np
import pygame

from .camera_graph import SEAL_CAMERA_MAP


class OfficeRendererMixin:
    """Compose the office, laptop, tablet, camera, and overlay layers."""

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

        if (
            model.server_state == "ON"
            and (model.hack_active or model.hack_progress > 0)
        ) or getattr(model, "post_hack_active", False):
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
                    if (
                        cam_idx in (8, 9, 10, 11)
                        and (
                            model.algem_state_name == "RETREAT"
                            or self._should_show_directional_vent_leave(model, cam_idx)
                        )
                    ):
                        cam_surf = self._algem_retreat_surfaces.get(cam_idx) or self._algem_surfaces.get(cam_idx)
                    else:
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
                seal_blocks_camera = (
                    seal_state is not None
                    and seal_state.name == "CLOSED"
                    and cam_idx in (8, 9, 10, 11)
                )
                if seal_blocks_camera:
                    cam_surf = self._closed_vent_surfaces.get(cam_idx, cam_surf)
                cam_max_off = self.camera_max_offsets.get(model.camera_idx, 0)
                if cam_surf is not None:
                    off = int((model.cam_look + 1) / 2 * cam_max_off)
                    self.screen.blit(
                        cam_surf,
                        (self.screen_rect.x - off, self.screen_rect.y),
                    )
                self._draw_cctv_effects(
                    model.camera_idx,
                    model,
                    suppress_algem_glitch=bool(seal_blocks_camera),
                )
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

                if self.vent_map_mode:
                    hint_lines = [
                        "CLICK THE GREEN BAR",
                        "NEXT TO THE TARGET VENT TO SEAL IT",
                    ]
                    tab_ty = (
                        self.screen_rect.bottom
                        - self.tabbutton_surf.get_height()
                        - self._tab_button_margin_bottom
                    )
                    hint_x = mmx + 8
                    hint_y = tab_ty - 34
                    for i, line in enumerate(hint_lines):
                        txt = self.font_very_small.render(
                            line,
                            False,
                            (232, 232, 232),
                        )
                        self.screen.blit(txt, (hint_x, hint_y + i * 12))

        # Кнопка TAB — на столе
        tx = (
            self.screen_rect.right
            - self.tabbutton_surf.get_width()
            - self._tab_button_margin_right
        )
        ty = (
            self.screen_rect.bottom
            - self.tabbutton_surf.get_height()
            - self._tab_button_margin_bottom
        )
        self.screen.blit(self.tabbutton_surf, (tx, ty))

        # Кнопка Mute Call — в левом верхнем углу под временем, чтобы не терялась на фоне.
        phone_on = model.phone_call_active
        if phone_on and not model.phone_muted:
            mx = 20
            my = 96
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
        if model.glitch_active and self._glitch_surfs:
            if model.glitch_frame == 1:
                idx = (model.glitch_timer // 2) % len(self._glitch_surfs)
                self.screen.blit(self._glitch_surfs[idx], (0, 0))
