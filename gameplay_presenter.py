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

import random
from typing import Any

import numpy as np
import pygame

from algem_ai import bfs_path
from gameplay_model import BASE_GRAPH, CAMERA_COUNT, GameModel

HACK_RATE: float = 1.0 / 1800  # прогресс взлома за тик (~30 сек реального времени)


class GamePresenter:
    """
    Связующий слой между GameModel и GameView.

    Атрибуты времени жизни:
        model  : GameModel — источник истины о состоянии игры.
        view   : GameView  — знает только как рисовать; у него нет данных.
    """

    def __init__(self, model: GameModel, view) -> None:
        self.model: GameModel = model
        self.view = view

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
        self._laptop_saved_app = None
        self._laptop_saved_menu = False

        # ── Ленивая загрузка звуков ──────────────────────────────────────
        self._sound_paths: dict[str, str] = {
            "snd_on": "sounds/night1/server_turning_on.mp3",
            "snd_work": "sounds/night1/server_is_working.mp3",
            "snd_off": "sounds/night1/server_turning_off.mp3",
            "snd_tablet": "sounds/blip3.mp3",
            "snd_cam_switch": "sounds/camera_switch.wav",
            "snd_cam_init": "sounds/camera_init.wav",
            "snd_ambience": "sounds/ambience.wav",
            "snd_algem_leave": "sounds/alegem_is_leaving.wav",
            "snd_phone_call": "sounds/night1/callnight1.mp3",
            "snd_startnight": "sounds/night_starts.wav",
            "snd_endnight": "sounds/night_ends.wav",
            "snd_wait": "sounds/wait.wav",
            "snd_danger2b": "sounds/danger2b.wav",
        }
        self._ad_path: str = "sounds/laptop/ad.mp3"
        self._snd_off_length: int = 60
        self._gadget_paths: list[str] = [f"sounds/gadget{i}.mp3" for i in range(1, 5)]
        self._algem_talk_paths: list[str] = [
            f"sounds/algemistalking/ambience{i}.mp3"
            for i in (1, 2, 4, 5, 6, 7, 8, 9, 10)
        ]
        self._algem_talk_channel: pygame.mixer.Channel = pygame.mixer.Channel(5)
        self._algem_leave_channel: pygame.mixer.Channel = pygame.mixer.Channel(4)
        self._cam_init_channel: pygame.mixer.Channel = pygame.mixer.Channel(6)
        self._cam_switch_channel: pygame.mixer.Channel = pygame.mixer.Channel(7)
        self._ad_playing: bool = False
        self._ad_channel: pygame.mixer.Channel = pygame.mixer.Channel(8)
        self._algem_talk_timer: int = random.randint(1800, 3600)

        # ── Звуки Алгема: расстояние от офиса ────────────────────────────
        self._office_distance: dict[int, int] = {}
        for node in range(1, 8):
            path = bfs_path(node, 0, BASE_GRAPH)
            self._office_distance[node] = len(path) - 1 if path else 4
        # (расстояние → (kernel_size, volume))
        self._dist_params: dict[int, tuple[int, float]] = {
            0: (0, 1.0),
            1: (5, 0.70),
            2: (15, 0.42),
            3: (25, 0.25),
            4: (40, 0.12),
        }
        self._algem_talk_variants: dict[int, list[pygame.mixer.Sound]] | None = None

        self._ambience_playing: bool = False
        self._prev_algem_trigger: int = 0
        self._phone_channel: Any | None = None
        self._end_sound_played: bool = False
        self._wait_playing: bool = False
        self._wait_timer: int = 0
        self._danger_playing: bool = False
        self._on_node5_grace: int = 0

        # ── Таймеры приманки (для анимации кнопки) ───────────────────────
        self._bait_timer: int = 0
        self._bait_cam_timer: int = 0

        # ── Стартовый экран ночи ─────────────────────────────────────────
        self.model.night_start_ticks = 300  # 5 секунд
        self._start_played: bool = False  # продублирует звук при старте

    # ──────────────────────────────────────────────────────────────────────
    # Ленивая загрузка звуков
    # ──────────────────────────────────────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        if name.startswith("snd_"):
            path = self._sound_paths.get(name)
            if path:
                try:
                    sound = pygame.mixer.Sound(path)
                    setattr(self, name, sound)
                    if name == "snd_ambience":
                        sound.set_volume(0.35)
                    return sound
                except pygame.error:
                    print(f"[GamePresenter] Sound not found: {path}")
                    setattr(self, name, None)
                    return None
        raise AttributeError(f"'GamePresenter' has no attribute '{name}'")

    @property
    def _off_frames(self) -> int:
        snd = self.snd_off
        return int(snd.get_length() * 60) + 1 if snd else 60

    @property
    def _gadget_sounds(self) -> list[pygame.mixer.Sound]:
        if not hasattr(self, '__gadget_cache'):
            cache: list[pygame.mixer.Sound] = []
            for path in self._gadget_paths:
                try:
                    cache.append(pygame.mixer.Sound(path))
                except pygame.error:
                    print(f"[GamePresenter] Sound not found: {path}")
            object.__setattr__(self, '__gadget_cache', cache)
        return object.__getattribute__(self, '__gadget_cache')

    @property
    def _algem_talk_sounds(self) -> list[pygame.mixer.Sound]:
        if not hasattr(self, '__algem_talk_cache'):
            cache: list[pygame.mixer.Sound] = []
            for path in self._algem_talk_paths:
                try:
                    cache.append(pygame.mixer.Sound(path))
                except pygame.error:
                    print(f"[GamePresenter] Sound not found: {path}")
            object.__setattr__(self, '__algem_talk_cache', cache)
        return object.__getattribute__(self, '__algem_talk_cache')

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
        if event.type == pygame.KEYDOWN:
            self._handle_keydown(event)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._handle_click(event.pos)

        elif event.type == pygame.MOUSEMOTION:
            self._handle_mouse_motion(event.pos)

    def _handle_keydown(self, event: pygame.event.Event) -> None:
        """Обработчик нажатий клавиш."""
        key = event.key

        if key == pygame.K_ESCAPE:
            if self.model.laptop_open and not self.model.server_rebooting:
                self._close_laptop()
            else:
                pygame.mouse.set_visible(not pygame.mouse.get_visible())

        # Переключение планшета по TAB — блокировано при ноутбуке
        elif key == pygame.K_TAB and not self.model.laptop_open:
            self._toggle_tablet()

        # DEBUG: F1 → принудительный game_over для теста скримера
        elif key == pygame.K_F1:
            self.model.game_over = True

        # F2 → toggle реального экрана ноутбука
        elif key == pygame.K_F2:
            self.model.show_real_screen = not self.model.show_real_screen

        # Цифровые клавиши 1–7 — переключение камер
        key_to_cam: dict[int, int] = {
            pygame.K_1: 1,
            pygame.K_2: 2,
            pygame.K_3: 3,
            pygame.K_4: 4,
            pygame.K_5: 5,
            pygame.K_6: 6,
            pygame.K_7: 7,
        }
        if key in key_to_cam and self.model.tablet_open and not self.model.laptop_open:
            self._switch_camera(key_to_cam[key])

        # 0 — сброс на камеру 1
        if key == pygame.K_0 and self.model.tablet_open and not self.model.laptop_open:
            self._switch_camera(1)
            self.model.cam_look = 0.0
            self.model.cam_state = "HOLDING"
            self.model.cam_hold_timer = 0

        # Стрелки — переключение камер по кругу
        if self.model.tablet_open and not self.model.laptop_open:
            if key == pygame.K_RIGHT:
                self._switch_camera((self.model.camera_idx % CAMERA_COUNT) + 1)
            elif key == pygame.K_LEFT:
                self._switch_camera(
                    ((self.model.camera_idx - 2) % CAMERA_COUNT) + 1
                )

    def _handle_click(self, pos: tuple[int, int]) -> None:
        """Обработчик кликов мышью (левая кнопка)."""

        # 0. Ноутбук открыт — обработка кликов внутри
        if self.model.laptop_zoom >= 0.95:
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
            if self.view.is_bait_clicked(pos):
                if (
                    not self.model.bait_active
                    and self.model.camera_idx not in self.model.bait_cooldown
                ):
                    self._activate_bait()
                return

            # MAP TOGGLE — в будущем смена режима отображения карты
            if self.view.is_map_clicked(pos):
                return

            # Кнопки RESET VENT_A / RESET VENT_B
            vent_hit = self.view.get_vent_reset_clicked(pos)
            if vent_hit is not None:
                self.model.start_vent_reset(vent_hit)
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
            elif item == "mycomputer":
                pass  # TODO: My Computer
            elif item == "shutdown" and not self.model.server_rebooting:
                self._close_laptop()
            elif item is not None:
                self.model.laptop_start_menu = False
            return

        # Клик по иконке на рабочем столе
        icon = self.view.is_laptop_icon_clicked(pos)
        if icon == "claude":
            self.model.laptop_app = "claude_mythos"
        elif icon == "mycomputer":
            pass  # TODO: My Computer

        # Закрыть меню если кликнул мимо
        self.model.laptop_start_menu = False

    def _close_laptop(self) -> None:
        """Закрыть ноутбук и вернуться в офис."""
        self._laptop_saved_app = self.model.laptop_app
        self._laptop_saved_menu = self.model.laptop_start_menu
        self.model.laptop_open = False
        self.model.laptop_zoom = 0.0
        self.model.laptop_start_menu = False

    def _handle_mouse_motion(self, pos: tuple[int, int]) -> None:
        """Обновить целевой взгляд офиса и обработать ховер кнопки TAB."""
        w = self.view.screen_w
        self.model.target_look = max(-1.0, min(1.0, (pos[0] / w) * 2 - 1))

        if self.model.laptop_open and self.model.laptop_zoom >= 0.95:
            self.model.laptop_cursor = pos

        if self.model.tablet_animating or self.model.laptop_open:
            self.view.tab_button_hovered = False
            self._tab_prev_hovered = False
            return

        hovered = self.view.is_tabbutton_clicked(pos)
        self.view.tab_button_hovered = hovered

        # Edge-trigger: только при входе в зону ховера
        if hovered and not self._tab_prev_hovered:
            self._toggle_tablet()

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

        if self.model.game_over or self.model.night_complete:
            self._cleanup_on_end()
            return

        self._update_node5_grace()

        if not self._ambience_playing:
            self._start_ambience()

        self._update_hack()
        self._update_server_anim()
        self._update_tablet_anim()
        self._update_bait_anim()
        self._update_phone()
        self._update_algem_sounds()
        self._update_danger_sound()
        self._update_reboot_sound()
        self._update_ad()
        self._update_laptop()

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
                # Если Алгем был в офисе и игрок закрыл планшет — game over
                if self.model.algem_in_office:
                    self.model.game_over = True
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

        if trigger_now > 0 and self._prev_algem_trigger == 0:
            if self.snd_algem_leave and cam_visible:
                self._algem_leave_channel.play(self.snd_algem_leave, loops=-1)
        elif trigger_now > 0 and cam_visible and self.snd_algem_leave and not self._algem_leave_channel.get_busy():
            self._algem_leave_channel.play(self.snd_algem_leave, loops=-1)
        elif trigger_now > 0 and not cam_visible:
            self._algem_leave_channel.stop()
        elif trigger_now == 0 and self._prev_algem_trigger > 0:
            self._algem_leave_channel.stop()
        self._prev_algem_trigger = trigger_now

        self._algem_talk_timer -= 1

        if self._algem_talk_channel.get_busy():
            if self.model.tablet_open and not self.model.tablet_animating:
                cam_to_algem = bfs_path(
                    self.model.camera_idx, self.model.algem_location, BASE_GRAPH
                )
                dist = len(cam_to_algem) - 1 if cam_to_algem else 4
            else:
                dist = self._office_distance.get(self.model.algem_location, 4)
            self._algem_talk_channel.set_volume(self._dist_params.get(dist, (0, 0.18))[1])
            return

        if self._algem_talk_timer > 0:
            return

        if not self._algem_talk_sounds:
            return

        if self.model.tablet_open and not self.model.tablet_animating:
            cam_to_algem = bfs_path(
                self.model.camera_idx, self.model.algem_location, BASE_GRAPH
            )
            dist = len(cam_to_algem) - 1 if cam_to_algem else 4
        else:
            dist = self._office_distance.get(self.model.algem_location, 4)
        variants = self._talk_variants.get(dist, self._talk_variants[4])
        self._algem_talk_channel.set_volume(self._dist_params.get(dist, (0, 0.18))[1])
        self._algem_talk_channel.play(random.choice(variants))
        self._algem_talk_timer = random.randint(3600, 5400)

    def _update_danger_sound(self) -> None:
        """Звук danger2b.wav когда Алгем на последней камере (node 5)."""
        on_last = self.model.algem_location == 5
        if on_last and not self._danger_playing:
            if self.snd_danger2b:
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
        self.model.camera_idx = idx
        if self.snd_cam_switch:
            self._cam_switch_channel.play(self.snd_cam_switch)

    def _toggle_server(self) -> None:
        """Включить или выключить сервер."""
        self._check_node5_attack()
        if self.model.game_over:
            return
        if self.model.server_state == "ON":
            self.model.server_state = "TURNING_OFF"
            self._transition_frames = self._off_frames
            self.model.server_blink = None
            if self.snd_work:
                self.snd_work.stop()
            if self.snd_off:
                self.snd_off.play()
        elif self.model.server_state == "OFF":
            self.model.server_state = "TURNING_ON"
            self.model.server_blink = "red"
            self._on_phase = 0
            self._on_phase_frames = 10
            if self.snd_on:
                self.snd_on.play()

    def _update_laptop(self) -> None:
        """Мгновенное переключение ноутбука."""
        if self.model.laptop_open:
            self.model.laptop_zoom = 1.0
        else:
            self.model.laptop_zoom = 0.0

    def _update_hack(self) -> None:
        """Прогресс взлома через ноутбук (Claude Mythos)."""
        # Взлом начинается когда Claude Mythos открыт и сервер включён,
        # но затем продолжается даже после закрытия ноутбука или выключения сервера
        if self.model.laptop_app == "claude_mythos" and self.model.server_state == "ON" and not self.model.server_rebooting:
            self.model.hack_active = True
        if self.model.hack_active:
            self.model.hack_progress = min(1.0, self.model.hack_progress + HACK_RATE)

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
            if self._wait_timer >= 180:  # раз в 3 секунды
                self._wait_timer = 0
                if self.snd_wait:
                    self.snd_wait.play()

    def _activate_bait(self) -> None:
        """Активировать аудио-приманку на текущей камере."""
        if self._gadget_sounds:
            random.choice(self._gadget_sounds).play()
        self.model.activate_bait(self.model.camera_idx)
        self._bait_timer = 0
        self._bait_cam_timer = 0

    def _check_node5_attack(self) -> None:
        """Если Алгем на node 5 дольше grace-периода — атака через любой триггер."""
        if self._on_node5_grace >= 60:
            self.model.game_over = True

    def _update_node5_grace(self) -> None:
        """Обновить счётчик времени Алгема на node 5."""
        if self.model.algem_location == 5:
            self._on_node5_grace += 1
        else:
            self._on_node5_grace = 0

    def _update_ad(self) -> None:
        """Управление рекламой: запуск звука и притяжение Алгема."""
        if self.model.ad_active:
            if not self._ad_playing:
                pygame.mixer.music.load(self._ad_path)
                pygame.mixer.music.set_volume(1.0)
                pygame.mixer.music.play(-1)
                self._ad_playing = True
            if self.model.night > 1:
                self.model._hack_attraction = min(1.0, self.model._hack_attraction + 0.002)
        else:
            if self._ad_playing:
                pygame.mixer.music.stop()
                self._ad_playing = False

    def _close_ad(self) -> None:
        """Закрыть рекламу и остановить звук."""
        if self.model.ad_active:
            self.model.ad_active = False
            self.model.ad_image_key = None
            self.model.ad_timer = 0
            if self._ad_playing:
                pygame.mixer.music.stop()
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
        self._cam_init_channel.stop()
        self._camera_inited = False
        if self._ad_playing:
            pygame.mixer.music.stop()
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
