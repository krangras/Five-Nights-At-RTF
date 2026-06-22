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

import numpy as np
import pygame

from algem_ai import AlgemEventType
from audio_mix import (
    AudioCalibrationOverlay,
    effective_volume,
    ensure_audio_settings,
)
from camera_graph import (
    BASE_GRAPH,
    SEAL_CAMERA_MAP,
    VENT_CAMERAS,
    VENT_SEALS,
)
from gameplay_model import GameModel, SealState
from laptop_power import LAPTOP_BOOT_TICKS, LAPTOP_SHUTDOWN_TICKS
from settings import save_settings
from spatial_audio import (
    AUDIO_CLOSED_RETREAT_GAIN,
    AUDIO_CLOSED_SOURCE_GAIN,
    AUDIO_MAX_BUCKET,
    AUDIO_OFFICE_FLOOR,
    AUDIO_SEALING_SOURCE_GAIN,
    AUDIO_UNREACHABLE_DISTANCE,
    AUDIO_VENT_MAP_GAIN,
    BASE_AUDIO_GRAPH,
    CHANNEL_MASTERS,
    CHANNEL_SOUND_IDS,
    TALK_DIST_PARAMS,
    _bucket_from_weighted_distance,
    _volume_from_distance,
    _weighted_audio_distance,
)

HACK_TICKS_BY_NIGHT: dict[int, int] = {
    1: 3900,   # 65 сек
    2: 5400,   # 90 сек
    3: 6900,   # 115 сек
    4: 8700,   # 145 сек
    5: 10500,  # 175 сек
}
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
DANGER_CAMERA_NODE = 7


def _phone_call_sound_path(night: int) -> str:
    night_idx = max(1, min(5, night))
    return f"sounds/ui/callnight{night_idx}.mp3"

