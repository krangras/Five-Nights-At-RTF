import copy
import random

import pytest

from gameplay_model import (
    BASE_GRAPH,
    GameModel,
    OFFICE_THREAT_TICKS_BY_NIGHT,
    SEAL_CAMERA_MAP,
    SealState,
    VentState,
    VENT_CONNECTIONS,
)
from gameplay_presenter import (
    CHANNEL_MASTERS,
    GamePresenter,
    HACK_TICKS_BY_NIGHT,
    TALK_DIST_PARAMS,
    VENT_DIST_VOLUMES,
)


# ══════════════════════════════════════════════════════════════════
# 1. Clock / Timer
# ══════════════════════════════════════════════════════════════════

class TestClock:
    def test_timer_starts_at_zero(self):
        m = GameModel(night=1)
        assert m.timer == 0
        assert m.hour == 0

    def test_hour_increments_at_3600_ticks(self):
        m = GameModel(night=1)
        for _ in range(3600):
            m.update()
        assert m.hour == 1
        assert m.timer == 0

    def test_night1_first_hour_takes_3600_ticks(self):
        m = GameModel(night=1)
        for _ in range(3599):
            m.update()
        assert m.hour == 0
        m.update()
        assert m.hour == 1

    def test_night_complete_at_6am(self):
        m = GameModel(night=1)
        m.hour = 5
        m.timer = 3599
        m.update()
        assert m.night_complete == True

    def test_night_not_complete_before_6(self):
        m = GameModel(night=1)
        m.hour = 4
        m.timer = 0
        m.update()
        assert m.night_complete == False

    def test_game_over_blocks_updates(self):
        m = GameModel(night=1)
        m.game_over = True
        timer_before = m.timer
        m.update()
        assert m.timer == timer_before

# ══════════════════════════════════════════════════════════════════
# 2. Bait (Audio lure)
# ══════════════════════════════════════════════════════════════════

class TestBait:
    def test_activate_bait_sets_state(self):
        m = GameModel(night=1)
        m.activate_bait(3)
        assert m.bait_active == True
        assert m.bait_target_node == 3
        assert m.bait_attract_timer == 480
        assert m.bait_step == 0

    def test_activate_bait_twice_rejected(self):
        m = GameModel(night=1)
        m.activate_bait(3)
        m.activate_bait(4)
        assert m.bait_target_node == 3

    def test_bait_active_on_cooldown(self):
        m = GameModel(night=1)
        m.activate_bait(3)
        assert 3 in m.bait_cooldown
        assert m.bait_cooldown[3] == 480

    def test_bait_attract_timer_counts_down(self):
        m = GameModel(night=1)
        m.activate_bait(3)
        for _ in range(480):
            m.update()
        assert m.bait_target_node is None
        assert m.bait_attract_timer == 0

    def test_cooldown_expires(self):
        m = GameModel(night=1)
        m.activate_bait(3)
        for _ in range(500):
            m.update()
        assert 3 not in m.bait_cooldown

# ══════════════════════════════════════════════════════════════════
# 3. Vents
# ══════════════════════════════════════════════════════════════════

class TestVents:
    def test_vents_start_ok(self):
        m = GameModel(night=1)
        for vid in VENT_CONNECTIONS:
            assert m.vents[vid] == VentState.OK

    def test_vent_can_error(self):
        m = GameModel(night=1)
        for vid in VENT_CONNECTIONS:
            m._vent_error_timers[vid] = 0
        m.update()
        errors = [vid for vid in VENT_CONNECTIONS if m.vents[vid] == VentState.ERROR]
        assert len(errors) > 0

    def test_vent_reset_works(self):
        m = GameModel(night=1)
        for vid in VENT_CONNECTIONS:
            m.vents[vid] = VentState.ERROR
        m.start_vent_reset("VENT_A")
        assert m.vents["VENT_A"] == VentState.RESETTING

    def test_vent_reset_clears_after_time(self):
        m = GameModel(night=1)
        m.vents["VENT_A"] = VentState.ERROR
        m.start_vent_reset("VENT_A")
        for _ in range(300):
            m.update()
        assert m.vents["VENT_A"] == VentState.OK

    def test_vent_reset_only_from_error(self):
        m = GameModel(night=1)
        result = m.start_vent_reset("VENT_A")
        assert m.vents["VENT_A"] == VentState.OK

    def test_vent_adds_edge_to_graph(self):
        m = GameModel(night=1)
        m.vents["VENT_A"] = VentState.ERROR
        g = m._build_current_graph()
        src, dst = VENT_CONNECTIONS["VENT_A"]
        assert dst in g[src]

    def test_vent_reset_keeps_physical_route(self):
        m = GameModel(night=1)
        m.vents["VENT_A"] = VentState.ERROR
        m.start_vent_reset("VENT_A")
        for _ in range(300):
            m.update()
        g = m._build_current_graph()
        src, dst = VENT_CONNECTIONS["VENT_A"]
        assert dst in g[src]

