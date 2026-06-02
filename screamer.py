import pygame
import glob
import os
import re


class ScreamerPlayer:
    """Покадровый проигрыватель скримера из PNG-фреймов."""

    def __init__(self, frames_dir="assets/screamer", screen_size=(1280, 720),
                 speed=0.96, door_frames=15, door_speed=8.0):
        self.screen_size = screen_size
        sw, sh = screen_size
        self._frames: list[tuple[pygame.Surface, float]] = []
        self._idx = 0
        self._elapsed = 0.0
        self._done = False

        pattern = os.path.join(frames_dir, "frame_*_delay-*.png")
        files = sorted(glob.glob(pattern))

        for i, path in enumerate(files):
            match = re.search(r"delay-([\d.]+)s", path)
            delay = float(match.group(1)) if match else 0.04
            delay /= door_speed if i < door_frames else speed

            raw = pygame.image.load(path).convert()
            fw, fh = raw.get_size()
            scale = max(sw / fw, sh / fh)
            scaled = pygame.transform.smoothscale(raw, (int(fw * scale), int(fh * scale)))
            sx = (scaled.get_width() - sw) // 2
            sy = (scaled.get_height() - sh) // 2
            cropped = scaled.subsurface(pygame.Rect(sx, sy, sw, sh)).copy()
            self._frames.append((cropped, delay))

    @property
    def done(self):
        return self._done

    def update(self, dt: float):
        if self._done or not self._frames:
            return
        self._elapsed += dt
        delay = self._frames[self._idx][1]
        while self._elapsed >= delay and not self._done:
            self._elapsed -= delay
            self._idx += 1
            if self._idx >= len(self._frames):
                self._idx = len(self._frames) - 1
                self._done = True

    def draw(self, surface: pygame.Surface):
        if self._frames:
            surface.blit(self._frames[self._idx][0], (0, 0))

    def reset(self):
        self._idx = 0
        self._elapsed = 0.0
        self._done = False
