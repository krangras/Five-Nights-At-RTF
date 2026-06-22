"""General gameplay audio loading, mixing, and Algem sound presentation."""

import random

import numpy as np
import pygame

from .algem_ai import AlgemEventType
from .camera_graph import SEAL_CAMERA_MAP, VENT_CAMERAS
from .vent_seal import SealState
from fnar.services.audio_mix import effective_volume
from fnar.services.settings import save_settings
from fnar.services.spatial_audio import (
    AUDIO_MAX_BUCKET,
    CHANNEL_MASTERS,
    CHANNEL_SOUND_IDS,
)


SOUND_BASE_VOLUMES: dict[str, float] = {
    "snd_on": 0.42,
    "snd_work": 0.24,
    "snd_off": 0.42,
    "snd_tablet": 0.33,
    "snd_cam_switch": 0.24,
    "snd_cam_init": 0.34,
    "snd_ambience": 0.22,
    "snd_algem_leave": 0.45,
    "snd_phone_call": 0.52,
    "snd_startnight": 0.48,
    "snd_endnight": 0.55,
    "snd_wait": 0.30,
    "snd_vent_close": 0.36,
    "snd_knock": 0.36,
    "snd_danger2b": 0.34,
}


def phone_call_sound_path(night: int) -> str:
    """Return the phone-call asset for a clamped night number."""
    night_idx = max(1, min(5, night))
    return f"sounds/ui/callnight{night_idx}.mp3"


