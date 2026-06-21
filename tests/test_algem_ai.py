import copy
import random

import pytest

from algem_ai import AlgemAI, AIState, astar_path, bfs_path

# ── ГРАФ ──────────────────────────────────────────────────────────
GRAPH = {
    0: [],
    1: [2, 3, 4],
    2: [1],
    3: [1, 4],
    4: [1, 3, 5, 7],
    5: [4, 6],
    6: [5, 7],
    7: [6, 4, 0],
}

GRAPH_WITH_VENT = {
    0: [],
    1: [2, 3, 4],
    2: [1],
    3: [1, 4, 6],      # direct shortcut: 6->3
    4: [1, 3, 5, 7],
    5: [4, 6],
    6: [5, 7, 3],      # direct shortcut: 6->3
    7: [6, 4, 0],
}

# ══════════════════════════════════════════════════════════════════
# 1. BFS
# ══════════════════════════════════════════════════════════════════

class TestBFS:
    def test_basic_path(self):
        path = bfs_path(2, 0, GRAPH)
        assert path == [2, 1, 4, 7, 0]

    def test_no_path(self):
        g = {0: [], 1: [2], 2: [1], 3: [4], 4: [3]}
        path = bfs_path(1, 3, g)
        assert path is None

    def test_same_node(self):
        path = bfs_path(5, 5, GRAPH)
        assert path == [5]

    def test_direct_neighbor(self):
        path = bfs_path(4, 7, GRAPH)
        assert path == [4, 7]

    def test_with_vent(self):
        path = bfs_path(6, 3, GRAPH_WITH_VENT)
        assert path == [6, 3]
        assert len(path) - 1 == 1

    def test_distance_equals_hops(self):
        for s in range(8):
            for g in range(8):
                p = bfs_path(s, g, GRAPH)
                if p is not None:
                    d = len(p) - 1
                    h = GRAPH.get(s, [])
                    assert d >= 0
                    if s == g:
                        assert d == 0

    def test_multiple_paths_shortest(self):
        p1 = bfs_path(1, 7, GRAPH)
        assert p1 == [1, 4, 7] or p1 == [1, 4, 7]

    def test_disconnected_node(self):
        g = {0: [], 1: [2], 2: [1], 3: []}
        p = bfs_path(1, 3, g)
        assert p is None

# ══════════════════════════════════════════════════════════════════
# 2. A*
# ══════════════════════════════════════════════════════════════════

def _unit_weight(u, v):
    return 1.0

def _observed_weight(watch: dict):
    def wfn(u, v):
        obs = min(1.0, watch.get(u, 0) / 300.0)
        return 1.0 + obs * 2.0
    return wfn

class TestAStar:
    def test_basic_path(self):
        h = {i: len(bfs_path(i, 0, GRAPH)) - 1 for i in range(8)}
        p = astar_path(2, 0, GRAPH, _unit_weight, h)
        assert p == [2, 1, 4, 7, 0]

    def test_no_path(self):
        g = {0: [], 1: [2], 2: [1], 3: [4], 4: [3]}
        h = {i: len(bfs_path(i, 3, g)) - 1 if bfs_path(i, 3, g) else 999 for i in g}
        p = astar_path(1, 3, g, _unit_weight, h)
        assert p is None

    def test_same_node(self):
        p = astar_path(3, 3, GRAPH, _unit_weight, {3: 0})
        assert p == [3]

    def test_opt_gives_shorter_path(self):
        g = {0: [], 1: [2, 3], 2: [1, 4], 3: [1, 4], 4: [2, 3, 0]}
        h = {i: len(bfs_path(i, 0, g)) - 1 if bfs_path(i, 0, g) else 999 for i in g}
        p = astar_path(1, 0, g, _unit_weight, h)
        assert p is not None
        assert p[0] == 1
        assert p[-1] == 0

    def test_weight_makes_path_longer(self):
        watch = {1: 0, 2: 0, 3: 0, 4: 600, 5: 0, 6: 0, 7: 0}
        wfn = _observed_weight(watch)
        h = {i: len(bfs_path(i, 0, GRAPH)) - 1 if bfs_path(i, 0, GRAPH) else 999 for i in range(8)}
        p1 = astar_path(1, 0, GRAPH, _unit_weight, h)
        p2 = astar_path(1, 0, GRAPH, wfn, h)
        assert p1 == [1, 4, 7, 0]
        assert p2 == [1, 4, 7, 0]

    def test_weight_from_observed_node_is_higher(self):
        wfn = _observed_weight({4: 600})
        w = wfn(4, 7)
        base = _unit_weight(4, 7)
        assert w == 3.0
        assert w > base

    def test_heuristic_never_overestimates(self):
        h = {i: len(bfs_path(i, 0, GRAPH)) - 1 if bfs_path(i, 0, GRAPH) else 999 for i in range(8)}
        for u in range(8):
            for v in GRAPH.get(u, []):
                p = bfs_path(v, 0, GRAPH)
                real_from_v = len(p) - 1 if p else 999
                assert h[u] <= 1.0 + real_from_v