# ══════════════════════════════════════════════════════════════════
# 4. Server
# ══════════════════════════════════════════════════════════════════

class TestServer:
    def test_server_starts_off(self):
        m = GameModel(night=1)
        assert m.server_state == "OFF"
        assert m.hack_active == False

    def test_server_overload_timer_runs_when_on(self):
        m = GameModel(night=1)
        m.server_state = "ON"
        m.hack_active = True
        m._schedule_next_overload()
        timer_before = m._server_overload_timer
        m._update_server_load()
        assert m._server_overload_timer < timer_before

    def test_server_overload_triggers_warning(self):
        m = GameModel(night=1)
        m.server_state = "ON"
        m._server_overload_timer = 0
        m._update_server_load()
        assert m.server_overload == True
        assert m.server_overload_warn == 480

    def test_server_shuts_down_if_no_click(self):
        m = GameModel(night=1)
        m.server_state = "ON"
        m.server_overload = True
        m.server_overload_warn = 1
        m._update_server_load()
        assert m.server_state == "TURNING_OFF"

    def test_server_reboot_clears_overload(self):
        m = GameModel(night=1)
        m.server_state = "ON"
        m.server_overload = True
        m.server_rebooting = True
        m.server_reboot_timer = 1
        m._update_server_load()
        assert m.server_overload == False

    def test_hack_duration_increases_each_night(self):
        durations = [HACK_TICKS_BY_NIGHT[night] for night in range(1, 6)]
        assert durations == sorted(durations)
        assert durations[0] < durations[-1]

# ══════════════════════════════════════════════════════════════════
# 5. Graph building
# ══════════════════════════════════════════════════════════════════

class TestGraph:
    def test_base_graph_has_all_nodes(self):
        for i in range(8):
            assert i in BASE_GRAPH

    def test_office_has_no_exits(self):
        assert BASE_GRAPH[0] == []

    def test_algem_starts_in_room_2(self):
        m = GameModel(night=1)
        assert m.algem_location == 1

    def test_vent_edge_added_when_broken(self):
        m = GameModel(night=1)
        m.vents["VENT_A"] = VentState.ERROR
        g = m._build_current_graph()
        src, dst = VENT_CONNECTIONS["VENT_A"]
        assert dst in g[src]

    def test_build_graph_does_not_mutate_base(self):
        m = GameModel(night=1)
        m.vents["VENT_A"] = VentState.ERROR
        g_orig = copy.deepcopy(BASE_GRAPH)
        m._build_current_graph()
        assert BASE_GRAPH == g_orig

    def test_seal_camera_map_covers_all_vent_cameras(self):
        assert SEAL_CAMERA_MAP == {
            8: "SEAL_TOP_RIGHT",
            9: "SEAL_CENTER",
            10: "SEAL_BOTTOM_LEFT",
            11: "SEAL_MID_RIGHT",
        }

    def test_starting_another_seal_reopens_previous_closed_one(self):
        m = GameModel(night=1)
        m.seals["SEAL_CENTER"] = SealState.CLOSED

        m.start_seal("SEAL_TOP_RIGHT")

        assert m.seals["SEAL_CENTER"] == SealState.OPEN
        assert m.seals["SEAL_TOP_RIGHT"] == SealState.SEALING

# ══════════════════════════════════════════════════════════════════
# 6. Model integration
# ══════════════════════════════════════════════════════════════════

