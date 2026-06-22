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
from .ai_domain import AlgemEvent
from .algem_ai import AlgemAI, bfs_path  # noqa: F401
from .camera_graph import (
    BASE_GRAPH,
    PATROL_GRAPH,
    SEAL_CAMERA_MAP,
    SEAL_RETREAT_GRAPH,
    VENT_CAMERAS,
    VENT_SEALS,
    copy_graph,
)
from .hack_logs import HACK_LOG_SEQUENCES, NIGHT_APPS, HackLogPlayer
from .vent_seal import SealState, VentSealController

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
        self._hack_log_player = HackLogPlayer(HACK_LOG_SEQUENCES)

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
        # SRP: GameModel больше не считает timer'ы seal и не собирает граф
        # вручную. Этим занимается отдельный контроллер вентиляции.
        self._seal_controller = VentSealController(
            vent_seals=VENT_SEALS,
            base_graph=BASE_GRAPH,
            seal_retreat_graph=SEAL_RETREAT_GRAPH,
            seal_duration=SEAL_DURATION,
        )
        self.seals: dict[str, SealState] = self._seal_controller.seals

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
        """Текущий узел Алгема в графе.

        Args:
            Нет.

        Returns:
            Значение типа ``int``."""
        return self._ai.location

    @property
    def algem_prev_location(self) -> int:
        """Предыдущий узел (для отрисовки глитча на нужной камере).

        Args:
            Нет.

        Returns:
            Значение типа ``int``."""
        return self._ai.prev_location

    @property
    def algem_trigger(self) -> int:
        """Анимационный триггер: > 0 = Алгем только что переместился.

        Args:
            Нет.

        Returns:
            Значение типа ``int``."""
        return self._ai.trigger_timer

    @property
    def algem_main_hall_sprite(self) -> int:
        """Вариант спрайта в Главном коридоре (0 или 1).

        Args:
            Нет.

        Returns:
            Значение типа ``int``."""
        return self._ai.main_hall_sprite

    @property
    def algem_state_name(self) -> str:
        """Имя текущего состояния ИИ для HUD (отладка / курсовая работа).

        Args:
            Нет.

        Returns:
            Значение типа ``str``."""
        return self._ai.state_name

    @property
    def algem_last_vent_move(self) -> tuple[int, int]:
        """Return the most recent movement between ventilation nodes."""
        return self._ai.last_vent_move

    @property
    def algem_vent_motion_ticks(self) -> int:
        """Return how long the current ventilation movement remains audible."""
        return self._ai.vent_motion_ticks

    @property
    def algem_vent_audio_source(self) -> int:
        """Return the ventilation node currently producing movement audio."""
        return self._ai.vent_audio_source

    @property
    def algem_last_vent_leave_source(self) -> int:
        """Return the ventilation node Algem most recently left."""
        return self._ai.last_vent_leave_source

    def notify_laptop_power_event(self, event: str) -> None:
        """Forward an office laptop power sound to the AI subsystem."""
        self._ai.notify_laptop_power_event(event)

    @property
    def glitch_active(self) -> bool:
        """Whether the office glitch overlay is currently active."""
        return self._glitch_active

    @property
    def glitch_frame(self) -> int:
        """Current alternating glitch frame."""
        return self._glitch_frame

    @property
    def glitch_timer(self) -> int:
        """Ticks remaining in the current glitch."""
        return self._glitch_timer

    def start_glitch(self, duration: int = 90) -> None:
        """Start a visual glitch for the requested number of ticks."""
        self._glitch_active = True
        self._glitch_timer = duration
        self._glitch_frame = 0
        self._glitch_frame_timer = 0

    def advance_glitch(self) -> bool:
        """Advance the glitch animation and report whether it remains active."""
        if not self._glitch_active:
            return False
        self._glitch_timer -= 1
        if self._glitch_timer <= 0:
            self._glitch_active = False
            return False
        self._glitch_frame_timer -= 1
        if self._glitch_frame_timer <= 0:
            self._glitch_frame = 1 - self._glitch_frame
            self._glitch_frame_timer = 0
        return True

    def drain_algem_events(self) -> list[AlgemEvent]:
        events = list(self.algem_events)
        self.algem_events.clear()
        return events

    def _collect_ai_events(self) -> None:
        self.algem_events.extend(self._ai.drain_events())

    @property
    def currently_sealing_id(self) -> str | None:
        """Id вентиляционной заслонки, которая сейчас закрывается.

        Args:
            Нет.

        Returns:
            Значение типа ``str | None``."""
        return self._seal_controller.currently_sealing_id

    @currently_sealing_id.setter
    def currently_sealing_id(self, value: str | None) -> None:
        """Установить активную SEALING-заслонку для demo-сценариев.

        Args:
            value: Параметр типа ``str | None``, используемый методом ``currently_sealing_id``.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        self._seal_controller.currently_sealing_id = value

    # ──────────────────────────────────────────────────────────────────────
    # Публичный API для Presenter
    # ──────────────────────────────────────────────────────────────────────

    def activate_bait(self, camera_idx: int) -> None:
        """Активировать аудио-приманку на камере camera_idx.

        Вызывается из Presenter при нажатии кнопки PLAY AUDIO.
        Устанавливает cooldown, чтобы нельзя было спамить одну камеру.

        Args:
            camera_idx: Параметр типа ``int``, используемый методом ``activate_bait``.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
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
        """Начать перезагрузку вентиляционного канала vent_id.

        Перезагрузка занимает 300 тиков (5 секунд). В это время
        Алгем всё ещё может использовать сломанный вент.

        Args:
            vent_id: Параметр типа ``str``, используемый методом ``start_vent_reset``.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        return

    def start_seal(self, seal_id: str) -> None:
        """Начать блокировку вентиляционного прохода seal_id (~7 сек).

        Args:
            seal_id: Идентификатор seal из ``VENT_SEALS``.

        Returns:
            ``None``. Команда безопасно игнорируется, если seal уже закрыт,
            не существует или другая заслонка уже находится в фазе SEALING.
        """
        vent_node = self._seal_controller.start(seal_id)
        if vent_node is None:
            return

        # SEALING ещё не блокирует граф. Это только анимация. Физическая
        # блокировка и stun/knock происходят после перехода SEALING -> CLOSED.
        notify = getattr(self._ai, "notify_seal_started", None)
        if notify is not None:
            notify(vent_node, SEAL_DURATION)

    # ──────────────────────────────────────────────────────────────────────
    # Главный тик модели
    # ──────────────────────────────────────────────────────────────────────

    def update(self) -> None:
        """Обновить всё состояние модели на один тик.

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

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
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
        """Плавное следование взгляда за курсором мыши (lerp).

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        self.current_look += (self.target_look - self.current_look) * 0.12

    def _update_cam_pan(self) -> None:
        """Автоматическое панорамирование камеры (покачивание).

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
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
        """Игровые часы: 2700 тиков = 45 секунд = 1 час; 6 AM = конец ночи.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
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
        """Телефонный звонок текущей ночи.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
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
        """Накапливать тики просмотра текущей камеры.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        if self.tablet_open and not self.tablet_animating:
            self.camera_watch_ticks[self.camera_idx] = (
                self.camera_watch_ticks.get(self.camera_idx, 0) + 1
            )

    def _update_bait(self) -> None:
        """Таймеры аудио-приманки и cooldown камер.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
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
        """Legacy vent reset mechanic is disabled in the current design.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        return

    def _update_seals(self) -> None:
        """Обновить подсистему вентиляционных блокировок.

        Args:
            Нет аргументов.

        Returns:
            ``None``. Закрытые на этом тике vent-узлы передаются в ИИ,
            который уже решает, будет ли stun, стук или отступление.
        """
        for vent_node in self._seal_controller.tick():
            notify = getattr(self._ai, "notify_seal_closed", None)
            if notify is not None:
                notify(vent_node)
                self._collect_ai_events()

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
            self._ai.ensure_attention_at_least(attention)

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
        """Тик ИИ Алгема.

        Передаём актуальный граф, данные о просмотре камер,
        состояние сервера и рекламы для шкалы внимания.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
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
        self._ai.set_hack_attraction(self._hack_attraction)

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

        Args:
            Нет.

        Returns:
            Значение типа ``int``."""
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
        """BFS-расстояние между узлами (для расчёта перегрузки сервера).

        Args:
            start: Параметр типа ``int``, используемый методом ``_bfs_dist``.
            goal: Параметр типа ``int``, используемый методом ``_bfs_dist``.

        Returns:
            Значение типа ``int``."""
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
        self._ai.reset_after_office_repel(
            node=5,
            prev_node=0,
            trigger_ticks=30,
            move_timer=120,
            idle_ticks=120,
        )
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

    def schedule_next_overload(self) -> None:
        """Запланировать следующую перегрузку сервера в зависимости от близости Алгема.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        dist = self._bfs_dist(self._ai.location, 0)
        # dist: 0 (офис)…4 (самая дальняя — комната 2)
        max_dist = 4
        factor = min(1.0, dist / max_dist)  # 0.0 рядом … 1.0 далеко
        min_ticks = int(900 + factor * 2100)   # 15 сек рядом, 50 сек далеко
        max_ticks = int(1800 + factor * 3000)  # 30 сек рядом, 80 сек далеко
        self._server_overload_timer = random.randint(min_ticks, max_ticks)

    def _update_server_load(self) -> None:
        """Логика перегрузки сервера.

        Пока сервер ON — тикает таймер. Когда дотикал — перегрузка.
        Если игрок не кликнул за server_overload_warn — сервер выключается.
        Если кликнул — начинается перезагрузка (5 сек), после — сброс.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
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
                self.schedule_next_overload()
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

    @property
    def night_app(self) -> dict[str, str]:
        """Метаданные приложения взлома для текущей ночи.

        Args:
            Нет аргументов.

        Returns:
            Словарь с названием, заголовком окна и заголовком терминала.
        """
        return NIGHT_APPS.get(self.night, NIGHT_APPS[1])

    def _update_hack_logs(self) -> None:
        """Генерировать терминальные логи по мере продвижения взлома.

        Args:
            Нет аргументов.

        Returns:
            ``None``. Детальная последовательность строк живёт в
            ``HackLogPlayer``, поэтому модель только передаёт текущий прогресс
            и игровое время.
        """
        if self.hack_progress <= 0.0 or self.server_state != "ON":
            return
        self._hack_log_player.append_available(
            logs=self.hack_logs,
            night=self.night,
            progress=self.hack_progress,
            hour=self.hour,
            minute=self._clock_minute(),
        )

    _AD_IMAGES = ["ad_hhru", "ad_kontur", "ad_sber"]

    def _rand_ad_interval(self) -> int:
        """Случайный интервал до следующей рекламы, зависит от ночи.

        Args:
            Нет.

        Returns:
            Значение типа ``int``."""
        lo = max(600, 2400 - self.night * 300)
        return random.randint(lo, lo * 2)

    def _update_ad(self) -> None:
        """Случайный спавн рекламы на ноутбуке.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
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
        """Получить текущий граф камер с учётом закрытых вентиляций.

        Args:
            Нет аргументов.

        Returns:
            Граф ``node -> neighbors``. Реальное построение и кэширование
            делегированы ``VentSealController``, чтобы модель не нарушала SRP.
        """
        return self._seal_controller.current_graph(self._ai.location)

    def _vent_break_interval(self) -> int:
        """Случайный интервал до поломки вентиля (в тиках).

        Более высокие ночи → венты ломаются чаще.

        Args:
            Нет.

        Returns:
            Значение типа ``int``."""
        base = max(600, 2400 - self.night * 280)
        return random.randint(base, base + 720)
