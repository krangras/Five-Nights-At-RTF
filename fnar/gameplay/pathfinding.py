"""Алгоритмы поиска пути для карты камер.

Модуль не зависит от Pygame и игровой модели. Его функции являются чистыми:
они получают граф и возвращают маршрут, не меняя внешнее состояние. Это
упрощает тестирование, повторное использование и объяснение сложности
алгоритмов в README.
"""

from __future__ import annotations

import heapq
from collections import deque
from typing import Callable


Graph = dict[int, list[int]]
GraphSignature = tuple[tuple[int, tuple[int, ...]], ...]

UNREACHABLE_HEURISTIC = 999
MIN_EDGE_WEIGHT = 0.05


def _reconstruct_path(
    parents: dict[int, int | None],
    goal: int,
) -> list[int]:
    path: list[int] = []
    current: int | None = goal
    while current is not None:
        path.append(current)
        current = parents[current]
    path.reverse()
    return path


def bfs_path(start: int, goal: int, graph: Graph) -> list[int] | None:
    """Кратчайший путь в невзвешенном графе. Сложность O(V + E).

    Args:
        start: Параметр типа ``int``, используемый методом ``bfs_path``.
        goal: Параметр типа ``int``, используемый методом ``bfs_path``.
        graph: Параметр типа ``Graph``, используемый методом ``bfs_path``.

    Returns:
        Значение типа ``list[int] | None``."""
    if start == goal:
        return [start]

    queue: deque[int] = deque([start])
    parents: dict[int, int | None] = {start: None}

    while queue:
        current = queue.popleft()
        for neighbor in graph.get(current, []):
            if neighbor in parents:
                continue
            parents[neighbor] = current
            if neighbor == goal:
                return _reconstruct_path(parents, goal)
            queue.append(neighbor)
    return None


def dfs_path(start: int, goal: int, graph: Graph) -> list[int] | None:
    """Один физически допустимый маршрут через DFS. Сложность O(V + E).

    Args:
        start: Параметр типа ``int``, используемый методом ``dfs_path``.
        goal: Параметр типа ``int``, используемый методом ``dfs_path``.
        graph: Параметр типа ``Graph``, используемый методом ``dfs_path``.

    Returns:
        Значение типа ``list[int] | None``."""
    if start == goal:
        return [start]

    stack: list[int] = [start]
    parents: dict[int, int | None] = {start: None}
    visited: set[int] = set()

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        if current == goal:
            return _reconstruct_path(parents, goal)

        for neighbor in reversed(graph.get(current, [])):
            if neighbor in visited or neighbor in parents:
                continue
            parents[neighbor] = current
            stack.append(neighbor)
    return None


def astar_path(
    start: int,
    goal: int,
    graph: Graph,
    edge_weight_fn: Callable[[int, int], float],
    heuristic: dict[int, int],
) -> list[int] | None:
    """A* для взвешенного графа. Сложность O((V + E) log V).

    Args:
        start: Параметр типа ``int``, используемый методом ``astar_path``.
        goal: Параметр типа ``int``, используемый методом ``astar_path``.
        graph: Параметр типа ``Graph``, используемый методом ``astar_path``.
        edge_weight_fn: Параметр типа ``Callable[[int, int], float]``, используемый методом ``astar_path``.
        heuristic: Параметр типа ``dict[int, int]``, используемый методом ``astar_path``.

    Returns:
        Значение типа ``list[int] | None``."""
    if start == goal:
        return [start]

    open_heap: list[tuple[float, float, int]] = []
    heapq.heappush(open_heap, (float(heuristic.get(start, UNREACHABLE_HEURISTIC)), 0.0, start))
    best_g: dict[int, float] = {start: 0.0}
    parents: dict[int, int | None] = {start: None}

    while open_heap:
        _f, g, current = heapq.heappop(open_heap)
        if g > best_g.get(current, float("inf")):
            continue
        if current == goal:
            return _reconstruct_path(parents, goal)

        for neighbor in graph.get(current, []):
            new_g = g + max(MIN_EDGE_WEIGHT, edge_weight_fn(current, neighbor))
            if new_g < best_g.get(neighbor, float("inf")):
                best_g[neighbor] = new_g
                parents[neighbor] = current
                heapq.heappush(
                    open_heap,
                    (new_g + heuristic.get(neighbor, UNREACHABLE_HEURISTIC), new_g, neighbor),
                )
    return None


def graph_signature(graph: Graph) -> GraphSignature:
    return tuple(
        (node, tuple(neighbors))
        for node, neighbors in sorted(graph.items())
    )


def single_target_hop_distances(graph: Graph, goal: int) -> dict[int, int]:
    reverse_graph: dict[int, list[int]] = {node: [] for node in graph}
    for node, neighbors in graph.items():
        for neighbor in neighbors:
            reverse_graph.setdefault(neighbor, []).append(node)

    distances: dict[int, int] = {node: UNREACHABLE_HEURISTIC for node in graph}
    distances[goal] = 0
    queue: deque[int] = deque([goal])

    while queue:
        current = queue.popleft()
        next_distance = distances[current] + 1
        for neighbor in reverse_graph.get(current, []):
            if next_distance >= distances.get(neighbor, 999):
                continue
            distances[neighbor] = next_distance
            queue.append(neighbor)
    return distances
