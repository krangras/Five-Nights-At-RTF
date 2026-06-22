"""Advertisement and glitch lifecycle presentation."""

import random

import pygame

from fnar.services.spatial_audio import CHANNEL_MASTERS


class GlitchControllerMixin:
    """Coordinate ad audio and glitch presentation state."""

    def _update_ad(self) -> None:
        """Обновляет состояние рекламного окна и его таймеров."""
        volume = self._mix_volume("ad_loop", CHANNEL_MASTERS["ad"])
        if self.model.ad_active:
            if self._ad_sound:
                if not self._ad_channel.get_busy():
                    self._ad_channel.play(self._ad_sound, loops=-1)
                self._ad_channel.set_volume(volume)
            self._ad_playing = True
        else:
            if self._ad_playing or self._ad_channel.get_busy():
                self._ad_channel.stop()
                self._ad_playing = False

    def _update_glitch(self) -> None:
        """Обновляет случайные глитчи интерфейса во время игры."""
        m = self.model
        if m.game_over or m.night_complete:
            return

        if not m.glitch_active:
            if not hasattr(self, "_glitch_tick_counter"):
                self._glitch_tick_counter = 0
            self._glitch_tick_counter += 1
            if self._glitch_tick_counter >= self._GLITCH_CHECK_INTERVAL:
                self._glitch_tick_counter = 0
                if random.random() < self._GLITCH_PER_SECOND_CHANCE:
                    m.start_glitch(90)
                    if self._glitch_sounds:
                        snd = self._glitch_sounds[0]
                        chan = pygame.mixer.find_channel(True)
                        if chan:
                            chan.set_volume(0.7)
                            chan.play(snd)
                            self._glitch_channel = chan
            return

        if not m.advance_glitch():
            self._glitch_tick_counter = 0
            if self._glitch_channel:
                self._glitch_channel.stop()
                self._glitch_channel = None

    def _close_ad(self) -> None:
        """Close ad and clear related transient state."""
        if self.model.ad_active:
            self.model.ad_active = False
            self.model.ad_image_key = None
            self.model.ad_timer = 0
            if self._ad_playing or self._ad_channel.get_busy():
                self._ad_channel.stop()
                self._ad_playing = False
