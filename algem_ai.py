"""
algem_ai.py — ИИ Алгема для Five Nights At RTF.

В модуле намеренно сохранены и явно используются три алгоритмические идеи
для курсового/ТЗ:

* FSM — конечный автомат поведения Алгема.
* DFS/BFS — патруль и поиск маршрута к приманке в обычной зоне.
* A* — целенаправленная атака к офису по полному графу.

Алгем не телепортируется: любой переход проходит только в соседний узел
текущего графа. Узлы 9 и 10 имеют прямой честный выход в screamer/BREACH,
поэтому атака из вентов разрешена, если путь до них не закрыт seal.
"""

from __future__ import annotations

import heapq
import random
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable


class AIState(Enum):
    """FSM-состояния Алгема."""

    IDLE = auto()          # короткая пауза / низкий интерес
    PATROL = auto()        # DFS-патруль по обычным камерам
    INVESTIGATE = auto()   # проверяет шум, приманку или активность игрока
    ATTACK = auto()        # A* к офису
    VENT_STALK = auto()    # A* уже идёт через вентиляцию
    BREACH = auto()        # ушёл с последней vent-камеры, но ещё не убил
    KILL_PENDING = auto()  # зарезервировано под расширение kill-window в AI
    STUNNED = auto()       # остановлен seal/потерял маршрут
    RETREAT = auto()       # отступает после блока/потери интереса


class AlgemEventType(str, Enum):
    MOVE = "MOVE"
    VENT_MOVE = "VENT_MOVE"
    SEAL_BLOCKED = "SEAL_BLOCKED"
    ROUTE_BLOCKED = "ROUTE_BLOCKED"
    BREACH_STARTED = "BREACH_STARTED"
    OFFICE_ENTERED = "OFFICE_ENTERED"
    ILLEGAL_MOVE_BLOCKED = "ILLEGAL_MOVE_BLOCKED"


@dataclass(frozen=True)
class AlgemEvent:
    kind: AlgemEventType
    source: int
    target: int
    state: str
    delay_ticks: int = 0


@dataclass(frozen=True)
class NightProfile:
    server_growth: float
    ad_growth: float
    hack_interest_scale: float
    silence_decay: float
    ad_safe_window: float
    tablet_growth: float
    tablet_cap: float
    camera_focus_growth: float
    camera_focus_cap: float
    camera_focus_threshold_ticks: int
    vent_growth: float
    vent_cap: float
    idle_attack_threshold: float
    patrol_attack_threshold: float
    hour_attack_delta: float
    office_pull_start: float
    office_pull_max: float
    watch_penalty_scale: float
    lure_fail_chance: float
    lure_hear_distance: int
    entry_delay: int


# ---------------------------------------------------------------------------
# Чистые функции поиска пути
# ---------------------------------------------------------------------------


def bfs_path(start: int, goal: int, graph: dict[int, list[int]]) -> list[int] | None:
    """Кратчайший путь в невзвешенном графе. Сложность O(V + E)."""
    if start == goal:
        return [start]

    queue: deque[list[int]] = deque([[start]])
    visited: set[int] = {start}

    while queue:
        path = queue.popleft()
        current = path[-1]
        for neighbor in graph.get(current, []):
            if neighbor in visited:
                continue
            new_path = path + [neighbor]
            if neighbor == goal:
                return new_path
            visited.add(neighbor)
            queue.append(new_path)
    return None


def dfs_path(start: int, goal: int, graph: dict[int, list[int]]) -> list[int] | None:
    """Один физически допустимый маршрут через DFS. Сложность O(V + E)."""
    if start == goal:
        return [start]

    stack: list[tuple[int, list[int]]] = [(start, [start])]
    visited: set[int] = set()

    while stack:
        current, path = stack.pop()
        if current in visited:
            continue
        if current == goal:
            return path
        visited.add(current)
        for neighbor in reversed(graph.get(current, [])):
            if neighbor not in visited:
                stack.append((neighbor, path + [neighbor]))
    return None


def astar_path(
    start: int,
    goal: int,
    graph: dict[int, list[int]],
    edge_weight_fn: Callable[[int, int], float],
    heuristic: dict[int, int],
) -> list[int] | None:
    """A* для взвешенного графа. Возвращает путь [start, ..., goal]."""
    if start == goal:
        return [start]

    open_heap: list[tuple[float, float, int, list[int]]] = []
    heapq.heappush(open_heap, (float(heuristic.get(start, 999)), 0.0, start, [start]))
    best_g: dict[int, float] = {start: 0.0}

    while open_heap:
        _f, g, current, path = heapq.heappop(open_heap)
        if g > best_g.get(current, float("inf")):
            continue
        if current == goal:
            return path

        for neighbor in graph.get(current, []):
            w = max(0.05, edge_weight_fn(current, neighbor))
            new_g = g + w
            if new_g < best_g.get(neighbor, float("inf")):
                best_g[neighbor] = new_g
                heapq.heappush(
                    open_heap,
                    (new_g + heuristic.get(neighbor, 999), new_g, neighbor, path + [neighbor]),
                )
    return None