class GameplayAudioMixin:
    """Provide sound loading, distance mixing, ambience, and cleanup."""

    def __getattr__(self, attr: str):
        """Load one named gameplay sound the first time it is requested."""
        definitions = self.__dict__.get("_sound_defs", {})
        if attr not in definitions:
            raise AttributeError(attr)
        sound = self._load_sound(definitions[attr])
        if sound is not None:
            sound_id, base_volume = self._sound_meta.get(
                attr, (definitions[attr], 0.5)
            )
            sound.set_volume(self._mix_volume(sound_id, base_volume))
        setattr(self, attr, sound)
        return sound

    def _load_sound_group(
        self,
        paths: tuple[str, ...],
        sound_id: str,
        base_volume: float,
    ) -> list[pygame.mixer.Sound]:
        """Load and mix a related group of sounds on demand."""
        sounds = []
        for path in paths:
            sound = self._load_sound(path)
            if sound is None:
                continue
            sound.set_volume(self._mix_volume(sound_id, base_volume))
            sounds.append(sound)
        return sounds

    @property
    def _off_frames(self) -> int:
        """Возвращает набор кадров/поверхностей для выключенного ноутбука."""
        snd = self.snd_off
        return int(snd.get_length() * 60) + 1 if snd else 60

    @property
    def _gadget_sounds(self) -> list[pygame.mixer.Sound]:
        """Лениво загружает звуки ноутбука, сервера, планшета и камер."""
        if self._gadget_cache is None:
            self._gadget_cache = self._load_sound_group(
                tuple(f"sounds/ui/gadget{i}.mp3" for i in range(1, 5)),
                "gadget_audio",
                0.30,
            )
        return self._gadget_cache

    @property
    def _vent_sounds(self) -> list[pygame.mixer.Sound]:
        """Лениво загружает звуки движения Алгема по вентиляции."""
        if self._vent_sounds_cache is None:
            names = (
                "vent_closer1.wav",
                "vent_louder2.wav",
                "vent_quiet1.wav",
                "vent_quiet2.wav",
            )
            self._vent_sounds_cache = self._load_sound_group(
                tuple(f"sounds/vents/{name}" for name in names),
                "vent_presence",
                0.78,
            )
        return self._vent_sounds_cache

    @property
    def _algem_talk_sounds(self) -> list[pygame.mixer.Sound]:
        """Лениво загружает голоса Алгема и их приглушённые варианты."""
        if self._algem_talk_cache is None:
            self._algem_talk_cache = self._load_sound_group(
                tuple(
                    f"sounds/ambience/ambience{i}.mp3"
                    for i in (1, 2, 4, 5, 6, 7, 8, 9, 10)
                ),
                "algem_talk",
                0.82,
            )
        return self._algem_talk_cache

    @staticmethod
    def _make_muffled(sound: pygame.mixer.Sound, kernel_size: int) -> pygame.mixer.Sound:
        """Create a muffled copy using a linear-time moving average."""
        if kernel_size <= 1:
            return sound
        raw = sound.get_raw()
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
        center = (kernel_size - 1) // 2
        left_pad = kernel_size - 1 - center
        right_pad = center
        padded = np.pad(samples, (left_pad, right_pad))
        prefix = np.empty(padded.size + 1, dtype=np.float64)
        prefix[0] = 0.0
        np.cumsum(padded, out=prefix[1:])
        filtered = (prefix[kernel_size:] - prefix[:-kernel_size]) / kernel_size
        np.clip(filtered, -32768, 32767, out=filtered)
        return pygame.mixer.Sound(buffer=filtered.astype(np.int16).tobytes())

    def _build_talk_variants(self, distances=None) -> None:
        """Build only the requested distance buckets and cache the results."""
        originals = self._algem_talk_sounds
        if self._algem_talk_variants is None:
            self._algem_talk_variants = {0: list(originals)}
        targets = self._dist_params if distances is None else distances
        for dist in targets:
            if dist in self._algem_talk_variants:
                continue
            kernel, _volume = self._dist_params[dist]
            self._algem_talk_variants[dist] = [
                self._make_muffled(s, kernel) for s in originals
            ]

    def _talk_variants_for(self, distance: int) -> list[pygame.mixer.Sound]:
        """Return one cached filter bucket, creating it on first use."""
        bucket = distance if distance in self._dist_params else AUDIO_MAX_BUCKET
        self._build_talk_variants((bucket,))
        return self._algem_talk_variants[bucket]

    @property
    def _talk_variants(self) -> dict[int, list[pygame.mixer.Sound]]:
        """Подготавливает обычную и приглушённую версии одного голосового клипа."""
        if self._algem_talk_variants is None:
            self._build_talk_variants()
        return self._algem_talk_variants

    def _update_algem_events(self) -> None:
        """Разбирает события ИИ и запускает соответствующие звуковые реакции."""
        drain = getattr(self.model, "drain_algem_events", None)
        if drain is None:
            return
        for event in drain():
            if event.kind == AlgemEventType.SEAL_BLOCKED:
                delay = max(1, int(getattr(event, "delay_ticks", 60)))
                self._pending_vent_knocks.append((delay, event.target, event.source))
            elif event.kind == AlgemEventType.VENT_MOVE:
                source = int(getattr(event, "source", -1))
                target = int(getattr(event, "target", -1))
                if source in VENT_CAMERAS and target != source:
                    seal_id = SEAL_CAMERA_MAP.get(source)
                    if seal_id is not None and self.model.seals.get(seal_id) == SealState.CLOSED:
                        self._start_closed_vent_retreat_audio(source)
            elif event.kind == AlgemEventType.BREACH_STARTED:
                source = int(getattr(event, "source", -1))
                if source in VENT_CAMERAS:
                    seal_id = SEAL_CAMERA_MAP.get(source)
                    if seal_id is not None and self.model.seals.get(seal_id) == SealState.CLOSED:
                        self._start_closed_vent_retreat_audio(source)
                self._algem_leave_channel.stop()

    def _update_algem_sounds(self) -> None:
        """Mix camera static and rare Algem voice lines from the listener position."""
        if self.model.night <= 1:
            return

        trigger_now = self.model.algem_trigger
        cam_visible = (
            self.model.tablet_open
            and not self.model.tablet_animating
            and self.model.camera_idx in (
                self.model.algem_location, self.model.algem_prev_location
            )
        )
        play_leave_static = cam_visible and not self._suppress_algem_leave_static()

        if trigger_now > 0 and self._prev_algem_trigger == 0:
            if self.snd_algem_leave and play_leave_static:
                self._algem_leave_channel.play(self.snd_algem_leave, loops=-1)
        elif trigger_now > 0 and play_leave_static and self.snd_algem_leave and not self._algem_leave_channel.get_busy():
            self._algem_leave_channel.play(self.snd_algem_leave, loops=-1)
        elif trigger_now > 0 and not play_leave_static:
            self._algem_leave_channel.stop()
        elif trigger_now == 0 and self._prev_algem_trigger > 0:
            self._algem_leave_channel.stop()
        self._prev_algem_trigger = trigger_now

        self._algem_talk_timer -= 1

        if self._algem_talk_channel.get_busy():
            self._algem_talk_channel.set_volume(
                self._current_audio_volume(self.model.algem_location, "algem_talk")
            )
            return

        if self._algem_talk_timer > 0:
            return

        if not self._algem_talk_sounds:
            return

        bucket = self._current_audio_distance(self.model.algem_location)
        variants = self._talk_variants_for(bucket)
        self._algem_talk_channel.set_volume(
            self._current_audio_volume(self.model.algem_location, "algem_talk")
        )
        self._algem_talk_channel.play(random.choice(variants))
        self._algem_talk_timer = random.randint(3600, 5400)


    def _distance_volume(
        self,
        params: dict[int, float] | dict[int, tuple[int, float]],
        dist: int,
        channel_key: str | None = None,
    ) -> float:
        """Convert a discrete distance bucket to a calibrated channel volume."""
        bucket = max(0, min(AUDIO_MAX_BUCKET, int(dist)))
        raw = params.get(bucket, params.get(AUDIO_MAX_BUCKET, 0.12))
        volume = raw[1] if isinstance(raw, tuple) else raw
        return self._apply_channel_volume(volume, channel_key)

    def _apply_channel_volume(
        self,
        base_volume: float,
        channel_key: str | None,
    ) -> float:
        """Return the computed apply channel volume for the current gameplay state."""
        volume = max(0.0, min(1.0, base_volume))
        if channel_key is None:
            return volume
        mixed = volume * CHANNEL_MASTERS.get(channel_key, 1.0)
        sound_id = CHANNEL_SOUND_IDS.get(channel_key)
        if sound_id is None:
            return max(0.0, min(1.0, mixed))
        return self._mix_volume(sound_id, mixed)

    def _update_sound_mix(self) -> None:
        """Refresh dynamic volumes so danger, ads, ambience, and server loops coexist."""
        self._refresh_cached_sound_levels()
        ambience_target = SOUND_BASE_VOLUMES["snd_ambience"]
        if self.model.tablet_open or self.model.laptop_open:
            ambience_target *= 0.82
        if self._danger_playing or self._ad_playing:
            ambience_target *= 0.65
        if self._wait_playing or self._seal_playing:
            ambience_target *= 0.78
        if self.snd_ambience:
            self.snd_ambience.set_volume(self._mix_volume("office_ambience", max(0.06, min(1.0, ambience_target))))

        if self.snd_work and self.model.server_state == "ON":
            work_target = SOUND_BASE_VOLUMES["snd_work"]
            if self.model.laptop_app == "claude_mythos":
                work_target *= 1.12
            if self._danger_playing:
                work_target *= 0.88
            self.snd_work.set_volume(self._mix_volume("server_loop", max(0.08, min(1.0, work_target))))

        if self.snd_phone_call:
            phone_target = SOUND_BASE_VOLUMES["snd_phone_call"]
            if self.model.tablet_open:
                phone_target *= 0.92
            self.snd_phone_call.set_volume(self._mix_volume("phone_call", max(0.10, min(1.0, phone_target))))

        if self.snd_wait:
            wait_target = SOUND_BASE_VOLUMES["snd_wait"]
            if self._seal_playing:
                wait_target *= 0.92
            self.snd_wait.set_volume(self._mix_volume("reboot_loop", max(0.08, min(1.0, wait_target))))

        if self._ad_channel.get_busy():
            self._ad_channel.set_volume(self._mix_volume("ad_loop", CHANNEL_MASTERS["ad"]))

    def _start_ambience(self) -> None:
        """Start the looping office ambience when a night begins."""
        if self.snd_ambience:
            self.snd_ambience.play(-1)
        self._ambience_playing = True

    def _cleanup_on_end(self) -> None:
        """Stop all gameplay audio and reset transient presentation state after a run."""
        if self.snd_ambience:
            self.snd_ambience.stop()
        self._ambience_playing = False
        if self.snd_work:
            self.snd_work.stop()
        if self.snd_danger2b:
            self.snd_danger2b.stop()
        self._danger_playing = False
        if self.snd_wait:
            self.snd_wait.stop()
        self._wait_playing = False
        self._algem_talk_channel.stop()
        self._algem_leave_channel.stop()
        self._vent_sound_channel.stop()
        self._pending_vent_knocks.clear()
        self._cam_init_channel.stop()
        self._camera_inited = False
        if self._ad_playing or self._ad_channel.get_busy():
            self._ad_channel.stop()
            self._ad_playing = False
        self._algem_talk_timer = random.randint(1800, 3600)

        self.model.hack_progress = 0.0
        self.model.hack_active = False
        self.model.server_rebooting = False
        self.model.server_reboot_timer = 0

        if self.model.night_complete and not self._end_sound_played:
            if self.snd_endnight:
                self.snd_endnight.play()
            self._end_sound_played = True

        self.model.bait_active = False
        self.model.bait_target_node = None
        self.model.bait_attract_timer = 0
        self.model.bait_cooldown.clear()
        self.model.algem_in_office = False

        if self.model.phone_call_active or self._phone_channel:
            self.model.phone_call_active = False
            if self.snd_phone_call:
                self.snd_phone_call.stop()
            self._phone_channel = None

        self._close_laptop()

    def _mix_volume(self, sound_id: str, base: float) -> float:
        """Apply saved per-sound calibration to a base volume."""
        return effective_volume(self.settings_data, sound_id, base)

    def _save_audio_settings(self) -> None:
        """Persist changes made in the in-game audio calibration overlay."""
        save_settings(self.settings_data)

    def _refresh_cached_sound_levels(self) -> None:
        """Re-apply calibration to sounds that were already loaded lazily."""
        for attr, (sound_id, base_volume) in self._sound_meta.items():
            snd = self.__dict__.get(attr)
            if snd is None or attr in {"snd_ambience", "snd_work", "snd_phone_call", "snd_wait"}:
                continue
            snd.set_volume(self._mix_volume(sound_id, base_volume))

        for snd in self._gadget_cache or ():
            snd.set_volume(self._mix_volume("gadget_audio", 0.30))
        for snd in self._algem_talk_cache or ():
            snd.set_volume(self._mix_volume("algem_talk", 0.82))
        for snd in self._vent_sounds_cache or ():
            snd.set_volume(self._mix_volume("vent_presence", 0.78))
        if self._ad_sound:
            self._ad_sound.set_volume(self._mix_volume("ad_loop", CHANNEL_MASTERS["ad"]))

    # ──────────────────────────────────────────────────────────────────────
    # Утилиты
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _load_sound(path: str) -> pygame.mixer.Sound | None:
        """Load a sound file, using a short silent placeholder when assets are absent."""
        try:
            if not pygame.mixer.get_init():
                return None
            return pygame.mixer.Sound(path)
        except (FileNotFoundError, pygame.error):
            try:
                return pygame.mixer.Sound(buffer=b"\x00\x00" * 4096)
            except pygame.error:
                return None
