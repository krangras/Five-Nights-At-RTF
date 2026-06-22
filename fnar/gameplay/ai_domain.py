"""Доменный слой ИИ Алгема.

Здесь лежат только небольшие типы данных: состояния конечного автомата,
типы событий и профиль баланса ночи. Вынесение этих структур из основного
ИИ уменьшает связанность и помогает соблюдать SRP: algoritms stay in
``algem_ai.py``/``pathfinding.py``, а данные предметной области — здесь.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


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
