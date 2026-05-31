"""
algem_ai.py — Модуль искусственного интеллекта для противника «Алгебраист».

Реализует конечный автомат (FSM) с тремя состояниями и алгоритм A* для
поиска пути. Полностью изолирован от Pygame — только чистая игровая логика.
Это позволяет тестировать ИИ независимо от рендеринга (принцип SRP).

Граф комнат (узлы):
    0 — Офис игрока (цель атаки)
    1 — Главный коридор
    2 — Комната Алгема (начальная позиция)
    3 — Туалеты
    4 — Западный коридор
    5 — Столовая
    6 — Коворкинг
    7 — Серверная

Состояния FSM:
    IDLE   — Алгем «думает», агрессия накапливается пассивно.
    PATROL — Случайное блуждание; узлы без камер притягивают сильнее.
    ATTACK — Целенаправленное движение к офису через A*.

Переходы:
    IDLE   → PATROL : таймер ожидания истёк.
    PATROL → ATTACK : вероятность растёт с ночью и накопленной агрессией.
    ATTACK → PATROL : сработала аудио-приманка или вентиляция сброшена.
    любое  → IDLE   : редкое «задумывание» (баг персонажа как геймплейный элемент).

Автор: генерируется как часть курсового проекта.
"""

from __future__ import annotations

import heapq
import random
import time
from collections import deque
from enum import Enum, auto
from typing import Callable


# ---------------------------------------------------------------------------
# Перечисление состояний FSM
# ---------------------------------------------------------------------------

class AIState(Enum):
    """
    Состояния конечного автомата (Finite State Machine) Алгебраиста.

    Использование Enum вместо строк/констант:
      - исключает опечатки;
      - позволяет сравнивать через `is`, не через `==`;
      - IDE подсвечивает все вхождения.
    """
    IDLE   = auto()   # Ожидание и накопление агрессии
    PATROL = auto()   # Случайный обход комнат
    ATTACK = auto()   # Целенаправленная атака через A*


# ---------------------------------------------------------------------------
# Чистые функции поиска пути (без побочных эффектов, легко тестируются)
# ---------------------------------------------------------------------------

def bfs_path(
    start: int,
    goal:  int,
    graph: dict[int, list[int]],
) -> list[int] | None:
    """
    Поиск кратчайшего пути в невзвешенном графе (BFS).

    Используется:
      - для предподсчёта эвристики A*;
      - как fallback в состоянии PATROL при аудио-приманке.

    Args:
        start : начальный узел.
        goal  : целевой узел.
        graph : словарь смежности {узел: [соседи]}.

    Returns:
        Список узлов пути [start, ..., goal] или None если путь не найден.

    Сложность: O(V + E).
    """
    if start == goal:
        return [start]

    queue:   deque[list[int]] = deque([[start]])
    visited: set[int]         = {start}

    while queue:
        path    = queue.popleft()
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


def astar_path(
    start:          int,
    goal:           int,
    graph:          dict[int, list[int]],
    edge_weight_fn: Callable[[int, int], float],
    heuristic:      dict[int, int],
) -> list[int] | None:
    """
    Алгоритм A* для взвешенного графа.

    Выбран вместо Dijkstra, потому что допустимая эвристика (BFS-расстояние
    до цели в невзвешенном графе) гарантирует оптимальность и ускоряет поиск.

    Args:
        start          : начальный узел.
        goal           : целевой узел (обычно офис = 0).
        graph          : текущий граф (может включать вент-короткие пути).
        edge_weight_fn : функция стоимости ребра (u, v) → float ≥ 1.0.
        heuristic      : предподсчитанный словарь {узел: BFS-расстояние до goal}.

    Returns:
        Список узлов оптимального пути или None.

    Сложность: O((V + E) · log V).
    """
    if start == goal:
        return [start]

    # Элемент кучи: (f = g + h, g, узел, путь)
    # f — оценка полного пути; g — пройденная стоимость
    open_heap: list[tuple[float, float, int, list[int]]] = []
    h0        = heuristic.get(start, 999)
    heapq.heappush(open_heap, (float(h0), 0.0, start, [start]))

    # Лучшая найденная стоимость g для каждого узла (для отброса устаревших)
    best_g: dict[int, float] = {start: 0.0}

    while open_heap:
        f, g, current, path = heapq.heappop(open_heap)

        # Устаревшая запись (нашли лучший путь позже) — пропускаем
        if g > best_g.get(current, float("inf")):
            continue

        if current == goal:
            return path

        for neighbor in graph.get(current, []):
            w     = edge_weight_fn(current, neighbor)
            new_g = g + w
            if new_g < best_g.get(neighbor, float("inf")):
                best_g[neighbor] = new_g
                h = heuristic.get(neighbor, 999)
                heapq.heappush(
                    open_heap,
                    (new_g + h, new_g, neighbor, path + [neighbor]),
                )

    return None


