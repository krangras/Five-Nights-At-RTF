"""
gameplay_presenter.py — Presenter (P в паттерне MVP).

Обязанности:
  - Обрабатывать ввод (мышь, клавиатура) и транслировать в команды модели.
  - Управлять логикой, которой нет ни в Model, ни в View:
      * анимация планшета (тик-по-тику);
      * звуки переключения камер и сервера;
      * телефонный звонок;
      * звуки Алгема при перемещении.
  - Вызывать model.update() и view.draw(model) НЕ нужно — это делает
    игровой цикл в main.py. Presenter только update() своей логики.

Принцип: Presenter «связывает» Model и View, но не знает деталей
         отрисовки и не хранит данные предметной области.
"""

from __future__ import annotations

import os
import random
from typing import Any

import pygame

from fnar.services.audio_mix import (
    AudioCalibrationOverlay,
    ensure_audio_settings,
)
from .gameplay_audio import (
    GameplayAudioMixin,
    SOUND_BASE_VOLUMES,
    phone_call_sound_path,
)
from .glitch_controller import GlitchControllerMixin
from .input_controller import InputControllerMixin
from .laptop_controller import LaptopControllerMixin
from .model import GameModel, SealState
from .tablet_controller import TabletControllerMixin
from .vent_audio_controller import DANGER_CAMERA_NODE, VentAudioControllerMixin
from fnar.services.spatial_audio import CHANNEL_MASTERS, TALK_DIST_PARAMS