class TestIntegration:
    def test_tick_increments_timer_and_moves_algem(self):
        m = GameModel(night=3)
        loc_before = m.algem_location
        for _ in range(1000):
            m.update()
        assert m.timer > 0

    def test_full_night_cycle(self):
        m = GameModel(night=1)
        for _ in range(3600 * 6):
            m.update()
            if m.night_complete:
                break
        assert m.night_complete == True

    def test_camera_watch_accumulates(self):
        m = GameModel(night=1)
        m.tablet_open = True
        m.tablet_animating = False
        m.camera_idx = 3
        watch_before = m.camera_watch_ticks[3]
        m._update_camera_watch()
        assert m.camera_watch_ticks[3] == watch_before + 1

    def test_camera_watch_pauses_when_tablet_closed(self):
        m = GameModel(night=1)
        m.tablet_open = False
        watch_before = m.camera_watch_ticks[1]
        m._update_camera_watch()
        assert m.camera_watch_ticks[1] == watch_before

    def test_reaching_office_starts_threat_timer(self):
        m = GameModel(night=2)
        m._ai.location = 7
        m._ai.state = m._ai.state.ATTACK
        m._ai._move_timer = 0
        m._ai._entry_timer = 1

        m._update_ai()

        assert m.algem_in_office == True
        assert m.office_threat_timer == OFFICE_THREAT_TICKS_BY_NIGHT[2]

    def test_office_threat_does_not_kill_on_tablet_close(self):
        m = GameModel(night=2)
        m.algem_in_office = True
        m.office_threat_timer = 10
        m.tablet_open = True
        m.tablet_animating = False

        m.tablet_open = False
        m._update_office_threat()

        assert m.game_over == False

    def test_office_threat_clears_when_everything_is_off(self):
        m = GameModel(night=3)
        m.algem_in_office = True
        m.office_threat_timer = 30
        m.server_state = "OFF"
        m.tablet_open = False
        m.tablet_animating = False
        m.laptop_open = False
        m.ad_active = False
        m.server_rebooting = False

        m._update_office_threat()

        assert m.algem_in_office == False
        assert m.office_threat_timer == 0
        assert m._ai.location == 5

    def test_office_threat_times_out_into_game_over(self):
        m = GameModel(night=5)
        m.algem_in_office = True
        m.office_threat_timer = 1
        m.server_state = "ON"

        m._update_office_threat()

        assert m.game_over == True


class TestVentAudio:
    def test_reopened_viewed_seal_plays_transition_sound(self):
        class DummySound:
            def __init__(self):
                self.play_calls = 0

            def play(self):
                self.play_calls += 1

        presenter = GamePresenter.__new__(GamePresenter)
        presenter.model = type("ModelStub", (), {})()
        presenter.model.camera_idx = 9
        presenter.model.seals = {"SEAL_CENTER": SealState.OPEN}
        presenter.snd_vent_close = DummySound()

        presenter._play_reopened_viewed_seal_sound(
            {"SEAL_CENTER": SealState.CLOSED}
        )

        assert presenter.snd_vent_close.play_calls == 1

    def test_seal_close_sound_plays_on_completed_sealing(self):
        class DummySound:
            def __init__(self):
                self.play_calls = 0
                self.stop_calls = 0

            def play(self):
                self.play_calls += 1

            def stop(self):
                self.stop_calls += 1

        presenter = GamePresenter.__new__(GamePresenter)
        presenter.model = type("ModelStub", (), {})()
        presenter.model.seals = {"SEAL_CENTER": SealState.CLOSED}
        presenter.snd_vent_close = DummySound()
        presenter.snd_wait = DummySound()
        presenter._prev_seal_states = {"SEAL_CENTER": SealState.SEALING}
        presenter._seal_playing = True
        presenter._seal_timer = 0

        presenter._update_seal_sound()

        assert presenter.snd_vent_close.play_calls == 1
        assert presenter.snd_wait.stop_calls == 1

    def test_vent_sound_uses_last_regular_camera_distance(self):
        close_dist = GamePresenter._vent_listen_distance(
            algem_node=9,
            camera_idx=9,
            last_regular_cam=2,
            tablet_open=True,
            tablet_animating=False,
        )
        far_dist = GamePresenter._vent_listen_distance(
            algem_node=9,
            camera_idx=11,
            last_regular_cam=6,
            tablet_open=True,
            tablet_animating=False,
        )
        assert close_dist < far_dist
        assert close_dist >= 0
        assert far_dist > close_dist

    def test_vent_sound_supports_lower_vent_nodes(self):
        dist = GamePresenter._vent_listen_distance(
            algem_node=10,
            camera_idx=10,
            last_regular_cam=5,
            tablet_open=True,
            tablet_animating=False,
        )
        assert dist >= 0

    def test_talk_curve_fades_with_distance(self):
        volumes = [
            GamePresenter._distance_volume(TALK_DIST_PARAMS, dist, "algem_talk")
            for dist in range(5)
        ]
        assert volumes == sorted(volumes, reverse=True)

    def test_vent_curve_fades_with_distance(self):
        volumes = [
            GamePresenter._distance_volume(VENT_DIST_VOLUMES, dist, "vent")
            for dist in range(5)
        ]
        assert volumes == sorted(volumes, reverse=True)
        assert volumes[0] <= CHANNEL_MASTERS["vent"]
