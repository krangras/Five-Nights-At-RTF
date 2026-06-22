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

import random
from bisect import bisect_left
from collections import deque
from typing import TypeVar

from .ai_domain import AIState, AlgemEvent, AlgemEventType, NightProfile
from .camera_graph import BASE_GRAPH, SPECIAL_DETOUR_EDGES
from .pathfinding import (
    Graph,
    GraphSignature,
    astar_path,
    bfs_path,
    dfs_path,
    graph_signature,
    single_target_hop_distances,
)


ChoiceT = TypeVar("ChoiceT")
_TABLE_LERP_KEY_CACHE: dict[int, tuple[int, ...]] = {}


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
    _SPECIAL_DETOUR_EDGES: dict[int, list[int]] = SPECIAL_DETOUR_EDGES
    _POST_HACK_RAGE_DETOUR_NODES = {7, 8, 9, 10, 11}
    _POST_HACK_RAGE_STEP_CAP_BY_NIGHT: dict[int, int] = {
        1: 120,
        2: 72,
        3: 54,
        4: 42,
        5: 30,
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
    _AMBIENT_CAP_BY_NIGHT: dict[int, float] = {
        1: 0.0,
        2: 7.0,
        3: 12.0,
        4: 17.0,
        5: 23.0,
    }
    _AMBIENT_GROWTH_BY_NIGHT: dict[int, float] = {
        1: 0.0,
        2: 0.28,
        3: 0.45,
        4: 0.62,
        5: 0.86,
    }

    _BREACH_DELAY_BY_NIGHT: dict[int, tuple[int, int]] = {
        1: (999999, 999999),
        2: (150, 270),  # 2.5–4.5 сек: кадр, где его уже нет в венте
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
        1: NightProfile(
            0.0,
            0.0,
            0.0,
            18.0,
            99.0,
            0.0,
            0.0,
            0.0,
            0.0,
            999999,
            0.0,
            0.0,
            999.0,
            999.0,
            0.0,
            999.0,
            0.0,
            0.85,
            0.15,
            2,
            90,
        ),
        2: NightProfile(
            5.2,
            18.0,
            18.0,
            14.0,
            2.4,
            6.5,
            16.0,
            9.0,
            20.0,
            240,
            10.0,
            16.0,
            88.0,
            92.0,
            2.0,
            28.0,
            0.35,
            0.60,
            0.08,
            3,
            105,
        ),
        3: NightProfile(
            8.5,
            24.0,
            25.0,
            17.0,
            1.9,
            8.0,
            20.0,
            12.0,
            26.0,
            210,
            12.0,
            22.0,
            78.0,
            84.0,
            3.0,
            24.0,
            0.55,
            0.75,
            0.13,
            3,
            90,
        ),
        4: NightProfile(
            11.5,
            26.0,
            30.0,
            18.0,
            1.65,
            10.0,
            24.0,
            15.0,
            30.0,
            180,
            14.0,
            24.0,
            72.0,
            78.0,
            3.6,
            20.0,
            0.72,
            0.85,
            0.15,
            3,
            90,
        ),
        5: NightProfile(
            15.0,
            28.0,
            38.0,
            18.0,
            1.45,
            12.0,
            28.0,
            18.0,
            34.0,
            150,
            16.0,
            28.0,
            64.0,
            72.0,
            4.5,
            16.0,
            0.88,
            0.95,
            0.17,
            3,
            90,
        ),
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
        """Выполняет специализированную операцию «init» в подсистеме algem ai."""
        self._graph = graph
        self._patrol_graph = patrol_graph or graph
        self._patrol_graph_is_dedicated = patrol_graph is not None
        self._night = night
        self._profile = self._NIGHT_PROFILES.get(night, self._NIGHT_PROFILES[5])
        self._current_hour = 0

        self._location = start_node
        self._prev_location = start_node
        self._trigger_timer = 0
        self._move_timer = self._initial_delay()

        self._state = AIState.IDLE
        self._idle_ticks_left = random.randint(60, 180)
        self._aggression = 0.0
        self._attention = 0.0
        self._hack_attraction = 0.0

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
        self._post_hack_rage_level = float(night)

        self._main_hall_sprite = 0
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
        self._blocked_vent_knock_cooldowns: dict[int, int] = {}
        self._pressure_cooldown_ticks = 0
        self._laptop_noise_cooldown = 0
        self._attack_route_epoch = 0
        self._attack_detour_queue: deque[int] = deque()
        self._attack_detour_cooldown = 0
        self._attack_detours_used = 0
        self._events: deque[AlgemEvent] = deque()
        self._last_valid_location = start_node
        self._move_history: deque[tuple[int, int, str]] = deque(maxlen=12)

        self._graph_signature = graph_signature(self._graph)
        self._detour_graph: Graph | None = None
        self._detour_graph_signature: GraphSignature | None = None
        self._heuristic_cache: dict[tuple[GraphSignature, int], dict[int, int]] = {}
        self._enterable_nodes = self._compute_enterable_nodes(self._graph)
        self._base_heuristic = self._heuristic_for(self._graph, self.OFFICE_NODE)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def location(self) -> int:
        """Возвращает или обновляет текущий узел Алгема на графе камер."""
        return self._location

    @location.setter
    def location(self, value: int) -> None:
        """Возвращает или обновляет текущий узел Алгема на графе камер."""
        self.force_location(int(value), prev_node=self._prev_location, trigger_ticks=self._trigger_timer)

    @property
    def prev_location(self) -> int:
        """Возвращает или обновляет предыдущий узел Алгема для корректной анимации перехода."""
        return self._prev_location

    @prev_location.setter
    def prev_location(self, value: int) -> None:
        """Возвращает или обновляет предыдущий узел Алгема для корректной анимации перехода."""
        self._prev_location = int(value)

    @property
    def trigger_timer(self) -> int:
        """Return the computed trigger timer for the current gameplay state."""
        return self._trigger_timer

    @trigger_timer.setter
    def trigger_timer(self, value: int) -> None:
        """Return the computed trigger timer for the current gameplay state."""
        self._trigger_timer = max(0, int(value))

    @property
    def state(self) -> AIState:
        """Возвращает или устанавливает текущее FSM-состояние Алгема."""
        return self._state

    @state.setter
    def state(self, value: AIState) -> None:
        """Возвращает или устанавливает текущее FSM-состояние Алгема."""
        if not isinstance(value, AIState):
            raise TypeError("state must be AIState")
        self._state = value

    @property
    def aggression(self) -> float:
        """Возвращает или задаёт уровень агрессии, влияющий на частоту атак."""
        return self._aggression

    @aggression.setter
    def aggression(self, value: float) -> None:
        """Возвращает или задаёт уровень агрессии, влияющий на частоту атак."""
        self._aggression = max(0.0, min(1.0, float(value)))

    @property
    def attention(self) -> float:
        """Возвращает или задаёт текущую заинтересованность Алгема игроком."""
        return self._attention

    @attention.setter
    def attention(self, value: float) -> None:
        """Возвращает или задаёт текущую заинтересованность Алгема игроком."""
        self._attention = max(0.0, min(100.0, float(value)))

    @property
    def hack_attraction(self) -> float:
        """Возвращает или задаёт силу приманки от активного взлома ноутбука."""
        return self._hack_attraction

    @hack_attraction.setter
    def hack_attraction(self, value: float) -> None:
        """Возвращает или задаёт силу приманки от активного взлома ноутбука."""
        self.set_hack_attraction(value)

    @property
    def main_hall_sprite(self) -> int:
        """Возвращает или задаёт вариант спрайта Алгема для главного коридора."""
        return self._main_hall_sprite

    @main_hall_sprite.setter
    def main_hall_sprite(self, value: int) -> None:
        """Возвращает или задаёт вариант спрайта Алгема для главного коридора."""
        self._main_hall_sprite = 1 if int(value) else 0

    def set_hack_attraction(self, value: float) -> None:
        """Обновляет силу приманки от взлома и ограничивает её безопасным диапазоном."""
        self._hack_attraction = max(0.0, min(1.0, float(value)))

    def ensure_attention_at_least(self, value: float) -> None:
        """Поднимает внимание Алгема до заданного минимума без резкого сброса текущего давления."""
        self._attention = max(self._attention, min(100.0, float(value)))

    def reset_after_office_repel(
        self,
        node: int,
        prev_node: int = OFFICE_NODE,
        trigger_ticks: int = 30,
        move_timer: int = 120,
        idle_ticks: int = 120,
    ) -> None:
        """Сбрасывает офисную угрозу после успешного отпугивания Алгема."""
        self.force_location(node, prev_node=prev_node, trigger_ticks=trigger_ticks)
        self._entry_timer = 0
        self._move_timer = max(1, int(move_timer))
        self._state = AIState.IDLE
        self._idle_ticks_left = max(0, int(idle_ticks))
        self._attention = 0.0
        self._hack_attraction = 0.0
        self.cancel_audio_lure()

    def update_graph(
        self,
        graph: Graph,
        patrol_graph: Graph | None = None,
    ) -> None:
        """Пересобирает граф доступных переходов с учётом закрытых вентиляционных заслонок."""
        signature = graph_signature(graph)
        if signature != self._graph_signature:
            self._graph = graph
            self._graph_signature = signature
            self._detour_graph = None
            self._detour_graph_signature = None
            self._heuristic_cache.clear()
            self._enterable_nodes = self._compute_enterable_nodes(self._graph)
            self._base_heuristic = self._heuristic_for(self._graph, self.OFFICE_NODE)
        else:
            self._graph = graph

        if patrol_graph is not None:
            self._patrol_graph = patrol_graph

    def drain_events(self) -> list[AlgemEvent]:
        """Возвращает накопленные события ИИ и очищает очередь для следующего тика."""
        events = list(self._events)
        self._events.clear()
        return events

    def force_location(self, node: int, prev_node: int | None = None, trigger_ticks: int = 30) -> None:
        """Принудительно переносит Алгема в указанный узел для тестов и сценарных переходов."""
        old = self._location if prev_node is None else prev_node
        self._prev_location = old
        self._location = node
        self._trigger_timer = max(0, trigger_ticks)
        self._last_valid_location = node
        self._move_history.append((old, node, "FORCE"))
        self._last_path = []
        self._attack_detour_queue.clear()
        self._attack_detour_cooldown = 0
        self._attack_detours_used = 0
        self._reset_patrol_memory()

    def update_camera_watch(self, watch: dict[int, int]) -> None:
        """Передаёт ИИ информацию о том, какую камеру сейчас смотрит игрок."""
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
        """Синхронизирует ИИ с состоянием ноутбука, камер и серверной нагрузки."""
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
                self._camera_focus_interest + self._profile.camera_focus_growth * (0.35 + overload) * dt,
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
        hack_curve = max(0.0, min(1.0, self._hack_attraction)) ** 1.28
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
            and self._hack_attraction <= 0.01
            and self._post_hack_rage_attention <= 0.01
        ):
            # Тишина гасит именно угрозу/интерес. Патруль при этом не заморожен:
            # его запускает FSM через IDLE -> PATROL, а не шкала attention.
            target_attention = 0.0

        self._attention += (target_attention - self._attention) * 0.12
        self._attention = max(0.0, min(100.0, self._attention))

    def trigger_post_hack_rage(
        self,
        duration_ticks: int,
        attention_floor: float = 92.0,
        rage_level: float | None = None,
    ) -> None:
        """Запускает усиленную фазу поведения Алгема после завершения взлома."""
        self._post_hack_rage_ticks = max(self._post_hack_rage_ticks, int(duration_ticks))
        self._post_hack_rage_attention = max(self._post_hack_rage_attention, float(attention_floor))
        if rage_level is not None:
            self._post_hack_rage_level = max(self._post_hack_rage_level, float(rage_level))
        else:
            self._post_hack_rage_level = max(self._post_hack_rage_level, self._night + 0.45)
        self._hack_attraction = max(self._hack_attraction, 1.0)
        self._attention = max(self._attention, min(100.0, attention_floor - 4.0))
        self._idle_ticks_left = 0
        if self._state not in (AIState.BREACH, AIState.KILL_PENDING, AIState.STUNNED):
            self.cancel_audio_lure()
            self._enter_attack_state()
            cap = int(self._table_lerp(self._POST_HACK_RAGE_STEP_CAP_BY_NIGHT, self._post_hack_rage_level))
            self._move_timer = min(self._move_timer, cap)

    def _post_hack_rage_active(self) -> bool:
        """Проверяет, активна ли фаза пост-взломной агрессии."""
        return self._post_hack_rage_ticks > 0 or self._post_hack_rage_attention >= 25.0

    @staticmethod
    def _table_lerp(table: dict[int, float | int], level: float) -> float:
        """Интерполирует значение по таблице контрольных точек сложности."""
        if not table:
            return 0.0

        cache_key = id(table)
        keys = _TABLE_LERP_KEY_CACHE.get(cache_key)
        if keys is None:
            keys = tuple(sorted(table))
            _TABLE_LERP_KEY_CACHE[cache_key] = keys

        if level <= keys[0]:
            return float(table[keys[0]])
        if level >= keys[-1]:
            if len(keys) >= 2:
                prev_key, last_key = keys[-2], keys[-1]
                step = float(table[last_key]) - float(table[prev_key])
                return float(table[last_key]) + step * min(0.55, level - last_key)
            return float(table[keys[-1]])

        right = bisect_left(keys, level)
        lo = keys[right - 1]
        hi = keys[right]
        ratio = (level - lo) / (hi - lo)
        return float(table[lo]) + (float(table[hi]) - float(table[lo])) * ratio

    def _rage_level(self) -> float:
        """Рассчитывает текущую прибавку агрессии после взлома."""
        if not self._post_hack_rage_active():
            return float(self._night)
        return max(float(self._night), self._post_hack_rage_level)

    def notify_audio_lure(self, target_node: int, duration: int = 480) -> None:
        """Сообщает ИИ о звуковой приманке, которая может изменить маршрут Алгема."""
        if target_node == self._location:
            return
        path = bfs_path(self._location, target_node, self._graph)
        if path is None or len(path) - 1 > self._profile.lure_hear_distance:
            return
        if random.random() < self._profile.lure_fail_chance:
            return

        self._lure_node = target_node
        self._lure_ticks_left = duration
        self._investigate_target = target_node
        self._state = AIState.INVESTIGATE
        self._idle_ticks_left = 0
        self._move_timer = min(self._move_timer, 45)

    def cancel_audio_lure(self) -> None:
        """Отключает активную звуковую приманку и возвращает ИИ к обычному поведению."""
        self._lure_node = -1
        self._lure_ticks_left = 0
        if self._state is AIState.INVESTIGATE and self._investigate_target is not None:
            self._investigate_target = None

    def notify_laptop_power_event(self, event: str) -> None:
        """Фиксирует шум включения или выключения ноутбука как возможный источник интереса."""
        if self._night <= 1:
            return
        cooldown_scale = 0.38 if self._laptop_noise_cooldown > 0 else 1.0
        self._laptop_noise_cooldown = 240
        source_node = self.OFFICE_NODE
        path = bfs_path(self._location, source_node, self._graph)
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
        self._attention = min(100.0, self._attention + attention_gain)
        self._idle_ticks_left = 0

        if distance <= hearing_limit:
            self.cancel_audio_lure()
            if self._state in (AIState.IDLE, AIState.PATROL):
                self._state = AIState.INVESTIGATE
                self._investigate_target = (
                    self._choose_investigate_target() or self._nearest_patrol_node() or self.PATROL_SAFE_HOME
                )
            self._move_timer = min(self._move_timer, fast_move_cap + distance * 12)

        if distance <= 2:
            self._hack_attraction = max(self._hack_attraction, 0.22 if event == "on" else 0.30)
            if event == "off" or self._attention >= self._attack_threshold(self._profile.patrol_attack_threshold) - 8.0:
                self._enter_attack_state()
                self._move_timer = min(self._move_timer, 24 if distance <= 1 else 36)

    def _is_leaving_vent(self, vent_node: int) -> bool:
        """Return whether leaving vent is true for the current gameplay state."""
        if self._location == vent_node:
            return False
        return bool(
            (
                self._prev_location == vent_node
                and (
                    self._trigger_timer > 0
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
        """Сообщает ИИ о начале закрытия вентиляционной заслонки."""
        if self._is_leaving_vent(vent_node):
            self._seal_knock_suppressed_vents.add(vent_node)
            self._last_vent_leave_source = vent_node
            self._last_vent_leave_ticks = max(self._last_vent_leave_ticks, duration_ticks + 90)

    def notify_seal_closed(self, vent_node: int) -> None:
        """Сообщает ИИ о полностью закрытой заслонке и возможном блокировании пути."""
        # Если игрок закрыл камеру, на которой сейчас видит `algem_is_leaving`,
        # Алгем уже физически уполз с этой vent-камеры. В таком случае стука быть
        # не должно: это не блок, а запоздалая помеха от прошлого положения.
        leaving_this_vent = self._is_leaving_vent(vent_node)
        if vent_node in self._seal_knock_suppressed_vents or leaving_this_vent:
            self._seal_knock_suppressed_vents.discard(vent_node)
            return

        if self._location == vent_node:
            self._emit(AlgemEventType.SEAL_BLOCKED, self._location, vent_node, delay_ticks=60)
            lo, hi = self._STUN_TICKS_BY_NIGHT.get(self._night, (120, 240))
            stun_ticks = max(random.randint(lo, hi), 150)
            if stun_ticks > 0:
                self._stun_timer = stun_ticks
                self._state = AIState.STUNNED
                self._retreat_target = self._nearest_patrol_node() or self.PATROL_SAFE_HOME
                self._move_timer = min(self._move_timer, 30)
                self._trigger_timer = 0
                self._pressure_cooldown_ticks = max(self._pressure_cooldown_ticks, 210)
                self._attention = max(0.0, self._attention - 16.0)
                self._server_interest *= 0.82
                self._ad_interest *= 0.86
                self._vent_interest *= 0.70

    def tick(self, hour: int) -> bool:
        """Выполняет один тик FSM Алгема и обновляет маршрут, таймеры и события."""
        self._current_hour = hour
        self._block_external_teleport_if_needed()

        if self._trigger_timer > 0:
            self._trigger_timer -= 1
        if self._last_vent_leave_ticks > 0:
            self._last_vent_leave_ticks -= 1
            if self._last_vent_leave_ticks <= 0:
                self._last_vent_leave_source = -1
        if self._vent_motion_ticks > 0:
            self._vent_motion_ticks -= 1
            if self._vent_motion_ticks <= 0 and self._location not in self.VENT_NODES:
                self._vent_audio_source = -1
        if self._pressure_cooldown_ticks > 0:
            self._pressure_cooldown_ticks -= 1
        for vent_node in list(self._blocked_vent_knock_cooldowns):
            self._blocked_vent_knock_cooldowns[vent_node] -= 1
            if self._blocked_vent_knock_cooldowns[vent_node] <= 0:
                del self._blocked_vent_knock_cooldowns[vent_node]
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

        if self._state is AIState.BREACH:
            self._breach_timer -= 1
            if self._breach_timer <= 0:
                # GameModel дальше запускает честное random kill-window.
                self._emit(AlgemEventType.OFFICE_ENTERED, self._breach_source, self.OFFICE_NODE)
                return True
            return False

        if self._state is AIState.KILL_PENDING:
            return True

        if self._state is AIState.STUNNED:
            self._stun_timer -= 1
            if self._stun_timer <= 0:
                self._state = AIState.RETREAT
                self._move_timer = 1
            return False

        self._move_timer -= 1
        if self._move_timer > 0:
            return False

        reached_office = self._step(hour)
        # Важно считать следующий интервал ПОСЛЕ шага. Иначе при входе в вент
        # таймер берётся от обычной комнаты, и Алгем может почти сразу уползти
        # дальше. Для vent-камер это ломает честное окно на закрытие seal.
        if not reached_office and self._state is not AIState.BREACH:
            self._move_timer = self._compute_interval(hour)
        return reached_office

    # ------------------------------------------------------------------
    # FSM
    # ------------------------------------------------------------------

    def _step(self, hour: int) -> bool:
        """Вызывает обработчик текущего FSM-состояния Алгема."""
        if self._state is AIState.IDLE:
            return self._step_idle(hour)
        if self._state is AIState.PATROL:
            return self._step_patrol()
        if self._state is AIState.INVESTIGATE:
            return self._step_investigate()
        if self._state in (AIState.ATTACK, AIState.VENT_STALK):
            return self._step_attack()
        if self._state is AIState.RETREAT:
            return self._step_retreat()
        return self._step_patrol()

    def _step_idle(self, hour: int) -> bool:
        """Обрабатывает спокойное ожидание перед выходом Алгема на патруль."""
        self._idle_ticks_left -= 1
        if self._idle_ticks_left > 0 and self._attention < self._investigate_threshold():
            return False

        if self._should_attack():
            self._enter_attack_state()
        elif self._attention >= self._investigate_threshold():
            self._state = AIState.INVESTIGATE
            self._investigate_target = self._choose_investigate_target()
        else:
            self._state = AIState.PATROL
        return False

    def _step_patrol(self) -> bool:
        """Ведёт Алгема по патрульному маршруту с использованием DFS/BFS-логики выбора."""
        if self._should_attack():
            self._enter_attack_state()
            return False
        if self._attention >= self._investigate_threshold() or self._lure_node >= 0:
            self._state = AIState.INVESTIGATE
            self._investigate_target = self._choose_investigate_target()
            return False

        next_node = self._choose_patrol_node()
        self._move_to(next_node, self._patrol_graph)
        return False

    def _step_investigate(self) -> bool:
        """Двигает Алгема к источнику интереса, пока он не перейдёт к атаке или патрулю."""
        target = self._choose_investigate_target()
        self._investigate_target = target

        if target is None or target == self._location:
            if self._should_attack():
                self._enter_attack_state()
            else:
                self._state = AIState.PATROL
            return False

        # Приманка/расследование в обычной зоне — через DFS, чтобы алгоритм был
        # явно использован как «средний» пункт ТЗ.
        graph = self._patrol_graph if target in self._PATROL_ZONES.get(self._night, set()) else self._graph
        path = dfs_path(self._location, target, graph)
        if path is None or len(path) < 2:
            path = bfs_path(self._location, target, self._graph)
        if path and len(path) > 1:
            self._move_to(
                path[1],
                self._graph if path[1] not in self._patrol_graph.get(self._location, []) else graph,
            )

        if self._lure_node < 0 and self._should_attack():
            self._enter_attack_state()
        elif self._lure_node < 0 and self._attention < self._investigate_threshold() * 0.65:
            self._state = AIState.PATROL
        return False

    def _step_attack(self) -> bool:
        """Строит и исполняет атакующий маршрут к офису через A* и динамический граф."""
        self._trim_reached_attack_detours()
        self._maybe_start_unpredictable_attack_detour()

        goal = self._current_attack_goal()
        route_graph = self._current_attack_graph(goal)
        heuristic = (
            self._base_heuristic
            if goal == self.OFFICE_NODE and route_graph is self._graph
            else self._heuristic_for(route_graph, goal)
        )
        path = astar_path(self._location, goal, route_graph, self._edge_weight, heuristic)
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
        if self._location in self.VENT_NODES:
            self._state = AIState.VENT_STALK
        elif self._lure_node >= 0:
            self._state = AIState.INVESTIGATE
        else:
            self._state = AIState.ATTACK
        return False

    def _current_attack_goal(self) -> int:
        """Возвращает текущую цель атаки с учётом офисного входа и вентиляции."""
        if self._lure_node >= 0:
            return self._lure_node
        self._trim_reached_attack_detours()
        if self._attack_detour_queue:
            return self._attack_detour_queue[0]
        return self.OFFICE_NODE

    def _current_attack_graph(self, goal: int) -> dict[int, list[int]]:
        """Возвращает граф, на котором сейчас строится атакующий маршрут."""
        if goal != self.OFFICE_NODE or self._attack_detour_queue:
            return self._graph_with_special_detour_edges()
        return self._graph

    def _graph_with_special_detour_edges(self) -> Graph:
        """Добавляет временные рёбра для честных непредсказуемых обходов без телепортации."""
        if self._detour_graph is not None:
            return self._detour_graph

        graph = {node: list(neighbors) for node, neighbors in self._graph.items()}
        for source, targets in self._SPECIAL_DETOUR_EDGES.items():
            if source not in graph:
                continue
            for target in targets:
                if target in graph[source] or not self._node_is_enterable_for_detour(target):
                    continue
                graph[source].append(target)

        self._detour_graph = graph
        self._detour_graph_signature = graph_signature(graph)
        return graph

    def _node_is_enterable_for_detour(self, node: int) -> bool:
        """Проверяет, можно ли использовать узел как часть обходного маршрута."""
        return node == self.OFFICE_NODE or node == self._location or node in self._enterable_nodes

    def _trim_reached_attack_detours(self) -> None:
        """Удаляет из очереди обхода цели, до которых Алгем уже дошёл."""
        while self._attack_detour_queue and self._attack_detour_queue[0] == self._location:
            self._attack_detour_queue.popleft()
            self._attack_detour_cooldown = self._DETOUR_COOLDOWN_BY_NIGHT.get(self._night, 2)

    def _maybe_start_unpredictable_attack_detour(self) -> None:
        """Иногда вставляет обходной участок атаки, чтобы движение не было линейным."""
        if self._lure_node >= 0 or self._attack_detour_queue or self._location == self.OFFICE_NODE:
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
        self._move_history.append((self._location, plan[-1], "DETOUR"))

    def _unpredictable_route_chance(self) -> float:
        """Рассчитывает шанс непредсказуемого обхода по ночи и текущему давлению."""
        base = self._UNPREDICTABLE_ROUTE_CHANCE_BY_NIGHT.get(self._night, 0.0)
        hack_bonus = min(0.08, self._hack_attraction * 0.08)
        watch_bonus = 0.0
        if self._current_camera_idx == self._location:
            watch_bonus = 0.08 + self._night * 0.008
        rage_bonus = 0.0
        if self._post_hack_rage_active():
            rage_level = self._rage_level()
            rage_bonus = 0.08 + rage_level * 0.022
        recent_penalty = 0.04 * sum(1 for node in self._recent_nodes if node == self._location)
        return max(
            0.0,
            min(0.82, base + hack_bonus + watch_bonus + rage_bonus - recent_penalty),
        )

    def _choose_unpredictable_attack_plan(self) -> tuple[int, ...] | None:
        """Выбирает допустимый обходной план атаки из доступных узлов графа."""
        options = self._UNPREDICTABLE_ROUTE_OPTIONS.get(self._location, [])
        if not options:
            return None
        graph = self._graph_with_special_detour_edges()
        candidates: list[tuple[int, ...]] = []
        weights: list[float] = []
        rage_active = self._post_hack_rage_active()
        for base_weight, plan in options:
            cleaned = tuple(node for node in plan if node != self._location)
            if not cleaned:
                continue
            if cleaned[0] in self._recent_nodes:
                continue
            if rage_active:
                if not any(node in self._POST_HACK_RAGE_DETOUR_NODES for node in cleaned):
                    continue
                if self._location in (1, 2, 3) and cleaned[0] == self.PATROL_SAFE_HOME:
                    continue
            if not self._attack_plan_is_reachable(cleaned, graph):
                continue
            weight = base_weight
            if rage_active:
                rage_level = self._rage_level()
                weight *= 1.30 + rage_level * 0.07
            if any(node in self.VENT_NODES for node in cleaned):
                weight *= 1.0 + self._VENT_ROUTE_CHANCE_BY_NIGHT.get(self._night, 0.0) * 0.75
            if any(node not in self._recent_nodes for node in cleaned):
                weight *= 1.18
            if any(self._camera_watch.get(node, 0) <= 40 for node in cleaned):
                weight *= 1.12
            if self._location == 9 and cleaned[:2] == (10, 7):
                weight *= 1.0 + self._rage_level() * 0.12
            candidates.append(cleaned)
            weights.append(weight)
        if not candidates:
            return None
        return self._weighted_choice(candidates, weights)

    def _attack_plan_is_reachable(self, plan: tuple[int, ...], graph: Graph) -> bool:
        """Проверяет, что выбранный план можно пройти без закрытых вентиляционных рёбер."""
        current = self._location
        for target in (*plan, self.OFFICE_NODE):
            if target == current:
                continue
            heuristic = self._heuristic_for(graph, target)
            path = astar_path(current, target, graph, self._edge_weight, heuristic)
            if path is None or len(path) < 2:
                return False
            current = target
        return True

    def _step_retreat(self) -> bool:
        """Уводит Алгема от закрытой вентиляции или после отпугивания игроком."""
        target = self._nearest_patrol_node() or self.PATROL_SAFE_HOME
        if self._location == target:
            self._state = AIState.PATROL
            self._reset_patrol_memory()
            return False
        path = bfs_path(self._location, target, self._graph)
        if path and len(path) > 1:
            self._move_to(path[1], self._graph)
        else:
            self._state = AIState.PATROL
        return False

    # ------------------------------------------------------------------
    # Выбор целей и движение
    # ------------------------------------------------------------------

    def _enter_attack_state(self) -> None:
        """Переводит Алгема в атакующее состояние и подготавливает маршрут."""
        if self._state not in (AIState.ATTACK, AIState.VENT_STALK):
            self._attack_route_epoch += 1
            self._last_path = []
            self._attack_detour_queue.clear()
            self._attack_detour_cooldown = 0
            self._attack_detours_used = 0
        self._state = AIState.ATTACK

    def _choose_patrol_node(self) -> int:
        """Выбирает следующий патрульный узел с весами, памятью посещений и честным графом."""
        neighbors = list(self._patrol_graph.get(self._location, []))
        if not neighbors:
            return self._location

        if self._lure_node >= 0:
            path = dfs_path(self._location, self._lure_node, self._patrol_graph)
            if path and len(path) > 1:
                return path[1]

        patrol_zone = self._PATROL_ZONES.get(self._night)
        if self._patrol_graph_is_dedicated and patrol_zone is not None and self._location in patrol_zone:
            filtered = [n for n in neighbors if n in patrol_zone]
            if filtered:
                neighbors = filtered

        # DFS-патруль: сначала непосещённые ветки, потом backtracking.
        if not self._patrol_stack or self._patrol_stack[-1] != self._location:
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
            path = bfs_path(self._location, backtrack_target, self._patrol_graph)
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
            if self._attention >= self._profile.office_pull_start:
                dist = self._base_heuristic.get(node, 999)
                if dist < 999:
                    pull = min(
                        self._profile.office_pull_max,
                        (self._attention - self._profile.office_pull_start) / 100.0,
                    )
                    weight *= 1.0 + max(0.0, 4.0 - dist) * 0.16 * pull

            if node in self._recent_nodes:
                weight *= 0.55
            weights.append(weight)

        picked = self._weighted_choice(candidates, weights)
        self._patrol_visited.add(picked)
        self._patrol_stack.append(picked)
        return picked

    def _choose_investigate_target(self) -> int | None:
        """Выбирает узел расследования по источникам шума и интереса."""
        if self._lure_node >= 0:
            return self._lure_node

        sources: list[tuple[float, list[int]]] = [
            (
                self._server_interest + self._hack_attraction * 18.0,
                self._SERVER_INVESTIGATE_TARGETS,
            ),
            (self._ad_interest, self._AD_INVESTIGATE_TARGETS),
            (
                self._tablet_interest + self._camera_focus_interest,
                self._TABLET_INVESTIGATE_TARGETS,
            ),
        ]
        sources.sort(key=lambda item: item[0], reverse=True)
        score, targets = sources[0]
        if score <= 0.5:
            return None

        # Выбираем достижимую ближайшую цель из тематического списка.
        reachable: list[tuple[int, int]] = []
        for target in targets:
            path = bfs_path(self._location, target, self._graph)
            if path:
                reachable.append((len(path), target))
        if not reachable:
            return None
        reachable.sort()
        best = [target for _dist, target in reachable[:2]]
        return random.choice(best)

    def _is_blocked_vent_attempt(self, node: int) -> bool:
        """Return whether blocked vent attempt is true for the current gameplay state."""
        if node not in self.VENT_NODES:
            return False
        physical_neighbors = set(BASE_GRAPH.get(self._location, []))
        physical_neighbors.update(self._SPECIAL_DETOUR_EDGES.get(self._location, []))
        return node in physical_neighbors and node not in self._graph.get(self._location, [])

    def _handle_blocked_vent_attempt(self, vent_node: int) -> None:
        """Handle blocked vent attempt and translate it into game actions."""
        if vent_node in self._blocked_vent_knock_cooldowns:
            return
        if vent_node in self._seal_knock_suppressed_vents or self._is_leaving_vent(vent_node):
            self._seal_knock_suppressed_vents.discard(vent_node)
            return
        self._blocked_vent_knock_cooldowns[vent_node] = 420
        self._emit(AlgemEventType.SEAL_BLOCKED, self._location, vent_node, delay_ticks=60)
        lo, hi = self._STUN_TICKS_BY_NIGHT.get(self._night, (120, 240))
        self._stun_timer = max(random.randint(lo, hi), 90)
        self._state = AIState.STUNNED
        self._retreat_target = self._nearest_patrol_node() or self.PATROL_SAFE_HOME
        self._move_timer = min(self._move_timer, 30)
        self._trigger_timer = 0
        self._pressure_cooldown_ticks = max(self._pressure_cooldown_ticks, 150)
        self._attention = max(0.0, self._attention - 10.0)
        self._server_interest *= 0.88
        self._ad_interest *= 0.90
        self._vent_interest *= 0.78

    def _move_to(self, node: int, graph: dict[int, list[int]] | None = None) -> bool:
        """Перемещает Алгема в соседний узел, записывает историю и события движения."""
        if node == self._location:
            return True
        active_graph = graph or (self._patrol_graph if self._state is AIState.PATROL else self._graph)
        if node not in active_graph.get(self._location, []):
            if self._is_blocked_vent_attempt(node):
                self._handle_blocked_vent_attempt(node)
            self._last_move_rejected = (self._location, node)
            self._move_history.append((self._location, node, "REJECTED"))
            self._emit(AlgemEventType.ILLEGAL_MOVE_BLOCKED, self._location, node)
            return False

        prev = self._location
        self._prev_location = prev
        self._location = node
        self._last_valid_location = node
        self._trigger_timer = 30
        self._recent_nodes.append(node)
        self._move_history.append((prev, node, self._state.name))

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
            self._main_hall_sprite = random.randint(0, 1)
        return True

    def _emit(
        self,
        kind: AlgemEventType,
        source: int,
        target: int,
        delay_ticks: int = 0,
    ) -> None:
        """Добавляет событие ИИ в очередь для Presenter и звуковых контроллеров."""
        self._events.append(
            AlgemEvent(
                kind=kind,
                source=source,
                target=target,
                state=self._state.name,
                delay_ticks=delay_ticks,
            )
        )

    def _start_breach(self) -> None:
        """Start breach and initialize its timers/state."""
        source = self._location
        self._prev_location = source
        self._location = self.OFFICE_NODE
        self._last_valid_location = self.OFFICE_NODE
        self._move_history.append((source, self.OFFICE_NODE, "BREACH"))
        if source in self.VENT_NODES:
            hold_ticks = self._vent_motion_hold_ticks(source, self.OFFICE_NODE)
            self._last_vent_leave_source = source
            self._last_vent_leave_ticks = max(self._last_vent_leave_ticks, hold_ticks)
            self._vent_audio_source = source
            self._vent_motion_ticks = max(self._vent_motion_ticks, hold_ticks)
        self._breach_source = source
        self._state = AIState.BREACH
        self._breach_timer = random.randint(*self._BREACH_DELAY_BY_NIGHT.get(self._night, (90, 210)))
        self._entry_timer = 0
        self._trigger_timer = 30
        self._move_timer = self._breach_timer
        self._emit(AlgemEventType.BREACH_STARTED, source, self.OFFICE_NODE)

    def _start_stun_or_retreat(self) -> None:
        """Start stun or retreat and initialize its timers/state."""
        self._attack_detour_queue.clear()
        self._attack_detour_cooldown = max(self._attack_detour_cooldown, 1)
        self._stun_timer = random.randint(*self._STUN_TICKS_BY_NIGHT.get(self._night, (120, 240)))
        if self._stun_timer > 0:
            self._state = AIState.STUNNED
        else:
            self._state = AIState.RETREAT
        self._retreat_target = self._nearest_patrol_node() or self.PATROL_SAFE_HOME
        self._emit(AlgemEventType.ROUTE_BLOCKED, self._location, self._retreat_target)

    def _reset_patrol_memory(self) -> None:
        """Очищает память патруля, чтобы новый цикл не наследовал старые веса."""
        self._patrol_stack = [self._location]
        self._patrol_visited = {self._location}

    def _nearest_patrol_node(self) -> int | None:
        """Ищет ближайший безопасный патрульный узел после нестандартного перехода."""
        zone = self._PATROL_ZONES.get(self._night, {1, 2, 3, 4, 5, 6})
        if self._location in zone:
            return self._location

        queue: deque[int] = deque([self._location])
        visited = {self._location}
        while queue:
            current = queue.popleft()
            for neighbor in self._graph.get(current, []):
                if neighbor in visited:
                    continue
                if neighbor in zone:
                    return neighbor
                visited.add(neighbor)
                queue.append(neighbor)
        return None

    def _block_external_teleport_if_needed(self) -> None:
        """Отменяет внешние телепорты, если они ломают связность или честность маршрута."""
        if self._location == self._last_valid_location:
            return

        prev = self._last_valid_location
        current = self._location
        external_reset_from_office = (
            prev == self.OFFICE_NODE
            and current in self._PATROL_ZONES.get(self._night, {1, 2, 3, 4, 5, 6})
            and self._state is AIState.IDLE
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
        self._prev_location = current
        self._location = prev
        self._trigger_timer = 0
        self._last_path = []

    def _vent_motion_hold_ticks(self, prev: int, node: int) -> int:
        """Определяет длительность удержания вентиляционной анимации после перехода."""
        if prev in self.VENT_NODES and node in self.VENT_NODES:
            return 360 if self._state is AIState.RETREAT else 300
        if prev in self.VENT_NODES and node not in self.VENT_NODES:
            return 330 if self._state is AIState.RETREAT else 270
        if node in self.VENT_NODES:
            return 300 if self._state is AIState.RETREAT else 240
        return 0

    # ------------------------------------------------------------------
    # Вес A* / пороги / таймеры
    # ------------------------------------------------------------------

    def _edge_weight(self, u: int, v: int) -> float:
        # Штрафуем именно узел, куда Алгем хочет зайти, а не тот, откуда он уходит.
        """Возвращает вес ребра графа для A* и расчёта звукового расстояния."""
        watch = self._camera_watch.get(v, 0)
        observed = min(1.0, watch / 300.0)
        weight = 1.0 + observed * (1.0 + self._profile.watch_penalty_scale * 1.5)

        # Свежие узлы чуть дороже, чтобы A* не выглядел как рельсы.
        if v in self._recent_nodes:
            weight *= 1.18

        # Маршруты атаки слегка меняются от попытки к попытке, но шум стабилен
        # внутри одной атаки. A* остаётся A*, просто не ходит по одному рельсу.
        if v != self.OFFICE_NODE:
            weight *= self._stable_edge_noise(u, v)

        rage_active = self._post_hack_rage_active()
        if v in self.VENT_NODES:
            chance = self._table_lerp(
                self._VENT_ROUTE_CHANCE_BY_NIGHT,
                self._rage_level() if rage_active else float(self._night),
            )
            pressure_bonus = min(0.18, self._hack_attraction * 0.18)
            rage_bonus = min(0.20, 0.05 + self._rage_level() * 0.026) if rage_active else 0.0
            vent_bias = min(0.58, chance * 0.34 + pressure_bonus + rage_bonus)
            weight *= 1.0 - vent_bias
            if v == 8 and self._night >= 2:
                weight *= max(0.74, 0.86 - self._rage_level() * 0.018) if rage_active else 0.82
        elif u not in self.VENT_NODES and v != self.OFFICE_NODE:
            chance = self._table_lerp(
                self._VENT_ROUTE_CHANCE_BY_NIGHT,
                self._rage_level() if rage_active else float(self._night),
            )
            weight *= 1.0 + max(0.0, chance - 0.35) * (0.28 if rage_active else 0.18)
            if rage_active and v in (1, 2):
                weight *= 1.35

        if u == 9 and v == 10:
            weight *= max(0.68, 0.86 - self._rage_level() * 0.032) if rage_active else 0.86
        if rage_active and v == self.DANGER_NODE:
            weight *= max(0.76, 0.88 - self._rage_level() * 0.018)

        # Прямой вход в офис не должен быть слишком дешёвым: это даёт время на
        # последнюю vent-фазу и не превращает A* в мгновенный скример.
        if v == self.OFFICE_NODE:
            weight *= 1.20

        return max(0.45, weight)

    def _stable_edge_noise(self, u: int, v: int) -> float:
        """Даёт стабильную псевдослучайную поправку к весу ребра без скачков между кадрами."""
        seed = self._attack_route_epoch * 10007 + self._night * 1009 + u * 137 + v * 271
        seed ^= seed << 13
        seed ^= seed >> 17
        seed ^= seed << 5
        return 0.92 + (abs(seed) % 1001) / 1000.0 * 0.20

    def _attack_threshold(self, base_threshold: float) -> float:
        """Рассчитывает порог, после которого Алгем переходит из давления в атаку."""
        hack_cut = self._hack_attraction * (8.0 + self._night * 1.5)
        hour_cut = self._current_hour * self._profile.hour_attack_delta
        return max(35.0, base_threshold - hour_cut - hack_cut)

    def _investigate_threshold(self) -> float:
        """Рассчитывает порог, после которого Алгем начинает проверять источник интереса."""
        return max(10.0, 24.0 - self._night * 1.8 - self._current_hour * 0.9)

    def _should_attack(self) -> bool:
        """Проверяет, достаточно ли агрессии и внимания для начала атаки."""
        if self._lure_node >= 0:
            return False
        if (
            self._pressure_cooldown_ticks > 0
            and self._state
            not in (
                AIState.ATTACK,
                AIState.VENT_STALK,
                AIState.BREACH,
                AIState.KILL_PENDING,
            )
            and not (self._hack_attraction >= 0.86 and self._attention >= 92.0)
        ):
            return False
        can_attack = (
            self._hack_attraction >= 0.10
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
            threshold = min(threshold, 64.0 - self._rage_level() * 2.0)
        return can_attack and self._attention >= threshold

    def _compute_interval(self, hour: int) -> int:
        """Рассчитывает задержку между шагами Алгема с учётом ночи и режима поведения."""
        if self._post_hack_rage_active():
            rage_speed_level = self._rage_level()
            lo = int(self._table_lerp({k: v[0] for k, v in self._NIGHT_SPEED.items()}, rage_speed_level))
            hi = int(self._table_lerp({k: v[1] for k, v in self._NIGHT_SPEED.items()}, rage_speed_level))
        else:
            lo, hi = self._NIGHT_SPEED.get(self._night, (240, 600))
        attention_factor = self._attention / 100.0
        interval = int(hi - (hi - lo) * attention_factor)

        if self._state in (AIState.ATTACK, AIState.VENT_STALK):
            interval = int(interval * 0.74)
        elif self._state is AIState.INVESTIGATE:
            interval = int(interval * 0.88)
        elif self._state is AIState.RETREAT:
            interval = int(interval * 0.75)

        hack_mult = 1.0 - min(0.48, self._hack_attraction * (0.32 + self._night * 0.035))
        interval = int(interval * hack_mult)
        if self._post_hack_rage_active():
            rage_level = self._rage_level()
            interval = int(interval * max(0.60, 0.86 - rage_level * 0.038))

        if self._pressure_cooldown_ticks > 0 and self._state in (
            AIState.PATROL,
            AIState.RETREAT,
            AIState.INVESTIGATE,
        ):
            interval = int(interval * 1.18)

        if self._location in self.VENT_NODES:
            stay_level = self._rage_level() if self._post_hack_rage_active() else float(self._night)
            interval = max(
                interval,
                int(self._table_lerp(self._VENT_STAY_TICKS_BY_NIGHT, stay_level)),
            )
        elif self._state is AIState.VENT_STALK:
            # На случай, если состояние уже vent-атака, но следующий тик ещё
            # считается из обычной камеры перед входом в вент.
            interval = max(interval, 420)
        elif self._location == self.DANGER_NODE:
            interval = max(interval, 360)

        if self._state in (AIState.ATTACK, AIState.VENT_STALK) and self._location not in self.VENT_NODES:
            room_level = self._rage_level() if self._post_hack_rage_active() else float(self._night)
            interval = max(
                interval,
                int(self._table_lerp(self._ATTACK_ROOM_STEP_MIN_TICKS_BY_NIGHT, room_level)),
            )

        return max(45, interval)

    def _initial_delay(self) -> int:
        """Возвращает стартовую паузу перед первым появлением Алгема на ночи."""
        if self._night <= 1:
            return random.randint(240, 540)
        lo, hi = self._NIGHT_SPEED.get(self._night, (240, 600))
        return random.randint(max(90, lo // 2), max(120, hi))

    @staticmethod
    def _compute_enterable_nodes(graph: Graph) -> set[int]:
        """Собирает узлы, в которые Алгем может честно войти из текущего графа."""
        nodes: set[int] = set()
        for neighbors in graph.values():
            nodes.update(neighbors)
        return nodes

    def _heuristic_for(self, graph: Graph, goal: int) -> dict[int, int]:
        """Возвращает эвристику расстояния до цели для алгоритма A*."""
        signature = graph_signature(graph)
        key = (signature, goal)
        cached = self._heuristic_cache.get(key)
        if cached is not None:
            return cached

        heuristic = self._precompute_heuristic(graph, goal)
        self._heuristic_cache[key] = heuristic
        return heuristic

    @staticmethod
    def _precompute_heuristic(graph: Graph, goal: int) -> dict[int, int]:
        """Предварительно считает расстояния BFS для быстрой эвристики маршрута."""
        return single_target_hop_distances(graph, goal)

    @staticmethod
    def _weighted_choice(nodes: list[ChoiceT], weights: list[float]) -> ChoiceT:
        """Выбирает элемент по весам без нарушения вероятностного баланса."""
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
        """Возвращает человекочитаемое имя текущего состояния Алгема для отладки."""
        return self._state.name

    @property
    def debug_target(self) -> int | None:
        """Возвращает текущую цель Алгема для отладочной панели."""
        if self._state is AIState.INVESTIGATE:
            return self._investigate_target
        if self._state in (AIState.ATTACK, AIState.VENT_STALK):
            return self._current_attack_goal()
        if self._state is AIState.BREACH:
            return self.OFFICE_NODE
        return None

    @property
    def debug_path(self) -> list[int]:
        """Return the asset path or route for debug."""
        return list(self._last_path)

    @property
    def debug_move_history(self) -> list[tuple[int, int, str]]:
        """Возвращает последние переходы Алгема для проверки маршрутов."""
        return list(self._move_history)

    @property
    def debug_detour_queue(self) -> list[int]:
        """Возвращает очередь обходных целей атаки для отладки ИИ."""
        return list(self._attack_detour_queue)

    @property
    def debug_unpredictable_chance(self) -> float:
        """Возвращает текущий шанс непредсказуемого обхода для проверки баланса."""
        return self._unpredictable_route_chance()

    @property
    def vent_motion_ticks(self) -> int:
        """Возвращает оставшееся время вентиляционной анимации движения."""
        return self._vent_motion_ticks

    @property
    def vent_audio_source(self) -> int:
        """Возвращает источник вентиляционного звука, который должен слышать игрок."""
        if self._location in self.VENT_NODES:
            return self._location
        if self._vent_motion_ticks > 0 and self._vent_audio_source in self.VENT_NODES:
            return self._vent_audio_source
        return -1

    @property
    def last_vent_move(self) -> tuple[int, int]:
        """Возвращает последний переход по вентиляции для выбора правильного кадра."""
        return self._last_vent_move

    @property
    def last_vent_leave_source(self) -> int:
        """Возвращает узел, из которого Алгем ушёл из вентиляции."""
        return self._last_vent_leave_source if self._last_vent_leave_ticks > 0 else -1

    @property
    def pressure_cooldown_ticks(self) -> int:
        """Возвращает оставшийся кулдаун давления после резкого события."""
        return self._pressure_cooldown_ticks

    def __repr__(self) -> str:
        """Выполняет специализированную операцию «repr» в подсистеме algem ai."""
        return (
            f"AlgemAI(state={self._state.name}, loc={self._location}, "
            f"prev={self._prev_location}, attention={self._attention:.1f}, "
            f"hack={self._hack_attraction:.2f}, rage_level={self._rage_level():.2f}, lure={self._lure_node})"
        )