class AlgemAI:
    """FSM + DFS/BFS + A* контроллер Алгема."""

    OFFICE_NODE = 0
    DANGER_NODE = 7
    VENT_NODES = {8, 9, 10, 11}
    LAST_VENT_NODES = {9, 10}
    SCREAMER_VENT_NODES = {9, 10}
    PATROL_SAFE_HOME = 1

    # Интервалы между решениями. Чем выше ночь, тем быстрее ИИ.
    _NIGHT_SPEED: dict[int, tuple[int, int]] = {
        1: (999999, 999999),
        2: (520, 920),
        3: (380, 720),
        4: (270, 560),
        5: (190, 420),
    }

    _VENT_STAY_TICKS_BY_NIGHT: dict[int, int] = {
        1: 999999,
        2: 1320,
        3: 1080,
        4: 840,
        5: 660,
    }

    _VENT_ROUTE_CHANCE_BY_NIGHT: dict[int, float] = {
        1: 0.0,
        2: 0.36,
        3: 0.48,
        4: 0.62,
        5: 0.74,
    }

    _UNPREDICTABLE_ROUTE_CHANCE_BY_NIGHT: dict[int, float] = {
        1: 0.0,
        2: 0.12,
        3: 0.22,
        4: 0.34,
        5: 0.48,
    }
    _MAX_DETOURS_PER_ATTACK_BY_NIGHT: dict[int, int] = {
        1: 0,
        2: 1,
        3: 2,
        4: 3,
        5: 4,
    }
    _DETOUR_COOLDOWN_BY_NIGHT: dict[int, int] = {
        1: 999,
        2: 5,
        3: 4,
        4: 3,
        5: 2,
    }
    _UNPREDICTABLE_ROUTE_OPTIONS: dict[int, list[tuple[float, tuple[int, ...]]]] = {
        1: [(1.55, (8,)), (1.05, (4, 11)), (0.80, (3, 5, 6))],
        2: [(1.90, (8,)), (0.95, (3, 4, 11)), (0.65, (1, 4))],
        3: [(1.70, (8,)), (0.95, (5, 6, 10)), (0.75, (4, 11))],
        4: [(1.35, (11, 10)), (0.90, (1, 8, 2)), (0.75, (5, 6))],
        5: [(1.25, (6, 10)), (0.95, (4, 11, 7)), (0.70, (3, 8))],
        6: [(1.65, (10, 7)), (0.90, (5, 4, 11)), (0.65, (3, 8))],
        7: [(1.20, (11, 10)), (0.90, (10, 11))],
        8: [(1.20, (3, 5, 6)), (1.05, (1, 4, 11)), (0.90, (2, 9))],
        9: [(1.45, (10, 7)), (0.95, (2, 3, 8)), (0.70, (2, 1, 4, 11))],
        10: [(1.25, (7, 11)), (0.95, (11, 4)), (0.65, (7, 10))],
        11: [(1.15, (7, 10)), (0.95, (4, 3, 8)), (0.75, (10, 7))],
    }
    _SPECIAL_DETOUR_EDGES: dict[int, list[int]] = {
        9: [10],
    }

    _ATTACK_ROOM_STEP_MIN_TICKS_BY_NIGHT: dict[int, int] = {
        1: 999999,
        2: 210,
        3: 165,
        4: 120,
        5: 90,
    }

    # Шанс/давление пассивного патруля. Он не стоит всю ночь, но и не убивает
    # игрока просто за бездействие на ранних ночах.
    _AMBIENT_CAP_BY_NIGHT: dict[int, float] = {1: 0.0, 2: 7.0, 3: 12.0, 4: 17.0, 5: 23.0}
    _AMBIENT_GROWTH_BY_NIGHT: dict[int, float] = {1: 0.0, 2: 0.28, 3: 0.45, 4: 0.62, 5: 0.86}

    _BREACH_DELAY_BY_NIGHT: dict[int, tuple[int, int]] = {
        1: (999999, 999999),
        2: (150, 270),   # 2.5–4.5 сек: кадр, где его уже нет в венте
        3: (120, 240),
        4: (90, 210),
        5: (70, 180),
    }
    _STUN_TICKS_BY_NIGHT: dict[int, tuple[int, int]] = {
        1: (0, 0),
        2: (180, 300),
        3: (150, 270),
        4: (120, 240),
        5: (90, 180),
    }

    _NIGHT_PROFILES: dict[int, NightProfile] = {
        1: NightProfile(0.0, 0.0, 0.0, 18.0, 99.0, 0.0, 0.0, 0.0, 0.0, 999999, 0.0, 0.0, 999.0, 999.0, 0.0, 999.0, 0.0, 0.85, 0.15, 2, 90),
        2: NightProfile(5.2, 18.0, 18.0, 14.0, 2.4, 6.5, 16.0, 9.0, 20.0, 240, 10.0, 16.0, 88.0, 92.0, 2.0, 28.0, 0.35, 0.60, 0.08, 3, 105),
        3: NightProfile(8.5, 24.0, 25.0, 17.0, 1.9, 8.0, 20.0, 12.0, 26.0, 210, 12.0, 22.0, 78.0, 84.0, 3.0, 24.0, 0.55, 0.75, 0.13, 3, 90),
        4: NightProfile(11.5, 26.0, 30.0, 18.0, 1.65, 10.0, 24.0, 15.0, 30.0, 180, 14.0, 24.0, 72.0, 78.0, 3.6, 20.0, 0.72, 0.85, 0.15, 3, 90),
        5: NightProfile(15.0, 28.0, 38.0, 18.0, 1.45, 12.0, 28.0, 18.0, 34.0, 150, 16.0, 28.0, 64.0, 72.0, 4.5, 16.0, 0.88, 0.95, 0.17, 3, 90),
    }

    _PATROL_ZONES: dict[int, set[int]] = {
        1: {1, 2, 3, 4, 5, 6},
        2: {1, 2, 3, 4, 5, 6},
        3: {1, 2, 3, 4, 5, 6},
        4: {1, 2, 3, 4, 5, 6},
        5: {1, 2, 3, 4, 5, 6},
    }

    # Предпочтительные точки проверки источников шума. Не обязательно цель
    # находится ровно там; это просто понятные игровые маршруты.
    _SERVER_INVESTIGATE_TARGETS = [5, 6, 3, 4]
    _TABLET_INVESTIGATE_TARGETS = [3, 4, 2, 5]
    _AD_INVESTIGATE_TARGETS = [2, 3, 4]

    def __init__(
        self,
        graph: dict[int, list[int]],
        night: int,
        start_node: int = 1,
        patrol_graph: dict[int, list[int]] | None = None,
    ) -> None:
        self._graph = graph
        self._patrol_graph = patrol_graph or graph
        self._patrol_graph_is_dedicated = patrol_graph is not None
        self._night = night
        self._profile = self._NIGHT_PROFILES.get(night, self._NIGHT_PROFILES[5])
        self._current_hour = 0

        self.location = start_node
        self.prev_location = start_node
        self.trigger_timer = 0
        self._move_timer = self._initial_delay()

        self.state = AIState.IDLE
        self._idle_ticks_left = random.randint(60, 180)
        self.aggression = 0.0
        self.attention = 0.0
        self.hack_attraction = 0.0

        self._lure_node = -1
        self._lure_ticks_left = 0
        self._investigate_target: int | None = None
        self._attack_goal = self.OFFICE_NODE
        self._breach_timer = 0
        self._breach_source = -1
        self._entry_timer = 0  # backward-compatible external hook
        self._stun_timer = 0
        self._retreat_target = self.PATROL_SAFE_HOME

        self._server_on = False
        self._ad_active = False
        self._tablet_open = False
        self._laptop_open = False
        self._current_camera_idx: int | None = None
        self._vent_error_count = 0
        self._ad_safe_timer = 0.0
        self._ad_immune = True
        self._server_interest = 0.0
        self._ad_interest = 0.0
        self._tablet_interest = 0.0
        self._camera_focus_interest = 0.0
        self._vent_interest = 0.0
        self._ambient_interest = 0.0
        self._post_hack_rage_ticks = 0
        self._post_hack_rage_attention = 0.0

        self.main_hall_sprite = 0
        self._camera_watch: dict[int, int] = {}
        self._patrol_stack = [start_node]
        self._patrol_visited = {start_node}
        self._recent_nodes: deque[int] = deque(maxlen=5)
        self._last_path: list[int] = []
        self._last_move_rejected: tuple[int, int] | None = None
        self._vent_motion_ticks = 0
        self._vent_audio_source = -1
        self._last_vent_move = (-1, -1)
        self._last_vent_leave_source = -1
        self._last_vent_leave_ticks = 0
        self._seal_knock_suppressed_vents: set[int] = set()
        self._pressure_cooldown_ticks = 0
        self._laptop_noise_cooldown = 0
        self._attack_route_epoch = 0
        self._attack_detour_queue: deque[int] = deque()
        self._attack_detour_cooldown = 0
        self._attack_detours_used = 0
        self._events: deque[AlgemEvent] = deque()
        self._last_valid_location = start_node
        self._move_history: deque[tuple[int, int, str]] = deque(maxlen=12)

        self._base_heuristic = self._precompute_heuristic(self._graph, self.OFFICE_NODE)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_graph(
        self,
        graph: dict[int, list[int]],
        patrol_graph: dict[int, list[int]] | None = None,
    ) -> None:
        self._graph = graph
        if patrol_graph is not None:
            self._patrol_graph = patrol_graph
        self._base_heuristic = self._precompute_heuristic(self._graph, self.OFFICE_NODE)

    def drain_events(self) -> list[AlgemEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def force_location(self, node: int, prev_node: int | None = None, trigger_ticks: int = 30) -> None:
        old = self.location if prev_node is None else prev_node
        self.prev_location = old
        self.location = node
        self.trigger_timer = max(0, trigger_ticks)
        self._last_valid_location = node
        self._move_history.append((old, node, "FORCE"))
        self._last_path = []
        self._attack_detour_queue.clear()
        self._attack_detour_cooldown = 0
        self._attack_detours_used = 0
        self._reset_patrol_memory()

    def update_camera_watch(self, watch: dict[int, int]) -> None:
        self._camera_watch = watch

    def update_game_state(
        self,
        server_on: bool,
        ad_active: bool,
        tablet_open: bool = False,
        laptop_open: bool = False,
        camera_idx: int | None = None,
        vent_error_count: int = 0,
        dt: float = 1 / 60,
    ) -> None:
        old_ad = self._ad_active
        self._server_on = server_on
        self._ad_active = ad_active
        self._tablet_open = tablet_open
        self._laptop_open = laptop_open
        self._current_camera_idx = camera_idx
        self._vent_error_count = vent_error_count

        if server_on:
            self._server_interest = min(
                58.0,
                self._server_interest + self._profile.server_growth * dt,
            )
        else:
            self._server_interest = max(
                0.0,
                self._server_interest - self._profile.silence_decay * dt,
            )

        if ad_active:
            if not old_ad:
                self._ad_safe_timer = 0.0
                self._ad_immune = True
            if self._ad_immune:
                self._ad_safe_timer += dt
                if self._ad_safe_timer >= self._profile.ad_safe_window:
                    self._ad_immune = False
            if not self._ad_immune:
                self._ad_interest = min(
                    45.0,
                    self._ad_interest + self._profile.ad_growth * dt,
                )
        else:
            self._ad_safe_timer = 0.0
            self._ad_immune = True
            self._ad_interest = max(0.0, self._ad_interest - self._profile.silence_decay * dt)

        if tablet_open and not laptop_open:
            self._tablet_interest = min(
                self._profile.tablet_cap,
                self._tablet_interest + self._profile.tablet_growth * dt,
            )
        else:
            self._tablet_interest = max(0.0, self._tablet_interest - self._profile.silence_decay * dt)

        focus_ticks = self._camera_watch.get(camera_idx, 0) if camera_idx is not None else 0
        if tablet_open and not laptop_open and focus_ticks >= self._profile.camera_focus_threshold_ticks:
            overload = min(1.0, (focus_ticks - self._profile.camera_focus_threshold_ticks) / 240.0)
            self._camera_focus_interest = min(
                self._profile.camera_focus_cap,
                self._camera_focus_interest
                + self._profile.camera_focus_growth * (0.35 + overload) * dt,
            )
        else:
            self._camera_focus_interest = max(
                0.0,
                self._camera_focus_interest - self._profile.silence_decay * dt,
            )

        if vent_error_count > 0:
            self._vent_interest = min(
                self._profile.vent_cap,
                self._vent_interest + self._profile.vent_growth * min(2, vent_error_count) * dt,
            )
        else:
            self._vent_interest = max(0.0, self._vent_interest - self._profile.silence_decay * dt)

        # Пассивный пульс: Алгем не стоит всю ночь, но на ранних ночах это
        # почти не превращается в атаку без действий игрока.
        ambient_cap = self._AMBIENT_CAP_BY_NIGHT.get(self._night, 0.0)
        ambient_growth = self._AMBIENT_GROWTH_BY_NIGHT.get(self._night, 0.0)
        if self._night >= 2:
            hour_bonus = 1.0 + self._current_hour * 0.18
            self._ambient_interest = min(ambient_cap, self._ambient_interest + ambient_growth * hour_bonus * dt)
        else:
            self._ambient_interest = 0.0

        rage_pressure = 0.0
        if self._post_hack_rage_ticks > 0:
            self._post_hack_rage_ticks -= 1
            rage_pressure = self._post_hack_rage_attention
        else:
            self._post_hack_rage_attention = max(0.0, self._post_hack_rage_attention - 0.35)

        # Hack attraction уже сглаженно передаётся из GameModel. Здесь делаем
        # нелинейный рост: ближе к завершению взлома Алгем ускоряется заметнее.
        hack_curve = max(0.0, min(1.0, self.hack_attraction)) ** 1.28
        hack_pressure = hack_curve * self._profile.hack_interest_scale

        target_attention = min(
            100.0,
            self._ambient_interest
            + self._server_interest
            + self._ad_interest
            + self._tablet_interest
            + self._camera_focus_interest
            + self._vent_interest
            + hack_pressure
            + rage_pressure,
        )
        if (
            not server_on
            and not ad_active
            and not tablet_open
            and vent_error_count <= 0
            and self.hack_attraction <= 0.01
            and self._post_hack_rage_attention <= 0.01
        ):
            # Тишина гасит именно угрозу/интерес. Патруль при этом не заморожен:
            # его запускает FSM через IDLE -> PATROL, а не шкала attention.
            target_attention = 0.0

        self.attention += (target_attention - self.attention) * 0.12
        self.attention = max(0.0, min(100.0, self.attention))

    def trigger_post_hack_rage(self, duration_ticks: int, attention_floor: float = 92.0) -> None:
        self._post_hack_rage_ticks = max(self._post_hack_rage_ticks, int(duration_ticks))
        self._post_hack_rage_attention = max(self._post_hack_rage_attention, float(attention_floor))
        self.hack_attraction = max(self.hack_attraction, 1.0)
        self.attention = max(self.attention, min(100.0, attention_floor - 6.0))
        self._pressure_cooldown_ticks = 0
        if self.state in (AIState.IDLE, AIState.PATROL, AIState.INVESTIGATE, AIState.RETREAT):
            self._enter_attack_state()

    def notify_audio_lure(self, target_node: int, duration: int = 480) -> None:
        if target_node == self.location:
            return
        path = bfs_path(self.location, target_node, self._graph)
        if path is None or len(path) - 1 > self._profile.lure_hear_distance:
            return
        if random.random() < self._profile.lure_fail_chance:
            return

        self._lure_node = target_node
        self._lure_ticks_left = duration
        self._investigate_target = target_node
        self.state = AIState.INVESTIGATE
        self._idle_ticks_left = 0
        self._move_timer = min(self._move_timer, 45)

    def cancel_audio_lure(self) -> None:
        self._lure_node = -1
        self._lure_ticks_left = 0
        if self.state is AIState.INVESTIGATE and self._investigate_target is not None:
            self._investigate_target = None

    def notify_laptop_power_event(self, event: str) -> None:
        """React to office laptop power sounds with distance-based urgency."""
        if self._night <= 1:
            return
        cooldown_scale = 0.38 if self._laptop_noise_cooldown > 0 else 1.0
        self._laptop_noise_cooldown = 240
        source_node = self.OFFICE_NODE
        path = bfs_path(self.location, source_node, self._graph)
        if path is None:
            distance = 6
        else:
            distance = max(0, len(path) - 1)

        event = event.lower().strip()
        if event == "on":
            base_interest = 11.0
            base_attention = 10.0
            hearing_limit = 4
            fast_move_cap = 54
        else:
            base_interest = 16.0
            base_attention = 15.0
            hearing_limit = 5
            fast_move_cap = 42

        if distance > hearing_limit:
            # Совсем далеко — слышит лишь на поздних ночах и с меньшим эффектом.
            if self._night < 4:
                return
            falloff = max(0.18, 1.0 - (distance - hearing_limit) * 0.22)
        else:
            falloff = max(0.30, 1.0 - distance * 0.18)

        interest_gain = base_interest * falloff * (0.85 + self._night * 0.08) * cooldown_scale
        attention_gain = base_attention * falloff * (0.80 + self._night * 0.07) * cooldown_scale

        self._server_interest = min(58.0, self._server_interest + interest_gain)
        self.attention = min(100.0, self.attention + attention_gain)
        self._idle_ticks_left = 0

        if distance <= hearing_limit:
            self.cancel_audio_lure()
            if self.state in (AIState.IDLE, AIState.PATROL):
                self.state = AIState.INVESTIGATE
                self._investigate_target = self._choose_investigate_target() or self._nearest_patrol_node() or self.PATROL_SAFE_HOME
            self._move_timer = min(self._move_timer, fast_move_cap + distance * 12)

        if distance <= 2:
            self.hack_attraction = max(self.hack_attraction, 0.22 if event == "on" else 0.30)
            if event == "off" or self.attention >= self._attack_threshold(self._profile.patrol_attack_threshold) - 8.0:
                self._enter_attack_state()
                self._move_timer = min(self._move_timer, 24 if distance <= 1 else 36)

    def _is_leaving_vent(self, vent_node: int) -> bool:
        if self.location == vent_node:
            return False
        return bool(
            (
                self.prev_location == vent_node
                and (
                    self.trigger_timer > 0
                    or self._last_vent_move[0] == vent_node
                    or self._last_vent_leave_source == vent_node
                    or vent_node in self._seal_knock_suppressed_vents
                )
            )
            or self._last_vent_leave_source == vent_node
            or (self._vent_audio_source == vent_node and self._vent_motion_ticks > 0)
            or vent_node in self._seal_knock_suppressed_vents
        )

    def notify_seal_started(self, vent_node: int, duration_ticks: int = 300) -> None:
        if self._is_leaving_vent(vent_node):
            self._seal_knock_suppressed_vents.add(vent_node)
            self._last_vent_leave_source = vent_node
            self._last_vent_leave_ticks = max(self._last_vent_leave_ticks, duration_ticks + 90)

    def notify_seal_closed(self, vent_node: int) -> None:
        """Игровая реакция на полностью закрытый вент.

        Вызывается только после перехода SEALING -> CLOSED, то есть когда на
        карте уже должна гореть красная полоска. Если Алгем оказался в закрытом
        венте или прямо перед ним, создаём событие стука с задержкой примерно
        в секунду и переводим его в отступление/оглушение.
        """
        # Если игрок закрыл камеру, на которой сейчас видит `algem_is_leaving`,
        # Алгем уже физически уполз с этой vent-камеры. В таком случае стука быть
        # не должно: это не блок, а запоздалая помеха от прошлого положения.
        leaving_this_vent = self._is_leaving_vent(vent_node)
        if vent_node in self._seal_knock_suppressed_vents or leaving_this_vent:
            self._seal_knock_suppressed_vents.discard(vent_node)
            return

        if self.location == vent_node or vent_node in self._graph.get(self.location, []):
            self._emit(AlgemEventType.SEAL_BLOCKED, self.location, vent_node, delay_ticks=60)
            lo, hi = self._STUN_TICKS_BY_NIGHT.get(self._night, (120, 240))
            stun_ticks = random.randint(lo, hi)
            if self.location == vent_node:
                stun_ticks = max(stun_ticks, 150)
            else:
                stun_ticks = max(stun_ticks, 90)
            if stun_ticks > 0:
                self._stun_timer = stun_ticks
                self.state = AIState.STUNNED
                self._retreat_target = self._nearest_patrol_node() or self.PATROL_SAFE_HOME
                self._move_timer = min(self._move_timer, 30)
                self.trigger_timer = 0
                if self.location == vent_node:
                    self._pressure_cooldown_ticks = max(self._pressure_cooldown_ticks, 210)
                    self.attention = max(0.0, self.attention - 16.0)
                    self._server_interest *= 0.82
                    self._ad_interest *= 0.86
                    self._vent_interest *= 0.70
                else:
                    self._pressure_cooldown_ticks = max(self._pressure_cooldown_ticks, 120)

    def tick(self, hour: int) -> bool:
        self._current_hour = hour
        self._block_external_teleport_if_needed()

        if self.trigger_timer > 0:
            self.trigger_timer -= 1
        if self._last_vent_leave_ticks > 0:
            self._last_vent_leave_ticks -= 1
            if self._last_vent_leave_ticks <= 0:
                self._last_vent_leave_source = -1
        if self._vent_motion_ticks > 0:
            self._vent_motion_ticks -= 1
            if self._vent_motion_ticks <= 0 and self.location not in self.VENT_NODES:
                self._vent_audio_source = -1
        if self._pressure_cooldown_ticks > 0:
            self._pressure_cooldown_ticks -= 1
        if self._laptop_noise_cooldown > 0:
            self._laptop_noise_cooldown -= 1

        if self._night <= 1:
            return False

        if self._lure_ticks_left > 0:
            self._lure_ticks_left -= 1
            if self._lure_ticks_left <= 0:
                self._lure_node = -1

        if self._entry_timer > 0:
            self._entry_timer -= 1
            if self._entry_timer <= 0:
                return True
            return False

        if self.state is AIState.BREACH:
            self._breach_timer -= 1
            if self._breach_timer <= 0:
                # GameModel дальше запускает честное random kill-window.
                self._emit(AlgemEventType.OFFICE_ENTERED, self._breach_source, self.OFFICE_NODE)
                return True
            return False

        if self.state is AIState.KILL_PENDING:
            return True

        if self.state is AIState.STUNNED:
            self._stun_timer -= 1
            if self._stun_timer <= 0:
                self.state = AIState.RETREAT
                self._move_timer = 1
            return False

        self._move_timer -= 1
        if self._move_timer > 0:
            return False

        reached_office = self._step(hour)
        # Важно считать следующий интервал ПОСЛЕ шага. Иначе при входе в вент
        # таймер берётся от обычной комнаты, и Алгем может почти сразу уползти
        # дальше. Для vent-камер это ломает честное окно на закрытие seal.
        if not reached_office and self.state is not AIState.BREACH:
            self._move_timer = self._compute_interval(hour)
        return reached_office

    # ------------------------------------------------------------------
    # FSM
    # ------------------------------------------------------------------

    def _step(self, hour: int) -> bool:
        dispatch: dict[AIState, Callable[[], bool]] = {
            AIState.IDLE: lambda: self._step_idle(hour),
            AIState.PATROL: self._step_patrol,
            AIState.INVESTIGATE: self._step_investigate,
            AIState.ATTACK: self._step_attack,
            AIState.VENT_STALK: self._step_attack,
            AIState.RETREAT: self._step_retreat,
        }
        return dispatch.get(self.state, self._step_patrol)()

    def _step_idle(self, hour: int) -> bool:
        self._idle_ticks_left -= 1
        if self._idle_ticks_left > 0 and self.attention < self._investigate_threshold():
            return False

        if self._should_attack():
            self._enter_attack_state()
        elif self.attention >= self._investigate_threshold():
            self.state = AIState.INVESTIGATE
            self._investigate_target = self._choose_investigate_target()
        else:
            self.state = AIState.PATROL
        return False

    def _step_patrol(self) -> bool:
        if self._should_attack():
            self._enter_attack_state()
            return False
        if self.attention >= self._investigate_threshold() or self._lure_node >= 0:
            self.state = AIState.INVESTIGATE
            self._investigate_target = self._choose_investigate_target()
            return False

        next_node = self._choose_patrol_node()
        self._move_to(next_node, self._patrol_graph)
        return False

    def _step_investigate(self) -> bool:
        target = self._choose_investigate_target()
        self._investigate_target = target

        if target is None or target == self.location:
            if self._should_attack():
                self._enter_attack_state()
            else:
                self.state = AIState.PATROL
            return False

        # Приманка/расследование в обычной зоне — через DFS, чтобы алгоритм был
        # явно использован как «средний» пункт ТЗ.
        graph = self._patrol_graph if target in self._PATROL_ZONES.get(self._night, set()) else self._graph
        path = dfs_path(self.location, target, graph)
        if path is None or len(path) < 2:
            path = bfs_path(self.location, target, self._graph)
        if path and len(path) > 1:
            self._move_to(path[1], self._graph if path[1] not in self._patrol_graph.get(self.location, []) else graph)

        if self._lure_node < 0 and self._should_attack():
            self._enter_attack_state()
        elif self._lure_node < 0 and self.attention < self._investigate_threshold() * 0.65:
            self.state = AIState.PATROL
        return False

    def _step_attack(self) -> bool:
        self._trim_reached_attack_detours()
        self._maybe_start_unpredictable_attack_detour()

        goal = self._current_attack_goal()
        route_graph = self._current_attack_graph(goal)
        heuristic = (
            self._base_heuristic
            if goal == self.OFFICE_NODE and route_graph is self._graph
            else self._precompute_heuristic(route_graph, goal)
        )
        path = astar_path(self.location, goal, route_graph, self._edge_weight, heuristic)
        self._last_path = path or []

        if path is None or len(path) < 2:
            if self._attack_detour_queue:
                self._attack_detour_queue.clear()
                self._attack_detour_cooldown = max(self._attack_detour_cooldown, 1)
                return False
            self._start_stun_or_retreat()
            return False

        next_node = path[1]
        if next_node == self.OFFICE_NODE:
            self._start_breach()
            return False

        if not self._move_to(next_node, route_graph):
            self._attack_detour_queue.clear()
            self._start_stun_or_retreat()
            return False

        self._trim_reached_attack_detours()
        if self.location in self.VENT_NODES:
            self.state = AIState.VENT_STALK
        elif self._lure_node >= 0:
            self.state = AIState.INVESTIGATE
        else:
            self.state = AIState.ATTACK
        return False

    def _current_attack_goal(self) -> int:
        if self._lure_node >= 0:
            return self._lure_node
        self._trim_reached_attack_detours()
        if self._attack_detour_queue:
            return self._attack_detour_queue[0]
        return self.OFFICE_NODE

    def _current_attack_graph(self, goal: int) -> dict[int, list[int]]:
        if goal != self.OFFICE_NODE or self._attack_detour_queue:
            return self._graph_with_special_detour_edges()
        return self._graph

    def _graph_with_special_detour_edges(self) -> dict[int, list[int]]:
        graph = {node: list(neighbors) for node, neighbors in self._graph.items()}
        for source, targets in self._SPECIAL_DETOUR_EDGES.items():
            if source not in graph:
                continue
            for target in targets:
                if target in graph[source] or not self._node_is_enterable_for_detour(target):
                    continue
                graph[source].append(target)
        return graph

    def _node_is_enterable_for_detour(self, node: int) -> bool:
        if node == self.OFFICE_NODE or node == self.location:
            return True
        return any(node in neighbors for neighbors in self._graph.values())

    def _trim_reached_attack_detours(self) -> None:
        while self._attack_detour_queue and self._attack_detour_queue[0] == self.location:
            self._attack_detour_queue.popleft()
            self._attack_detour_cooldown = self._DETOUR_COOLDOWN_BY_NIGHT.get(self._night, 2)

    def _maybe_start_unpredictable_attack_detour(self) -> None:
        if self._lure_node >= 0 or self._attack_detour_queue or self.location == self.OFFICE_NODE:
            return
        if self._attack_detour_cooldown > 0:
            self._attack_detour_cooldown -= 1
            return
        max_detours = self._MAX_DETOURS_PER_ATTACK_BY_NIGHT.get(self._night, 0)
        if self._attack_detours_used >= max_detours:
            return
        chance = self._unpredictable_route_chance()
        if random.random() >= chance:
            return
        plan = self._choose_unpredictable_attack_plan()
        if not plan:
            return
        self._attack_detour_queue.clear()
        self._attack_detour_queue.extend(plan)
        self._attack_detours_used += 1
        self._attack_route_epoch += 1
        self._move_history.append((self.location, plan[-1], "DETOUR"))

    def _unpredictable_route_chance(self) -> float:
        base = self._UNPREDICTABLE_ROUTE_CHANCE_BY_NIGHT.get(self._night, 0.0)
        hack_bonus = min(0.08, self.hack_attraction * 0.08)
        watch_bonus = 0.0
        if self._current_camera_idx == self.location:
            watch_bonus = 0.08 + self._night * 0.008
        recent_penalty = 0.04 * sum(1 for node in self._recent_nodes if node == self.location)
        return max(0.0, min(0.72, base + hack_bonus + watch_bonus - recent_penalty))

    def _choose_unpredictable_attack_plan(self) -> tuple[int, ...] | None:
        options = self._UNPREDICTABLE_ROUTE_OPTIONS.get(self.location, [])
        if not options:
            return None
        graph = self._graph_with_special_detour_edges()
        candidates: list[tuple[int, ...]] = []
        weights: list[float] = []
        for base_weight, plan in options:
            cleaned = tuple(node for node in plan if node != self.location)
            if not cleaned:
                continue
            if cleaned[0] in self._recent_nodes:
                continue
            if not self._attack_plan_is_reachable(cleaned, graph):
                continue
            weight = base_weight
            if any(node in self.VENT_NODES for node in cleaned):
                weight *= 1.0 + self._VENT_ROUTE_CHANCE_BY_NIGHT.get(self._night, 0.0) * 0.75
            if any(node not in self._recent_nodes for node in cleaned):
                weight *= 1.18
            if any(self._camera_watch.get(node, 0) <= 40 for node in cleaned):
                weight *= 1.12
            if self.location == 9 and cleaned[:2] == (10, 7):
                weight *= 1.0 + self._night * 0.14
            candidates.append(cleaned)
            weights.append(weight)
        if not candidates:
            return None
        return self._weighted_choice(candidates, weights)

    def _attack_plan_is_reachable(self, plan: tuple[int, ...], graph: dict[int, list[int]]) -> bool:
        current = self.location
        for target in plan:
            if target == current:
                continue
            path = astar_path(current, target, graph, self._edge_weight, self._precompute_heuristic(graph, target))
            if path is None or len(path) < 2:
                return False
            current = target
        path_to_office = astar_path(current, self.OFFICE_NODE, graph, self._edge_weight, self._precompute_heuristic(graph, self.OFFICE_NODE))
        return path_to_office is not None and len(path_to_office) > 1

    def _step_retreat(self) -> bool:
        target = self._nearest_patrol_node() or self.PATROL_SAFE_HOME
        if self.location == target:
            self.state = AIState.PATROL
            self._reset_patrol_memory()
            return False
        path = bfs_path(self.location, target, self._graph)
        if path and len(path) > 1:
            self._move_to(path[1], self._graph)
        else:
            self.state = AIState.PATROL
        return False

    # ------------------------------------------------------------------
    # Выбор целей и движение
    # ------------------------------------------------------------------

    def _enter_attack_state(self) -> None:
        if self.state not in (AIState.ATTACK, AIState.VENT_STALK):
            self._attack_route_epoch += 1
            self._last_path = []
            self._attack_detour_queue.clear()
            self._attack_detour_cooldown = 0
            self._attack_detours_used = 0
        self.state = AIState.ATTACK

    def _choose_patrol_node(self) -> int:
        neighbors = list(self._patrol_graph.get(self.location, []))
        if not neighbors:
            return self.location

        if self._lure_node >= 0:
            path = dfs_path(self.location, self._lure_node, self._patrol_graph)
            if path and len(path) > 1:
                return path[1]

        patrol_zone = self._PATROL_ZONES.get(self._night)
        if (
            self._patrol_graph_is_dedicated
            and patrol_zone is not None
            and self.location in patrol_zone
        ):
            filtered = [n for n in neighbors if n in patrol_zone]
            if filtered:
                neighbors = filtered

        # DFS-патруль: сначала непосещённые ветки, потом backtracking.
        if not self._patrol_stack or self._patrol_stack[-1] != self.location:
            self._reset_patrol_memory()
        unvisited = [n for n in neighbors if n not in self._patrol_visited]
        if unvisited:
            candidates = unvisited
        elif len(self._patrol_stack) > 1:
            self._patrol_stack.pop()
            backtrack_target = self._patrol_stack[-1]
            if backtrack_target in neighbors:
                return backtrack_target
            # PATROL_GRAPH может быть направленным. Backtracking через стек DFS
            # не имеет права телепортировать Алгема, поэтому идём к целевому
            # узлу кратчайшим физическим шагом через BFS.
            path = bfs_path(self.location, backtrack_target, self._patrol_graph)
            if path and len(path) > 1 and path[1] in neighbors:
                return path[1]
            self._reset_patrol_memory()
            candidates = neighbors
        else:
            self._reset_patrol_memory()
            candidates = neighbors

        weights: list[float] = []
        for node in candidates:
            watch = self._camera_watch.get(node, 0)
            observed = min(1.0, watch / 300.0)
            weight = max(0.06, 1.0 - observed * self._profile.watch_penalty_scale)

            # При умеренном интересе он не атакует мгновенно, но чаще выбирает
            # камеры, которые ближе к будущему attack-маршруту.
            if self.attention >= self._profile.office_pull_start:
                dist = self._base_heuristic.get(node, 999)
                if dist < 999:
                    pull = min(self._profile.office_pull_max, (self.attention - self._profile.office_pull_start) / 100.0)
                    weight *= 1.0 + max(0.0, 4.0 - dist) * 0.16 * pull

            if node in self._recent_nodes:
                weight *= 0.55
            weights.append(weight)

        picked = self._weighted_choice(candidates, weights)
        self._patrol_visited.add(picked)
        self._patrol_stack.append(picked)
        return picked

    def _choose_investigate_target(self) -> int | None:
        if self._lure_node >= 0:
            return self._lure_node

        sources: list[tuple[float, list[int]]] = [
            (self._server_interest + self.hack_attraction * 18.0, self._SERVER_INVESTIGATE_TARGETS),
            (self._ad_interest, self._AD_INVESTIGATE_TARGETS),
            (self._tablet_interest + self._camera_focus_interest, self._TABLET_INVESTIGATE_TARGETS),
        ]
        sources.sort(key=lambda item: item[0], reverse=True)
        score, targets = sources[0]
        if score <= 0.5:
            return None

        # Выбираем достижимую ближайшую цель из тематического списка.
        reachable: list[tuple[int, int]] = []
        for target in targets:
            path = bfs_path(self.location, target, self._graph)
            if path:
                reachable.append((len(path), target))
        if not reachable:
            return None
        reachable.sort()
        best = [target for _dist, target in reachable[:2]]
        return random.choice(best)

    def _move_to(self, node: int, graph: dict[int, list[int]] | None = None) -> bool:
        if node == self.location:
            return True
        active_graph = graph or (self._patrol_graph if self.state is AIState.PATROL else self._graph)
        if node not in active_graph.get(self.location, []):
            self._last_move_rejected = (self.location, node)
            self._move_history.append((self.location, node, "REJECTED"))
            self._emit(AlgemEventType.ILLEGAL_MOVE_BLOCKED, self.location, node)
            return False

        prev = self.location
        self.prev_location = prev
        self.location = node
        self._last_valid_location = node
        self.trigger_timer = 30
        self._recent_nodes.append(node)
        self._move_history.append((prev, node, self.state.name))

        if prev in self.VENT_NODES or node in self.VENT_NODES:
            self._last_vent_move = (prev, node)
            hold_ticks = self._vent_motion_hold_ticks(prev, node)
            if prev in self.VENT_NODES and node != prev:
                self._last_vent_leave_source = prev
                self._last_vent_leave_ticks = max(self._last_vent_leave_ticks, hold_ticks)
                self._vent_audio_source = prev
            elif node in self.VENT_NODES:
                self._vent_audio_source = node
            else:
                self._vent_audio_source = prev if prev in self.VENT_NODES else node
            self._vent_motion_ticks = max(self._vent_motion_ticks, hold_ticks)
            self._emit(AlgemEventType.VENT_MOVE, prev, node)
        else:
            self._emit(AlgemEventType.MOVE, prev, node)

        if node == 1:
            self.main_hall_sprite = random.randint(0, 1)
        return True

    def _emit(
        self,
        kind: AlgemEventType,
        source: int,
        target: int,
        delay_ticks: int = 0,
    ) -> None:
        self._events.append(
            AlgemEvent(
                kind=kind,
                source=source,
                target=target,
                state=self.state.name,
                delay_ticks=delay_ticks,
            )
        )

    def _start_breach(self) -> None:
        """Последний шаг в screamer/BREACH: камера пустеет, скример ещё не мгновенный."""
        source = self.location
        self.prev_location = source
        self.location = self.OFFICE_NODE
        self._last_valid_location = self.OFFICE_NODE
        self._move_history.append((source, self.OFFICE_NODE, "BREACH"))
        if source in self.VENT_NODES:
            hold_ticks = self._vent_motion_hold_ticks(source, self.OFFICE_NODE)
            self._last_vent_leave_source = source
            self._last_vent_leave_ticks = max(self._last_vent_leave_ticks, hold_ticks)
            self._vent_audio_source = source
            self._vent_motion_ticks = max(self._vent_motion_ticks, hold_ticks)
        self._breach_source = source
        self.state = AIState.BREACH
        self._breach_timer = random.randint(*self._BREACH_DELAY_BY_NIGHT.get(self._night, (90, 210)))
        self._entry_timer = 0
        self.trigger_timer = 30
        self._move_timer = self._breach_timer
        self._emit(AlgemEventType.BREACH_STARTED, source, self.OFFICE_NODE)

    def _start_stun_or_retreat(self) -> None:
        self._attack_detour_queue.clear()
        self._attack_detour_cooldown = max(self._attack_detour_cooldown, 1)
        self._stun_timer = random.randint(*self._STUN_TICKS_BY_NIGHT.get(self._night, (120, 240)))
        if self._stun_timer > 0:
            self.state = AIState.STUNNED
        else:
            self.state = AIState.RETREAT
        self._retreat_target = self._nearest_patrol_node() or self.PATROL_SAFE_HOME
        self._emit(AlgemEventType.ROUTE_BLOCKED, self.location, self._retreat_target)

    def _reset_patrol_memory(self) -> None:
        self._patrol_stack = [self.location]
        self._patrol_visited = {self.location}

    def _nearest_patrol_node(self) -> int | None:
        zone = self._PATROL_ZONES.get(self._night, {1, 2, 3, 4, 5, 6})
        if self.location in zone:
            return self.location
        best: tuple[int, int] | None = None
        for node in zone:
            path = bfs_path(self.location, node, self._graph)
            if path is None:
                continue
            candidate = (len(path), node)
            if best is None or candidate < best:
                best = candidate
        return best[1] if best else None


    def _block_external_teleport_if_needed(self) -> None:
        if self.location == self._last_valid_location:
            return

        prev = self._last_valid_location
        current = self.location
        external_reset_from_office = (
            prev == self.OFFICE_NODE
            and current in self._PATROL_ZONES.get(self._night, {1, 2, 3, 4, 5, 6})
            and self.state is AIState.IDLE
        )
        if external_reset_from_office:
            self._last_valid_location = current
            self._move_history.append((prev, current, "FORCE_RESET"))
            return

        if current in self._graph.get(prev, []):
            self._last_valid_location = current
            self._move_history.append((prev, current, "EXTERNAL_EDGE"))
            return

        self._last_move_rejected = (prev, current)
        self._move_history.append((prev, current, "EXTERNAL_BLOCKED"))
        self._emit(AlgemEventType.ILLEGAL_MOVE_BLOCKED, prev, current)
        self.prev_location = current
        self.location = prev
        self.trigger_timer = 0
        self._last_path = []

    def _vent_motion_hold_ticks(self, prev: int, node: int) -> int:
        if prev in self.VENT_NODES and node in self.VENT_NODES:
            return 360 if self.state is AIState.RETREAT else 300
        if prev in self.VENT_NODES and node not in self.VENT_NODES:
            return 330 if self.state is AIState.RETREAT else 270
        if node in self.VENT_NODES:
            return 300 if self.state is AIState.RETREAT else 240
        return 0

    # ------------------------------------------------------------------
    # Вес A* / пороги / таймеры
    # ------------------------------------------------------------------

    def _edge_weight(self, u: int, v: int) -> float:
        # Штрафуем именно узел, куда Алгем хочет зайти, а не тот, откуда он уходит.
        watch = self._camera_watch.get(v, 0)
        observed = min(1.0, watch / 300.0)
        weight = 1.0 + observed * (1.0 + self._profile.watch_penalty_scale * 1.5)

        # Свежие узлы чуть дороже, чтобы A* не выглядел как рельсы.
        if v in self._recent_nodes:
            weight *= 1.18

        # Маршруты атаки слегка меняются от попытки к попытке, но шум стабилен
        # внутри одной атаки. A* остаётся A*, просто не ходит по одному рельсу.
        if v != self.OFFICE_NODE:
            rng = random.Random(self._attack_route_epoch * 10007 + self._night * 1009 + u * 137 + v * 271)
            weight *= rng.uniform(0.92, 1.12)

        if v in self.VENT_NODES:
            chance = self._VENT_ROUTE_CHANCE_BY_NIGHT.get(self._night, 0.74)
            pressure_bonus = min(0.18, self.hack_attraction * 0.18)
            vent_bias = min(0.42, chance * 0.34 + pressure_bonus)
            weight *= 1.0 - vent_bias
            if v == 8 and self._night >= 2:
                weight *= 0.82
        elif u not in self.VENT_NODES and v != self.OFFICE_NODE:
            chance = self._VENT_ROUTE_CHANCE_BY_NIGHT.get(self._night, 0.74)
            weight *= 1.0 + max(0.0, chance - 0.35) * 0.18

        if u == 9 and v == 10:
            weight *= 0.86

        # Прямой вход в офис не должен быть слишком дешёвым: это даёт время на
        # последнюю vent-фазу и не превращает A* в мгновенный скример.
        if v == self.OFFICE_NODE:
            weight *= 1.20

        return max(0.45, weight)

    def _attack_threshold(self, base_threshold: float) -> float:
        hack_cut = self.hack_attraction * (8.0 + self._night * 1.5)
        hour_cut = self._current_hour * self._profile.hour_attack_delta
        return max(35.0, base_threshold - hour_cut - hack_cut)

    def _investigate_threshold(self) -> float:
        return max(10.0, 24.0 - self._night * 1.8 - self._current_hour * 0.9)

    def _should_attack(self) -> bool:
        if self._lure_node >= 0:
            return False
        if (
            self._pressure_cooldown_ticks > 0
            and self.state not in (AIState.ATTACK, AIState.VENT_STALK, AIState.BREACH, AIState.KILL_PENDING)
            and not (self.hack_attraction >= 0.86 and self.attention >= 92.0)
        ):
            return False
        can_attack = (
            self.hack_attraction >= 0.10
            or self._server_interest >= 10.0
            or self._ad_interest >= 10.0
            or self._tablet_interest >= 10.0
            or self._camera_focus_interest >= 10.0
            or self._vent_interest >= 10.0
            or self._post_hack_rage_attention >= 25.0
            or (self._night >= 4 and self._ambient_interest >= self._AMBIENT_CAP_BY_NIGHT.get(self._night, 0) * 0.85)
        )
        threshold = self._attack_threshold(self._profile.patrol_attack_threshold)
        if self._post_hack_rage_attention >= 25.0:
            threshold = min(threshold, 62.0 - self._night * 2.0)
        return can_attack and self.attention >= threshold

    def _compute_interval(self, hour: int) -> int:
        lo, hi = self._NIGHT_SPEED.get(self._night, (240, 600))
        attention_factor = self.attention / 100.0
        interval = int(hi - (hi - lo) * attention_factor)

        if self.state in (AIState.ATTACK, AIState.VENT_STALK):
            interval = int(interval * 0.74)
        elif self.state is AIState.INVESTIGATE:
            interval = int(interval * 0.88)
        elif self.state is AIState.RETREAT:
            interval = int(interval * 0.75)

        hack_mult = 1.0 - min(0.48, self.hack_attraction * (0.32 + self._night * 0.035))
        interval = int(interval * hack_mult)
        if self._post_hack_rage_attention >= 25.0:
            interval = int(interval * max(0.70, 0.92 - self._night * 0.035))

        if self._pressure_cooldown_ticks > 0 and self.state in (AIState.PATROL, AIState.RETREAT, AIState.INVESTIGATE):
            interval = int(interval * 1.18)

        if self.location in self.VENT_NODES:
            interval = max(interval, self._VENT_STAY_TICKS_BY_NIGHT.get(self._night, 660))
        elif self.state is AIState.VENT_STALK:
            # На случай, если состояние уже vent-атака, но следующий тик ещё
            # считается из обычной камеры перед входом в вент.
            interval = max(interval, 420)
        elif self.location == self.DANGER_NODE:
            interval = max(interval, 360)

        if self.state in (AIState.ATTACK, AIState.VENT_STALK) and self.location not in self.VENT_NODES:
            interval = max(interval, self._ATTACK_ROOM_STEP_MIN_TICKS_BY_NIGHT.get(self._night, 90))

        return max(45, interval)

    def _initial_delay(self) -> int:
        if self._night <= 1:
            return random.randint(240, 540)
        lo, hi = self._NIGHT_SPEED.get(self._night, (240, 600))
        return random.randint(max(90, lo // 2), max(120, hi))

    @staticmethod
    def _precompute_heuristic(graph: dict[int, list[int]], goal: int) -> dict[int, int]:
        result: dict[int, int] = {}
        for node in graph:
            path = bfs_path(node, goal, graph)
            result[node] = (len(path) - 1) if path else 999
        return result

    @staticmethod
    def _weighted_choice(nodes: list[int], weights: list[float]) -> int:
        total = sum(weights)
        if total <= 0:
            return random.choice(nodes)
        r = random.uniform(0.0, total)
        accum = 0.0
        for node, weight in zip(nodes, weights):
            accum += weight
            if r <= accum:
                return node
        return nodes[-1]

    @property
    def state_name(self) -> str:
        return self.state.name

    @property
    def debug_target(self) -> int | None:
        if self.state is AIState.INVESTIGATE:
            return self._investigate_target
        if self.state in (AIState.ATTACK, AIState.VENT_STALK):
            return self._current_attack_goal()
        if self.state is AIState.BREACH:
            return self.OFFICE_NODE
        return None

    @property
    def debug_path(self) -> list[int]:
        return list(self._last_path)

    @property
    def debug_move_history(self) -> list[tuple[int, int, str]]:
        return list(self._move_history)

    @property
    def debug_detour_queue(self) -> list[int]:
        return list(self._attack_detour_queue)

    @property
    def debug_unpredictable_chance(self) -> float:
        return self._unpredictable_route_chance()

    @property
    def vent_motion_ticks(self) -> int:
        return self._vent_motion_ticks

    @property
    def vent_audio_source(self) -> int:
        if self.location in self.VENT_NODES:
            return self.location
        if self._vent_motion_ticks > 0 and self._vent_audio_source in self.VENT_NODES:
            return self._vent_audio_source
        return -1

    @property
    def last_vent_move(self) -> tuple[int, int]:
        return self._last_vent_move

    @property
    def last_vent_leave_source(self) -> int:
        return self._last_vent_leave_source if self._last_vent_leave_ticks > 0 else -1

    @property
    def pressure_cooldown_ticks(self) -> int:
        return self._pressure_cooldown_ticks

    def __repr__(self) -> str:
        return (
            f"AlgemAI(state={self.state.name}, loc={self.location}, "
            f"prev={self.prev_location}, attention={self.attention:.1f}, "
            f"hack={self.hack_attraction:.2f}, lure={self._lure_node})"
        )
