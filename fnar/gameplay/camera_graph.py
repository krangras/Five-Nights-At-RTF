"""Граф камер и вентиляции для маршрутизации Алгема и расчёта доступных путей."""

from __future__ import annotations

from .pathfinding import bfs_path

OFFICE_NODE = 0
VENT_CAMERAS: set[int] = {8, 9, 10, 11}

BASE_GRAPH: dict[int, list[int]] = {
    0: [],
    1: [2, 3, 4, 8],
    2: [1, 3, 8, 9],
    3: [1, 2, 4, 5, 8],
    4: [1, 2, 3, 5, 11],
    5: [3, 4, 6],
    6: [5, 10],
    7: [10, 11],
    8: [1, 2, 3],
    9: [2, 0],
    10: [7, 11, 0],
    11: [4, 10, 7],
}

PATROL_GRAPH: dict[int, list[int]] = {
    0: [],
    1: [2, 3, 4],
    2: [1, 3],
    3: [1, 2, 4, 5],
    4: [1, 2, 3, 5],
    5: [3, 4, 6],
    6: [5],
    7: [],
    8: [],
    9: [],
    10: [],
    11: [],
}

SPECIAL_DETOUR_EDGES: dict[int, list[int]] = {
    9: [10],
}

VENT_SEALS: dict[str, int] = {
    "SEAL_TOP_RIGHT": 9,
    "SEAL_CENTER": 10,
    "SEAL_MID_RIGHT": 8,
    "SEAL_BOTTOM_LEFT": 11,
}

SEAL_CAMERA_MAP: dict[int, str] = {
    8: "SEAL_MID_RIGHT",
    9: "SEAL_TOP_RIGHT",
    10: "SEAL_CENTER",
    11: "SEAL_BOTTOM_LEFT",
}

SEAL_RETREAT_GRAPH: dict[int, list[int]] = {
    8: [1, 2, 3],
    9: [2],
    10: [6, 11],
    11: [4, 10],
}

AUDIO_EDGE_WEIGHTS: dict[tuple[int, int], float] = {
    (0, 7): 0.80,
    (0, 9): 1.25,
    (0, 10): 2.40,
    (1, 2): 2.55,
    (1, 3): 1.35,
    (1, 4): 1.15,
    (1, 8): 1.35,
    (2, 3): 1.40,
    (2, 4): 2.35,
    (2, 8): 1.25,
    (2, 9): 1.45,
    (3, 4): 0.75,
    (3, 5): 1.55,
    (3, 8): 0.90,
    (4, 5): 1.25,
    (4, 11): 1.70,
    (5, 6): 1.05,
    (5, 7): 1.35,
    (5, 10): 1.45,
    (5, 11): 1.10,
    (6, 10): 0.85,
    (6, 11): 1.75,
    (7, 9): 1.65,
    (7, 10): 1.65,
    (8, 9): 2.10,
    (8, 11): 4.05,
    (9, 10): 3.80,
    (10, 11): 3.10,
}


VENT_DIRECTION_GRAPH: dict[int, list[int]] = {node: list(neighbors) for node, neighbors in BASE_GRAPH.items()}
for source, targets in SPECIAL_DETOUR_EDGES.items():
    VENT_DIRECTION_GRAPH.setdefault(source, [])
    for target in targets:
        if target not in VENT_DIRECTION_GRAPH[source]:
            VENT_DIRECTION_GRAPH[source].append(target)


def copy_graph(graph: dict[int, list[int]]) -> dict[int, list[int]]:
    """Return a shallow copy of a camera graph without sharing neighbor lists."""
    return {node: list(neighbors) for node, neighbors in graph.items()}


def distance_to_office(node: int, graph: dict[int, list[int]] | None = None) -> int:
    """Return the number of graph hops from a node to the office."""
    path = bfs_path(node, OFFICE_NODE, graph or VENT_DIRECTION_GRAPH)
    return 999 if not path else max(0, len(path) - 1)


def is_vent_detour_away_from_office(source: int, target: int) -> bool:
    """Return whether a vent move increases distance from the office."""
    if source not in VENT_CAMERAS or target not in VENT_CAMERAS:
        return False
    return distance_to_office(target) >= distance_to_office(source)