# ---------------------------------------------------------------------------
# Главный класс ИИ
# ---------------------------------------------------------------------------

class AlgemAI:
    """
    Конечный автомат (FSM) для управления Алгебраистом.

    Принцип единственной ответственности (SRP):
      - Этот класс знает ТОЛЬКО о логике перемещения и состояниях.
      - Он не рендерит, не воспроизводит звуки, не работает с Pygame напрямую.
      - Граф и конфиг ночи передаются извне → легко тестировать и расширять.

    Публичные атрибуты (читаются из GameModel через свойства):
        location         : int         — текущий узел в графе.
        prev_location    : int         — предыдущий узел (для анимации глитча).
        trigger_timer    : int         — тиков осталось от анимационного события.
        main_hall_sprite : int         — 0 или 1, вариант спрайта в Гл. коридоре.
        state            : AIState     — текущее состояние FSM.
    """

    # Узел офиса — цель атаки
    OFFICE_NODE: int = 0

    # Конфиг скоростей для каждой ночи: (мин. интервал, макс. интервал) в тиках
    _NIGHT_SPEED: dict[int, tuple[int, int]] = {
        1: (600, 900),
        2: (420, 600),
        3: (300, 420),
        4: (180, 300),
        5: (90, 180),
    }

    # Зоны патруля по ночам (какие узлы доступны для случайного блуждания)
    _PATROL_ZONES: dict[int, set[int]] = {
        1: {1, 2, 3, 4, 5, 6, 7},
        2: {1, 2, 3, 4},
        3: {1, 2, 3, 4, 5, 7},
        4: {1, 2, 3, 4, 5, 6, 7},
        5: {1, 2, 3, 4, 5, 6, 7},
    }

    def __init__(
        self,
        graph:      dict[int, list[int]],
        night:      int,
        start_node: int = 1,
    ) -> None:
        """
        Args:
            graph      : начальный граф комнат (может обновляться при вентах).
            night      : номер ночи 1–5; влияет на скорость и агрессивность.
            start_node : начальная позиция (по умолчанию — комната Алгема, узел 1).
        """
        self._graph:  dict[int, list[int]] = graph
        self._night:  int                  = night

        # ── Позиция ──────────────────────────────────────────────────────
        self.location:         int = start_node
        self.prev_location:    int = start_node

        # ── Таймеры ──────────────────────────────────────────────────────
        self.trigger_timer:    int = 0        # тиков для анимации перехода
        self._move_timer:      int = self._initial_delay()

        # ── FSM ──────────────────────────────────────────────────────────
        self.state:            AIState = AIState.IDLE   # начинает в покое
        self._idle_ticks_left: int     = 0

        # ── Агрессия [0.0 … 1.0] — растёт в IDLE, сбрасывается при смене ──
        self.aggression:       float = 0.0

        # ── Аудио-приманка ───────────────────────────────────────────────
        self._lure_node:       int  = -1    # -1 = нет приманки
        self._lure_ticks_left: int  = 0

        # ── Таймер входа в офис ──────────────────────────────────────────
        # Когда Алгем решает войти в офис, он задерживается на ~1.5 сек
        # на текущей камере, давая игроку шанс заметить и среагировать.
        self._entry_timer: int = 0

        # ── Приманка сервера (взлом) ─────────────────────────────────────
        # Чем выше значение, тем сильнее сервер притягивает Алгема.
        self.hack_attraction: float = 0.0

        # ── Вспомогательные ─────────────────────────────────────────────
        self.main_hall_sprite: int  = 0   # вариант спрайта в Главном коридоре
        self._camera_watch:    dict[int, int] = {}  # передаётся из GameModel

        # Предподсчёт BFS-эвристики до офиса (неизменна для базового графа)
        self._base_heuristic: dict[int, int] = self._precompute_heuristic(
            self._graph, self.OFFICE_NODE
        )

    # ──────────────────────────────────────────────────────────────────────
    # Публичный API — вызывается из GameModel
    # ──────────────────────────────────────────────────────────────────────

    def update_graph(self, graph: dict[int, list[int]]) -> None:
        """
        Обновить граф движения (например, при поломке вентиляции).

        Вызывается из GameModel каждый тик, передавая граф с учётом
        текущего состояния вентов.
        """
        self._graph = graph
        # Эвристика пересчитывается только если граф изменился
        self._base_heuristic = self._precompute_heuristic(self._graph, self.OFFICE_NODE)

    def update_camera_watch(self, watch: dict[int, int]) -> None:
        """
        Передать данные о «просматриваемости» комнат.

        Камеры, на которые долго смотрит игрок, увеличивают стоимость
        соответствующих рёбер — Алгем избегает наблюдаемых комнат.
        """
        self._camera_watch = watch

    def notify_audio_lure(self, target_node: int, duration: int = 480) -> None:
        """
        Сообщить ИИ об активации аудио-приманки в комнате target_node.

        Механика (как в FNAF3):
          - В режиме ATTACK: цель меняется с офиса на источник звука.
          - В режиме PATROL: следующий шаг будет в сторону приманки.
          - В режиме IDLE: Алгем «просыпается» и начинает патруль.

        Алгем слышит приманку только в радиусе 2 комнат (BFS-расстояние).

        Args:
            target_node : узел, где играет звук.
            duration    : сколько тиков действует приманка.
        """
        if target_node == self.location:
            return          # Алгем уже в этой комнате, эффекта нет

        path = bfs_path(self.location, target_node, self._graph)
        if path is None or len(path) - 1 > 2:
            return          # Слишком далеко — не слышит

        self._lure_node       = target_node
        self._lure_ticks_left = duration

        # Приманка «будит» Алгема
        if self.state == AIState.IDLE:
            self.state             = AIState.PATROL
            self._idle_ticks_left  = 0

    def cancel_audio_lure(self) -> None:
        """Принудительно отменить аудио-приманку (например, при сбросе вента)."""
        self._lure_node       = -1
        self._lure_ticks_left = 0

    def tick(self, hour: int) -> bool:
        """
        Один игровой тик ИИ.

        Обновляет таймеры, агрессию, и при необходимости делает ход.

        Args:
            hour : текущий игровой час (0–5); ускоряет поведение.

        Returns:
            True  — Алгем добрался до офиса (Game Over).
            False — всё в порядке.
        """
        # Обратный отсчёт анимационного триггера
        if self.trigger_timer > 0:
            self.trigger_timer -= 1

        # Первая ночь — ознакомительная, Алгем не двигается
        if self._night <= 1:
            return False

        # Обратный отсчёт аудио-приманки
        if self._lure_ticks_left > 0:
            self._lure_ticks_left -= 1
            if self._lure_ticks_left <= 0:
                self._lure_node = -1

        # Таймер входа в офис (тикает каждый кадр, а не только на ходах)
        if self._entry_timer > 0:
            self._entry_timer -= 1
            if self._entry_timer <= 0:
                return True     # Время вышло — Алгем ворвался в офис
            return False        # Ещё входит, не двигаемся

        # Накопление агрессии в состоянии IDLE
        if self.state is AIState.IDLE:
            gain = 0.0006 * (1 + self._night * 0.25)
            self.aggression = min(1.0, self.aggression + gain)

        # Таймер хода
        self._move_timer -= 1
        if self._move_timer > 0:
            return False

        # Сбрасываем таймер и выполняем шаг FSM
        self._move_timer = self._compute_interval(hour)
        return self._step(hour)

    # ──────────────────────────────────────────────────────────────────────
    # Внутренняя логика FSM
    # ──────────────────────────────────────────────────────────────────────

    def _step(self, hour: int) -> bool:
        """
        Основной диспетчер FSM — делегирует выполнение нужному состоянию.

        Returns:
            True если достигнут офис.
        """
        dispatch: dict[AIState, Callable[[int], bool]] = {
            AIState.IDLE:   lambda: self._step_idle(hour),
            AIState.PATROL: self._step_patrol,
            AIState.ATTACK: self._step_attack,
        }
        handler = dispatch.get(self.state, self._step_patrol)
        return handler()

    def _step_idle(self, hour: int) -> bool:
        """
        Состояние IDLE: ожидание.
        """
        self._idle_ticks_left -= 1
        if self._idle_ticks_left > 0:
            return False

        # FNAF-style: на ранних часах Алгем более пассивен
        hour_factor = (hour / 6.0) * 0.5
        idle_chance = 0.95 - (self._night * 0.05) - hour_factor
        
        if self.hack_attraction < 0.05 and random.random() < idle_chance:
            self._idle_ticks_left = random.randint(300, 600)
            return False

        # Переход в ATTACK: на ночах 1–3 без сервера — только PATROL
        attack_threshold = 0.7 - (self._night * 0.05)
        can_attack = self.hack_attraction >= 0.05 or self._night > 3
        if can_attack and self.aggression > attack_threshold and random.random() < (0.3 + hour * 0.1):
            if self._night > 1:
                self.state = AIState.ATTACK
            else:
                self.state = AIState.PATROL
                self.aggression = max(0.0, self.aggression - 0.1)
        else:
            self.state            = AIState.PATROL
            self.aggression       = max(0.0, self.aggression - 0.1)
        return False

    def _step_patrol(self) -> bool:
        """
        Состояние PATROL: случайное блуждание с весами.

        Узлы выбираются взвешенно:
          - Менее наблюдаемые камеры притягивают сильнее.
          - Если активна аудио-приманка — направляется к ней через BFS.

        Returns:
            True если случайно забрёл в офис (редко, только при algo_chance).
        """
        # На последней камере не двигается без приманки
        if self.location == 7 and self._lure_node < 0:
            return False

        next_node = self._choose_patrol_node()

        if next_node == self.OFFICE_NODE:
            return True     # Алгем дошёл до офиса

        self._move_to(next_node)

        # Вероятностный переход в ATTACK (только со 2-й ночи и с сервером)
        can_attack = self.hack_attraction >= 0.05 or self._night > 3
        if can_attack and self._night > 1:
            night_factor   = self._night / 5.0
            hack_mult      = self.hack_attraction
            attack_chance  = (0.06 + night_factor * 0.18 + self.aggression * 0.15) * hack_mult
            if random.random() < attack_chance:
                self.state = AIState.ATTACK

        # Редкое задумывание → IDLE (делает поведение менее предсказуемым)
        elif random.random() < 0.025:
            self.state             = AIState.IDLE
            self._idle_ticks_left  = random.randint(60, 180)

        return False

    def _step_attack(self) -> bool:
        """
        Состояние ATTACK: целенаправленное движение через A*.

        Цель — офис (узел 0), если нет активной приманки.
        Если приманка активна — идёт к ней (как в FNAF3: отвлекается).

        Returns:
            True если достиг офиса.
        """
        goal = (
            self._lure_node
            if self._lure_node >= 0
            else self.OFFICE_NODE
        )

        # Пересчитываем эвристику для не-офисной цели
        heuristic = (
            self._base_heuristic
            if goal == self.OFFICE_NODE
            else self._precompute_heuristic(self._graph, goal)
        )

        path = astar_path(
            start          = self.location,
            goal           = goal,
            graph          = self._graph,
            edge_weight_fn = self._edge_weight,
            heuristic      = heuristic,
        )

        if path is None or len(path) < 2:
            # Путь не найден — откатываемся в PATROL
            self.state = AIState.PATROL
            return False

        next_node = path[1]

        if next_node == self.OFFICE_NODE:
            self._entry_timer = 90  # ~1.5 сек на реакцию игрока
            return False

        self._move_to(next_node)
        return False

    # ──────────────────────────────────────────────────────────────────────
    # Вспомогательные методы выбора узла и оценки рёбер
    # ──────────────────────────────────────────────────────────────────────

    def _choose_patrol_node(self) -> int:
        """
        Взвешенный выбор следующего узла для PATROL.

        Если активна аудио-приманка — BFS к её источнику.
        Иначе — стохастический выбор с учётом наблюдаемости камер
        и зоны патруля (первые ночи ходит только рядом со своей комнатой).

        На последней камере (node 7) стоит на месте без приманки.
        """
        # На node 7 не двигается, пока не сработает приманка
        if self.location == 7 and self._lure_node < 0:
            return 7

        neighbors = self._graph.get(self.location, [])
        if not neighbors:
            return self.location

        # Аудио-приманка: идём к источнику звука
        if self._lure_node >= 0:
            path = bfs_path(self.location, self._lure_node, self._graph)
            if path and len(path) > 1:
                candidate = path[1]
                if candidate != self.OFFICE_NODE or self._lure_node == self.OFFICE_NODE:
                    return candidate

        # Фильтр по зоне патруля (только для случайного блуждания)
        patrol_zone = self._PATROL_ZONES.get(self._night)
        if patrol_zone is not None and self.location in patrol_zone:
            neighbors = [n for n in neighbors if n in patrol_zone]
            if not neighbors:
                neighbors = self._graph.get(self.location, [])

        # Взвешенный случайный выбор
        weights: list[float] = []
        for n in neighbors:
            watch    = self._camera_watch.get(n, 0)
            observed = min(1.0, watch / 300.0)
            penalty  = 0.05 if n == self.OFFICE_NODE else 1.0
            weights.append(max(0.05, (1.0 - observed * 0.85)) * penalty)

        total = sum(weights)
        r     = random.uniform(0.0, total)
        accum = 0.0
        for node, w in zip(neighbors, weights):
            accum += w
            if r <= accum:
                return node

        return neighbors[-1]   # fallback

    def _edge_weight(self, u: int, v: int) -> float:
        """
        Стоимость перемещения из u в v для A*.

        Камеры, которые долго наблюдает игрок, дороже (Алгем избегает).
        Базовая стоимость = 1.0; наблюдение добавляет до +2.0.

        Эта функция делает поведение «реактивным» на действия игрока:
        смотри на камеру → Алгем будет обходить эту комнату.
        """
        watch    = self._camera_watch.get(u, 0)
        observed = min(1.0, watch / 300.0)
        return 1.0 + observed * 2.0

    def _move_to(self, node: int) -> None:
        """Переместить Алгема и взвести анимационный триггер."""
        if node != self.location:
            self.prev_location = self.location
            self.location      = node
            self.trigger_timer = 60

            # В Главном коридоре — случайный вариант спрайта
            if node == 1:
                self.main_hall_sprite = random.randint(0, 1)

    # ──────────────────────────────────────────────────────────────────────
    # Утилиты
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _precompute_heuristic(
        graph: dict[int, list[int]],
        goal:  int,
    ) -> dict[int, int]:
        """
        Предподсчитать BFS-расстояния от каждого узла до goal.

        Используется как допустимая эвристика для A*:
        h(n) ≤ реального расстояния → A* остаётся оптимальным.
        """
        result: dict[int, int] = {}
        for node in graph:
            path         = bfs_path(node, goal, graph)
            result[node] = (len(path) - 1) if path else 999
        return result

    def _initial_delay(self) -> int:
        """Начальная задержка перед первым ходом (зависит от номера ночи)."""
        if self._night <= 3:
            base = random.randint(1800, 3000)  # 30–50 секунд на ранних ночах
        else:
            base = max(60, 300 - self._night * 40)
            base = random.randint(base, base + 120)
        return base

    def _compute_interval(self, hour: int) -> int:
        """
        Интервал между ходами (тиков).

        Влияющие факторы:
          - Номер ночи (чем выше — тем быстрее).
          - Игровой час (каждый час ускоряет на 20 тиков).
          - Состояние ATTACK: вдвое быстрее для нагнетания напряжения.
          - Приманка сервера (hack_attraction): ускоряет движение Алгема.

        Минимум — 60 тиков (1 секунда при 60 FPS).
        """
        lo, hi = self._NIGHT_SPEED.get(self._night, (120, 240))

        speed_mult = 0.5 if self.state is AIState.ATTACK else 1.0

        # Приманка сервера: до 3x ускорения при hack_attraction = 1.0
        # Когда сервер выключен (hack_attraction ≈ 0) — базовая скорость
        hack_mult = 1.0 - self.hack_attraction * 0.67

        lo_adj = max(60, int((lo - hour * 20) * speed_mult * hack_mult))
        hi_adj = max(90, int((hi - hour * 20) * speed_mult * hack_mult))
        return random.randint(lo_adj, hi_adj)

    # ──────────────────────────────────────────────────────────────────────
    # Debug / repr
    # ──────────────────────────────────────────────────────────────────────

    @property
    def state_name(self) -> str:
        """Строковое имя состояния для HUD и отладки."""
        return self.state.name

    def __repr__(self) -> str:
        return (
            f"AlgemAI(state={self.state.name}, "
            f"loc={self.location}, "
            f"aggr={self.aggression:.2f}, "
            f"lure={self._lure_node})"
        )