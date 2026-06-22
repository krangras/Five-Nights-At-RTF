"""Проигрыватель покадрового скримера с дверной анимацией и красным финальным затемнением."""

import pygame
import glob
import os
import re


DEFAULT_SCREAMER_DIR = "assets/screamer"
DEFAULT_SCREAMER_SCREEN_SIZE = (1280, 720)
DEFAULT_PLAYBACK_SPEED = 1.0
DEFAULT_DOOR_FRAME_COUNT = 15
DEFAULT_DOOR_SPEED = 8.0
DEFAULT_SCREAM_FRAME = 40
DEFAULT_FRAME_DELAY_SECONDS = 0.04
DEFAULT_RED_START_FRAME = 60
DEFAULT_HOLD_LAST_SECONDS = 0.0
DEFAULT_RED_DURATION_SECONDS = 1.5
FRAME_INDEX_FALLBACK = 0
RED_OVERLAY_COLOR = (180, 0, 0, 0)
RED_OVERLAY_RGB = (180, 0, 0)
MAX_ALPHA = 255


class ScreamerPlayer:
    """Frame-based screamer player from PNG/JPG frames.

    Class-level constants keep timing and visual parameters named, so the
    screamer can be tuned without searching for hardcoded numbers.
    """

    DEFAULT_DIR = DEFAULT_SCREAMER_DIR
    DEFAULT_SCREEN_SIZE = DEFAULT_SCREAMER_SCREEN_SIZE
    DEFAULT_SPEED = DEFAULT_PLAYBACK_SPEED
    DEFAULT_DOOR_FRAMES = DEFAULT_DOOR_FRAME_COUNT
    DEFAULT_DOOR_SPEED = DEFAULT_DOOR_SPEED
    DEFAULT_SCREAM_FRAME = DEFAULT_SCREAM_FRAME
    DEFAULT_DELAY = DEFAULT_FRAME_DELAY_SECONDS
    DEFAULT_RED_START = DEFAULT_RED_START_FRAME
    DEFAULT_HOLD_LAST = DEFAULT_HOLD_LAST_SECONDS
    DEFAULT_RED_DURATION = DEFAULT_RED_DURATION_SECONDS

    def __init__(
        self,
        frames_dir=DEFAULT_SCREAMER_DIR,
        screen_size=DEFAULT_SCREAMER_SCREEN_SIZE,
        speed=DEFAULT_PLAYBACK_SPEED,
        door_frames=DEFAULT_DOOR_FRAME_COUNT,
        door_speed=DEFAULT_DOOR_SPEED,
        scream_frame=DEFAULT_SCREAM_FRAME,
        delay_default=DEFAULT_FRAME_DELAY_SECONDS,
        red_start=DEFAULT_RED_START_FRAME,
        hold_last=DEFAULT_HOLD_LAST_SECONDS,
        red_duration=DEFAULT_RED_DURATION_SECONDS,
    ):
        """Выполняет специализированную операцию «init» в подсистеме screamer."""
        self.screen_size = screen_size
        sw, sh = screen_size
        self._frames: list[tuple[pygame.Surface, float]] = []
        self._idx = 0
        self._elapsed = 0.0
        self._done = False
        self.scream_frame = scream_frame
        self.scream_triggered = False

        png_pattern = os.path.join(frames_dir, "frame_*_delay-*.png")
        jpg_pattern = os.path.join(frames_dir, "ezgif-frame-*.jpg")
        files = sorted(glob.glob(png_pattern) + glob.glob(jpg_pattern))

        def _sort_key(path):
            """Извлекает числовой индекс кадра для правильной сортировки файлов скримера."""
            base = os.path.basename(path)
            m = re.search(r"frame[_-](\d+)", base)
            return int(m.group(1)) if m else FRAME_INDEX_FALLBACK

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
        self._red_overlay.fill(RED_OVERLAY_COLOR)
        self._red_start = red_start
        self._hold_last = hold_last
        self._hold_timer = 0.0
        self._initial_scream_frame = scream_frame
        self._red_elapsed = 0.0
        self._red_duration = red_duration

    @property
    def done(self):
        """Return whether the animation has finished."""
        return self._done

    def update(self, dt: float):
        """Выполняет один игровой тик модели, таймеров, угроз и состояния ночи."""
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
        """Отрисовывает соответствующую часть интерфейса на текущем кадре."""
        if self._frames:
            surface.blit(self._frames[self._idx][0], (0, 0))
            if self._red_elapsed > 0.0:
                progress = min(1.0, self._red_elapsed / self._red_duration)
                alpha = int(progress * MAX_ALPHA)
                self._red_overlay.fill((*RED_OVERLAY_RGB, alpha))
                surface.blit(self._red_overlay, (0, 0))

    def reset(self):
        """Сбрасывает внутреннее состояние компонента к началу нового сценария."""
        self._idx = 0
        self._elapsed = 0.0
        self._done = False
        self._hold_timer = 0.0
        self._red_elapsed = 0.0
        self.scream_triggered = False
        self.scream_frame = self._initial_scream_frame
        self._red_overlay.fill(RED_OVERLAY_COLOR)
