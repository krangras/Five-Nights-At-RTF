"""Spatial audio math for gameplay.

This module contains only distance/volume calculations. It has no pygame
objects and does not know about input, rendering, or the game loop.
"""

from __future__ import annotations

import heapq

from fnar.gameplay.camera_graph import AUDIO_EDGE_WEIGHTS, BASE_GRAPH

TALK_DIST_PARAMS: dict[int, tuple[int, float]] = {
    0: (0, 1.00),
    1: (5, 0.72),
    2: (13, 0.46),
    3: (24, 0.27),
    4: (36, 0.14),
}

AUDIO_MAX_BUCKET = 4
AUDIO_DIRECT_GAIN = 1.00
AUDIO_MIN_GAIN = 0.10
AUDIO_OFFICE_FLOOR = 0.16
AUDIO_VENT_MAP_GAIN = 0.34
AUDIO_SEALING_SOURCE_GAIN = 0.62
AUDIO_CLOSED_SOURCE_GAIN = 0.48
AUDIO_CLOSED_RETREAT_GAIN = 0.42
AUDIO_UNREACHABLE_DISTANCE = 9999.0

AUDIO_DISTANCE_VOLUME_CURVE: tuple[tuple[float, float], ...] = (
    (0.00, 1.00),
    (0.70, 0.92),
    (1.20, 0.78),
    (1.85, 0.60),
    (2.60, 0.42),
    (3.50, 0.26),
    (4.60, 0.14),
    (6.20, 0.09),
)

AUDIO_BUCKET_THRESHOLDS: tuple[float, float, float, float] = (
    0.05,
    1.25,
    2.35,
    3.45,
)

def _audio_edge_key(node: int, neighbor: int) -> tuple[int, int]:
    """Выполнить ``audio edge key``.
    
    Args:
        node: Входной параметр метода ``_audio_edge_key``.
        neighbor: Входной параметр метода ``_audio_edge_key``.
    
    Returns:
        Значение типа ``tuple[int, int]``.
    """
    return (node, neighbor) if node < neighbor else (neighbor, node)


def _build_audio_graph() -> dict[int, list[int]]:
    """Выполнить ``build audio graph``.
    
    Args:
        Нет аргументов.
    
    Returns:
        Значение типа ``dict[int, list[int]]``.
    """
    graph: dict[int, set[int]] = {node: set() for node in BASE_GRAPH}
    for node_a, node_b in AUDIO_EDGE_WEIGHTS:
        graph.setdefault(node_a, set()).add(node_b)
        graph.setdefault(node_b, set()).add(node_a)
    return {node: sorted(neighbors) for node, neighbors in graph.items()}


BASE_AUDIO_GRAPH: dict[int, list[int]] = _build_audio_graph()


def _edge_audio_weight(node: int, neighbor: int) -> float:
    """Выполнить ``edge audio weight``.
    
    Args:
        node: Входной параметр метода ``_edge_audio_weight``.
        neighbor: Входной параметр метода ``_edge_audio_weight``.
    
    Returns:
        Значение типа ``float``.
    """
    return AUDIO_EDGE_WEIGHTS.get(_audio_edge_key(node, neighbor), 6.40)


def _weighted_audio_distance(
    start: int,
    goal: int,
    graph: dict[int, list[int]],
) -> float:
    """Выполнить ``weighted audio distance``.
    
    Args:
        start: Входной параметр метода ``_weighted_audio_distance``.
        goal: Входной параметр метода ``_weighted_audio_distance``.
        graph: Входной параметр метода ``_weighted_audio_distance``.
    
    Returns:
        Значение типа ``float``.
    """
    if start == goal:
        return 0.0

    dist_map: dict[int, float] = {start: 0.0}
    heap = [(0.0, start)]
    while heap:
        dist, node = heapq.heappop(heap)
        if node == goal:
            return dist
        if dist > dist_map.get(node, float("inf")):
            continue
        for neighbor in graph.get(node, []):
            new_dist = dist + _edge_audio_weight(node, neighbor)
            if new_dist < dist_map.get(neighbor, float("inf")):
                dist_map[neighbor] = new_dist
                heapq.heappush(heap, (new_dist, neighbor))
    return AUDIO_UNREACHABLE_DISTANCE


def _precompute_weighted_distances() -> dict[tuple[int, int], float]:
    """Выполнить ``precompute weighted distances``.
    
    Args:
        Нет аргументов.
    
    Returns:
        Значение типа ``dict[tuple[int, int], float]``.
    """
    result: dict[tuple[int, int], float] = {}
    for start in BASE_AUDIO_GRAPH:
        for end in BASE_AUDIO_GRAPH:
            result[(start, end)] = _weighted_audio_distance(start, end, BASE_AUDIO_GRAPH)
    return result


WEIGHTED_DISTANCES: dict[tuple[int, int], float] = _precompute_weighted_distances()


def _volume_from_distance(dist: float) -> float:
    """Выполнить ``volume from distance``.
    
    Args:
        dist: Входной параметр метода ``_volume_from_distance``.
    
    Returns:
        Значение типа ``float``.
    """
    if dist <= 0.0:
        return AUDIO_DIRECT_GAIN
    if dist >= AUDIO_UNREACHABLE_DISTANCE:
        return AUDIO_MIN_GAIN

    points = AUDIO_DISTANCE_VOLUME_CURVE
    if dist <= points[0][0]:
        return points[0][1]
    for (left_dist, left_vol), (right_dist, right_vol) in zip(points, points[1:]):
        if dist <= right_dist:
            t = (dist - left_dist) / max(0.001, right_dist - left_dist)
            return left_vol + (right_vol - left_vol) * t
    return max(AUDIO_MIN_GAIN, points[-1][1])


def _bucket_from_weighted_distance(dist: float) -> int:
    """Выполнить ``bucket from weighted distance``.
    
    Args:
        dist: Входной параметр метода ``_bucket_from_weighted_distance``.
    
    Returns:
        Значение типа ``int``.
    """
    if dist <= AUDIO_BUCKET_THRESHOLDS[0]:
        return 0
    if dist <= AUDIO_BUCKET_THRESHOLDS[1]:
        return 1
    if dist <= AUDIO_BUCKET_THRESHOLDS[2]:
        return 2
    if dist <= AUDIO_BUCKET_THRESHOLDS[3]:
        return 3
    return AUDIO_MAX_BUCKET

CHANNEL_MASTERS: dict[str, float] = {
    "algem_talk": 0.82,
    "vent": 0.86,
    "ad": 0.38,
}

CHANNEL_SOUND_IDS: dict[str, str] = {
    "algem_talk": "algem_talk",
    "vent": "vent_presence",
    "ad": "ad_loop",
}
