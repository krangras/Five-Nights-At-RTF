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
]
CAMERA_COUNT: int = len(CAMERAS)

# Базовый граф: {узел: [соседи]}
# Узел 0 — офис (цель), узлы 1–7 — камеры.
BASE_GRAPH: dict[int, list[int]] = {
    0: [],
    1: [4],          # ALGEM'S ROOM — тупик
    2: [6, 7],       # CANTEEN
    3: [4, 6],       # TOILETS
    4: [1, 3, 6],    # MAIN HALL
    5: [7, 6, 0],    # SERVICE ROOM — последняя перед офисом
    6: [4, 3, 2, 5], # WEST HALL — хаб
    7: [2, 5],       # COWORKING
}

# Вентиляционные короткие пути: {id: (из, в)}
# При поломке вентиля соответствующее ребро добавляется в граф.
VENT_CONNECTIONS: dict[str, tuple[int, int]] = {
    "VENT_A": (7, 3),  # COWORKING → TOILETS (обходной путь)
    "VENT_B": (2, 4),  # CANTEEN → MAIN HALL (обходной путь)
}


# ─────────────────────────────────────────────────────────────────────────────
# Перечисление состояний вентиляции
# ─────────────────────────────────────────────────────────────────────────────

class VentState(Enum):
    """
    Состояния вентиляционного канала.

    OK        — всё в порядке, канал закрыт для Алгема.
    ERROR     — поломка: канал открыт, Алгем может использовать как шорткат.
    RESETTING — игрок нажал «RESET», идёт перезагрузка (~5 секунд).
    """
    OK        = auto()
    ERROR     = auto()
    RESETTING = auto()


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
        self.camera_watch_ticks: dict[int, int] = {i: 0 for i in range(1, 8)}

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
        # Два вентиляционных канала; при ошибке открывается шорткат в графе.
        self.vents:             dict[str, VentState] = {
            vid: VentState.OK for vid in VENT_CONNECTIONS
        }
        # Таймер до случайной поломки (тики)
        self._vent_error_timers: dict[str, int] = {
            vid: self._vent_break_interval() for vid in VENT_CONNECTIONS
        }
        # Прогресс перезагрузки (тики до завершения, 0 = не идёт)
        self._vent_reset_timers: dict[str, int] = {
            vid: 0 for vid in VENT_CONNECTIONS
        }

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
        self._vent_reset_timers[vent_id] = 300   # 5 секунд при 60 FPS

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

    def _update_ai(self) -> None:
        """
        Тик ИИ Алгема.

        Передаём актуальный граф (с учётом сломанных вентов) и данные
        о просмотре камер, затем вызываем tick().
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

        Базовый граф + рёбра сломанных вентов.
        Создаёт новый объект каждый тик — не мутирует BASE_GRAPH.
        """
        g: dict[int, list[int]] = copy.deepcopy(BASE_GRAPH)
        for vid, (src, dst) in VENT_CONNECTIONS.items():
            if self.vents[vid] == VentState.ERROR:
                if dst not in g[src]:
                    g[src] = g[src] + [dst]
        return g

    def _vent_break_interval(self) -> int:
        """
        Случайный интервал до поломки вентиля (в тиках).

        Более высокие ночи → венты ломаются чаще.
        """
        base = max(600, 2400 - self.night * 280)
        return random.randint(base, base + 720)