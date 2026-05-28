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

import pygame

from gameplay_model import CAMERA_COUNT, GameModel

HACK_RATE: float = 1.0 / 21600  # прогресс взлома за тик (~6 игровых часов)


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
        self._snd_off_length: int = 60
        self._gadget_paths: list[str] = [f"sounds/gadget{i}.mp3" for i in range(1, 5)]

        self._ambience_playing: bool = False
        self._prev_algem_trigger: int = 0
        self._phone_channel: Any | None = None
        self._end_sound_played: bool = False
        self._wait_playing: bool = False
        self._wait_timer: int = 0
        self._danger_playing: bool = False
        self._on_node7_grace: int = 0

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
            pygame.mouse.set_visible(not pygame.mouse.get_visible())

        # Переключение планшета по TAB
        elif key == pygame.K_TAB:
            self._toggle_tablet()

        # DEBUG: F1 → принудительный game_over для теста скримера
        elif key == pygame.K_F1:
            self.model.game_over = True

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
        if key in key_to_cam and self.model.tablet_open:
            self._switch_camera(key_to_cam[key])

        # 0 — сброс на камеру 1
        if key == pygame.K_0 and self.model.tablet_open:
            self._switch_camera(1)
            self.model.cam_look = 0.0
            self.model.cam_state = "HOLDING"
            self.model.cam_hold_timer = 0

        # Стрелки — переключение камер по кругу
        if self.model.tablet_open:
            if key == pygame.K_RIGHT:
                self._switch_camera((self.model.camera_idx % CAMERA_COUNT) + 1)
            elif key == pygame.K_LEFT:
                self._switch_camera(
                    ((self.model.camera_idx - 2) % CAMERA_COUNT) + 1
                )

    def _handle_click(self, pos: tuple[int, int]) -> None:
        """Обработчик кликов мышью (левая кнопка)."""

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

        # 4. Клик по серверу (в офисе)
        if self.model.server_state in ("OFF", "ON"):
            offset = int(
                (self.model.current_look + 1) / 2 * self.view.max_offset
            )
            if self.view.is_server_clicked(pos, offset):
                if self.model.server_overload:
                    self._check_node7_attack()
                    if self.model.game_over:
                        return
                    self.model.server_rebooting = True
                    self.model.server_reboot_timer = 300  # 5 секунд
                    self.model.server_overload_warn = 0
                else:
                    self._toggle_server()

    def _handle_mouse_motion(self, pos: tuple[int, int]) -> None:
        """Обновить целевой взгляд офиса и обработать ховер кнопки TAB."""
        w = self.view.screen_w
        self.model.target_look = max(-1.0, min(1.0, (pos[0] / w) * 2 - 1))

        if self.model.tablet_animating:
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

        self._update_node7_grace()

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
                self.model.hack_active = False

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
        Звуковая реакция на перемещение Алгема.

        Звук помех играет пока активен trigger_timer (60 тиков).
        Используем edge-trigger: звук начинается при trigger > 0,
        а останавливается когда trigger обнулился.
        """
        trigger_now = self.model.algem_trigger

        if trigger_now > 0 and self._prev_algem_trigger == 0:
            if self.snd_algem_leave:
                self.snd_algem_leave.play(-1)

        elif trigger_now == 0 and self._prev_algem_trigger > 0:
            if self.snd_algem_leave:
                self.snd_algem_leave.stop()

        self._prev_algem_trigger = trigger_now

    def _update_danger_sound(self) -> None:
        """Звук danger2b.wav когда Алгем на последней камере (node 7)."""
        on_last = self.model.algem_location == 7
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
        self._check_node7_attack()
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

        if not self._camera_inited:
            self._camera_inited = True
            if self.snd_cam_init:
                self.snd_cam_init.play()

        if self.snd_tablet:
            self.snd_tablet.play()

    def _close_tablet(self) -> None:
        """Начать анимацию закрытия планшета."""
        self.model.tablet_animating = True
        self._anim_dir = -1
        self.model.tablet_anim_frame = 9
        self._anim_timer = 2

        if self.snd_tablet:
            self.snd_tablet.play()

    def _switch_camera(self, idx: int) -> None:
        """Переключить активную камеру с звуком."""
        self.model.camera_idx = idx
        if self.snd_cam_switch:
            self.snd_cam_switch.play()

    def _toggle_server(self) -> None:
        """Включить или выключить сервер."""
        self._check_node7_attack()
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

    def _update_hack(self) -> None:
        """Авто-прогресс взлома сервера. Чем выше прогресс, тем сильнее приманка для Алгема."""
        if not self.model.hack_active or self.model.server_rebooting:
            return
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

    def _check_node7_attack(self) -> None:
        """Если Алгем на node 7 дольше grace-периода — атака через любой триггер."""
        if self._on_node7_grace >= 60:
            self.model.game_over = True

    def _update_node7_grace(self) -> None:
        """Обновить счётчик времени Алгема на node 7."""
        if self.model.algem_location == 7:
            self._on_node7_grace += 1
        else:
            self._on_node7_grace = 0

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
