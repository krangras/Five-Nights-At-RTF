"""Подсистема блокировки вентиляционных шахт.

``GameModel`` раньше напрямую хранила таймеры seal, состояние каждой
заслонки и кэш графа. Это превращало модель ночи в god-object: она
одновременно считала время, сервер, рекламу, ИИ и геометрию вентов.

``VentSealController`` забирает одну ответственность: принять команду
закрытия, отсчитать анимацию SEALING -> CLOSED и построить актуальный
граф камер с учётом закрытых шахт.
"""

from __future__ import annotations

from enum import Enum, auto

from .pathfinding import Graph


class SealState(Enum):
    """Состояние одной блокировки вентиляции."""

    OPEN = auto()
    SEALING = auto()
    CLOSED = auto()


class VentSealController:
    """Owns vent seal timers and builds the current traversal graph."""

    def __init__(
        self,
        vent_seals: dict[str, int],
        base_graph: Graph,
        seal_retreat_graph: Graph,
        seal_duration: int,
    ) -> None:
        """Выполняет специализированную операцию «init» в подсистеме vent seal."""
        self._vent_seals = vent_seals
        self._base_graph = base_graph
        self._seal_retreat_graph = seal_retreat_graph
        self._seal_duration = seal_duration
        self.seals: dict[str, SealState] = {seal_id: SealState.OPEN for seal_id in vent_seals}
        self._timers: dict[str, int] = {seal_id: 0 for seal_id in vent_seals}
        self._currently_sealing_id: str | None = None
        self._graph_cache_key: tuple[tuple[str, ...], int] | None = None
        self._graph_cache: Graph | None = None

    @property
    def currently_sealing_id(self) -> str | None:
        """Возвращает или задаёт номер вентиляции, которая закрывается сейчас."""
        return self._currently_sealing_id

    @currently_sealing_id.setter
    def currently_sealing_id(self, value: str | None) -> None:
        """Возвращает или задаёт номер вентиляции, которая закрывается сейчас."""
        self._currently_sealing_id = value
        self._invalidate_graph_cache()

    def start(self, seal_id: str) -> int | None:
        """Начинает закрытие выбранной вентиляции, если это допустимо текущим состоянием."""
        if self.seals.get(seal_id) is not SealState.OPEN:
            return None
        if self._currently_sealing_id is not None:
            return None

        # Одновременно активным может быть только один seal. Поэтому новый
        # клик открывает ранее закрытые заслонки и делает выбор игрока явным.
        for known_id in self._vent_seals:
            if self.seals[known_id] is SealState.CLOSED:
                self.seals[known_id] = SealState.OPEN

        self.seals[seal_id] = SealState.SEALING
        self._timers[seal_id] = self._seal_duration
        self._currently_sealing_id = seal_id
        self._invalidate_graph_cache()
        return self._vent_seals.get(seal_id)

    def tick(self) -> list[int]:
        """Выполняет один тик FSM Алгема и обновляет маршрут, таймеры и события."""
        closed_now: list[int] = []
        for seal_id in self._vent_seals:
            if self.seals[seal_id] is not SealState.SEALING:
                continue

            self._timers[seal_id] -= 1
            if self._timers[seal_id] > 0:
                continue

            self.seals[seal_id] = SealState.CLOSED
            self._timers[seal_id] = 0
            vent_node = self._vent_seals.get(seal_id)
            if vent_node is not None:
                closed_now.append(vent_node)
            if self._currently_sealing_id == seal_id:
                self._currently_sealing_id = None

        if closed_now:
            self._invalidate_graph_cache()
        return closed_now

    def current_graph(self, actor_location: int) -> Graph:
        """Возвращает граф камер с удалёнными рёбрами закрытых вентиляций."""
        closed = tuple(seal_id for seal_id in self._vent_seals if self.seals[seal_id] is SealState.CLOSED)
        location_key = actor_location if closed else -1
        cache_key = (closed, location_key)
        if self._graph_cache_key == cache_key and self._graph_cache is not None:
            return self._graph_cache

        graph = self._copy_graph(self._base_graph)
        for seal_id in closed:
            vent_node = self._vent_seals[seal_id]
            self._remove_external_edges_to_vent(graph, vent_node)
            if actor_location == vent_node:
                graph[vent_node] = self._safe_retreats_from(vent_node)
            else:
                graph[vent_node] = []

        self._graph_cache_key = cache_key
        self._graph_cache = graph
        return graph

    def _remove_external_edges_to_vent(self, graph: Graph, vent_node: int) -> None:
        """Удаляет входы в закрытую вентиляцию, оставляя внутренние безопасные связи."""
        for other_node, neighbors in list(graph.items()):
            if other_node == vent_node or vent_node not in neighbors:
                continue
            graph[other_node] = [node for node in neighbors if node != vent_node]

    def _safe_retreats_from(self, vent_node: int) -> list[int]:
        """Находит безопасные узлы отступления от заблокированной вентиляции."""
        base_neighbors = self._base_graph.get(vent_node, [])
        return [node for node in self._seal_retreat_graph.get(vent_node, []) if node in base_neighbors]

    def _invalidate_graph_cache(self) -> None:
        """Сбрасывает кэш графа после изменения состояния заслонок."""
        self._graph_cache_key = None
        self._graph_cache = None

    @staticmethod
    def _copy_graph(graph: Graph) -> Graph:
        """Создаёт независимую копию графа для безопасных изменений."""
        return {node: list(neighbors) for node, neighbors in graph.items()}
