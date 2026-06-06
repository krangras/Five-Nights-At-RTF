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

import copy
import random
from collections import deque
from enum import Enum, auto

from algem_ai import AlgemAI, AIState, bfs_path   # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# Константы карты камер
# ─────────────────────────────────────────────────────────────────────────────

CAMERAS: list[tuple[int, str, str, str]] = [
    (1, "01", "ALGEM'S ROOM",  "algems' room.png"),
    (2, "02", "CANTEEN",       "canteen.png"),
    (3, "03", "TOILETS",       "toilets.png"),
    (4, "04", "MAIN HALL",     "main_hall.png"),
    (5, "05", "SERVICE ROOM",  "service_room.png"),
    (6, "06", "WEST HALL",     "westhall.png"),
    (7, "07", "COWORKING",     "coworking.png"),
    (8, "08", "UPPER VENT",    "cam8.png"),
    (9, "09", "LEFT VENT",     "cam9.png"),
    (10, "10", "LEFT VENT LOW", "cam_10.png"),
    (11, "11", "RIGHT VENT",   "cam11.png"),
]
CAMERA_COUNT: int = len(CAMERAS)

# Индексы вент-камер (8–11)
VENT_CAMERAS: set[int] = {8, 9, 10, 11}


def find_nearest_vent_camera(
    current_cam: int,
    graph: dict[int, list[int]],
) -> int:
    """BFS: найти ближайшую вент-камеру к current_cam."""
    if current_cam in VENT_CAMERAS:
        return current_cam
    visited: set[int] = {current_cam}
    queue: deque[list[int]] = deque([[current_cam]])
    while queue:
        path = queue.popleft()
        node = path[-1]
        for nb in graph.get(node, []):
            if nb in visited:
                continue
            new_path = path + [nb]
            if nb in VENT_CAMERAS:
                return nb
            visited.add(nb)
            queue.append(new_path)
    return 8  # fallback


# Базовый граф: {узел: [соседи]}
# Узел 0 — офис (цель), узлы 1–7 — камеры.
BASE_GRAPH: dict[int, list[int]] = {
    0: [],             # OFFICE
    1: [4],            # ALGEM'S ROOM — тупик
    2: [6, 7, 9],      # CANTEEN → WEST HALL, COWORKING, LEFT VENT
    3: [4, 6, 8],      # TOILETS → MAIN HALL, WEST HALL, UPPER VENT
    4: [1, 3, 6, 9],   # MAIN HALL → ALGEM'S ROOM, TOILETS, WEST HALL, LEFT VENT
    5: [7, 6, 0],      # SERVICE ROOM — последняя перед офисом
    6: [4, 3, 2, 5],   # WEST HALL — хаб
    7: [2, 5, 8],      # COWORKING → CANTEEN, SERVICE ROOM, UPPER VENT
    8: [3, 7, 11],     # UPPER VENT — между TOILETS, COWORKING и RIGHT VENT
    9: [2, 4, 10],     # LEFT VENT — между CANTEEN, MAIN HALL и LEFT VENT LOW
    10: [9, 5],        # LEFT VENT LOW → LEFT VENT, SERVICE ROOM
    11: [8, 5],        # RIGHT VENT → UPPER VENT, SERVICE ROOM
}

# Вентиляционные короткие пути: {id: (из, в)}
VENT_CONNECTIONS: dict[str, tuple[int, int]] = {
    "VENT_A": (7, 3),  # COWORKING → TOILETS
    "VENT_B": (2, 4),  # CANTEEN → MAIN HALL
}

# Точки блокировки вентов (SEAL) — {id: (из, в)}
# При активном seal ребро ВРЕМЕННО удаляется из графа.
VENT_SEALS: dict[str, tuple[int, int]] = {
    "SEAL_TOP_RIGHT":  (7, 2),  # COWORKING → CANTEEN
    "SEAL_CENTER":     (3, 4),  # TOILETS → MAIN HALL
    "SEAL_MID_RIGHT":  (2, 6),  # CANTEEN → WEST HALL
    "SEAL_BOTTOM_LEFT": (6, 4), # WEST HALL → MAIN HALL
}

SEAL_DURATION = 300  # 5 секунд при 60 FPS