class GamePresenter:
    """
    Связующий слой между GameModel и GameView.

    Атрибуты времени жизни:
        model  : GameModel — источник истины о состоянии игры.
        view   : GameView  — знает только как рисовать; у него нет данных.
    """

    def __init__(self, model: GameModel, view, settings_data: dict | None = None) -> None:
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

        # ── Загрузка всех звуков сразу ───────────────────────────────────
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
        _sound_defs: dict[str, str] = {
            "snd_on": "sounds/server/server_turning_on.mp3",
            "snd_work": "sounds/server/server_is_working.mp3",
            "snd_off": "sounds/server/server_turning_off.mp3",
            "snd_tablet": "sounds/ui/blip3.mp3",
            "snd_cam_switch": "sounds/cameras/camera_switch.wav",
            "snd_cam_init": "sounds/cameras/camera_init.wav",
            "snd_ambience": "sounds/ambience/ambience.wav",
            "snd_algem_leave": "sounds/threats/alegem_is_leaving.wav",
            "snd_phone_call": _phone_call_sound_path(self.model.night),
            "snd_startnight": "sounds/ui/night_starts.wav",
            "snd_endnight": "sounds/ui/night_ends.wav",
            "snd_wait": "sounds/ui/wait.wav",
            "snd_vent_close": "sounds/vents/vent_close.wav",
            "snd_knock": "sounds/vents/knock.wav",
            "snd_danger2b": "sounds/threats/danger2b.wav",
            "snd_laptop_on": "sounds/laptop/laptop_turning_on.mp3",
            "snd_laptop_off": "sounds/laptop/laptop_turning_off.mp3",
        }
        for attr, path in _sound_defs.items():
            try:
                snd = pygame.mixer.Sound(path)
                sound_id, base_volume = self._sound_meta.get(attr, (path, 0.5))
                snd.set_volume(self._mix_volume(sound_id, base_volume))
                setattr(self, attr, snd)
            except pygame.error:
                setattr(self, attr, None)
        self._ad_paths: tuple[str, ...] = (
            "sounds/laptop/ad.wav",
            "sounds/laptop/ad.mp3",
            "sounds/ui/ad.wav",
            "sounds/ui/ad.mp3",
        )
        self._ad_path: str = self._ad_paths[0]
        self._snd_off_length: int = 60
        self.__gadget_cache: list[pygame.mixer.Sound] = []
        for i in range(1, 5):
            try:
                snd = pygame.mixer.Sound(f"sounds/ui/gadget{i}.mp3")
                snd.set_volume(self._mix_volume("gadget_audio", 0.30))
                self.__gadget_cache.append(snd)
            except pygame.error:
                pass
        self.__algem_talk_cache: list[pygame.mixer.Sound] = []
        for i in (1, 2, 4, 5, 6, 7, 8, 9, 10):
            try:
                snd = pygame.mixer.Sound(f"sounds/ambience/ambience{i}.mp3")
                snd.set_volume(self._mix_volume("algem_talk", 0.82))
                self.__algem_talk_cache.append(snd)
            except pygame.error:
                pass
        self.__vent_sounds_cache: list[pygame.mixer.Sound] = []
        for f in ("vent_closer1.wav", "vent_louder2.wav", "vent_quiet1.wav", "vent_quiet2.wav"):
            try:
                snd = pygame.mixer.Sound(f"sounds/vents/{f}")
                snd.set_volume(self._mix_volume("vent_presence", 0.78))
                self.__vent_sounds_cache.append(snd)
            except pygame.error:
                pass
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
        self._algem_talk_variants: dict[int, list[pygame.mixer.Sound]] | None = None

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

        # ── Предзагрузка muffled-вариантов звуков Алгема ──────────────────
        self._build_talk_variants()

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

    # ──────────────────────────────────────────────────────────────────────
    # Ленивая загрузка звуков
    # ──────────────────────────────────────────────────────────────────────

    @property
    def _off_frames(self) -> int:
        snd = self.snd_off
        return int(snd.get_length() * 60) + 1 if snd else 60

    @property
    def _gadget_sounds(self) -> list[pygame.mixer.Sound]:
        return self.__gadget_cache

    @property
    def _vent_sounds(self) -> list[pygame.mixer.Sound]:
        return self.__vent_sounds_cache

    @property
    def _algem_talk_sounds(self) -> list[pygame.mixer.Sound]:
        return self.__algem_talk_cache

    @staticmethod
    def _make_muffled(sound: pygame.mixer.Sound, kernel_size: int) -> pygame.mixer.Sound:
        """Создать «глушёную» версию звука через low-pass фильтр (скользящее среднее)."""
        if kernel_size <= 1:
            return sound
        raw = sound.get_raw()
        arr = np.frombuffer(raw, dtype=np.int16).copy()
        kernel = np.ones(kernel_size, dtype=np.float64) / kernel_size
        filtered = np.convolve(arr.astype(np.float64), kernel, mode='same')
        np.clip(filtered, -32768, 32767, out=filtered)
        return pygame.mixer.Sound(buffer=filtered.astype(np.int16).tobytes())

    def _build_talk_variants(self) -> None:
        """Создать наборы звуков с разной степенью глушения для каждой дистанции."""
        originals = self._algem_talk_sounds
        self._algem_talk_variants = {}
        self._algem_talk_variants[0] = list(originals)
        for dist, (kernel, _vol) in self._dist_params.items():
            self._algem_talk_variants[dist] = [
                self._make_muffled(s, kernel) for s in originals
            ]

    @property
    def _talk_variants(self) -> dict[int, list[pygame.mixer.Sound]]:
        if self._algem_talk_variants is None:
            self._build_talk_variants()
        return self._algem_talk_variants

    # ──────────────────────────────────────────────────────────────────────
    # Обработка ввода
    # ──────────────────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> None:
        """
        Обработать одно событие Pygame.

        Вся обработка ввода сосредоточена здесь — Presenter «переводит»
        пользовательские действия в вызовы модели.
        """
        if self.model.night_start_ticks > 0:
            return

        if self.audio_overlay.handle_event(event):
            return

        if self._handle_projection_overlay_event(event):
            return

        # Блокировка ввода во время глитча
        if self.model._glitch_active:
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
        """Обработчик нажатий клавиш."""
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
        """Handle the live laptop projection editor when it is active."""
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
                self.view.nudge_laptop_projection_corner(
                    self._projection_corner_idx, dx, dy
                )
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
                self.view.move_laptop_projection_corner(
                    self._projection_corner_idx, event.pos, offset
                )
            return True

        return False

    def _handle_click(self, pos: tuple[int, int]) -> None:
        """Обработчик кликов мышью (левая кнопка)."""

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
        if (
            self.model.phone_call_active or self._phone_channel
        ) and not self.model.phone_muted:
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
                if (
                    not self.model.bait_active
                    and self.model.camera_idx not in self.model.bait_cooldown
                ):
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
            offset = int(
                (self.model.current_look + 1) / 2 * self.view.max_offset
            )
            if self.view.is_laptop_clicked(pos, offset):
                self.model.laptop_open = True
                self.model.laptop_app = self._laptop_saved_app
                self.model.laptop_start_menu = self._laptop_saved_menu

    def _handle_laptop_click(self, pos: tuple[int, int]) -> None:
        """Обработка кликов внутри открытого ноутбука."""
        # Клик по крестику рекламы — закрыть
        if self.model.ad_active:
            if self.view._ad_close_rect and self.view._ad_close_rect.collidepoint(pos):
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
        """Закрыть ноутбук и вернуться в офис."""
        self._laptop_saved_app = self.model.laptop_app
        self._laptop_saved_menu = self.model.laptop_start_menu
        self.model.laptop_open = False
        self.model.laptop_start_menu = False

    def _handle_mouse_motion(self, pos: tuple[int, int]) -> None:
        """Обновить целевой взгляд офиса и обработать ховер кнопки TAB."""
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

    # ──────────────────────────────────────────────────────────────────────
    # Главный тик Presenter
    # ──────────────────────────────────────────────────────────────────────

    def update(self) -> None:
        """
        Обновить логику Presenter на один тик.

        Вызывается игровым циклом ПОСЛЕ model.update().
        """
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

    def _update_server_anim(self) -> None:
        """Анимация включения/выключения сервера."""
        if self.model.server_state == "TURNING_ON":
            self._on_phase_frames -= 1
            if self._on_phase_frames <= 0:
                self._on_phase += 1
                if self._on_phase >= 8:
                    self.model.server_state = "ON"
                    self.model.server_blink = None
                    self.model.hack_active = True
                    self.model.server_overload = False
                    self.model.server_overload_warn = 0
                    self.model._schedule_next_overload()
                    if self.snd_work:
                        self.snd_work.play(-1)
                    return
                blink_seq = [
                    "red",
                    None,
                    "red",
                    None,
                    "green",
                    None,
                    "green",
                    None,
                ]
                self.model.server_blink = blink_seq[self._on_phase]
                self._on_phase_frames = 10

        elif self.model.server_state == "TURNING_OFF":
            if self._transition_frames <= 0:
                self._transition_frames = 60
                if self.snd_work:
                    self.snd_work.stop()
                if self.snd_off:
                    self.snd_off.play()
            self._transition_frames -= 1
            if self._transition_frames <= 0:
                self.model.server_state = "OFF"
                try_last_chance = getattr(self.model, "try_last_chance_server_shutdown", None)
                if try_last_chance is not None:
                    try_last_chance()

    def _update_tablet_anim(self) -> None:
        """Покадровая анимация открытия/закрытия планшета."""
        if not self.model.tablet_animating:
            return

        self._anim_timer -= 1
        if self._anim_timer > 0:
            return

        self.model.tablet_anim_frame += self._anim_dir
        if (
            self.model.tablet_anim_frame >= 10
            or self.model.tablet_anim_frame < 0
        ):
            self.model.tablet_animating = False
            if self._anim_dir == 1:
                self.model.tablet_anim_frame = 9  # полностью открыт
            else:
                self.model.tablet_open = False
        else:
            self._anim_timer = 2

    def _update_bait_anim(self) -> None:
        """
        Анимация прогресса аудио-приманки.

        6 шагов × 80 тиков ≈ 8 секунд воспроизведения.
        bait_cam_step управляет анимацией audio-иконки на мини-карте.
        """
        if not self.model.bait_active:
            return

        self._bait_timer += 1
        if self._bait_timer >= 80:
            self._bait_timer = 0
            self.model.bait_step += 1
            if self.model.bait_step >= 6:
                self.model.bait_active = False
                self.model.bait_step = 0
                self.model.bait_cam_step = 0

        self._bait_cam_timer += 1
        if self._bait_cam_timer >= 40:
            self._bait_cam_timer = 0
            if self.model.bait_cam_step < 3:
                self.model.bait_cam_step += 1

    def _update_phone(self) -> None:
        """Запуск/отслеживание телефонного звонка."""
        if self.model.phone_call_active and self._phone_channel is None:
            if self.snd_phone_call:
                self._phone_channel = self.snd_phone_call.play()
            else:
                self.model.phone_call_active = False

        if self._phone_channel and not self._phone_channel.get_busy():
            self._phone_channel = None
            self.model.phone_call_active = False

    def _update_algem_events(self) -> None:
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
        """
        Звуки Алгема:
        - Помеха (alegem_is_leaving.wav) — луп пока длится глитч (trigger > 0)
          и игрок смотрит на камеру Алгема.
        - Случайные цитаты из algemistalking — рандомно, не в начале ночи.
        """
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
        variants = self._talk_variants.get(bucket, self._talk_variants[AUDIO_MAX_BUCKET])
        self._algem_talk_channel.set_volume(
            self._current_audio_volume(self.model.algem_location, "algem_talk")
        )
        self._algem_talk_channel.play(random.choice(variants))
        self._algem_talk_timer = random.randint(3600, 5400)

    def _update_vent_sounds(self) -> None:
        loc = self.model.algem_location
        ai = getattr(self.model, "_ai", None)
        vent_motion_ticks = getattr(ai, "vent_motion_ticks", 0)
        source_node = getattr(ai, "vent_audio_source", -1)
        forced_retreat = False

        if self._closed_vent_retreat_timer > 0:
            self._closed_vent_retreat_timer -= 1
            if self._closed_vent_retreat_source in VENT_CAMERAS:
                source_node = self._closed_vent_retreat_source
                forced_retreat = True
            if self._closed_vent_retreat_timer <= 0:
                self._closed_vent_retreat_source = -1

        if source_node not in VENT_CAMERAS and loc in VENT_CAMERAS:
            source_node = loc

        seal_id = SEAL_CAMERA_MAP.get(source_node) if source_node in VENT_CAMERAS else None
        seal_state = self.model.seals.get(seal_id) if seal_id is not None else None
        closed_without_retreat = seal_state == SealState.CLOSED and not forced_retreat
        active = (
            source_node in VENT_CAMERAS
            and not closed_without_retreat
            and (forced_retreat or loc in VENT_CAMERAS or vent_motion_ticks > 0)
        )
        direct_vent_view = (
            False if forced_retreat else self._is_any_active_vent_camera_view(source_node)
        )
        target_volume = 0.0

        if direct_vent_view:
            self._vent_sound_source = source_node if source_node in VENT_CAMERAS else -1
            self._vent_sound_volume = 0.0
            if self._vent_sound_channel.get_busy():
                self._vent_sound_channel.set_volume(0.0)
            self._vent_sound_timer = 0
            return

        if active:
            target_volume = self._vent_listen_volume(
                algem_node=source_node,
                camera_idx=self.model.camera_idx,
                last_regular_cam=self._last_regular_cam,
                tablet_open=self.model.tablet_open,
                tablet_animating=self.model.tablet_animating,
            )
            if forced_retreat and seal_state == SealState.CLOSED:
                target_volume *= AUDIO_CLOSED_RETREAT_GAIN
                if self._is_direct_vent_camera_view(source_node):
                    target_volume = max(target_volume, self._apply_channel_volume(0.18, "vent"))

        if target_volume > 0.0:
            if self._vent_sound_source != source_node and self._vent_sound_channel.get_busy():
                self._vent_sound_channel.stop()
                self._vent_sound_volume = 0.0
            self._vent_sound_source = source_node
            if not self._vent_sound_channel.get_busy():
                if not self._vent_sounds:
                    return
                self._vent_sound_channel.play(random.choice(self._vent_sounds), loops=-1)
                self._vent_sound_volume = 0.0
            step = 0.050 if target_volume > self._vent_sound_volume else 0.120
            self._vent_sound_volume += max(-step, min(step, target_volume - self._vent_sound_volume))
            self._vent_sound_channel.set_volume(max(0.0, min(1.0, self._vent_sound_volume)))
            return

        if self._vent_sound_channel.get_busy():
            self._vent_sound_volume = max(0.0, self._vent_sound_volume - 0.120)
            if self._vent_sound_volume <= 0.01:
                self._vent_sound_channel.stop()
                self._vent_sound_volume = 0.0
                self._vent_sound_source = -1
            else:
                self._vent_sound_channel.set_volume(self._vent_sound_volume)
        else:
            self._vent_sound_volume = 0.0
            self._vent_sound_source = -1
        self._vent_sound_timer = 0

    def _update_vent_block_sound(self) -> None:
        """Play delayed one-shot knocks from explicit Algem AI events."""
        if self._vent_seal_just_closed > 0:
            self._vent_seal_just_closed -= 1
        if not self._pending_vent_knocks:
            return
        remaining: list[tuple[int, int, int]] = []
        ai = getattr(self.model, "_ai", None)
        leave_source = getattr(ai, "last_vent_leave_source", -1)
        vent_audio_source = getattr(ai, "vent_audio_source", -1)
        for item in self._pending_vent_knocks:
            if isinstance(item, tuple):
                timer, vent_node, source_node = item
            else:
                timer, vent_node, source_node = item, -1, -1
            timer -= 1
            if timer <= 0:
                should_skip = bool(
                    vent_node in VENT_CAMERAS
                    and (
                        leave_source == vent_node
                        or (vent_audio_source == vent_node and self.model.algem_location != vent_node)
                        or (
                            self.model.algem_prev_location == vent_node
                            and self.model.algem_location != vent_node
                            and self.model.algem_trigger > 0
                        )
                    )
                )
                if self.snd_knock and not should_skip:
                    self.snd_knock.play()
            else:
                remaining.append((timer, vent_node, source_node))
        self._pending_vent_knocks = remaining

    def _start_closed_vent_retreat_audio(self, vent_node: int) -> None:
        if vent_node not in VENT_CAMERAS:
            return
        self._closed_vent_retreat_source = vent_node
        self._closed_vent_retreat_timer = max(self._closed_vent_retreat_timer, 210)
        if self._vent_sound_source != vent_node and self._vent_sound_channel.get_busy():
            self._vent_sound_channel.stop()
            self._vent_sound_volume = 0.0
        self._vent_sound_source = vent_node

    def _distance_volume(
        self,
        params: dict[int, float] | dict[int, tuple[int, float]],
        dist: int,
        channel_key: str | None = None,
    ) -> float:
        """Compatibility helper: bucketed distance -> mixed volume."""
        bucket = max(0, min(AUDIO_MAX_BUCKET, int(dist)))
        raw = params.get(bucket, params.get(AUDIO_MAX_BUCKET, 0.12))
        volume = raw[1] if isinstance(raw, tuple) else raw
        return self._apply_channel_volume(volume, channel_key)

    def _apply_channel_volume(
        self,
        base_volume: float,
        channel_key: str | None,
    ) -> float:
        volume = max(0.0, min(1.0, base_volume))
        if channel_key is None:
            return volume
        mixed = volume * CHANNEL_MASTERS.get(channel_key, 1.0)
        sound_id = CHANNEL_SOUND_IDS.get(channel_key)
        if sound_id is None:
            return max(0.0, min(1.0, mixed))
        return self._mix_volume(sound_id, mixed)

    def _current_audio_distance(self, source_node: int) -> int:
        """Bucket 0..4 from the active listening point to a source node."""
        listener_node = self._current_listener_audio_node()
        return self._camera_audio_distance(listener_node, source_node)

    def _current_audio_volume(self, source_node: int, channel_key: str) -> float:
        """Continuous volume from the active listening point to a source node."""
        listener_node = self._current_listener_audio_node()
        dist = self._audio_weighted_distance(listener_node, source_node)
        if listener_node == 0 and source_node != 0:
            base = max(AUDIO_OFFICE_FLOOR, _volume_from_distance(dist))
        elif self._is_vent_map_open():
            base = min(AUDIO_VENT_MAP_GAIN, _volume_from_distance(dist))
        else:
            base = _volume_from_distance(dist)
        if listener_node != source_node:
            base *= self._source_seal_audio_gain(source_node)
        return self._apply_channel_volume(base, channel_key)

    def _current_listener_audio_node(self) -> int:
        return self._listener_audio_node(
            camera_idx=self.model.camera_idx,
            tablet_open=self.model.tablet_open,
            tablet_animating=self.model.tablet_animating,
        )

    def _current_audio_graph(self) -> dict[int, list[int]]:
        return {node: list(neighbors) for node, neighbors in BASE_AUDIO_GRAPH.items()}

    def _source_seal_audio_gain(self, source_node: int) -> float:
        """Return muffling gain for a vent source behind an active seal.

        The seal must not disconnect the source from the diagnostic audio map:
        otherwise every listener gets the same unreachable distance and the
        sandbox appears frozen. A closed/sealing vent should make Algem quieter,
        but nearby cameras still have to be louder than distant cameras.
        """
        if source_node not in VENT_CAMERAS:
            return 1.0
        seal_id = SEAL_CAMERA_MAP.get(source_node)
        if seal_id is None:
            return 1.0
        state = getattr(self.model, "seals", {}).get(seal_id)
        if state == SealState.SEALING:
            return AUDIO_SEALING_SOURCE_GAIN
        if state == SealState.CLOSED:
            return AUDIO_CLOSED_SOURCE_GAIN
        return 1.0

    def _is_vent_map_open(self) -> bool:
        return bool(
            self.model.tablet_open
            and not self.model.tablet_animating
            and getattr(self.view, "vent_map_mode", False)
        )

    def _is_direct_vent_camera_view(self, source_node: int) -> bool:
        if source_node not in VENT_CAMERAS:
            return False
        return bool(
            self.model.tablet_open
            and not self.model.tablet_animating
            and self.model.camera_idx == source_node
        )

    def _is_any_active_vent_camera_view(self, source_node: int) -> bool:
        if not (
            self.model.tablet_open
            and not self.model.tablet_animating
        ):
            return False
        cam_idx = self.model.camera_idx
        if cam_idx == source_node and source_node in VENT_CAMERAS:
            return True
        if cam_idx == self.model.algem_location and cam_idx in VENT_CAMERAS:
            return True
        if (
            cam_idx == self.model.algem_prev_location
            and cam_idx in VENT_CAMERAS
            and self.model.algem_trigger > 0
        ):
            return True
        ai = getattr(self.model, "_ai", None)
        if cam_idx == getattr(ai, "last_vent_leave_source", -1):
            return True
        return False

    def _suppress_algem_leave_static(self) -> bool:
        cam_idx = self.model.camera_idx
        if cam_idx not in VENT_CAMERAS:
            return False
        seal_id = SEAL_CAMERA_MAP.get(cam_idx)
        seal_state = self.model.seals.get(seal_id) if seal_id is not None else None
        algem_here = cam_idx in (self.model.algem_location, self.model.algem_prev_location)

        return bool(seal_state == SealState.CLOSED and algem_here)

    @staticmethod
    def _listener_audio_node(
        camera_idx: int,
        tablet_open: bool,
        tablet_animating: bool,
    ) -> int:
        if tablet_open and not tablet_animating:
            return camera_idx
        return 0

    @staticmethod
    def _camera_audio_distance(listener_node: int, source_node: int) -> int:
        dist = _weighted_audio_distance(listener_node, source_node, BASE_AUDIO_GRAPH)
        return _bucket_from_weighted_distance(dist)

    def _audio_weighted_distance(self, listener_node: int, source_node: int) -> float:
        return _weighted_audio_distance(listener_node, source_node, self._current_audio_graph())

    @staticmethod
    def _vent_listen_distance(
        algem_node: int,
        camera_idx: int,
        last_regular_cam: int,
        tablet_open: bool,
        tablet_animating: bool,
    ) -> int:
        """Bucketed vent distance kept for demos/tests."""
        _ = last_regular_cam
        if algem_node not in VENT_CAMERAS:
            return AUDIO_MAX_BUCKET
        listener_node = GamePresenter._listener_audio_node(
            camera_idx=camera_idx,
            tablet_open=tablet_open,
            tablet_animating=tablet_animating,
        )
        return GamePresenter._camera_audio_distance(listener_node, algem_node)

    def _vent_listen_weighted_distance(
        self,
        algem_node: int,
        camera_idx: int,
        last_regular_cam: int,
        tablet_open: bool,
        tablet_animating: bool,
    ) -> float:
        _ = last_regular_cam
        if algem_node not in VENT_CAMERAS:
            return AUDIO_UNREACHABLE_DISTANCE
        listener_node = self._listener_audio_node(
            camera_idx=camera_idx,
            tablet_open=tablet_open,
            tablet_animating=tablet_animating,
        )
        return self._audio_weighted_distance(listener_node, algem_node)

    def _vent_listen_volume(
        self,
        algem_node: int,
        camera_idx: int,
        last_regular_cam: int,
        tablet_open: bool,
        tablet_animating: bool,
    ) -> float:
        """Continuous vent volume for the current listening mode."""
        _ = last_regular_cam
        if algem_node not in VENT_CAMERAS:
            return 0.0
        seal_id = SEAL_CAMERA_MAP.get(algem_node)
        seal_state = self.model.seals.get(seal_id) if seal_id is not None else None
        if (
            tablet_open
            and not tablet_animating
            and camera_idx == algem_node
            and seal_state != SealState.CLOSED
        ):
            return 0.0
        listener_node = self._listener_audio_node(
            camera_idx=camera_idx,
            tablet_open=tablet_open,
            tablet_animating=tablet_animating,
        )
        dist = self._audio_weighted_distance(listener_node, algem_node)
        if not tablet_open or tablet_animating:
            base = max(AUDIO_OFFICE_FLOOR, _volume_from_distance(dist))
        elif self._is_vent_map_open():
            base = min(AUDIO_VENT_MAP_GAIN, _volume_from_distance(dist))
        else:
            base = _volume_from_distance(dist)
        if listener_node != algem_node:
            base *= self._source_seal_audio_gain(algem_node)
        return self._apply_channel_volume(base, "vent")

    def _current_vent_block_signature(self) -> tuple | None:
        """Detect a sealed vent near a moving Algem."""
        blocked_nodes = {
            vent_node
            for seal_id, vent_node in VENT_SEALS.items()
            if self.model.seals.get(seal_id) == SealState.CLOSED
        }
        if not blocked_nodes:
            return None

        loc = self.model.algem_location
        if loc in blocked_nodes:
            return ("inside", loc)

        adjacent_blocked = tuple(
            sorted(node for node in blocked_nodes if node in BASE_GRAPH.get(loc, []))
        )
        if adjacent_blocked:
            return ("adjacent", loc, adjacent_blocked)

        return None

    def _update_danger_sound(self) -> None:
        """Звук danger2b.wav когда Алгем дошёл до честной предофисной камеры."""
        on_last = self.model.algem_location == DANGER_CAMERA_NODE
        if on_last and not self._danger_playing:
            if self.snd_danger2b:
                self.snd_danger2b.set_volume(
                    self._mix_volume("danger_loop", SOUND_BASE_VOLUMES["snd_danger2b"])
                )
                self.snd_danger2b.play(-1)
            self._danger_playing = True
        elif not on_last and self._danger_playing:
            if self.snd_danger2b:
                self.snd_danger2b.stop()
            self._danger_playing = False

    # ──────────────────────────────────────────────────────────────────────
    # Вспомогательные команды
    # ──────────────────────────────────────────────────────────────────────

    def _toggle_tablet(self) -> None:
        """Открыть или закрыть планшет (с анимацией и звуком)."""
        self._check_node5_attack()
        if self.model.game_over:
            return
        if not self.model.tablet_open:
            self._open_tablet()
        elif not self.model.tablet_animating:
            # Нельзя закрывать планшет, если идёт процесс закрывания seal'а
            if self.model.currently_sealing_id is not None:
                return
            self._close_tablet()

    def _open_tablet(self) -> None:
        """Начать анимацию открытия планшета."""
        self.model.tablet_open = True
        self.model.tablet_animating = True
        self._anim_dir = 1
        self.model.tablet_anim_frame = 0
        self._anim_timer = 2

        if self._cam_init_channel.get_busy():
            self._cam_init_channel.set_volume(1.0)
        elif not self._camera_inited:
            self._camera_inited = True
            if self.snd_cam_init:
                self._cam_init_channel.play(self.snd_cam_init)

        if self.snd_tablet:
            self.snd_tablet.play()

    def _close_tablet(self) -> None:
        """Начать анимацию закрытия планшета."""
        self.model.tablet_animating = True
        self._anim_dir = -1
        self.model.tablet_anim_frame = 9
        self._anim_timer = 2
        self._cam_init_channel.set_volume(0.0)

        if self.snd_tablet:
            self.snd_tablet.play()

    def _switch_camera(self, idx: int) -> None:
        """Переключить активную камеру с звуком."""
        if self.model.camera_idx == idx:
            return
        self.model.camera_idx = idx
        if idx in VENT_CAMERAS:
            self._last_vent_cam = idx
        else:
            self._last_regular_cam = idx
        play_switch_sound = True
        if idx in VENT_CAMERAS:
            seal_id = SEAL_CAMERA_MAP.get(idx)
            seal_state = self.model.seals.get(seal_id) if seal_id is not None else None
            if seal_state == SealState.CLOSED and idx == self.model.algem_location:
                play_switch_sound = False
        if play_switch_sound and self.snd_cam_switch:
            self._cam_switch_channel.play(self.snd_cam_switch)

    def _shutdown_server_hotkey(self) -> None:
        """Выключить сервер клавишей S независимо от приложения и угрозы Алгема."""
        if self.model.game_over:
            return
        if self.model.server_state == "ON":
            self._toggle_server()
        elif self.model.server_state == "TURNING_ON":
            notify_shutdown = getattr(self.model, "notify_manual_server_shutdown_started", None)
            if notify_shutdown is not None:
                notify_shutdown()
            self.model.server_state = "TURNING_OFF"
            self._transition_frames = self._off_frames
            self.model.server_blink = None
            if self.snd_work:
                self.snd_work.stop()
            if self.snd_off:
                self.snd_off.play()

    def _toggle_server(self) -> None:
        """Включить или выключить сервер."""
        self._check_node5_attack()
        if self.model.game_over:
            return
        if self.model.server_state == "ON":
            notify_shutdown = getattr(self.model, "notify_manual_server_shutdown_started", None)
            if notify_shutdown is not None:
                notify_shutdown()
            self.model.server_state = "TURNING_OFF"
            self._transition_frames = self._off_frames
            self.model.server_blink = None
            if self.snd_work:
                self.snd_work.stop()
            if self.snd_off:
                self.snd_off.play()
        elif self.model.server_state == "OFF":
            if self.model.laptop_power_state != "ON":
                return
            self.model.server_state = "TURNING_ON"
            self.model.server_blink = "red"
            self._on_phase = 0
            self._on_phase_frames = 10
            if self.snd_on:
                self.snd_on.play()

    def _update_laptop(self) -> None:
        """Состояния питания ноутбука без промежуточного zoom-режима."""
        self.model.laptop_zoom = 1.0 if self.model.laptop_open else 0.0

        if self.model.laptop_power_state == "BOOTING":
            if self.model.laptop_power_timer > 0:
                self.model.laptop_power_timer -= 1
            if self.model.laptop_power_timer > 90:
                self.model.laptop_boot_stage = "boot_black"
            elif self.model.laptop_power_timer > 0:
                self.model.laptop_boot_stage = "initializing"
                if self.model.laptop_power_timer <= 24 and not self._laptop_boot_sound_played:
                    if self.snd_laptop_on:
                        self.snd_laptop_on.play()
                    self._laptop_boot_sound_played = True
            else:
                self.model.laptop_power_state = "ON"
                self.model.laptop_boot_stage = "desktop"

        elif self.model.laptop_power_state == "SHUTTING_DOWN":
            if self.model.laptop_power_timer > 0:
                self.model.laptop_power_timer -= 1
            else:
                self.model.laptop_power_state = "OFF"
                self.model.laptop_boot_stage = "boot_black"

    def _update_hack(self) -> None:
        """Прогресс взлома через ноутбук (Claude Mythos)."""
        # Взлом запускается из Claude Mythos и продвигается только пока сервер ON.
        # Во время ребута, перегрузки или выключенного сервера прогресс стоит.
        if self.model.laptop_app == "claude_mythos" and self.model.server_state == "ON" and not self.model.server_rebooting and not self.model.server_overload:
            self.model.hack_active = True
        if self.model.hack_active and not self.model.server_rebooting and not self.model.server_overload and self.model.server_state == "ON":
            hack_ticks = HACK_TICKS_BY_NIGHT.get(self.model.night, HACK_TICKS_BY_NIGHT[5])
            hack_rate = 1.0 / hack_ticks
            was_complete = self.model.hack_progress >= 1.0
            self.model.hack_progress = min(1.0, self.model.hack_progress + hack_rate)
            if not was_complete and self.model.hack_progress >= 1.0:
                start_post_hack = getattr(self.model, "_start_post_hack_phase", None)
                if start_post_hack is not None:
                    start_post_hack()

    def _update_reboot_sound(self) -> None:
        if self.model.server_rebooting and not self._wait_playing:
            self._wait_playing = True
            self._wait_timer = 0
            if self.snd_wait:
                self.snd_wait.play()
        if not self.model.server_rebooting and self._wait_playing:
            if self.snd_wait:
                self.snd_wait.stop()
            self._wait_playing = False

        if self._wait_playing:
            self._wait_timer += 1
            if self._wait_timer >= 180:
                self._wait_timer = 0
                if self.snd_wait:
                    self.snd_wait.play()

    def _play_seal_sound(self) -> None:
        """Запустить звук блокировки (сейчас используем snd_wait)."""
        if not self._seal_playing and self.snd_wait:
            self._seal_playing = True
            self._seal_timer = 0
            self.snd_wait.play()

    def _play_reopened_viewed_seal_sound(
        self,
        prev_seals: dict[str, SealState],
    ) -> None:
        """Проиграть звук заслонки, если ранее закрытый seal открылся."""
        for seal_id, prev_state in prev_seals.items():
            seal_now = self.model.seals.get(seal_id)
            if prev_state == SealState.CLOSED and seal_now == SealState.OPEN:
                self._play_vent_close_sound_for_node(VENT_SEALS.get(seal_id, -1))
                return

    def _play_vent_close_sound_for_node(self, vent_node: int) -> None:
        if not self.snd_vent_close:
            return
        volume = self._current_audio_volume(vent_node, "snd_vent_close") if vent_node > 0 else self._apply_channel_volume(SOUND_BASE_VOLUMES["snd_vent_close"], "snd_vent_close")
        channel = self.snd_vent_close.play()
        if channel is not None:
            channel.set_volume(max(0.0, min(1.0, volume)))

    def _update_seal_sound(self) -> None:
        """Обновить циклическое воспроизведение звука блокировки."""
        for seal_id, prev_state in self._prev_seal_states.items():
            seal_now = self.model.seals.get(seal_id)
            vent_node = VENT_SEALS.get(seal_id, -1)
            if prev_state == SealState.CLOSED and seal_now == SealState.OPEN:
                self._play_vent_close_sound_for_node(vent_node)
            if prev_state == SealState.SEALING and seal_now == SealState.CLOSED:
                self._play_vent_close_sound_for_node(vent_node)
                self._vent_seal_just_closed = 60

        active = any(
            self.model.seals.get(s) == SealState.SEALING
            for s in VENT_SEALS
        )
        if active and not self._seal_playing:
            self._play_seal_sound()
        if not active and self._seal_playing:
            if self.snd_wait:
                self.snd_wait.stop()
            self._seal_playing = False

        if self._seal_playing:
            self._seal_timer += 1
            if self._seal_timer >= 180:
                self._seal_timer = 0
                if self.snd_wait:
                    self.snd_wait.play()

        self._prev_seal_states = dict(self.model.seals)


    def _activate_bait(self) -> None:
        """Активировать аудио-приманку на текущей камере."""
        if self._gadget_sounds:
            random.choice(self._gadget_sounds).play()
        self.model.activate_bait(self.model.camera_idx)
        self._bait_timer = 0
        self._bait_cam_timer = 0

    def _check_node5_attack(self) -> None:
        """Legacy hook: раньше скример привязывался к закрытию планшета.

        Теперь убийство считается моделью/ИИ через BREACH + random kill-window,
        поэтому переключение планшета само по себе не должно вызывать game_over.
        """
        return

    def _update_danger_camera_grace(self) -> None:
        """Обновить счётчик времени Алгема на предофисной камере."""
        if self.model.algem_location == DANGER_CAMERA_NODE:
            self._on_danger_camera_grace += 1
        else:
            self._on_danger_camera_grace = 0

    def _update_ad(self) -> None:
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

    def _update_sound_mix(self) -> None:
        """Лёгкий runtime-микс, чтобы важные сигналы не тонули в фоне."""
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

    _GLITCH_PER_SECOND_CHANCE = 0.00083
    _GLITCH_CHECK_INTERVAL = 60

    def _update_glitch(self) -> None:
        """Случайный визуальный глитч: раз в секунду шанс ~0.4%."""
        m = self.model
        if m.game_over or m.night_complete:
            return

        if not m._glitch_active:
            if not hasattr(self, "_glitch_tick_counter"):
                self._glitch_tick_counter = 0
            self._glitch_tick_counter += 1
            if self._glitch_tick_counter >= self._GLITCH_CHECK_INTERVAL:
                self._glitch_tick_counter = 0
                if random.random() < self._GLITCH_PER_SECOND_CHANCE:
                    m._glitch_active = True
                    m._glitch_timer = 90
                    m._glitch_frame = 0
                    m._glitch_frame_timer = 0
                    if self._glitch_sounds:
                        snd = self._glitch_sounds[0]
                        chan = pygame.mixer.find_channel(True)
                        if chan:
                            chan.set_volume(0.7)
                            chan.play(snd)
                            self._glitch_channel = chan
            return

        m._glitch_timer -= 1
        if m._glitch_timer <= 0:
            m._glitch_active = False
            self._glitch_tick_counter = 0
            if self._glitch_channel:
                self._glitch_channel.stop()
                self._glitch_channel = None
            return

        m._glitch_frame_timer -= 1
        if m._glitch_frame_timer <= 0:
            m._glitch_frame = 1 - m._glitch_frame
            m._glitch_frame_timer = 0

    def _close_ad(self) -> None:
        """Закрыть рекламу и остановить звук."""
        if self.model.ad_active:
            self.model.ad_active = False
            self.model.ad_image_key = None
            self.model.ad_timer = 0
            if self._ad_playing or self._ad_channel.get_busy():
                self._ad_channel.stop()
                self._ad_playing = False

    def _start_ambience(self) -> None:
        if self.snd_ambience:
            self.snd_ambience.play(-1)
        self._ambience_playing = True

    def _cleanup_on_end(self) -> None:
        """Остановить звуки и сбросить состояния при конце ночи / game over."""
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

    def draw_overlays(self, surface: pygame.Surface) -> None:
        self.audio_overlay.draw(surface)
        if self._projection_overlay_active:
            offset = int((self.model.current_look + 1) / 2 * self.view.max_offset)
            self.view.draw_laptop_projection_editor(
                surface,
                offset,
                self._projection_corner_idx,
                self._projection_dragging,
            )

    def _start_laptop_boot(self) -> None:
        if self.model.laptop_power_state != "OFF":
            return
        self.model.laptop_power_state = "BOOTING"
        self.model.laptop_power_timer = LAPTOP_BOOT_TICKS
        self.model.laptop_boot_stage = "boot_black"
        self.model.laptop_start_menu = False
        self.model.laptop_app = None
        self._laptop_saved_app = None
        self._laptop_saved_menu = False
        self._projection_overlay_active = False
        self._projection_corner_idx = 0
        self._projection_dragging = False
        self._projection_overlay_active = False
        self._projection_corner_idx = 0
        self._projection_dragging = False
        self.model.ad_active = False
        self.model.ad_image_key = None
        self._laptop_boot_sound_played = False
        self._trigger_laptop_power_noise("on")

    def _start_laptop_shutdown(self) -> None:
        if self.model.laptop_power_state != "ON":
            return
        self._trigger_laptop_power_noise("off")
        self._sync_server_with_laptop_shutdown()
        self.model.laptop_power_state = "SHUTTING_DOWN"
        self.model.laptop_power_timer = LAPTOP_SHUTDOWN_TICKS
        self._laptop_boot_sound_played = False
        self.model.laptop_start_menu = False
        self.model.laptop_app = None
        self._laptop_saved_app = None
        self._laptop_saved_menu = False
        self.model.ad_active = False
        self.model.ad_image_key = None
        if self.snd_laptop_off:
            self.snd_laptop_off.play()

    def _trigger_laptop_power_noise(self, event: str) -> None:
        """Forward laptop on/off sounds to Algem with distance-based reaction."""
        if self.model.night <= 1:
            return
        ai = getattr(self.model, "_ai", None)
        if ai is None or not hasattr(ai, "notify_laptop_power_event"):
            return
        ai.notify_laptop_power_event(event)

    def _sync_server_with_laptop_shutdown(self) -> None:
        self.model.server_overload = False
        self.model.server_overload_warn = 0
        self.model.server_rebooting = False
        self.model.server_reboot_timer = 0
        self.model.hack_active = False
        if self.model.server_state in ("ON", "TURNING_ON", "TURNING_OFF"):
            self.model.server_state = "OFF"
            self._transition_frames = 0
            self.model.server_blink = None
            if self.snd_work:
                self.snd_work.stop()
            if self.snd_off:
                self.snd_off.play()

    def _mix_volume(self, sound_id: str, base: float) -> float:
        return effective_volume(self.settings_data, sound_id, base)

    def _save_audio_settings(self) -> None:
        save_settings(self.settings_data)

    def _refresh_cached_sound_levels(self) -> None:
        for attr, (sound_id, base_volume) in self._sound_meta.items():
            snd = getattr(self, attr, None)
            if snd is None or attr in {"snd_ambience", "snd_work", "snd_phone_call", "snd_wait"}:
                continue
            snd.set_volume(self._mix_volume(sound_id, base_volume))

        for snd in self.__gadget_cache:
            snd.set_volume(self._mix_volume("gadget_audio", 0.30))
        for snd in self.__algem_talk_cache:
            snd.set_volume(self._mix_volume("algem_talk", 0.82))
        for snd in self.__vent_sounds_cache:
            snd.set_volume(self._mix_volume("vent_presence", 0.78))
        if self._ad_sound:
            self._ad_sound.set_volume(self._mix_volume("ad_loop", CHANNEL_MASTERS["ad"]))

    # ──────────────────────────────────────────────────────────────────────
    # Утилиты
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _load_sound(path: str) -> pygame.mixer.Sound | None:
        """
        Безопасная загрузка звука.

        Возвращает None вместо исключения если файл не найден —
        это позволяет игре работать без звукового файла.
        """
        try:
            return pygame.mixer.Sound(path)
        except pygame.error:
            print(f"[GamePresenter] Sound not found: {path}")
            return None
