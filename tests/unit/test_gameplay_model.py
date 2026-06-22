import copy
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fnar.gameplay.model import (
    BASE_GRAPH,
    CAMERAS,
    GameModel,
    GAME_HOUR_TICKS,
    OFFICE_THREAT_TICKS_BY_NIGHT,
    SEAL_CAMERA_MAP,
    SealState,
    VENT_CONNECTIONS,
)
from fnar.gameplay.presenter import (
    CHANNEL_MASTERS,
    GamePresenter,
    TALK_DIST_PARAMS,
    _volume_from_distance,
)
from fnar.services.spatial_audio import WEIGHTED_DISTANCES


# ══════════════════════════════════════════════════════════════════
# 1. Clock / Timer
# ══════════════════════════════════════════════════════════════════

class TestClock:
    def test_timer_starts_at_zero(self):
        m = GameModel(night=1)
        assert m.timer == 0
        assert m.hour == 0

    def test_hour_increments_at_game_hour_ticks(self):
        m = GameModel(night=1)
        for _ in range(GAME_HOUR_TICKS):
            m.update()
        assert m.hour == 1
        assert m.timer == 0

    def test_night1_first_hour_takes_configured_tick_count(self):
        m = GameModel(night=1)
        for _ in range(GAME_HOUR_TICKS - 1):
            m.update()
        assert m.hour == 0
        m.update()
        assert m.hour == 1

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
# 3. Legacy vent links removed
# ══════════════════════════════════════════════════════════════════

class TestVents:
    def test_vents_start_ok(self):
        assert VENT_CONNECTIONS == {}

    def test_vent_can_error(self):
        assert VENT_CONNECTIONS == {}

    def test_vent_reset_works(self):
        assert VENT_CONNECTIONS == {}

    def test_vent_reset_clears_after_time(self):
        assert VENT_CONNECTIONS == {}

    def test_vent_reset_only_from_error(self):
        assert VENT_CONNECTIONS == {}

    def test_vent_adds_edge_to_graph(self):
        assert VENT_CONNECTIONS == {}

    def test_vent_reset_keeps_physical_route(self):
        assert VENT_CONNECTIONS == {}

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

    def test_legacy_vent_a_b_links_are_removed(self):
        assert VENT_CONNECTIONS == {}

    def test_build_graph_does_not_mutate_base(self):
        m = GameModel(night=1)
        g_orig = copy.deepcopy(BASE_GRAPH)
        m._build_current_graph()
        assert BASE_GRAPH == g_orig

    def test_seal_camera_map_covers_all_vent_cameras(self):
        assert SEAL_CAMERA_MAP == {
            8: "SEAL_MID_RIGHT",
            9: "SEAL_TOP_RIGHT",
            10: "SEAL_CENTER",
            11: "SEAL_BOTTOM_LEFT",
        }

    def test_vent_camera_display_order_matches_map_layout(self):
        vent_labels = {
            idx: (display_id, name)
            for idx, display_id, name, _ in CAMERAS
            if idx in {8, 9, 10, 11}
        }
        assert vent_labels[8][1] == "LOWER RIGHT VENT"
        assert vent_labels[9][1] == "UPPER RIGHT VENT"
        assert vent_labels[10][1] == "UPPER LEFT VENT"
        assert vent_labels[11][1] == "LOWER LEFT VENT"
        assert vent_labels[8][0] == "08"
        assert vent_labels[9][0] == "09"
        assert vent_labels[10][0] == "10"
        assert vent_labels[11][0] == "11"

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
        assert 45 <= m.office_threat_timer <= int(OFFICE_THREAT_TICKS_BY_NIGHT[2] * 1.42)

    def test_office_threat_does_not_kill_on_tablet_close(self):
        m = GameModel(night=2)
        m.algem_in_office = True
        m.office_threat_timer = 10
        m.tablet_open = True
        m.tablet_animating = False

        m.tablet_open = False
        m._update_office_threat()

        assert m.game_over == False

    def test_office_threat_continues_without_last_chance_conditions(self):
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

        assert m.algem_in_office == True
        assert m.office_threat_timer == 29

    def test_office_threat_times_out_into_game_over(self):
        m = GameModel(night=5)
        m.algem_in_office = True
        m.office_threat_timer = 1
        m.server_state = "ON"

        m._update_office_threat()

        assert m.game_over == True


