import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fnar.gameplay.algem_ai import AIState, AlgemAI, dfs_path
from fnar.gameplay.model import BASE_GRAPH, PATROL_GRAPH, GameModel, SealState


def test_patrol_graph_matches_regular_camera_map():
    assert PATROL_GRAPH[1] == [2, 3, 4]
    assert PATROL_GRAPH[2] == [1, 3]
    assert PATROL_GRAPH[3] == [1, 2, 4, 5]
    assert PATROL_GRAPH[4] == [1, 2, 3, 5]
    assert PATROL_GRAPH[5] == [3, 4, 6]
    assert PATROL_GRAPH[6] == [5]
    assert all(not PATROL_GRAPH[node] for node in (7, 8, 9, 10, 11))


def test_attack_graph_has_described_vent_entries_and_exits():
    assert BASE_GRAPH[1] == [2, 3, 4, 8]
    assert BASE_GRAPH[4] == [1, 2, 3, 5, 11]
    assert 8 in BASE_GRAPH[2]
    assert 9 in BASE_GRAPH[2]
    assert BASE_GRAPH[9] == [2, 0]
    assert BASE_GRAPH[10] == [7, 11, 0]


def test_dfs_patrol_path_never_skips_a_camera():
    path = dfs_path(1, 6, PATROL_GRAPH)
    assert path is not None
    assert path[0] == 1
    assert path[-1] == 6
    assert all(dst in PATROL_GRAPH[src] for src, dst in zip(path, path[1:]))


def test_move_to_rejects_non_neighbor_teleport():
    ai = AlgemAI(
        copy.deepcopy(BASE_GRAPH),
        night=2,
        start_node=1,
        patrol_graph=copy.deepcopy(PATROL_GRAPH),
    )
    ai.state = AIState.ATTACK
    ai._move_to(7)
    assert ai.location == 1


def test_patrol_can_only_step_to_regular_neighbor():
    ai = AlgemAI(
        copy.deepcopy(BASE_GRAPH),
        night=2,
        start_node=1,
        patrol_graph=copy.deepcopy(PATROL_GRAPH),
    )
    ai.state = AIState.PATROL
    for _ in range(100):
        assert ai._choose_patrol_node() in {2, 3, 4}


def test_patrol_dfs_walk_and_backtracking_use_only_edges():
    ai = AlgemAI(
        copy.deepcopy(BASE_GRAPH),
        night=2,
        start_node=1,
        patrol_graph=copy.deepcopy(PATROL_GRAPH),
    )
    ai.state = AIState.PATROL
    ai._server_on = True
    visited = {ai.location}

    for _ in range(20):
        previous = ai.location
        ai._step_patrol()
        assert ai.location in PATROL_GRAPH[previous]
        visited.add(ai.location)

    assert visited == {1, 2, 3, 4, 5, 6}


def test_closed_seal_blocks_entry_but_allows_physical_exit():
    model = GameModel(night=2)
    model.seals["SEAL_BOTTOM_LEFT"] = SealState.CLOSED
    graph = model._build_current_graph()

    assert 10 not in graph[4]
    assert graph[10] == [7, 0]


def test_astar_replans_around_closed_vent_entry():
    model = GameModel(night=2)
    model.seals["SEAL_BOTTOM_LEFT"] = SealState.CLOSED
    graph = model._build_current_graph()
    ai = AlgemAI(
        graph,
        night=2,
        start_node=4,
        patrol_graph=copy.deepcopy(PATROL_GRAPH),
    )
    ai.state = AIState.ATTACK

    ai._step_attack()

    assert ai.location in graph[4]
    assert ai.location != 10


def test_vent_dwell_outlasts_seal_closing_time():
    ai = AlgemAI(
        copy.deepcopy(BASE_GRAPH),
        night=5,
        start_node=10,
        patrol_graph=copy.deepcopy(PATROL_GRAPH),
    )
    ai.state = AIState.ATTACK
    ai.attention = 100.0
    ai.hack_attraction = 1.0

    assert ai._compute_interval(hour=5) >= 420


def test_entering_vent_immediately_starts_reaction_window():
    ai = AlgemAI(
        copy.deepcopy(BASE_GRAPH),
        night=5,
        start_node=4,
        patrol_graph=copy.deepcopy(PATROL_GRAPH),
    )
    ai.state = AIState.ATTACK
    ai._move_timer = 60

    ai._move_to(11)

    assert ai.location == 11
    assert ai._move_timer >= 60