class GamePresenter(
    InputControllerMixin,
    TabletControllerMixin,
    LaptopControllerMixin,
    GameplayAudioMixin,
    VentAudioControllerMixin,
    GlitchControllerMixin,
):
    """
    Связующий слой между GameModel и GameView.

    Атрибуты времени жизни:
        model  : GameModel — источник истины о состоянии игры.
        view   : GameView  — знает только как рисовать; у него нет данных.
    """

    def __init__(self, model: GameModel, view, settings_data: dict | None = None) -> None:
        """Выполняет специализированную операцию «init» в подсистеме presenter."""
        self.model: GameModel = model
        self.view = view
        self.settings_data = ensure_audio_settings(settings_data)
        self.audio_overlay = AudioCalibrationOverlay(
            self.settings_data,
            on_change=self._save_audio_settings,
        )

        # ── Анимация сервера ─────────────────────────────────────────────
        self._transition_frames: int = 0  # TURNING_OFF: кадров до конца
        self._on_phase: int = 0  # TURNING_ON: фаза мигания
        self._on_phase_frames: int = 0  # TURNING_ON: кадров в фазе

        # ── Анимация планшета ────────────────────────────────────────────
        self._anim_dir: int = 1  #  1 = открытие, -1 = закрытие
        self._anim_timer: int = 0  # тиков до следующего кадра

        # ── Флаги UI ─────────────────────────────────────────────────────
        self._camera_inited: bool = False  # первое открытие планшета
        self._tab_prev_hovered: bool = False  # для edge-trigger ховера
        self._tab_hover_cooldown: int = 0  # кулдаун после toggle по ховеру (в тиках)
        self._laptop_saved_app = None
        self._laptop_saved_menu = False

        # ── Запоминание камеры при переключении vent/map ──────────────────
        self._projection_overlay_active = False
        self._projection_corner_idx = 0
        self._projection_dragging = False
        self._last_regular_cam: int = 1
        self._last_vent_cam: int = 8

        self._keys_held: set[int] = set()
        self._sound_meta: dict[str, tuple[str, float]] = {
            "snd_on": ("server_on", SOUND_BASE_VOLUMES["snd_on"]),
            "snd_work": ("server_loop", SOUND_BASE_VOLUMES["snd_work"]),
            "snd_off": ("server_off", SOUND_BASE_VOLUMES["snd_off"]),
            "snd_tablet": ("tablet_toggle", SOUND_BASE_VOLUMES["snd_tablet"]),
            "snd_cam_switch": ("camera_switch", SOUND_BASE_VOLUMES["snd_cam_switch"]),
            "snd_cam_init": ("camera_init", SOUND_BASE_VOLUMES["snd_cam_init"]),
            "snd_ambience": ("office_ambience", SOUND_BASE_VOLUMES["snd_ambience"]),
            "snd_algem_leave": ("algem_leave", SOUND_BASE_VOLUMES["snd_algem_leave"]),
            "snd_phone_call": ("phone_call", SOUND_BASE_VOLUMES["snd_phone_call"]),
            "snd_startnight": ("night_start", SOUND_BASE_VOLUMES["snd_startnight"]),
            "snd_endnight": ("night_end", SOUND_BASE_VOLUMES["snd_endnight"]),
            "snd_wait": ("reboot_loop", SOUND_BASE_VOLUMES["snd_wait"]),
            "snd_vent_close": ("vent_close", SOUND_BASE_VOLUMES["snd_vent_close"]),
            "snd_knock": ("vent_knock", SOUND_BASE_VOLUMES["snd_knock"]),
            "snd_danger2b": ("danger_loop", SOUND_BASE_VOLUMES["snd_danger2b"]),
            "snd_laptop_on": ("sounds/laptop/laptop_turning_on.mp3", 0.60),
            "snd_laptop_off": ("sounds/laptop/laptop_turning_off.mp3", 0.60),
        }
        self._sound_defs: dict[str, str] = {
            "snd_on": "sounds/server/server_turning_on.mp3",
            "snd_work": "sounds/server/server_is_working.mp3",
            "snd_off": "sounds/server/server_turning_off.mp3",
            "snd_tablet": "sounds/ui/blip3.mp3",
            "snd_cam_switch": "sounds/cameras/camera_switch.wav",
            "snd_cam_init": "sounds/cameras/camera_init.wav",
            "snd_ambience": "sounds/ambience/ambience.wav",
            "snd_algem_leave": "sounds/threats/alegem_is_leaving.wav",
            "snd_phone_call": phone_call_sound_path(self.model.night),
            "snd_startnight": "sounds/ui/night_starts.wav",
            "snd_endnight": "sounds/ui/night_ends.wav",
            "snd_wait": "sounds/ui/wait.wav",
            "snd_vent_close": "sounds/vents/vent_close.wav",
            "snd_knock": "sounds/vents/knock.wav",
            "snd_danger2b": "sounds/threats/danger2b.wav",
            "snd_laptop_on": "sounds/laptop/laptop_turning_on.mp3",
            "snd_laptop_off": "sounds/laptop/laptop_turning_off.mp3",
        }
        self._ad_paths: tuple[str, ...] = (
            "sounds/laptop/ad.wav",
            "sounds/laptop/ad.mp3",
            "sounds/ui/ad.wav",
            "sounds/ui/ad.mp3",
        )
        self._ad_path: str = self._ad_paths[0]
        self._snd_off_length: int = 60
        if pygame.mixer.get_init() and pygame.mixer.get_num_channels() < 16:
            pygame.mixer.set_num_channels(16)
        self._algem_talk_channel: pygame.mixer.Channel = pygame.mixer.Channel(5)
        self._algem_leave_channel: pygame.mixer.Channel = pygame.mixer.Channel(4)
        self._cam_init_channel: pygame.mixer.Channel = pygame.mixer.Channel(6)
        self._cam_switch_channel: pygame.mixer.Channel = pygame.mixer.Channel(7)
        self._vent_sound_channel: pygame.mixer.Channel = pygame.mixer.Channel(9)

        self._ad_playing: bool = False
        self._ad_channel: pygame.mixer.Channel = pygame.mixer.Channel(8)
        self._algem_talk_timer: int = random.randint(1800, 3600)
        self._vent_sound_timer: int = 0
        self._vent_sound_volume: float = 0.0
        self._vent_sound_source: int = -1
        self._closed_vent_retreat_source: int = -1
        self._closed_vent_retreat_timer: int = 0
        self._vent_presence_hold_timer: int = 0

        # ── Звуки Алгема: расстояние от офиса ────────────────────────────
        self._dist_params: dict[int, tuple[int, float]] = TALK_DIST_PARAMS

        self._ambience_playing: bool = False
        self._prev_algem_trigger: int = 0
        self._phone_channel: Any | None = None
        self._end_sound_played: bool = False
        self._wait_playing: bool = False
        self._wait_timer: int = 0
        self._seal_playing: bool = False
        self._seal_timer: int = 0
        self._prev_seal_states: dict[str, SealState] = dict(self.model.seals)
        self._vent_block_signature: tuple | None = None
        self._vent_seal_just_closed: int = 0  # тиков с момента последнего закрытия вента
        self._pending_vent_knocks: list[int] = []
        self._danger_playing: bool = False
        self._on_danger_camera_grace: int = 0
        self._laptop_boot_sound_played: bool = False

        # ── Таймеры приманки (для анимации кнопки) ───────────────────────
        self._bait_timer: int = 0
        self._bait_cam_timer: int = 0

        # ── Стартовый экран ночи ─────────────────────────────────────────
        self.model.night_start_ticks = 300  # 5 секунд
        self._start_played: bool = False  # продублирует звук при старте

        # ── Предзагрузка ad-звука в Sound-объект (вместо mixer.music.load) ─
        self._ad_sound: pygame.mixer.Sound | None = None
        for path in self._ad_paths:
            if not os.path.exists(path):
                continue
            try:
                self._ad_sound = pygame.mixer.Sound(path)
                self._ad_path = path
                self._ad_sound.set_volume(self._mix_volume("ad_loop", CHANNEL_MASTERS["ad"]))
                break
            except pygame.error:
                self._ad_sound = None

        # ── Глитч-звуки ────────────────────────────────────────────────
        self._glitch_sounds: list[pygame.mixer.Sound] = []
        snd = self._load_sound("sounds/glitches/robotvoice.wav")
        if snd:
            self._glitch_sounds.append(snd)
        self._glitch_channel: pygame.mixer.Channel | None = None

        # ── Предзагрузка всех звуков (чтобы не лагало во время игры) ──────
        self._init_sounds()

    # ──────────────────────────────────────────────────────────────────────
    # Обработка ввода
    # ──────────────────────────────────────────────────────────────────────

    # ──────────────────────────────────────────────────────────────────────
    # Главный тик Presenter
    # ──────────────────────────────────────────────────────────────────────

    def update(self) -> None:
        """Выполняет один игровой тик модели, таймеров, угроз и состояния ночи."""
        if self.model.night_start_ticks > 0:
            if not self._start_played and self.snd_startnight:
                self.snd_startnight.play()
                self._start_played = True
            self.model.night_start_ticks -= 1

        if self._tab_hover_cooldown > 0:
            self._tab_hover_cooldown -= 1

        if self.model.game_over or self.model.night_complete:
            self._cleanup_on_end()
            return

        # DEBUG: C+D → skip to next night
        if pygame.K_c in self._keys_held and pygame.K_d in self._keys_held:
            self.model.night_complete = True
            self._cleanup_on_end()
            return

        self._update_danger_camera_grace()

        if not self._ambience_playing:
            self._start_ambience()

        self._update_hack()
        resolve_night_end = getattr(self.model, "resolve_night_end", None)
        if resolve_night_end is not None:
            resolve_night_end()
        if self.model.game_over or self.model.night_complete:
            self._cleanup_on_end()
            return
        self._update_server_anim()
        self._update_tablet_anim()
        self._update_bait_anim()
        self._update_phone()
        self._update_algem_events()
        self._update_algem_sounds()
        self._update_vent_sounds()
        self._update_seal_sound()
        self._update_vent_block_sound()
        self._update_danger_sound()
        self._update_reboot_sound()

        self._update_ad()
        self._update_laptop()
        self._update_sound_mix()
        self._update_glitch()

    # ──────────────────────────────────────────────────────────────────────
    # Внутренние методы обновления подсистем
    # ──────────────────────────────────────────────────────────────────────

    def _update_phone(self) -> None:
        """Start and monitor the first-night phone call without blocking gameplay."""
        if self.model.phone_call_active and self._phone_channel is None:
            if self.snd_phone_call:
                self._phone_channel = self.snd_phone_call.play()
            else:
                self.model.phone_call_active = False

        if self._phone_channel and not self._phone_channel.get_busy():
            self._phone_channel = None
            self.model.phone_call_active = False

    # ──────────────────────────────────────────────────────────────────────
    # Вспомогательные команды
    # ──────────────────────────────────────────────────────────────────────

    def _activate_bait(self) -> None:
        """Trigger the lure on the selected camera and play a short gadget sound."""
        if self._gadget_sounds:
            random.choice(self._gadget_sounds).play()
        self.model.activate_bait(self.model.camera_idx)
        self._bait_timer = 0
        self._bait_cam_timer = 0

    def _check_node5_attack(self) -> None:
        """Проверяет специальную угрозу из пятого узла и запускает последствия."""
        return

    def _update_danger_camera_grace(self) -> None:
        """Track how long Algem stays on the final fair-warning camera."""
        if self.model.algem_location == DANGER_CAMERA_NODE:
            self._on_danger_camera_grace += 1
        else:
            self._on_danger_camera_grace = 0

    _GLITCH_PER_SECOND_CHANCE = 0.004
    _GLITCH_CHECK_INTERVAL = 60

    def draw_overlays(self, surface: pygame.Surface) -> None:
        """Render overlays for the current frame."""
        self.audio_overlay.draw(surface)
        if self._projection_overlay_active:
            offset = int((self.model.current_look + 1) / 2 * self.view.max_offset)
            self.view.draw_laptop_projection_editor(
                surface,
                offset,
                self._projection_corner_idx,
                self._projection_dragging,
            )