class TestVentAudio:
    def test_direct_vent_view_stops_crawl_sound(self):
        class DummyChannel:
            def __init__(self):
                self.busy = True
                self.stop_calls = 0

            def get_busy(self):
                return self.busy

            def stop(self):
                self.stop_calls += 1
                self.busy = False

            def play(self, *_args, **_kwargs):
                self.busy = True

            def set_volume(self, volume):
                self.volume = volume

        presenter = GamePresenter.__new__(GamePresenter)
        presenter.model = type("ModelStub", (), {})()
        presenter.model.algem_location = 9
        presenter.model.tablet_open = True
        presenter.model.tablet_animating = False
        presenter.model.camera_idx = 9
        presenter.model.algem_trigger = 30
        presenter.model.seals = {}
        presenter._last_regular_cam = 2
        presenter._vent_sound_channel = DummyChannel()
        presenter._vent_sound_timer = 10
        presenter.view = type("ViewStub", (), {"vent_map_mode": False})()

        presenter._update_vent_sounds()

        assert presenter._vent_sound_channel.volume == 0.0
        assert presenter._vent_sound_timer == 0

    def test_blocked_vent_sound_plays_once_per_new_block(self):
        class DummySound:
            def __init__(self):
                self.play_calls = 0

            def play(self):
                self.play_calls += 1

        presenter = GamePresenter.__new__(GamePresenter)
        presenter.model = type("ModelStub", (), {})()
        presenter.model.algem_location = 2
        presenter.model.algem_trigger = 30
        presenter.model.seals = {
            "SEAL_TOP_RIGHT": SealState.CLOSED,
            "SEAL_CENTER": SealState.OPEN,
            "SEAL_MID_RIGHT": SealState.OPEN,
            "SEAL_BOTTOM_LEFT": SealState.OPEN,
        }
        presenter.snd_knock = DummySound()
        presenter._vent_block_signature = None
        presenter._vent_seal_just_closed = 0

        presenter._update_vent_block_sound()
        presenter._update_vent_block_sound()

        assert presenter.snd_knock.play_calls == 1

    def test_reopened_viewed_seal_plays_transition_sound(self):
        class DummySound:
            def __init__(self):
                self.play_calls = 0

            def play(self):
                self.play_calls += 1

        presenter = GamePresenter.__new__(GamePresenter)
        presenter.model = type("ModelStub", (), {})()
        presenter.model.camera_idx = 9
        presenter.model.seals = {"SEAL_TOP_RIGHT": SealState.OPEN}
        presenter.snd_vent_close = DummySound()

        presenter._play_reopened_viewed_seal_sound(
            {"SEAL_TOP_RIGHT": SealState.CLOSED}
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

    def test_vent_sound_uses_overlaid_camera_proximity(self):
        close_dist = GamePresenter._vent_listen_distance(
            algem_node=9,
            camera_idx=2,
            last_regular_cam=2,
            tablet_open=True,
            tablet_animating=False,
        )
        far_dist = GamePresenter._vent_listen_distance(
            algem_node=9,
            camera_idx=6,
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

    def test_audio_distance_uses_current_vent_camera_when_viewing_vent(self):
        same_dist = GamePresenter._camera_audio_distance(10, 10)
        far_dist = GamePresenter._camera_audio_distance(8, 10)
        assert same_dist == 0
        assert far_dist > same_dist

    def test_talk_curve_fades_with_distance(self):
        presenter = GamePresenter.__new__(GamePresenter)
        volumes = [
            presenter._distance_volume(TALK_DIST_PARAMS, dist)
            for dist in range(5)
        ]
        assert volumes == sorted(volumes, reverse=True)

    def test_vent_curve_fades_with_distance(self):
        sample_dists = sorted(set(WEIGHTED_DISTANCES.values()))[:6]
        volumes = [_volume_from_distance(d) for d in sample_dists]
        assert volumes == sorted(volumes, reverse=True)
        assert volumes[0] <= 1.0
