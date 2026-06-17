import pygame
import glob
import os
import re


class ScreamerPlayer:
    """Покадровый проигрыватель скримера из PNG/JPG фреймов."""

    def __init__(self, frames_dir="assets/screamer", screen_size=(1280, 720),
                 speed=1.0, door_frames=15, door_speed=8.0, scream_frame=40,
                 delay_default=0.04, red_start=60, hold_last=0.0, red_duration=1.5):
        self.screen_size = screen_size
        sw, sh = screen_size
        self._frames: list[tuple[pygame.Surface, float]] = []
        self._idx = 0
        self._elapsed = 0.0
        self._done = False
        self.scream_frame = scream_frame
        self.scream_triggered = False

        # Поддерживаем два формата именования:
        #   frame_XX_delay-0.04s.png  (office_screamer)
        #   ezgif-frame-XXX.jpg       (vent_screamer)
        png_pattern = os.path.join(frames_dir, "frame_*_delay-*.png")
        jpg_pattern = os.path.join(frames_dir, "ezgif-frame-*.jpg")
        files = sorted(glob.glob(png_pattern) + glob.glob(jpg_pattern))

        def _sort_key(path):
            base = os.path.basename(path)
            m = re.search(r"frame[_-](\d+)", base)
            return int(m.group(1)) if m else 0

        files = sorted(files, key=_sort_key)

        for i, path in enumerate(files):
            base = os.path.basename(path)
            m = re.search(r"delay-([\d.]+)s", base)
            delay = float(m.group(1)) if m else delay_default
            delay /= door_speed if i < door_frames else speed

            raw = pygame.image.load(path).convert()
            fw, fh = raw.get_size()
            scale = max(sw / fw, sh / fh)
            scaled = pygame.transform.smoothscale(raw, (int(fw * scale), int(fh * scale)))
            sx = (scaled.get_width() - sw) // 2
            sy = (scaled.get_height() - sh) // 2
            cropped = scaled.subsurface(pygame.Rect(sx, sy, sw, sh)).copy()
            self._frames.append((cropped, delay))

        self._red_overlay = pygame.Surface(screen_size, pygame.SRCALPHA)
        self._red_overlay.fill((180, 0, 0, 0))
        self._red_start = red_start
        self._hold_last = hold_last
        self._hold_timer = 0.0
        self._initial_scream_frame = scream_frame
        self._red_elapsed = 0.0
        self._red_duration = red_duration

    @property
    def done(self):
        return self._done

    def update(self, dt: float):
        if self._done or not self._frames:
            return
        if self._hold_timer > 0.0:
            self._hold_timer -= dt
            self._red_elapsed += dt
            if self._hold_timer <= 0.0:
                self._done = True
            return
        self._elapsed += dt
        if self._idx >= self._red_start:
            self._red_elapsed += dt
        delay = self._frames[self._idx][1]
        while self._elapsed >= delay and not self._done:
            self._elapsed -= delay
            self._idx += 1
            if self._idx >= len(self._frames):
                self._idx = len(self._frames) - 1
                if self._hold_last > 0.0:
                    self._hold_timer = self._hold_last
                else:
                    self._done = True
        if not self.scream_triggered and self._idx >= self.scream_frame:
            self.scream_triggered = True

    def draw(self, surface: pygame.Surface):
        if self._frames:
            surface.blit(self._frames[self._idx][0], (0, 0))
            if self._red_elapsed > 0.0:
                progress = min(1.0, self._red_elapsed / self._red_duration)
                alpha = int(progress * 255)
                self._red_overlay.fill((180, 0, 0, alpha))
                surface.blit(self._red_overlay, (0, 0))

    def reset(self):
        self._idx = 0
        self._elapsed = 0.0
        self._done = False
        self._hold_timer = 0.0
        self._red_elapsed = 0.0
        self.scream_triggered = False
        self.scream_frame = self._initial_scream_frame
        self._red_overlay.fill((180, 0, 0, 0))
