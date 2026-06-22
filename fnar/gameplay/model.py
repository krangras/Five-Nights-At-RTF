"""
gameplay_model.py — Игровая модель (M в паттерне MVP).

Хранит всё состояние игры: позицию Алгема, граф комнат, вентиляцию,
состояние планшета, сервера, энергию и время. Не знает ничего о Pygame
и рендеринге — чистая логика данных.

Ключевые добавления по сравнению с предыдущей версией:
  - Делегирование ИИ классу AlgemAI (algem_ai.py).
  - Система вентиляции (два вентиляционных канала с возможными ошибками).
  - Динамический граф: при поломке вентиля открываются короткие пути.
  - Флаг algem_in_office: Алгем попадает внутрь, но не game_over сразу —
    нужно закрыть планшет.
"""

from __future__ import annotations

import random
from enum import Enum, auto

from .algem_ai import AIState, AlgemAI, AlgemEvent, bfs_path  # noqa: F401
from .camera_graph import (
    BASE_GRAPH,
    PATROL_GRAPH,
    SEAL_CAMERA_MAP,
    SEAL_RETREAT_GRAPH,
    VENT_SEALS,
    VENT_CAMERAS,
    copy_graph,
)

# ─────────────────────────────────────────────────────────────────────────────
# Константы карты камер
# ─────────────────────────────────────────────────────────────────────────────

CAMERAS: list[tuple[int, str, str, str]] = [
    (1, "01", "ALGEM'S ROOM",  "algems' room.png"),
    (2, "02", "CANTEEN",       "canteen.png"),
    (3, "03", "TOILETS",       "toilets.png"),
    (4, "04", "MAIN HALL",     "main_hall.png"),
    (5, "05", "WEST HALL",     "westhall.png"),
    (6, "06", "COWORKING",     "coworking.png"),
    (7, "07", "SERVICE ROOM",  "service_room.png"),
    (8, "08", "LOWER RIGHT VENT", "cam11.png"),
    (9, "09", "UPPER RIGHT VENT", "cam8.png"),
    (10, "10", "UPPER LEFT VENT", "cam9.png"),
    (11, "11", "LOWER LEFT VENT", "cam_10.png"),
]
CAMERA_COUNT: int = len(CAMERAS)