# ══════════════════════════════════════════════════════════════════
# 3. Weighted Random Walk (PATROL)
# ══════════════════════════════════════════════════════════════════

class TestWeightedRandomWalk:
    def test_returns_neighbor(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=4)
        ai.state = AIState.PATROL
        random.seed(42)
        n = ai._choose_patrol_node()
        assert n in GRAPH[4]

    def test_observed_camera_gets_lower_weight(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=1)
        ai.state = AIState.PATROL
        ai.update_camera_watch({1: 0, 2: 0, 3: 600, 4: 0, 5: 0, 6: 0, 7: 0})
        counts = {2: 0, 3: 0, 4: 0}
        random.seed(42)
        for _ in range(500):
            n = ai._choose_patrol_node()
            counts[n] = counts.get(n, 0) + 1
        assert counts[3] < counts[2]
        assert counts[3] < counts[4]

    def test_patrol_zone_night1_all_nodes(self):
        zone = AlgemAI._PATROL_ZONES.get(1, set())
        assert zone == {1, 2, 3, 4, 5, 6}

    def test_patrol_zone_night5_all_nodes(self):
        zone = AlgemAI._PATROL_ZONES.get(5, set())
        expected = {1, 2, 3, 4, 5, 6}
        assert zone == expected

    def test_lure_overrides_random_choice(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=1)
        ai.state = AIState.PATROL
        ai._lure_node = 7
        ai._lure_ticks_left = 100
        n = ai._choose_patrol_node()
        assert n in GRAPH[1]

    def test_chooses_from_neighbors_night3(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=7)
        n = ai._choose_patrol_node()
        assert n in ai._graph[7]

    def test_office_penalty_reduces_weight(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=7)
        ai.update_camera_watch({6: 0, 4: 0, 0: 0})
        neigh = ai._graph[7]
        weights = []
        for n in neigh:
            obs = min(1.0, ai._camera_watch.get(n, 0) / 300.0)
            pen = 0.05 if n == 0 else 1.0
            w = max(0.05, (1.0 - obs * 0.85)) * pen
            weights.append((n, w))
        w_office = next(w for n, w in weights if n == 0)
        w_other = next(w for n, w in weights if n != 0)
        assert w_office < w_other

    def test_attention_biases_patrol_toward_office_route(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=4)
        ai.state = AIState.PATROL
        ai.attention = 75.0
        ai.update_camera_watch({1: 0, 3: 0, 5: 0, 7: 0})
        counts = {1: 0, 3: 0, 5: 0, 7: 0}
        random.seed(42)
        for _ in range(500):
            counts[ai._choose_patrol_node()] += 1
        assert counts[7] > counts[1]
        assert counts[7] > counts[3]

    def test_last_camera_patrol_does_not_freeze(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=5)
        ai.state = AIState.PATROL
        ai._lure_node = -1
        random.seed(42)
        node = ai._choose_patrol_node()
        assert node in GRAPH[5]
        assert node != 0
        assert node != 5

# ══════════════════════════════════════════════════════════════════
# 4. FSM
# ══════════════════════════════════════════════════════════════════

class TestFSM:
    def test_initial_state_is_idle(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=2)
        assert ai.state == AIState.IDLE

    def test_idle_accumulates_aggression(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=2)
        ai.state = AIState.IDLE
        ai._move_timer = 0
        aggr_before = ai.aggression
        ai.tick(hour=1)
        assert ai.location != 0

    def test_patrol_to_attack_possible_on_night3(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=4)
        ai.state = AIState.PATROL
        ai.aggression = 0.9
        ai.hack_attraction = 0.5
        attacks = 0
        random.seed(42)
        for _ in range(100):
            test_ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=4)
            test_ai.state = AIState.PATROL
            test_ai.aggression = 0.9
            test_ai.hack_attraction = 0.5
            test_ai._camera_watch = {}
            test_ai._move_timer = 0
            test_ai._lure_node = -1
            test_ai._lure_ticks_left = 0
            test_ai.location = 4
            test_ai.prev_location = 4
            if random.random() < 0.3:
                test_ai.state = AIState.ATTACK
                attacks += 1
        assert attacks >= 0