# ─────────────────────────────────────────────────────────────────────────────
# Перечисление состояний вентиляции
# ─────────────────────────────────────────────────────────────────────────────

class VentState(Enum):
    OK        = auto()
    ERROR     = auto()
    RESETTING = auto()


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
      - start_vent_reset(vid)  — при нажатии кнопки RESET VENT.

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

        # ── Реклама на ноутбуке ─────────────────────────────────────────
        self.ad_active:      bool = False         # показывается ли реклама
        self.ad_image_key:   str | None = None    # ключ изображения рекламы
        self.ad_sound_channel = None              # канал для звука рекламы
        self.ad_timer:       int = 0              # тиков с момента показа
        self.ad_spawn_timer: int = random.randint(1800, 7200)  # тиков до следующей рекламы

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
            graph      = copy.deepcopy(BASE_GRAPH),
            night      = night,
            start_node = 1,
        )
        self.algem_in_office: bool = False   # вошёл, но не убил (планшет открыт)

        # ── Аудио-приманка ───────────────────────────────────────────────
        self.bait_active:       bool            = False
        self.bait_step:         int             = 0    # 0–5, для отрисовки прогресса
        self.bait_cam_step:     int             = 0    # 0–3, для аудио-иконки
        self.bait_target_node:  int | None      = None
        self.bait_attract_timer: int            = 0    # сколько тиков приманка активна
        self.bait_cooldown:     dict[int, int]  = {}   # {camera_idx: тиков до перезарядки}

        # ── Вентиляция ───────────────────────────────────────────────────
        self.vents:             dict[str, VentState] = {
            vid: VentState.OK for vid in VENT_CONNECTIONS
        }
        self._vent_error_timers: dict[str, int] = {
            vid: self._vent_break_interval() for vid in VENT_CONNECTIONS
        }
        self._vent_reset_timers: dict[str, int] = {
            vid: 0 for vid in VENT_CONNECTIONS
        }

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

        # ── Флаги завершения ─────────────────────────────────────────────
        self.game_over:      bool = False
        self.night_complete: bool = False

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
        if self.vents.get(vent_id) != VentState.ERROR:
            return
        self.vents[vent_id]              = VentState.RESETTING
        self._vent_reset_timers[vent_id] = 300

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
            self.night_start_ticks -= 1

        self._update_office_look()
        self._update_cam_pan()
        self._update_clock()
        self._update_phone()
        self._update_camera_watch()
        self._update_bait()
        self._update_vents()
        self._update_seals()
        self._update_server_load()
        self._update_hack_logs()
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

    def _update_clock(self) -> None:
        """Игровые часы: 3600 тиков = 1 час; 6 AM = конец ночи."""
        self.timer += 1
        if self.timer >= 3600:
            self.hour  += 1
            self.timer  = 0
            if self.hour >= 6:
                if self.hack_progress < 1.0:
                    self.game_over = True
                else:
                    self.night_complete = True

    def _update_phone(self) -> None:
        """Телефонный звонок первой ночи."""
        if (
            self.night == 1
            and self.phone_call_ready
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
        """
        Обновить состояние вентиляционных каналов.

        Каждый вент со временем ломается случайно (зависит от ночи).
        Перезагрузка занимает фиксированное время.
        """
        for vid in VENT_CONNECTIONS:
            state = self.vents[vid]

            if state == VentState.OK:
                # Отсчёт до случайной поломки
                self._vent_error_timers[vid] -= 1
                if self._vent_error_timers[vid] <= 0:
                    self.vents[vid]              = VentState.ERROR
                    self._vent_error_timers[vid] = self._vent_break_interval()

            elif state == VentState.RESETTING:
                # Прогресс перезагрузки
                self._vent_reset_timers[vid] -= 1
                if self._vent_reset_timers[vid] <= 0:
                    self.vents[vid] = VentState.OK
                    self._vent_error_timers[vid] = self._vent_break_interval()

    def _update_seals(self) -> None:
        """Обновить таймеры блокировки вентов."""
        for sid in VENT_SEALS:
            if self.seals[sid] == SealState.SEALING:
                self._seal_timers[sid] -= 1
                if self._seal_timers[sid] <= 0:
                    # После SEALING -> CLOSED (закрыта полностью)
                    self.seals[sid] = SealState.CLOSED
                    # Если этот seal был текущим активным, сбросить флаг
                    if self.currently_sealing_id == sid:
                        self.currently_sealing_id = None

    def _update_ai(self) -> None:
        """
        Тик ИИ Алгема.

        Передаём актуальный граф, данные о просмотре камер,
        состояние сервера и рекламы для шкалы внимания.
        """
        if self.algem_in_office:
            return   # Алгем уже в офисе, ждём закрытия планшета

        # Строим граф с учётом сломанных вентов
        current_graph = self._build_current_graph()
        self._ai.update_graph(current_graph)
        self._ai.update_camera_watch(self.camera_watch_ticks)

        # Притяжение Алгема: растёт пока сервер включён, падает когда выключен
        target = self.hack_progress if self.server_state == "ON" else 0.0
        self._hack_attraction += (target - self._hack_attraction) * 0.01
        self._ai.hack_attraction = self._hack_attraction

        # Передаём состояние сервера и рекламы для шкалы внимания
        server_on = self.server_state == "ON"
        self._ai.update_game_state(
            server_on=server_on,
            ad_active=self.ad_active,
        )

        # Тик ИИ
        reached_office = self._ai.tick(self.hour)

        if reached_office:
            if self.tablet_open and not self.tablet_animating:
                # Алгем вошёл пока открыт планшет — «прячется»
                self.algem_in_office = True
            else:
                # Планшет закрыт — мгновенный game over
                self.game_over = True

    def _bfs_dist(self, start: int, goal: int) -> int:
        """BFS-расстояние между узлами (для расчёта перегрузки сервера)."""
        path = bfs_path(start, goal, BASE_GRAPH)
        return (len(path) - 1) if path else 99

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
        3: {"name": "Moodle", "title": "Moodle АГиТДУ — Курс по АГиТДУ",
            "header": "Moodle — Task Completion"},
        4: {"name": "exam1", "title": "exam1 — Система сдачи экзаменов",
            "header": "exam1 — Auto-Submit Module"},
        5: {"name": "БРС", "title": "БРС — База Рейтинговой Системы",
            "header": "БРС — Debt Closure Engine"},
    }

    @property
    def night_app(self) -> dict[str, str]:
        return self.NIGHT_APPS.get(self.night, self.NIGHT_APPS[1])

    _HACK_LOG_SEQUENCES: dict[int, list[tuple[float, str]]] = {
        1: [
            (0.00, "> CLAUDE MYTHOS v2.1 — Neural Hack Engine"),
            (0.00, "> Initializing neural network..."),
            (0.01, "> Loading transformer model (175B params)..."),
            (0.03, "> Model loaded. GPU memory: 11.2 GB"),
            (0.05, "> Scanning target network topology..."),
            (0.07, "> Found: teacher-pc.local (192.168.1.42)"),
            (0.10, "> Probing open ports... 22, 80, 445, 3389"),
            (0.13, "> SMBv3 detected — attempting relay attack..."),
            (0.16, "> NTLM hash captured: admin\\$3cr3t"),
            (0.19, "> Cracking hash with rules engine..."),
            (0.22, "> Hash cracked in 3.2s — password: Pr0f2024!"),
            (0.25, "> Establishing RDP session to teacher-pc.local..."),
            (0.28, "> Connection established. OS: Windows 10 Education"),
            (0.30, "> Running enumeration script..."),
            (0.33, "> Users found: Admin, Teacher, Student"),
            (0.36, "> Searching for target documents..."),
            (0.39, "> Scanning: C:\\Users\\Teacher\\Documents\\"),
            (0.42, "> Found: Ведомость_2024.docx (2.4 MB)"),
            (0.45, "> Found: Зачетная_книжка.xlsx (890 KB)"),
            (0.48, "> Found: Пароли_ЭИОС.txt (1.2 KB)"),
            (0.50, "> Analyzing document structure..."),
            (0.53, "> Extracting embedded macros..."),
            (0.56, "> Decrypting VBA module..."),
            (0.59, "> Extracting grade data from tables..."),
            (0.62, "> Parsing student records... 847 entries"),
            (0.65, "> Modifying target grades..."),
            (0.68, "> Injecting modified content into docx..."),
            (0.70, "> Rebuilding document hash..."),
            (0.73, "> Validating modified file integrity..."),
            (0.76, "> Wiping access logs on teacher-pc..."),
            (0.79, "> Clearing SMB connection artifacts..."),
            (0.82, "> Removing RDP session history..."),
            (0.85, "> Deploying persistence module..."),
            (0.88, "> Covering tracks: 14 log entries erased"),
            (0.90, "> Generating false audit trail..."),
            (0.93, "> Uploading exfiltrated data to C2..."),
            (0.96, "> Compression ratio: 87.3% (deduplication)"),
            (0.98, "> Final verification..."),
            (1.00, "> MISSION COMPLETE — all objectives achieved"),
        ],
        2: [
            (0.00, "> ARTEMIS v3.8 — Vibecode Lab Engine"),
            (0.00, "> Подключение к artemis.agitdu.ru..."),
            (0.02, "> TLS handshake... OK"),
            (0.04, "> Авторизация: student_42..."),
            (0.06, "> Получение списка курсов..."),
            (0.08, "> Найдено: 6 курсов, 42 задания"),
            (0.10, "> Курс: Устройство ПК (неделя 1-2)"),
            (0.13, "> 1.1 Устройство ПК... генерация ответов"),
            (0.16, "> 1.2 Работа CPU и RAM... vibecode"),
            (0.19, "> 1.3 Хранение данных в памяти... OK"),
            (0.22, "> 1.4 Стек вызовов... генерация"),
            (0.25, "> 1.5 Объекты в Python... OK"),
            (0.28, "> 1.6 Адреса и карты памяти... OK"),
            (0.31, "> 1.7 Типизация и сборка мусора... OK"),
            (0.34, "> Все задания курса 1 сданы"),
            (0.37, "> Курс: Связные списки (неделя 3-4)"),
            (0.40, "> 2.1 Массивы и листы... vibecode"),
            (0.43, "> 2.2 Связные списки... генерация"),
            (0.46, "> 2.3-2.4 LinkedList и Queue... OK"),
            (0.49, "> Все задания курса 2 сданы"),
            (0.52, "> Курс: Анализ сложности (неделя 5-6)"),
            (0.55, "> 3.1 Введение в алгоритмы... OK"),
            (0.58, "> 3.2 Асимптотический анализ... vibecode"),
            (0.61, "> 3.3 Основы оценки сложности... OK"),
            (0.64, "> 3.4 Асимптотический анализ: нюансы... OK"),
            (0.67, "> 3.5 Практический подход к оценке... OK"),
            (0.70, "> 3.6 Анализ сложности: исключения... OK"),
            (0.73, "> 3.7-3.8 Продолжаем погружение... OK"),
            (0.76, "> Все задания курса 3 сданы"),
            (0.79, "> Курс: Рекурсия (неделя 7-8)"),
            (0.82, "> 4.1 Рекурсия в программировании... vibecode"),
            (0.85, "> 5.1 Оптимизация рекурсии... OK"),
            (0.88, "> 5.2 Декомпозиция: разделяй и властвуй... OK"),
            (0.91, "> 5.3 Сортировка слиянием... OK"),
            (0.94, "> Все задания курса 4 сданы"),
            (0.96, "> Синхронизация оценок..."),
            (0.98, "> Обновление рейтинга..."),
            (1.00, "> ALL LABS COMPLETE — все задания сданы"),
        ],
        3: [
            (0.00, "> MOODLE CONNECTOR v2.0 — Task Engine"),
            (0.00, "> Подключение к moodle.agitdu.ru..."),
            (0.02, "> SSL certificate: valid"),
            (0.05, "> Авторизация: student_42..."),
            (0.08, "> Получение курсов... 3 найдено"),
            (0.11, "> Курс: АГиТДУ — Анализ и Графический Интерфейс"),
            (0.14, "> Просроченные задания: 7"),
            (0.17, "> Анализ требований заданий..."),
            (0.20, "> Задание: autolisp_03 (Циклы в AutoLISP)"),
            (0.23, "> Генерация кода на AutoLISP..."),
            (0.26, "> (defun c:solve () (princ))... OK"),
            (0.29, "> Загрузка файла... MIME: application/lisp"),
            (0.32, "> Отправка... graded: 8/10"),
            (0.35, "> Задание: autolisp_05 (Функции)"),
            (0.38, "> Генерация... (defun factoral (n)...)"),
            (0.41, "> Отправка... graded: 9/10"),
            (0.44, "> Задание: dynamo_02 (Параметризация)"),
            (0.47, "> Генерация Node.json..."),
            (0.50, "> Валидация графа... OK"),
            (0.53, "> Отправка... graded: 7/10"),
            (0.56, "> Задание: dynamo_04 (Семплирование)"),
            (0.59, "> Генерация нод... 47 элементов"),
            (0.62, "> Отправка... graded: 8/10"),
            (0.65, "> Задание: revit_api_01 (BIM API)"),
            (0.68, "> C# код: Wall.Create(...)"),
            (0.71, "> Компиляция... DLL built"),
            (0.74, "> Отправка... graded: 9/10"),
            (0.77, "> Задание: python_calc_02"),
            (0.80, "> NumPy/scipy расчёт..."),
            (0.83, "> Отправка... graded: 10/10"),
            (0.86, "> Задание: git_01 (Версионирование)"),
            (0.89, "> git add . && git commit... OK"),
            (0.92, "> Отправка... graded: 10/10"),
            (0.95, "> Пересчёт итоговых баллов..."),
            (0.97, "> Синхронизация с рейтингом..."),
            (1.00, "> ALL TASKS COMPLETE — дедлайны закрыты"),
        ],
        4: [
            (0.00, "> EXAM1 SUBMITTER v1.5 — Auto-Grade Module"),
            (0.00, "> Подключение к exam1.agitdu.ru..."),
            (0.03, "> Авторизация: student_42..."),
            (0.06, "> Получение варианта... Вариант 17"),
            (0.09, "> Предмет: Английский язык (B2)"),
            (0.12, "> Раздел 1: Reading Comprehension"),
            (0.15, "> Загрузка текста... 2847 слов"),
            (0.18, "> NLP-парсинг текста..."),
            (0.21, "> Вопрос 1/12: a) option_3"),
            (0.24, "> Вопрос 2/12: c) option_1"),
            (0.27, "> Вопрос 3/12: b) option_2"),
            (0.30, "> Все ответы Reading... OK"),
            (0.33, "> Раздел 2: Grammar & Vocabulary"),
            (0.36, "> Вопрос 13/24: present perfect"),
            (0.39, "> Вопрос 14/24: passive voice"),
            (0.42, "> Вопрос 15/24: conditional"),
            (0.45, "> Вопрос 16/24: reported speech"),
            (0.48, "> Все ответы Grammar... OK"),
            (0.51, "> Раздел 3: Listening"),
            (0.54, "> Загрузка аудио... 3.2 MB"),
            (0.57, "> Speech-to-text... 12 фрагментов"),
            (0.60, "> Вопрос 25/36: transcript match"),
            (0.63, "> Вопрос 26/36: inference"),
            (0.66, "> Все ответы Listening... OK"),
            (0.69, "> Раздел 4: Writing"),
            (0.72, "> Тема: \"Technology in Education\""),
            (0.75, "> Генерация эссе... 387 слов"),
            (0.78, "> Проверка грамматики... OK"),
            (0.81, "> Проверка лексики... B2 level confirmed"),
            (0.84, "> Отправка эссе... OK"),
            (0.87, "> Расчёт итоговой оценки..."),
            (0.90, "> Reading: 12/12, Grammar: 12/12"),
            (0.93, "> Listening: 12/12, Writing: 8/10"),
            (0.96, "> Итого: 44/46 — ОЦЕНКА: ОТЛИЧНО"),
            (0.98, "> Финальная верификация..."),
            (1.00, "> EXAM PASSED — сертификат сгенерирован"),
        ],
        5: [
            (0.00, "> БРС INTRUDER v4.0 — Debt Closure Engine"),
            (0.00, "> WARNING: BOSS FIGHT — максимальная угроза"),
            (0.02, "> Подключение к brs.agitdu.ru..."),
            (0.05, "> SSL pinning detected — bypass..."),
            (0.08, "> 2FA challenge: SMS code intercepted"),
            (0.11, "> Авторизация: admin_override..."),
            (0.14, "> Доступ получен: READ/WRITE"),
            (0.17, "> Сканирование долгов студента..."),
            (0.20, "> Найдено задолженностей: 7"),
            (0.23, "> Долг 1: Математика — задание 14 (не сдано)"),
            (0.26, "> Генерация ответов... numpy/scipy"),
            (0.29, "> Запись в БД: оценка = 4"),
            (0.32, "> Долг 2: Физика — лабораторная 6"),
            (0.35, "> Генерация отчёта... 12 страниц"),
            (0.38, "> Запись в БД: оценка = 5"),
            (0.41, "> Долг 3: БД — курсовая работа"),
            (0.44, "> Генерация SQL-схемы + запросов..."),
            (0.47, "> Запись в БД: оценка = 5"),
            (0.50, "> Долг 4: ООП — проект \"Калькулятор\""),
            (0.53, "> Генерация Java классов... 14 файлов"),
            (0.56, "> Запись в БД: оценка = 4"),
            (0.59, "> Долг 5: Сети — тест 3"),
            (0.62, "> Генерация ответов... TCP/IP, OSI"),
            (0.65, "> Запись в БД: оценка = 5"),
            (0.68, "> Долг 6: Английский — пропущенный экзамен"),
            (0.71, "> Генерация протокола... B2 level"),
            (0.74, "> Запись в БД: оценка = 5"),
            (0.77, "> Долг 7: История — реферат"),
            (0.80, "> Генерация текста... 23 страницы"),
            (0.83, "> Запись в БД: оценка = 4"),
            (0.86, "> Все долги закрыты (7/7)"),
            (0.89, "> Пересчёт среднего балла..."),
            (0.92, "> Новый средний: 4.71"),
            (0.95, "> Обновление рейтинга..."),
            (0.97, "> Запись в зачётную книжку..."),
            (0.99, "> Удаление следов入侵..."),
            (1.00, "> ALL DEBTS CLOSED — студент чист"),
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
                ts_m = self.timer // 60
                ts = f"[{self.hour}:{ts_m:02d}]"
                self.hack_logs.append(f"{ts} {msg}")
                self._hack_log_idx += 1
            else:
                break

    _AD_IMAGES = ["ad_hhru", "ad_kontur", "ad_sber"]

    def _update_ad(self) -> None:
        """Случайный спавн рекламы на ноутбуке."""
        if self.ad_active:
            self.ad_timer += 1
            return
        self.ad_spawn_timer -= 1
        if self.ad_spawn_timer <= 0:
            self.ad_active = True
            self.ad_image_key = random.choice(self._AD_IMAGES)
            self.ad_timer = 0
            self.ad_spawn_timer = random.randint(2400, 9600)

    # ──────────────────────────────────────────────────────────────────────
    # Утилиты
    # ──────────────────────────────────────────────────────────────────────

    def _build_current_graph(self) -> dict[int, list[int]]:
        """
        Собрать актуальный граф движения.

        Базовый граф + рёбра сломанных вентов - рёбра заблокированных seal'ов.
        """
        g: dict[int, list[int]] = copy.deepcopy(BASE_GRAPH)
        for vid, (src, dst) in VENT_CONNECTIONS.items():
            if self.vents[vid] == VentState.ERROR:
                if dst not in g[src]:
                    g[src] = g[src] + [dst]
        for sid, (src, dst) in VENT_SEALS.items():
            # Блокируем проход если seal в процессе закрывания ИЛИ уже закрыт
            if self.seals[sid] in (SealState.SEALING, SealState.CLOSED):
                if dst in g.get(src, []):
                    g[src] = [n for n in g[src] if n != dst]
        return g

    def _vent_break_interval(self) -> int:
        """
        Случайный интервал до поломки вентиля (в тиках).

        Более высокие ночи → венты ломаются чаще.
        """
        base = max(600, 2400 - self.night * 280)
        return random.randint(base, base + 720)