FPS = 60
GAME_HOUR_SECONDS = 45
GAME_HOUR_TICKS = FPS * GAME_HOUR_SECONDS
GAME_MINUTE_TICKS = max(1, GAME_HOUR_TICKS // 60)

# Графы и привязки вентиляции берутся из camera_graph.py.
VENT_CONNECTIONS: dict[str, tuple[int, int]] = {}

SEAL_DURATION = 420  # 7 секунд при 60 FPS

OFFICE_THREAT_TICKS_BY_NIGHT: dict[int, int] = {
    1: 360,  # 6 сек
    2: 300,  # 5 сек
    3: 240,  # 4 сек
    4: 180,  # 3 сек
    5: 120,  # 2 сек
}

LAST_CHANCE_ROULETTE_CHANCES_BY_NIGHT: dict[int, tuple[float, ...]] = {
    1: (0.0,),
    2: (1.0, 1.0, 5 / 6, 4 / 6, 3 / 6, 2 / 6, 1 / 6, 0.0),
    3: (1.0, 1.0, 5 / 6, 4 / 6, 3 / 6, 2 / 6, 1 / 6, 0.0),
    4: (1.0, 5 / 6, 4 / 6, 3 / 6, 2 / 6, 1 / 6, 0.0),
    5: (5 / 6, 4 / 6, 3 / 6, 2 / 6, 1 / 6, 0.0),
}

POST_HACK_SURVIVAL_TICKS_BY_NIGHT: dict[int, int] = {
    1: 900,
    2: 1200,
    3: 1500,
    4: 1800,
    5: 2100,
}

POST_HACK_RAGE_TICKS_BY_NIGHT: dict[int, int] = {
    1: 900,
    2: 1500,
    3: 1800,
    4: 2100,
    5: 2400,
}

POST_HACK_RAGE_ATTENTION_BY_NIGHT: dict[int, float] = {
    1: 56.0,
    2: 73.0,
    3: 84.0,
    4: 91.0,
    5: 96.0,
}

POST_HACK_DARK_RAGE_ATTENTION_BY_NIGHT: dict[int, float] = {
    1: 48.0,
    2: 66.0,
    3: 77.0,
    4: 85.0,
    5: 90.0,
}

POST_HACK_RAGE_LEVEL_BY_NIGHT: dict[int, float] = {
    1: 1.55,
    2: 2.55,
    3: 3.55,
    4: 4.55,
    5: 5.35,
}

POST_HACK_DARK_RAGE_LEVEL_BY_NIGHT: dict[int, float] = {
    1: 1.35,
    2: 2.35,
    3: 3.35,
    4: 4.35,
    5: 5.20,
}


# ─────────────────────────────────────────────────────────────────────────────
# Перечисление состояний вентиляции
# ─────────────────────────────────────────────────────────────────────────────

class SealState(Enum):
    OPEN    = auto()
    SEALING = auto()
    CLOSED  = auto()


# ─────────────────────────────────────────────────────────────────────────────
# Основная модель
# ─────────────────────────────────────────────────────────────────────────────

class GameModel:
    """
    Центральное хранилище состояния одной ночи.

    Presenter вызывает:
      - update()               — каждый тик игрового цикла.
      - activate_bait(cam_idx) — при нажатии кнопки PLAY AUDIO.
    View читает публичные атрибуты напрямую (без сеттеров — упрощение для
    учебного проекта; в продакшене использовались бы свойства + Observer).
    """

    def __init__(self, night: int = 1) -> None:
        self.night:  int   = night

        # ── Время ────────────────────────────────────────────────────────
        self.hour:  int = 0
        self.timer: int = 0
        self.night_start_ticks: int = 0     # таймер стартового экрана

        # ── Взгляд игрока (панорамирование офиса) ────────────────────────
        self.target_look:  float = 0.0
        self.current_look: float = 0.0

        # ── Сервер ───────────────────────────────────────────────────────
        self.server_state: str        = "OFF"   # OFF | TURNING_ON | ON | TURNING_OFF
        self.server_blink: str | None = None    # "red" | "green" | None
        self.hack_progress: float = 0.0          # 0.0–1.0 прогресс взлома
        self.hack_active: bool = False           # идёт ли авто-взлом
        self._hack_attraction: float = 0.0       # сглаженное притяжение Алгема
        self.server_overload: bool = False       # флаг перегрузки сервера
        self.server_overload_warn: int = 0       # тиков до аварийного выключения
        self._server_overload_timer: int = 0     # тиков до следующей перегрузки
        self.server_rebooting: bool = False      # идёт ли перезагрузка
        self.server_reboot_timer: int = 0        # тиков до конца перезагрузки

        # ── Логи ноутбука (терминал Claude Mythos) ────────────────────────
        self.hack_logs: list[str] = []
        self._hack_log_timer: int = 0
        self._hack_log_idx: int = 0

        # ── Планшет (анимация открытия/закрытия) ─────────────────────────
        self.tablet_open:       bool = False
        self.tablet_animating:  bool = False
        self.tablet_anim_frame: int  = 0

        # ── Ноутбук ─────────────────────────────────────────────────────
        self.laptop_open:   bool = False          # открыт ли экран ноутбука
        self.laptop_zoom:   float = 0.0           # 0.0 = офис, 1.0 = полный зум
        self.laptop_cursor: tuple[int, int] = (640, 360)  # позиция курсора
        self.laptop_start_menu: bool = False      # открыто ли меню Start
        self.laptop_app:    str | None = None     # запущенное приложение
        self.show_real_screen: bool = True        # показывать реальный экран на ноутбуке (F2)
        self.laptop_power_state: str = "OFF"      # OFF | BOOTING | ON | SHUTTING_DOWN
        self.laptop_power_timer: int = 0          # тики до конца boot/shutdown
        self.laptop_boot_stage: str = "boot_black"   # boot_black | initializing | desktop

        # ── Реклама на ноутбуке ─────────────────────────────────────────
        self.ad_active:      bool = False         # показывается ли реклама
        self.ad_image_key:   str | None = None    # ключ изображения рекламы
        self.ad_sound_channel = None              # канал для звука рекламы
        self.ad_timer:       int = 0              # тиков с момента показа
        self.ad_spawn_timer: int = self._rand_ad_interval()     # тиков до следующей рекламы

        # ── Камера (текущая и панорамирование) ───────────────────────────
        self.camera_idx:        int   = 1
        self.cam_look:          float = -1.0
        self.cam_state:         str   = "HOLDING"   # HOLDING | MOVING
        self.cam_hold_timer:    int   = 0
        self.cam_move_progress: float = 0.0
        self.cam_dir:           int   = 1

        # Сколько тиков игрок смотрел на каждую камеру
        self.camera_watch_ticks: dict[int, int] = {i: 0 for i in range(1, CAMERA_COUNT + 1)}

        # ── ИИ Алгема ────────────────────────────────────────────────────
        # AlgemAI инкапсулирует FSM, A* и всю логику перемещения.
        self._ai: AlgemAI = AlgemAI(
            graph      = copy_graph(BASE_GRAPH),
            night      = night,
            start_node = 1,
            patrol_graph=copy_graph(PATROL_GRAPH),
        )
        self.algem_in_office: bool = False   # вошёл, но не убил (планшет открыт)
        self.office_threat_timer: int = 0
        self.office_breach_source: int = -1
        self.manual_server_shutdown_pending: bool = False
        self.last_chance_attempted: bool = False
        self.last_chance_success: bool = False
        self.last_chance_roll: float | None = None
        self.last_chance_chance: float | None = None
        self.last_chance_attempt_index: int = 0
        self.last_chance_save_attempts_total: int = 0
        self.post_hack_started: bool = False
        self.post_hack_active: bool = False
        self.post_hack_shutdown_ready: bool = False
        self.post_hack_survival_timer: int = 0
        self.post_hack_survival_total: int = 0
        self.post_hack_rage_timer: int = 0
        self.post_hack_complete: bool = False
        self.post_hack_log_stage: int = 0
        self.algem_events: list[AlgemEvent] = []

        # ── Аудио-приманка ───────────────────────────────────────────────
        self.bait_active:       bool            = False
        self.bait_step:         int             = 0    # 0–5, для отрисовки прогресса
        self.bait_cam_step:     int             = 0    # 0–3, для аудио-иконки
        self.bait_target_node:  int | None      = None
        self.bait_attract_timer: int            = 0    # сколько тиков приманка активна
        self.bait_cooldown:     dict[int, int]  = {}   # {camera_idx: тиков до перезарядки}

        # ── Вентиляция ───────────────────────────────────────────────────

        # ── Блокировка вентов (SEAL) ─────────────────────────────────────
        self.seals: dict[str, SealState] = {
            sid: SealState.OPEN for sid in VENT_SEALS
        }
        self._seal_timers: dict[str, int] = {
            sid: 0 for sid in VENT_SEALS
        }
        self.currently_sealing_id: str | None = None  # отслеживаем текущий закрываемый seal

        # ── Телефонный звонок (Ночь 1) ───────────────────────────────────
        self.phone_call_ready:  bool = True
        self.phone_call_active: bool = False
        self.phone_muted:       bool = False
        self._phone_timer:      int  = 300   # тиков задержки перед звонком

        # ── Глитч (случайный эффект, каждый тик шанс) ───────────────────
        self._glitch_active: bool = False
        self._glitch_timer: int = 0
        self._glitch_frame: int = 0
        self._glitch_frame_timer: int = 0

        # ── Флаги завершения ─────────────────────────────────────────────
        self.game_over:      bool = False
        self.night_complete: bool = False
        self.kill_from_vent: bool = False
        self._night_end_pending: bool = False

    # ──────────────────────────────────────────────────────────────────────
    # Свойства-делегаты к AlgemAI (View обращается к модели, не к AI)
    # ──────────────────────────────────────────────────────────────────────

    @property
    def algem_location(self) -> int:
        """Текущий узел Алгема в графе."""
        return self._ai.location

    @property
    def algem_prev_location(self) -> int:
        """Предыдущий узел (для отрисовки глитча на нужной камере)."""
        return self._ai.prev_location

    @property
    def algem_trigger(self) -> int:
        """Анимационный триггер: > 0 = Алгем только что переместился."""
        return self._ai.trigger_timer

    @property
    def algem_main_hall_sprite(self) -> int:
        """Вариант спрайта в Главном коридоре (0 или 1)."""
        return self._ai.main_hall_sprite

    @property
    def algem_state_name(self) -> str:
        """Имя текущего состояния ИИ для HUD (отладка / курсовая работа)."""
        return self._ai.state_name

    def drain_algem_events(self) -> list[AlgemEvent]:
        events = list(self.algem_events)
        self.algem_events.clear()
        return events

    def _collect_ai_events(self) -> None:
        self.algem_events.extend(self._ai.drain_events())

    # ──────────────────────────────────────────────────────────────────────
    # Публичный API для Presenter
    # ──────────────────────────────────────────────────────────────────────

    def activate_bait(self, camera_idx: int) -> None:
        """
        Активировать аудио-приманку на камере camera_idx.

        Вызывается из Presenter при нажатии кнопки PLAY AUDIO.
        Устанавливает cooldown, чтобы нельзя было спамить одну камеру.
        """
        if self.bait_active:
            return
        if camera_idx in self.bait_cooldown:
            return

        self.bait_active         = True
        self.bait_step           = 0
        self.bait_cam_step       = 0
        self.bait_target_node    = camera_idx
        self.bait_attract_timer  = 480        # 8 секунд при 60 FPS
        self.bait_cooldown[camera_idx] = 480  # cooldown 8 секунд

        # Уведомляем ИИ
        self._ai.notify_audio_lure(camera_idx, duration=480)

    def start_vent_reset(self, vent_id: str) -> None:
        """
        Начать перезагрузку вентиляционного канала vent_id.

        Перезагрузка занимает 300 тиков (5 секунд). В это время
        Алгем всё ещё может использовать сломанный вент.
        """
        return

    def start_seal(self, seal_id: str) -> None:
        """Начать блокировку вентиляционного прохода seal_id (~5 сек).
        
        Можно закрывать только один seal одновременно.
        При клике на новый seal — все остальные автоматически открываются.
        Кликать можно только на OPEN seal'ы.
        """
        # Проверяем, что клик на OPEN seal (нельзя кликать на CLOSED)
        if self.seals.get(seal_id) != SealState.OPEN:
            return
        
        # Если уже есть seal в процессе закрывания, игнорируем новый
        if self.currently_sealing_id is not None:
            return
        
        # Открыть все закрытые seal'ы (зеленеют)
        for sid in VENT_SEALS:
            if self.seals[sid] == SealState.CLOSED:
                self.seals[sid] = SealState.OPEN
        
        self.seals[seal_id] = SealState.SEALING
        self._seal_timers[seal_id] = SEAL_DURATION
        self.currently_sealing_id = seal_id

        # SEALING ещё не блокирует Алгема. Это только анимация закрытия.
        # Физическая блокировка, stun и knock происходят ниже, при переходе
        # SEALING -> CLOSED, когда на карте уже загорелась красная полоска.
        vent_node = VENT_SEALS.get(seal_id)
        if vent_node is not None and hasattr(self._ai, "notify_seal_started"):
            self._ai.notify_seal_started(vent_node, SEAL_DURATION)

    # ──────────────────────────────────────────────────────────────────────
    # Главный тик модели
    # ──────────────────────────────────────────────────────────────────────

    def update(self) -> None:
        """
        Обновить всё состояние модели на один тик.

        Порядок обновления:
          1. Ранний выход при завершении игры.
          2. Плавное панорамирование офиса.
          3. Автопанорамирование камеры.
          4. Игровой таймер и смена часа.
          5. Телефонный звонок.
          6. Счётчики просмотра камер.
          7. Аудио-приманка.
          8. Вентиляция.
          9. ИИ Алгема (получает актуальный граф и watch-данные).
        """
        if self.game_over or self.night_complete:
            return

        if self.night_start_ticks > 0:
            # Стартовую заставку ночи считает Presenter. Пока она идёт,
            # не запускаем часы, звонок, серверные события и ИИ: иначе
            # телефонный звонок может начаться/закончиться ещё на экране
            # "Night starts", а игрок будто зря записывал звонок.
            self._update_office_look()
            return

        self._update_office_look()
        self._update_cam_pan()
        self._update_clock()
        self._update_phone()
        self._update_camera_watch()
        self._update_bait()
        # Legacy vent reset mechanic removed from the game.
        self._update_seals()
        self._update_server_load()
        self._update_hack_logs()
        self._update_post_hack_phase()
        self._update_ad()
        self._update_ai()

    # ──────────────────────────────────────────────────────────────────────
    # Приватные методы обновления подсистем
    # ──────────────────────────────────────────────────────────────────────

    def _update_office_look(self) -> None:
        """Плавное следование взгляда за курсором мыши (lerp)."""
        self.current_look += (self.target_look - self.current_look) * 0.12

    def _update_cam_pan(self) -> None:
        """Автоматическое панорамирование камеры (покачивание)."""
        if self.cam_state == "HOLDING":
            self.cam_hold_timer += 1
            if self.cam_hold_timer >= 180:
                self.cam_state         = "MOVING"
                self.cam_move_progress = 0.0
        elif self.cam_state == "MOVING":
            self.cam_move_progress += 0.006
            if self.cam_move_progress >= 1.0:
                self.cam_state      = "HOLDING"
                self.cam_hold_timer = 0
                self.cam_dir        = -self.cam_dir
            else:
                t          = self.cam_move_progress
                eased      = t * t * (3 - 2 * t)      # smoothstep
                self.cam_look = (
                    eased * self.cam_dir + (1 - eased) * (-self.cam_dir)
                )

    def _clock_minute(self) -> int:
        return min(59, self.timer // GAME_MINUTE_TICKS)

    @property
    def clock_minute(self) -> int:
        return self._clock_minute()

    def _update_clock(self) -> None:
        """Игровые часы: 2700 тиков = 45 секунд = 1 час; 6 AM = конец ночи."""
        if self._night_end_pending:
            return
        self.timer += 1
        if self.timer >= GAME_HOUR_TICKS:
            self.hour += 1
            self.timer = 0
            if self.hour >= 6:
                self._night_end_pending = True

    def resolve_night_end(self) -> None:
        if not self._night_end_pending or self.game_over or self.night_complete:
            return
        if self.hack_progress >= 0.999:
            self.hack_progress = 1.0
            self.night_complete = True
        else:
            self.game_over = True

    def _update_phone(self) -> None:
        """Телефонный звонок текущей ночи."""
        if (
            self.phone_call_ready
            and not self.phone_call_active
            and not self.phone_muted
        ):
            self._phone_timer -= 1
            if self._phone_timer <= 0:
                self.phone_call_active = True
                self.phone_call_ready  = False

    def _update_camera_watch(self) -> None:
        """Накапливать тики просмотра текущей камеры."""
        if self.tablet_open and not self.tablet_animating:
            self.camera_watch_ticks[self.camera_idx] = (
                self.camera_watch_ticks.get(self.camera_idx, 0) + 1
            )

    def _update_bait(self) -> None:
        """Таймеры аудио-приманки и cooldown камер."""
        if self.bait_attract_timer > 0:
            self.bait_attract_timer -= 1
            if self.bait_attract_timer <= 0:
                self.bait_target_node = None
                self._ai.cancel_audio_lure()

        # Cooldown камер
        for cam in list(self.bait_cooldown):
            self.bait_cooldown[cam] -= 1
            if self.bait_cooldown[cam] <= 0:
                del self.bait_cooldown[cam]

    def _update_vents(self) -> None:
        """Legacy vent reset mechanic is disabled in the current design."""
        return

    def _update_seals(self) -> None:
        """Обновить таймеры блокировки вентов."""
        for sid in VENT_SEALS:
            if self.seals[sid] == SealState.SEALING:
                self._seal_timers[sid] -= 1
                if self._seal_timers[sid] <= 0:
                    # После SEALING -> CLOSED (закрыта полностью). Только
                    # теперь вент реально блокирует путь Алгема.
                    self.seals[sid] = SealState.CLOSED
                    vent_node = VENT_SEALS.get(sid)
                    if vent_node is not None and hasattr(self._ai, "notify_seal_closed"):
                        self._ai.notify_seal_closed(vent_node)
                        self._collect_ai_events()
                    # Если этот seal был текущим активным, сбросить флаг
                    if self.currently_sealing_id == sid:
                        self.currently_sealing_id = None

    def _start_post_hack_phase(self) -> None:
        if self.post_hack_started or self.hack_progress < 1.0:
            return
        self.post_hack_started = True
        self.post_hack_active = True
        self.post_hack_complete = False
        self.post_hack_survival_total = POST_HACK_SURVIVAL_TICKS_BY_NIGHT.get(
            self.night,
            POST_HACK_SURVIVAL_TICKS_BY_NIGHT[5],
        )
        self.post_hack_survival_timer = self.post_hack_survival_total
        self.post_hack_rage_timer = POST_HACK_RAGE_TICKS_BY_NIGHT.get(
            self.night,
            POST_HACK_RAGE_TICKS_BY_NIGHT[5],
        )
        self.post_hack_log_stage = 1
        ts_m = self._clock_minute()
        ts = f"[{self.hour}:{ts_m:02d}]"
        self.hack_logs.append(f"{ts} > ROOT ACCESS: 100%")
        self.hack_logs.append(f"{ts} > ALERT: Algem detected intrusion")
        self.hack_logs.append(f"{ts} > SHUT DOWN SERVER AND LAPTOP")
        self._push_post_hack_rage(False)

    def _post_hack_ready(self) -> bool:
        return (
            self.server_state == "OFF"
            and self.laptop_power_state == "OFF"
            and not self.laptop_open
            and not self.server_rebooting
            and not self.algem_in_office
        )

    def _push_post_hack_rage(self, shutdown_ready: bool = False) -> None:
        if not self.post_hack_active:
            return
        attention_table = (
            POST_HACK_DARK_RAGE_ATTENTION_BY_NIGHT
            if shutdown_ready
            else POST_HACK_RAGE_ATTENTION_BY_NIGHT
        )
        level_table = (
            POST_HACK_DARK_RAGE_LEVEL_BY_NIGHT
            if shutdown_ready
            else POST_HACK_RAGE_LEVEL_BY_NIGHT
        )
        attention = attention_table.get(self.night, attention_table[5])
        rage_level = level_table.get(self.night, level_table[5])
        trigger = getattr(self._ai, "trigger_post_hack_rage", None)
        if trigger is not None:
            trigger(max(120, self.post_hack_rage_timer), attention, rage_level)
        else:
            self._ai.attention = max(self._ai.attention, attention)

    def _update_post_hack_phase(self) -> None:
        if self.hack_progress >= 1.0 and not self.post_hack_started:
            self._start_post_hack_phase()
        if not self.post_hack_active:
            return

        if self.post_hack_rage_timer > 0:
            self.post_hack_rage_timer -= 1

        ready = self._post_hack_ready()
        self._push_post_hack_rage(ready)
        if ready and not self.post_hack_shutdown_ready:
            ts_m = self._clock_minute()
            ts = f"[{self.hour}:{ts_m:02d}]"
            self.hack_logs.append(f"{ts} > SYSTEM DARK: survive until 6 AM")
        self.post_hack_shutdown_ready = ready
        if not ready:
            self.post_hack_survival_timer = self.post_hack_survival_total
        else:
            self.post_hack_survival_timer = 0

    def _update_ai(self) -> None:
        """
        Тик ИИ Алгема.

        Передаём актуальный граф, данные о просмотре камер,
        состояние сервера и рекламы для шкалы внимания.
        """
        if self.algem_in_office:
            self._update_office_threat()
            return

        # Строим граф с учётом сломанных вентов
        current_graph = self._build_current_graph()
        self._ai.update_graph(current_graph, copy_graph(PATROL_GRAPH))
        self._ai.update_camera_watch(self.camera_watch_ticks)

        target = self.hack_progress if self.server_state == "ON" else 0.0
        if self.post_hack_active:
            target = max(target, 0.82 if self.post_hack_shutdown_ready else 1.0)
        self._hack_attraction += (target - self._hack_attraction) * 0.01
        if self.post_hack_active:
            self._hack_attraction = max(self._hack_attraction, 0.78 if self.post_hack_shutdown_ready else 0.92)
        self._ai.hack_attraction = self._hack_attraction

        # Передаём состояние сервера и рекламы для шкалы внимания
        server_on = self.server_state == "ON"
        self._ai.update_game_state(
            server_on=server_on,
            ad_active=self.ad_active,
            tablet_open=self.tablet_open and not self.tablet_animating,
            laptop_open=self.laptop_open and self.laptop_power_state == "ON",
            camera_idx=self.camera_idx if self.tablet_open and not self.tablet_animating else None,
            vent_error_count=0,
        )

        # Тик ИИ
        reached_office = self._ai.tick(self.hour)
        self._collect_ai_events()

        if reached_office:
            self.algem_in_office = True
            self.office_breach_source = self._ai.prev_location
            self.kill_from_vent = self.office_breach_source in (9, 10)
            self.office_threat_timer = self._random_office_threat_timer()
            self.manual_server_shutdown_pending = False
            self.last_chance_attempted = False
            self.last_chance_success = False
            self.last_chance_roll = None
            self.last_chance_chance = None
            self.last_chance_attempt_index = 0

    def _random_office_threat_timer(self) -> int:
        """Случайное, но честное окно перед скримером.

        Скример больше не привязан к закрытию планшета. Алгем сначала
        исчезает с последней камеры/вента, потом игрок получает короткое
        random-окно на реакцию. Чем выше ночь и progress взлома, тем окно
        короче.
        """
        base = OFFICE_THREAT_TICKS_BY_NIGHT.get(self.night, OFFICE_THREAT_TICKS_BY_NIGHT[5])
        spread = max(36, int(base * 0.42))
        timer = random.randint(max(45, base - spread), base + spread)
        if self.kill_from_vent:
            timer = int(timer * 1.10)  # маленький бонус, чтобы vent-смерть не была мгновенной
        if self.hack_progress >= 0.75:
            timer = int(timer * 0.78)
        elif self.hack_progress >= 0.50:
            timer = int(timer * 0.88)
        return max(45, timer)

    def _bfs_dist(self, start: int, goal: int) -> int:
        """BFS-расстояние между узлами (для расчёта перегрузки сервера)."""
        path = bfs_path(start, goal, BASE_GRAPH)
        return (len(path) - 1) if path else 99

    def _can_algem_lose_interest(self) -> bool:
        return (
            self.server_state == "OFF"
            and not self.tablet_open
            and not self.tablet_animating
            and (
                not self.laptop_open
                or self.laptop_power_state == "OFF"
            )
            and not self.ad_active
            and not self.server_rebooting
        )

    def _last_chance_save_chance(self) -> float:
        chances = LAST_CHANCE_ROULETTE_CHANCES_BY_NIGHT.get(
            self.night,
            LAST_CHANCE_ROULETTE_CHANCES_BY_NIGHT[5],
        )
        idx = min(self.last_chance_save_attempts_total, len(chances) - 1)
        return chances[idx]

    def notify_manual_server_shutdown_started(self) -> None:
        if (
            self.algem_in_office
            and self.office_breach_source in (9, 10)
            and not self.last_chance_attempted
        ):
            self.manual_server_shutdown_pending = True

    def try_last_chance_server_shutdown(self) -> bool:
        if not (
            self.algem_in_office
            and self.office_breach_source in (9, 10)
            and self.manual_server_shutdown_pending
            and not self.last_chance_attempted
            and self.server_state == "OFF"
        ):
            return False

        self.last_chance_attempted = True
        self.manual_server_shutdown_pending = False
        chance = self._last_chance_save_chance()
        roll = random.random()
        self.last_chance_save_attempts_total += 1
        self.last_chance_attempt_index = self.last_chance_save_attempts_total
        self.last_chance_chance = chance
        self.last_chance_roll = roll
        ts_m = self._clock_minute()
        ts = f"[{self.hour}:{ts_m:02d}]"
        chance_pct = int(round(chance * 100))
        if roll < chance:
            self.last_chance_success = True
            self.hack_logs.append(
                f"{ts} > SERVER OFF: Algem lost interest "
                f"[save {self.last_chance_attempt_index}, chance {chance_pct}%]"
            )
            self._repel_algem_from_office(reset_hack=False)
            return True

        self.last_chance_success = False
        self.hack_logs.append(
            f"{ts} > SERVER OFF: Algem ignored shutdown "
            f"[save {self.last_chance_attempt_index}, chance {chance_pct}%]"
        )
        return False

    def _repel_algem_from_office(self, reset_hack: bool = True) -> None:
        self.algem_in_office = False
        self.office_threat_timer = 0
        self.office_breach_source = -1
        self.manual_server_shutdown_pending = False
        if hasattr(self._ai, "force_location"):
            self._ai.force_location(5, prev_node=0, trigger_ticks=30)
        else:
            self._ai.location = 5
            self._ai.prev_location = 0
            self._ai.trigger_timer = 30
        self._ai._entry_timer = 0
        self._ai._move_timer = 120
        self._ai.state = AIState.IDLE
        self._ai._idle_ticks_left = 120
        self._ai.attention = 0.0
        self._ai.hack_attraction = 0.0
        self._ai.cancel_audio_lure()
        self._hack_attraction = 0.0
        self.hack_active = False
        if reset_hack:
            self.hack_progress = 0.0

    def _update_office_threat(self) -> None:
        if self.server_state == "OFF":
            if self.try_last_chance_server_shutdown():
                return

        self.office_threat_timer -= 1
        if self.office_threat_timer <= 0:
            self.game_over = True

    def _schedule_next_overload(self) -> None:
        """Запланировать следующую перегрузку сервера в зависимости от близости Алгема."""
        dist = self._bfs_dist(self._ai.location, 0)
        # dist: 0 (офис)…4 (самая дальняя — комната 2)
        max_dist = 4
        factor = min(1.0, dist / max_dist)  # 0.0 рядом … 1.0 далеко
        min_ticks = int(900 + factor * 2100)   # 15 сек рядом, 50 сек далеко
        max_ticks = int(1800 + factor * 3000)  # 30 сек рядом, 80 сек далеко
        self._server_overload_timer = random.randint(min_ticks, max_ticks)

    def _update_server_load(self) -> None:
        """
        Логика перегрузки сервера.

        Пока сервер ON — тикает таймер. Когда дотикал — перегрузка.
        Если игрок не кликнул за server_overload_warn — сервер выключается.
        Если кликнул — начинается перезагрузка (5 сек), после — сброс.
        """
        if self.server_state != "ON":
            self.server_overload = False
            self.server_overload_warn = 0
            self._server_overload_timer = 0
            self.server_rebooting = False
            self.server_reboot_timer = 0
            return

        if self.server_rebooting:
            self.server_reboot_timer -= 1
            if self.server_reboot_timer <= 0:
                self.server_rebooting = False
                self.server_overload = False
                self._schedule_next_overload()
            return

        if self.server_overload:
            self.server_overload_warn -= 1
            if self.server_overload_warn <= 0:
                self.server_state = "TURNING_OFF"
            return

        self._server_overload_timer -= 1
        if self._server_overload_timer <= 0:
            self.server_overload = True
            self.server_overload_warn = 480

    # ── Логи взлома ───────────────────────────────────────────────────────

    NIGHT_APPS: dict[int, dict[str, str]] = {
        1: {"name": "Claude Mythos", "title": "Claude Mythos v2.1 — Neural Hack Engine",
            "header": "Claude Mythos — Terminal Output"},
        2: {"name": "Artemis", "title": "Artemis — Лабораторные по программированию",
            "header": "Artemis — Vibecode Engine"},
        3: {"name": "Moodle", "title": "Moodle — Курс по АГиТДУ",
            "header": "Moodle — Task Completion"},
        4: {"name": "exam1", "title": "exam1 — Система сдачи экзаменов",
            "header": "exam1 — Auto-Submit Module"},
        5: {"name": "БРС", "title": "БРС — Бально-Рейтинговая Система",
            "header": "БРС — Debt Closure Engine"},
    }

    @property
    def night_app(self) -> dict[str, str]:
        return self.NIGHT_APPS.get(self.night, self.NIGHT_APPS[1])

    _HACK_LOG_SEQUENCES: dict[int, list[tuple[float, str]]] = {
        1: [
            (0.00, "> GRADEBOOK ACCESS MODULE v1.4"),
            (0.00, "> Initializing terminal session..."),
            (0.01, "> Loading network profile: RTF-INTERNAL"),
            (0.02, "> Resolving host: rtf-storage.local"),
            (0.03, "> Host resolved"),
            (0.04, "> Opening SMB session..."),
            (0.05, "> SMB dialect: 3.1.1"),
            (0.06, "> Negotiating security context..."),
            (0.08, "> Kerberos cache detected"),
            (0.09, "> Requesting service ticket: cifs/rtf-storage.local"),
            (0.10, "> Service ticket accepted"),
            (0.12, "> Session established"),

            (0.14, "> Enumerating shares..."),
            (0.16, "> Share mounted: \\\\rtf-storage.local\\statements"),
            (0.18, "> Checking ACL: /statements/2024/"),
            (0.20, "> Effective permissions: READ, LIST"),
            (0.22, "> Write permission: denied"),
            (0.24, "> Searching cached workbook copies..."),
            (0.26, "> Temp workspace available"),
            (0.28, "> Creating shadow copy... OK"),

            (0.30, "> Scanning gradebook directory..."),
            (0.32, "> Found: statement_2024_draft.xlsx"),
            (0.34, "> Found: statement_2024_final.xlsx"),
            (0.36, "> Found: statement_2024_final_rev2.xlsx"),
            (0.38, "> Found: statement_2024_signed.xlsx"),
            (0.40, "> Comparing metadata and revision IDs..."),
            (0.42, "> Selected target: statement_2024_signed.xlsx"),
            (0.44, "> File lock: inactive"),
            (0.46, "> Copying target workbook... OK"),

            (0.48, "> Parsing XLSX container..."),
            (0.50, "> Reading workbook.xml... OK"),
            (0.52, "> Reading sharedStrings.xml... OK"),
            (0.54, "> Reading worksheet relations... OK"),
            (0.56, "> Sheet: attendance"),
            (0.58, "> Sheet: labs"),
            (0.60, "> Sheet: practice"),
            (0.62, "> Sheet: final_statement"),
            (0.64, "> Workbook protection: enabled"),
            (0.66, "> Extracting cell references..."),

            (0.68, "> Locating student record..."),
            (0.70, "> Match: group_id + student_id"),
            (0.72, "> Target row: 18"),
            (0.74, "> Current final status: PENDING"),
            (0.76, "> Checking linked cells..."),
            (0.78, "> Labs: PASSED"),
            (0.80, "> Practice: PASSED"),
            (0.82, "> Attendance: ACCEPTED"),
            (0.84, "> Final mark: EMPTY"),

            (0.86, "> Building worksheet patch..."),
            (0.88, "> Updating final_mark cell..."),
            (0.90, "> Updating final_status cell: PASSED"),
            (0.92, "> Recalculating formulas..."),
            (0.94, "> Updating workbook checksum..."),
            (0.96, "> Repacking XLSX archive..."),
            (0.97, "> Verifying patched workbook... OK"),
            (0.98, "> Replacing cached workbook revision..."),
            (0.99, "> Syncing modified copy to gradebook storage..."),
            (1.00, "> GRADEBOOK PATCH COMPLETE — statement_2024_signed.xlsx updated"),
        ],
        2: [
            (0.00, "> ARTEMIS — semester recovery module"),
            (0.00, "> Подключение к artemis.xetren.com..."),
            (0.01, "> Проверка сессии... OK"),
            (0.03, "> Курс: Практика Python"),
            (0.05, "> Сканирование прошедших заданий..."),
            (0.07, "> Найдено заданий: 41"),
            (0.09, "> Диапазон: Feb 22, 2024 — Jun 6, 2024"),
            (0.11, "> Режим: восстановление прогресса"),

            (0.13, "> [1.x] Устройство ПК / CPU / RAM / Memory..."),
            (0.15, "> 1.1 Устройство ПК... 92.9%"),
            (0.17, "> 1.2 Работа CPU и RAM... 87.5%"),
            (0.19, "> 1.3 Хранение данных в памяти... 83.3%"),
            (0.21, "> 1.4 Стек вызовов... 60%"),
            (0.23, "> 1.5 Объекты в Python... 71.4%"),
            (0.25, "> 1.6 Адреса и карты памяти... 81%"),
            (0.27, "> 1.7 Типизация и сборка мусора... 55.6%"),
            (0.29, "> Модуль 1: требуется добор баллов"),

            (0.31, "> [2.x] Массивы, списки, LinkedList, Queue..."),
            (0.33, "> 2.1 Массивы и листы... 75%"),
            (0.35, "> 2.2 Связные списки... 100%"),
            (0.37, "> 2.3-2.4 LinkedList и Queue... 66.7%"),
            (0.39, "> Memory Map Pt1... 83.3%"),
            (0.41, "> Remember everything 0... 60%, Сборка не удалась"),
            (0.43, "> Brain workout Pt1... 100%"),
            (0.45, "> Модуль 2: найдено 2 слабых места"),

            (0.47, "> [3.x] Алгоритмическая сложность..."),
            (0.49, "> 3.1 Введение... 93.3%"),
            (0.51, "> 3.2 Асимптотический анализ... 84.6%"),
            (0.53, "> 3.3 Основы оценки сложности... 100%"),
            (0.55, "> 3.4 Нюансы асимптотики... 100%"),
            (0.57, "> 3.5 Практический подход к оценке... 42.9%"),
            (0.59, "> 3.6 Исключения в анализе сложности... 66.7%"),
            (0.61, "> 3.7-3.8 Продолжаем погружение... 100%"),
            (0.63, "> Algrorithmic Complexity Pt0... 75%, Сборка не удалась"),
            (0.65, "> Algorithmic Complexity Pt1... 100%, Сборка не удалась"),
            (0.67, "> Аномалия Artemis: баллы есть, сборка красная"),
            (0.69, "> Статус помечен как конфликт автопроверки"),

            (0.71, "> [4.x-5.x] Рекурсия и divide and conquer..."),
            (0.73, "> 4.1 Рекурсия... 100%"),
            (0.75, "> Recursion Pt0... 100%"),
            (0.77, "> 5.1 Оптимизация рекурсии... 100%"),
            (0.79, "> 5.2 Разделяй и властвуй... 80%"),
            (0.81, "> 5.3 Сортировка слиянием... 83.3%"),
            (0.83, "> Explore and make 0... 70%"),
            (0.85, "> Brain Workout Pt0... 100%"),
            (0.87, "> LinkedLists and Co Pt0... 100%"),

            (0.89, "> [6.x] Хеши и словари..."),
            (0.90, "> 6.1 Поиск без поиска. Хеши... 100%"),
            (0.91, "> 6.2 Придумываем хеш-функцию... 75%"),
            (0.92, "> 6.3 Полиномиальный хеш... 100%"),
            (0.93, "> 6.4 Устройство словарей и хеш-таблиц... 100%"),
            (0.94, "> 6.5 __hash__ и __eq__... 100%"),
            (0.95, "> Hashes Pt0... 100%"),

            (0.96, "> [Final] Sort and Search block..."),
            (0.97, "> Sort and Search Pt0... 100%"),
            (0.98, "> Sort and Search Pt1... 99.6%"),
            (0.985, "> Sort and Search Pt2... 100%"),
            (0.99, "> Синхронизация итогового прогресса..."),
            (0.995, "> Проверка итоговых процентов..."),
            (1.00, "> ARTEMIS COMPLETE — 41 задание обработано"),
        ],
        3: [
            (0.00, "> MOODLE QUIZ INJECTION MODULE v2.6"),
            (0.00, "> Controlled session initialization..."),
            (0.01, "> Target host: moodle.agitdu.local"),
            (0.02, "> HTTPS connection established"),
            (0.03, "> Moodle sesskey loaded"),
            (0.04, "> Session context: student"),
            (0.05, "> Course scan started"),
            (0.07, "> Course matched: АГиТДУ"),
            (0.09, "> Educational program: ОП \"Алгоритмы ИИ\""),

            (0.11, "> Quiz target list prepared"),
            (0.13, "> 01: Евклидовы пространства (ДР-II-1)"),
            (0.15, "> 02: Линейные операторы (ДР-II-2)"),
            (0.17, "> 03: Дифференциальные уравнения (КР-II-1)"),

            (0.19, "> Reading access policy..."),
            (0.21, "> Attempt duration: 60 minutes"),
            (0.23, "> Attempt limit: unlimited"),
            (0.25, "> Deadline: 31 May 2024"),
            (0.27, "> Navigation policy: sequential"),
            (0.29, "> Reverse navigation: blocked"),
            (0.31, "> Skipped answers are committed as empty"),
            (0.33, "> Safe sequence mode enabled"),

            (0.35, "> Preparing answer payloads..."),
            (0.37, "> Formula parser initialized"),
            (0.39, "> MathJax rendering cache loaded"),
            (0.41, "> Autosave channel verified"),
            (0.43, "> Submit channel verified"),

            (0.45, "> Launching attempt 1/3: ДР-II-1"),
            (0.47, "> Attempt token issued"),
            (0.49, "> Question sequence locked"),
            (0.51, "> Solving block: Euclidean spaces"),
            (0.53, "> Processing: scalar product"),
            (0.55, "> Processing: norm and distance"),
            (0.57, "> Processing: orthogonality"),
            (0.59, "> Processing: Gram matrix"),
            (0.61, "> Processing: projection theorem"),
            (0.63, "> Payload accepted by autosave"),
            (0.65, "> Attempt submitted: ДР-II-1"),

            (0.67, "> Launching attempt 2/3: ДР-II-2"),
            (0.69, "> Attempt token issued"),
            (0.71, "> Question sequence locked"),
            (0.73, "> Solving block: linear operators"),
            (0.75, "> Processing: kernel and image"),
            (0.77, "> Processing: operator matrix"),
            (0.79, "> Processing: basis transformation"),
            (0.81, "> Processing: eigenvalues"),
            (0.83, "> Processing: invariant subspaces"),
            (0.85, "> Payload accepted by autosave"),
            (0.87, "> Attempt submitted: ДР-II-2"),

            (0.89, "> Launching attempt 3/3: КР-II-1"),
            (0.90, "> Attempt token issued"),
            (0.91, "> Question sequence locked"),
            (0.92, "> Solving block: differential equations"),
            (0.93, "> Processing: separable equations"),
            (0.94, "> Processing: linear first-order equations"),
            (0.95, "> Processing: Cauchy problem"),
            (0.96, "> Processing: higher-order linear DE"),
            (0.97, "> Processing: systems of DE"),
            (0.98, "> Payload accepted by autosave"),
            (0.99, "> Attempt submitted: КР-II-1"),
            (1.00, "> MOODLE QUIZ CHAIN COMPLETE — all targets submitted"),
        ],
        4: [
            (0.00, "> EXAM1 CONTROLLED SUBMITTER v3.2"),
            (0.00, "> Secure exam session initialization..."),
            (0.01, "> Target host: exam1.ntk.local"),
            (0.02, "> HTTPS connection established"),
            (0.03, "> Loading session state..."),
            (0.04, "> Session token: valid"),
            (0.05, "> CSRF token: valid"),
            (0.06, "> Exam context loaded"),
            (0.07, "> User role: student"),
            (0.08, "> Interface state: locked attempt"),

            (0.10, "> Searching active exams..."),
            (0.12, "> Exam matched: Английский язык НТК"),
            (0.14, "> Attempt found: active"),
            (0.16, "> Timer synchronization... OK"),
            (0.18, "> Autosave endpoint verified"),
            (0.20, "> Final submit endpoint verified"),
            (0.22, "> Passive proctoring flag detected"),
            (0.24, "> Navigation restrictions loaded"),

            (0.26, "> Reading exam layout..."),
            (0.28, "> Section detected: Reading"),
            (0.30, "> Section detected: Use of English"),
            (0.32, "> Section detected: Listening"),
            (0.34, "> Section detected: Writing"),
            (0.36, "> Answer fields indexed"),
            (0.38, "> Building response queue..."),

            (0.40, "> [READING] Loading passage data..."),
            (0.42, "> Passage block received"),
            (0.44, "> Question group: multiple choice"),
            (0.46, "> Question group: matching"),
            (0.48, "> Question group: true/false"),
            (0.50, "> Extracting context anchors..."),
            (0.52, "> Resolving reference answers..."),
            (0.54, "> Reading payload built"),
            (0.56, "> Autosave checkpoint: Reading"),

            (0.58, "> [USE_OF_ENGLISH] Parsing grammar blocks..."),
            (0.60, "> Block: verb tenses"),
            (0.62, "> Block: modal verbs"),
            (0.64, "> Block: passive voice"),
            (0.66, "> Block: conditionals"),
            (0.68, "> Block: word formation"),
            (0.70, "> Block: phrasal verbs"),
            (0.72, "> Grammar payload built"),
            (0.74, "> Autosave checkpoint: Use of English"),

            (0.76, "> [LISTENING] Audio task detected"),
            (0.77, "> Audio stream handshake... OK"),
            (0.78, "> Segmenting audio track..."),
            (0.79, "> Segment 1/3 processed"),
            (0.80, "> Segment 2/3 processed"),
            (0.81, "> Segment 3/3 processed"),
            (0.82, "> Speech-to-text confidence: acceptable"),
            (0.83, "> Extracting timestamps and keywords..."),
            (0.84, "> Listening payload built"),
            (0.85, "> Autosave checkpoint: Listening"),

            (0.86, "> [WRITING] Loading prompt..."),
            (0.87, "> Prompt type: essay"),
            (0.88, "> Topic detected: education / technology"),
            (0.89, "> Planning structure: intro, arguments, conclusion"),
            (0.90, "> Generating text within word limit..."),
            (0.91, "> Grammar pass: OK"),
            (0.92, "> Vocabulary level: B1/B2"),
            (0.93, "> Plagiarism risk: low"),
            (0.94, "> Writing payload built"),
            (0.95, "> Autosave checkpoint: Writing"),

            (0.96, "> Final consistency check..."),
            (0.97, "> Empty fields: 0"),
            (0.98, "> Attempt state: ready to submit"),
            (0.99, "> Sending final submission..."),
            (1.00, "> EXAM1 COMPLETE — English NTK exam submitted"),
        ],
        5: [
            (0.00, "> BRS FINAL OVERRIDE MODULE v5.0"),
            (0.00, "> Boss session initialization..."),
            (0.01, "> Target system: brs.rtf.local"),
            (0.02, "> Establishing secure channel... OK"),
            (0.03, "> Loading student record context..."),
            (0.04, "> Student ID: 2309876"),
            (0.05, "> Faculty: Радиоэлектроники и информационных технологий — РТФ"),
            (0.06, "> Study form: очная"),
            (0.07, "> Admission date: 01.09.2023"),

            (0.09, "> Opening BRS registry..."),
            (0.11, "> Authentication context: limited"),
            (0.13, "> Checking role permissions..."),
            (0.15, "> WRITE permission: denied"),
            (0.17, "> Searching cached grade transactions..."),
            (0.19, "> Transaction template found"),
            (0.21, "> Preparing gradebook synchronization layer..."),
            (0.23, "> Loading attestation table..."),

            (0.25, "> Found records: 12"),
            (0.26, "> Term: 2024 interim attestation"),
            (0.27, "> Grade format: 5-point scale"),
            (0.28, "> Signature column detected"),
            (0.29, "> Date column detected"),
            (0.30, "> Validation rules loaded"),

            (0.32, "> [01/12] Английский язык"),
            (0.33, "> Work type: экзамен"),
            (0.34, "> Current state: pending sync"),
            (0.35, "> Setting grade: 5 (отлично)"),
            (0.36, "> Date: 14.06.2024"),
            (0.37, "> Signature hash attached"),

            (0.39, "> [02/12] Программирование"),
            (0.40, "> Work type: экзамен"),
            (0.41, "> Setting grade: 5 (отлично)"),
            (0.42, "> Date: 16.06.2024"),
            (0.43, "> Checking lab dependencies... OK"),
            (0.44, "> Signature hash attached"),

            (0.46, "> [03/12] Алгебра, геометрия и ТДУ"),
            (0.47, "> Work type: экзамен"),
            (0.48, "> Linked course: АГиТДУ"),
            (0.49, "> Moodle debt reference detected"),
            (0.50, "> Resolving dependency... OK"),
            (0.51, "> Setting grade: 5 (отлично)"),
            (0.52, "> Date: 18.06.2024"),
            (0.53, "> Signature hash attached"),

            (0.55, "> [04/12] Философия"),
            (0.56, "> Work type: зачёт"),
            (0.57, "> Setting result: зачтено"),
            (0.58, "> Grade mirror: 5 (отлично)"),
            (0.59, "> Date: 20.06.2024"),
            (0.60, "> Signature hash attached"),

            (0.62, "> [05/12] Физика"),
            (0.63, "> Work type: экзамен"),
            (0.64, "> Lab reports dependency detected"),
            (0.65, "> Dependency state: accepted"),
            (0.66, "> Setting grade: 5 (отлично)"),
            (0.67, "> Date: 21.06.2024"),
            (0.68, "> Signature hash attached"),

            (0.70, "> [06/12] Электротехника и электроника"),
            (0.71, "> Work type: зачёт"),
            (0.72, "> Setting result: зачтено"),
            (0.73, "> Grade mirror: 5 (отлично)"),
            (0.74, "> Date: 22.06.2024"),
            (0.75, "> Signature hash attached"),

            (0.77, "> [07/12] Математический анализ"),
            (0.78, "> Work type: экзамен"),
            (0.79, "> Checking exam protocol..."),
            (0.80, "> Protocol state: available"),
            (0.81, "> Setting grade: 5 (отлично)"),
            (0.82, "> Date: 12.06.2024"),
            (0.83, "> Signature hash attached"),

            (0.85, "> [08/12] Теория вероятностей и мат. статистика"),
            (0.86, "> Work type: зачёт"),
            (0.87, "> Setting result: зачтено"),
            (0.88, "> Grade mirror: 5 (отлично)"),
            (0.89, "> Date: 13.06.2024"),
            (0.90, "> Signature hash attached"),

            (0.91, "> [09/12] Дискретная математика"),
            (0.92, "> Work type: экзамен"),
            (0.93, "> Setting grade: 5 (отлично)"),
            (0.94, "> Date: 17.06.2024"),

            (0.95, "> [10/12] Базы данных"),
            (0.955, "> Work type: экзамен"),
            (0.960, "> Setting grade: 5 (отлично)"),
            (0.965, "> Date: 19.06.2024"),

            (0.970, "> [11/12] Операционные системы"),
            (0.975, "> Work type: зачёт"),
            (0.980, "> Setting result: зачтено"),

            (0.985, "> [12/12] Физическая культура"),
            (0.990, "> Work type: зачёт"),
            (0.992, "> Setting result: зачтено"),

            (0.994, "> Recalculating semester rating..."),
            (0.996, "> Updating зачётная книжка mirror..."),
            (0.997, "> Validating all 12 records... OK"),
            (0.998, "> Writing final BRS transaction..."),
            (0.999, "> Audit state: pending"),
            (1.00, "> BRS FINAL COMPLETE — all exams and credits closed"),
        ],
    }

    def _update_hack_logs(self) -> None:
        """Генерировать логи взлома по мере продвижения hack_progress."""
        if self.hack_progress <= 0.0 or self.server_state != "ON":
            return
        seq = self._HACK_LOG_SEQUENCES.get(self.night, self._HACK_LOG_SEQUENCES[1])
        while self._hack_log_idx < len(seq):
            threshold, msg = seq[self._hack_log_idx]
            if self.hack_progress >= threshold:
                ts_m = self._clock_minute()
                ts = f"[{self.hour}:{ts_m:02d}]"
                self.hack_logs.append(f"{ts} {msg}")
                self._hack_log_idx += 1
            else:
                break

    _AD_IMAGES = ["ad_hhru", "ad_kontur", "ad_sber"]

    def _rand_ad_interval(self) -> int:
        """Случайный интервал до следующей рекламы, зависит от ночи."""
        lo = max(600, 2400 - self.night * 300)
        return random.randint(lo, lo * 2)

    def _update_ad(self) -> None:
        """Случайный спавн рекламы на ноутбуке."""
        if (
            self.laptop_power_state != "ON"
            or not self.hack_active
            or self.server_state != "ON"
            or self.hack_progress >= 1.0
        ):
            self.ad_active = False
            self.ad_image_key = None
            self.ad_timer = 0
            self.ad_spawn_timer = max(self.ad_spawn_timer, self._rand_ad_interval())
            return
        if self.ad_active:
            self.ad_timer += 1
            return
        self.ad_spawn_timer -= 1
        if self.ad_spawn_timer <= 0:
            self.ad_active = True
            self.ad_image_key = random.choice(self._AD_IMAGES)
            self.ad_timer = 0
            self.ad_spawn_timer = self._rand_ad_interval()

    # ──────────────────────────────────────────────────────────────────────
    # Утилиты
    # ──────────────────────────────────────────────────────────────────────

    def _build_current_graph(self) -> dict[int, list[int]]:
        g: dict[int, list[int]] = copy_graph(BASE_GRAPH)

        for sid, vent_node in VENT_SEALS.items():
            if self.seals[sid] == SealState.CLOSED:
                for other in list(g):
                    if other != vent_node:
                        g[other] = [n for n in g[other] if n != vent_node]
                if self._ai.location == vent_node:
                    safe_retreats = SEAL_RETREAT_GRAPH.get(vent_node, [])
                    g[vent_node] = [n for n in safe_retreats if n in BASE_GRAPH.get(vent_node, [])]
                else:
                    g[vent_node] = []

        return g

    def _vent_break_interval(self) -> int:
        """
        Случайный интервал до поломки вентиля (в тиках).

        Более высокие ночи → венты ломаются чаще.
        """
        base = max(600, 2400 - self.night * 280)
        return random.randint(base, base + 720)