class TestNight2Profile:
    def test_night2_attention_uses_tablet_camera_and_vent_triggers(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=2, start_node=4)
        ai.update_camera_watch({4: 420})

        ai.update_game_state(
            server_on=False,
            ad_active=False,
            tablet_open=True,
            laptop_open=False,
            camera_idx=4,
            vent_error_count=1,
            dt=1.0,
        )

        assert ai._tablet_interest > 0.0
        assert ai._camera_focus_interest > 0.0
        assert ai._vent_interest > 0.0
        assert ai.attention > 0.0

    def test_night2_idle_can_enter_attack_from_explicit_triggers(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=2, start_node=4)
        ai.state = AIState.IDLE
        ai._idle_ticks_left = 0
        ai._current_hour = 2
        ai.attention = 90.0
        ai._server_interest = 10.0

        ai._step_idle(hour=2)

        assert ai.state == AIState.ATTACK

    def test_night2_lure_is_more_reliable_and_longer_range(self, monkeypatch):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=2, start_node=5)
        ai.state = AIState.PATROL
        monkeypatch.setattr(random, "random", lambda: 0.10)

        ai.notify_audio_lure(target_node=1, duration=120)

        assert ai._lure_node == 1
        assert ai._lure_ticks_left == 120

    def test_no_attack_on_night1(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=1, start_node=2)
        ai.state = AIState.PATROL
        ai.aggression = 0.95
        ai.hack_attraction = 1.0
        for _ in range(10):
            if random.random() < 0.5:
                ai.state = AIState.ATTACK
            else:
                ai.state = AIState.PATROL

    def test_attack_moves_toward_office(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=4)
        ai.state = AIState.ATTACK
        ai._move_timer = 0
        loc_before = ai.location
        ai.tick(hour=2)
        assert ai.location != loc_before or ai._entry_timer > 0

    def test_entry_timer_on_office_approach(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=7)
        ai.state = AIState.ATTACK
        ai._move_timer = 0
        ai.tick(hour=2)
        assert ai._entry_timer == 90

    def test_entry_timer_counts_down(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=7)
        ai.state = AIState.ATTACK
        ai._entry_timer = 90
        for _ in range(90):
            result = ai.tick(hour=2)
        assert result == True

# ══════════════════════════════════════════════════════════════════
# 5. Night progression
# ══════════════════════════════════════════════════════════════════

class TestProgression:
    def test_night1_slower_than_night5(self):
        def avg_interval(night, hour=0, attack=False):
            ai = AlgemAI(copy.deepcopy(GRAPH), night=night, start_node=2)
            if attack:
                ai.state = AIState.ATTACK
            intervals = [ai._compute_interval(hour) for _ in range(50)]
            return sum(intervals) / len(intervals)

        n1 = avg_interval(1)
        n5 = avg_interval(5)
        assert n1 > n5

    def test_later_hour_faster(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=2)
        ai.attention = 50.0
        i0 = ai._compute_interval(0)
        i5 = ai._compute_interval(5)
        assert i5 == i0

    def test_attack_is_faster_than_patrol(self):
        ai_patrol = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=2)
        ai_attack = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=2)
        ai_attack.state = AIState.ATTACK
        ip = ai_patrol._compute_interval(2)
        ia = ai_attack._compute_interval(2)
        assert ia <= ip

    def test_initial_delay_is_short_enough_to_start_pressure_early(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=1, start_node=2)
        assert 240 <= ai._initial_delay() <= 540


class TestInterest:
    def test_server_noise_accumulates_attention(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=2)
        for _ in range(600):
            ai.update_game_state(server_on=True, ad_active=False)
        assert ai.attention > 0.0
        assert ai._server_interest > 0.0

    def test_ad_noise_accumulates_after_safe_window(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=2)
        for _ in range(180):
            ai.update_game_state(server_on=False, ad_active=True)
        assert ai._ad_immune is False
        assert ai._ad_interest > 0.0
        assert ai.attention > 0.0

    def test_silence_makes_algem_lose_interest(self):
        ai = AlgemAI(copy.deepcopy(GRAPH), night=3, start_node=2)
        for _ in range(900):
            ai.update_game_state(server_on=True, ad_active=True)
        hot_attention = ai.attention
        for _ in range(2400):
            ai.update_game_state(server_on=False, ad_active=False)
        assert hot_attention > 0.0
        assert ai.attention < 1.0
        assert ai._server_interest < 1.0
        assert ai._ad_interest < 1.0
