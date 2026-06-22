"""Distance-aware ventilation, seal, retreat, and danger audio."""

import random

from .camera_graph import BASE_GRAPH, SEAL_CAMERA_MAP, VENT_CAMERAS, VENT_SEALS
from .gameplay_audio import SOUND_BASE_VOLUMES
from .model import SealState
from fnar.services.spatial_audio import (
    AUDIO_CLOSED_RETREAT_GAIN,
    AUDIO_CLOSED_SOURCE_GAIN,
    AUDIO_OFFICE_FLOOR,
    AUDIO_SEALING_SOURCE_GAIN,
    AUDIO_UNREACHABLE_DISTANCE,
    AUDIO_VENT_MAP_GAIN,
    BASE_AUDIO_GRAPH,
    _bucket_from_weighted_distance,
    _weighted_audio_distance,
)


DANGER_CAMERA_NODE = 7


class VentAudioControllerMixin:
    """Present ventilation threats through the dedicated audio channels."""

    def _update_vent_sounds(self) -> None:
        loc = self.model.algem_location
        vent_motion_ticks = self.model.algem_vent_motion_ticks
        source_node = self.model.algem_vent_audio_source
        forced_retreat = False

        if self._closed_vent_retreat_timer > 0:
            self._closed_vent_retreat_timer -= 1
            if self._closed_vent_retreat_source in VENT_CAMERAS:
                source_node = self._closed_vent_retreat_source
                forced_retreat = True
            if self._closed_vent_retreat_timer <= 0:
                self._closed_vent_retreat_source = -1

        if source_node not in VENT_CAMERAS and loc in VENT_CAMERAS:
            source_node = loc

        seal_id = SEAL_CAMERA_MAP.get(source_node) if source_node in VENT_CAMERAS else None
        seal_state = self.model.seals.get(seal_id) if seal_id is not None else None
        closed_without_retreat = seal_state == SealState.CLOSED and not forced_retreat
        active = (
            source_node in VENT_CAMERAS
            and not closed_without_retreat
            and (forced_retreat or loc in VENT_CAMERAS or vent_motion_ticks > 0)
        )
        direct_vent_view = (
            False if forced_retreat else self._is_any_active_vent_camera_view(source_node)
        )
        target_volume = 0.0

        if direct_vent_view:
            self._vent_sound_source = source_node if source_node in VENT_CAMERAS else -1
            self._vent_sound_volume = 0.0
            if self._vent_sound_channel.get_busy():
                self._vent_sound_channel.set_volume(0.0)
            self._vent_sound_timer = 0
            return

        if active:
            target_volume = self._vent_listen_volume(
                algem_node=source_node,
                camera_idx=self.model.camera_idx,
                last_regular_cam=self._last_regular_cam,
                tablet_open=self.model.tablet_open,
                tablet_animating=self.model.tablet_animating,
            )
            if forced_retreat and seal_state == SealState.CLOSED:
                target_volume *= AUDIO_CLOSED_RETREAT_GAIN
                if self._is_direct_vent_camera_view(source_node):
                    target_volume = max(target_volume, self._apply_channel_volume(0.18, "vent"))

        if target_volume > 0.0:
            if self._vent_sound_source != source_node and self._vent_sound_channel.get_busy():
                self._vent_sound_channel.stop()
                self._vent_sound_volume = 0.0
            self._vent_sound_source = source_node
            if not self._vent_sound_channel.get_busy():
                if not self._vent_sounds:
                    return
                self._vent_sound_channel.play(random.choice(self._vent_sounds), loops=-1)
                self._vent_sound_volume = 0.0
            step = 0.050 if target_volume > self._vent_sound_volume else 0.120
            self._vent_sound_volume += max(-step, min(step, target_volume - self._vent_sound_volume))
            self._vent_sound_channel.set_volume(max(0.0, min(1.0, self._vent_sound_volume)))
            return

        if self._vent_sound_channel.get_busy():
            self._vent_sound_volume = max(0.0, self._vent_sound_volume - 0.120)
            if self._vent_sound_volume <= 0.01:
                self._vent_sound_channel.stop()
                self._vent_sound_volume = 0.0
                self._vent_sound_source = -1
            else:
                self._vent_sound_channel.set_volume(self._vent_sound_volume)
        else:
            self._vent_sound_volume = 0.0
            self._vent_sound_source = -1
        self._vent_sound_timer = 0

    def _update_vent_block_sound(self) -> None:
        """Play delayed one-shot knocks from explicit Algem AI events.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        if self._vent_seal_just_closed > 0:
            self._vent_seal_just_closed -= 1
        if not self._pending_vent_knocks:
            return
        remaining: list[tuple[int, int, int]] = []
        leave_source = self.model.algem_last_vent_leave_source
        vent_audio_source = self.model.algem_vent_audio_source
        for item in self._pending_vent_knocks:
            if isinstance(item, tuple):
                timer, vent_node, source_node = item
            else:
                timer, vent_node, source_node = item, -1, -1
            timer -= 1
            if timer <= 0:
                should_skip = bool(
                    vent_node in VENT_CAMERAS
                    and (
                        leave_source == vent_node
                        or (vent_audio_source == vent_node and self.model.algem_location != vent_node)
                        or (
                            self.model.algem_prev_location == vent_node
                            and self.model.algem_location != vent_node
                            and self.model.algem_trigger > 0
                        )
                    )
                )
                if self.snd_knock and not should_skip:
                    self.snd_knock.play()
            else:
                remaining.append((timer, vent_node, source_node))
        self._pending_vent_knocks = remaining

    def _start_closed_vent_retreat_audio(self, vent_node: int) -> None:
        if vent_node not in VENT_CAMERAS:
            return
        self._closed_vent_retreat_source = vent_node
        self._closed_vent_retreat_timer = max(self._closed_vent_retreat_timer, 210)
        if self._vent_sound_source != vent_node and self._vent_sound_channel.get_busy():
            self._vent_sound_channel.stop()
            self._vent_sound_volume = 0.0
        self._vent_sound_source = vent_node

    def _current_audio_distance(self, source_node: int) -> int:
        """Bucket 0..4 from the active listening point to a source node.

        Args:
            source_node: Параметр типа ``int``, используемый методом ``_current_audio_distance``.

        Returns:
            Значение типа ``int``."""
        listener_node = self._current_listener_audio_node()
        return self._camera_audio_distance(listener_node, source_node)

    def _current_audio_volume(self, source_node: int, channel_key: str) -> float:
        """Continuous volume from the active listening point to a source node.

        Args:
            source_node: Параметр типа ``int``, используемый методом ``_current_audio_volume``.
            channel_key: Параметр типа ``str``, используемый методом ``_current_audio_volume``.

        Returns:
            Значение типа ``float``."""
        listener_node = self._current_listener_audio_node()
        dist = self._audio_weighted_distance(listener_node, source_node)
        if listener_node == 0 and source_node != 0:
            base = max(AUDIO_OFFICE_FLOOR, _volume_from_distance(dist))
        elif self._is_vent_map_open():
            base = min(AUDIO_VENT_MAP_GAIN, _volume_from_distance(dist))
        else:
            base = _volume_from_distance(dist)
        if listener_node != source_node:
            base *= self._source_seal_audio_gain(source_node)
        return self._apply_channel_volume(base, channel_key)

    def _current_listener_audio_node(self) -> int:
        return self._listener_audio_node(
            camera_idx=self.model.camera_idx,
            tablet_open=self.model.tablet_open,
            tablet_animating=self.model.tablet_animating,
        )

    def _current_audio_graph(self) -> dict[int, list[int]]:
        return {node: list(neighbors) for node, neighbors in BASE_AUDIO_GRAPH.items()}

    def _source_seal_audio_gain(self, source_node: int) -> float:
        """Return muffling gain for a vent source behind an active seal.

        The seal must not disconnect the source from the diagnostic audio map:
        otherwise every listener gets the same unreachable distance and the
        sandbox appears frozen. A closed/sealing vent should make Algem quieter,
        but nearby cameras still have to be louder than distant cameras.

        Args:
            source_node: Параметр типа ``int``, используемый методом ``_source_seal_audio_gain``.

        Returns:
            Значение типа ``float``."""
        if source_node not in VENT_CAMERAS:
            return 1.0
        seal_id = SEAL_CAMERA_MAP.get(source_node)
        if seal_id is None:
            return 1.0
        state = getattr(self.model, "seals", {}).get(seal_id)
        if state == SealState.SEALING:
            return AUDIO_SEALING_SOURCE_GAIN
        if state == SealState.CLOSED:
            return AUDIO_CLOSED_SOURCE_GAIN
        return 1.0

    def _is_vent_map_open(self) -> bool:
        return bool(
            self.model.tablet_open
            and not self.model.tablet_animating
            and getattr(self.view, "vent_map_mode", False)
        )

    def _is_direct_vent_camera_view(self, source_node: int) -> bool:
        if source_node not in VENT_CAMERAS:
            return False
        return bool(
            self.model.tablet_open
            and not self.model.tablet_animating
            and self.model.camera_idx == source_node
        )

    def _is_any_active_vent_camera_view(self, source_node: int) -> bool:
        if not (
            self.model.tablet_open
            and not self.model.tablet_animating
        ):
            return False
        cam_idx = self.model.camera_idx
        if cam_idx == source_node and source_node in VENT_CAMERAS:
            return True
        if cam_idx == self.model.algem_location and cam_idx in VENT_CAMERAS:
            return True
        if (
            cam_idx == self.model.algem_prev_location
            and cam_idx in VENT_CAMERAS
            and self.model.algem_trigger > 0
        ):
            return True
        if cam_idx == self.model.algem_last_vent_leave_source:
            return True
        return False

    def _suppress_algem_leave_static(self) -> bool:
        cam_idx = self.model.camera_idx
        if cam_idx not in VENT_CAMERAS:
            return False
        seal_id = SEAL_CAMERA_MAP.get(cam_idx)
        seal_state = self.model.seals.get(seal_id) if seal_id is not None else None
        algem_here = cam_idx in (self.model.algem_location, self.model.algem_prev_location)

        return bool(seal_state == SealState.CLOSED and algem_here)

    @staticmethod
    def _listener_audio_node(
        camera_idx: int,
        tablet_open: bool,
        tablet_animating: bool,
    ) -> int:
        if tablet_open and not tablet_animating:
            return camera_idx
        return 0

    @staticmethod
    def _camera_audio_distance(listener_node: int, source_node: int) -> int:
        dist = _weighted_audio_distance(listener_node, source_node, BASE_AUDIO_GRAPH)
        return _bucket_from_weighted_distance(dist)

    def _audio_weighted_distance(self, listener_node: int, source_node: int) -> float:
        return _weighted_audio_distance(listener_node, source_node, self._current_audio_graph())

    @staticmethod
    def _vent_listen_distance(
        algem_node: int,
        camera_idx: int,
        last_regular_cam: int,
        tablet_open: bool,
        tablet_animating: bool,
    ) -> int:
        """Bucketed vent distance kept for demos/tests.

        Args:
            algem_node: Параметр типа ``int``, используемый методом ``_vent_listen_distance``.
            camera_idx: Параметр типа ``int``, используемый методом ``_vent_listen_distance``.
            last_regular_cam: Параметр типа ``int``, используемый методом ``_vent_listen_distance``.
            tablet_open: Параметр типа ``bool``, используемый методом ``_vent_listen_distance``.
            tablet_animating: Параметр типа ``bool``, используемый методом ``_vent_listen_distance``.

        Returns:
            Значение типа ``int``."""
        _ = last_regular_cam
        if algem_node not in VENT_CAMERAS:
            return AUDIO_MAX_BUCKET
        listener_node = GamePresenter._listener_audio_node(
            camera_idx=camera_idx,
            tablet_open=tablet_open,
            tablet_animating=tablet_animating,
        )
        return GamePresenter._camera_audio_distance(listener_node, algem_node)

    def _vent_listen_weighted_distance(
        self,
        algem_node: int,
        camera_idx: int,
        last_regular_cam: int,
        tablet_open: bool,
        tablet_animating: bool,
    ) -> float:
        _ = last_regular_cam
        if algem_node not in VENT_CAMERAS:
            return AUDIO_UNREACHABLE_DISTANCE
        listener_node = self._listener_audio_node(
            camera_idx=camera_idx,
            tablet_open=tablet_open,
            tablet_animating=tablet_animating,
        )
        return self._audio_weighted_distance(listener_node, algem_node)

    def _vent_listen_volume(
        self,
        algem_node: int,
        camera_idx: int,
        last_regular_cam: int,
        tablet_open: bool,
        tablet_animating: bool,
    ) -> float:
        """Continuous vent volume for the current listening mode.

        Args:
            algem_node: Параметр типа ``int``, используемый методом ``_vent_listen_volume``.
            camera_idx: Параметр типа ``int``, используемый методом ``_vent_listen_volume``.
            last_regular_cam: Параметр типа ``int``, используемый методом ``_vent_listen_volume``.
            tablet_open: Параметр типа ``bool``, используемый методом ``_vent_listen_volume``.
            tablet_animating: Параметр типа ``bool``, используемый методом ``_vent_listen_volume``.

        Returns:
            Значение типа ``float``."""
        _ = last_regular_cam
        if algem_node not in VENT_CAMERAS:
            return 0.0
        seal_id = SEAL_CAMERA_MAP.get(algem_node)
        seal_state = self.model.seals.get(seal_id) if seal_id is not None else None
        if (
            tablet_open
            and not tablet_animating
            and camera_idx == algem_node
            and seal_state != SealState.CLOSED
        ):
            return 0.0
        listener_node = self._listener_audio_node(
            camera_idx=camera_idx,
            tablet_open=tablet_open,
            tablet_animating=tablet_animating,
        )
        dist = self._audio_weighted_distance(listener_node, algem_node)
        if not tablet_open or tablet_animating:
            base = max(AUDIO_OFFICE_FLOOR, _volume_from_distance(dist))
        elif self._is_vent_map_open():
            base = min(AUDIO_VENT_MAP_GAIN, _volume_from_distance(dist))
        else:
            base = _volume_from_distance(dist)
        if listener_node != algem_node:
            base *= self._source_seal_audio_gain(algem_node)
        return self._apply_channel_volume(base, "vent")

    def _current_vent_block_signature(self) -> tuple | None:
        """Detect a sealed vent near a moving Algem.

        Args:
            Нет.

        Returns:
            Значение типа ``tuple | None``."""
        blocked_nodes = {
            vent_node
            for seal_id, vent_node in VENT_SEALS.items()
            if self.model.seals.get(seal_id) == SealState.CLOSED
        }
        if not blocked_nodes:
            return None

        loc = self.model.algem_location
        if loc in blocked_nodes:
            return ("inside", loc)

        adjacent_blocked = tuple(
            sorted(node for node in blocked_nodes if node in BASE_GRAPH.get(loc, []))
        )
        if adjacent_blocked:
            return ("adjacent", loc, adjacent_blocked)

        return None

    def _update_danger_sound(self) -> None:
        """Звук danger2b.wav когда Алгем дошёл до честной предофисной камеры.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        on_last = self.model.algem_location == DANGER_CAMERA_NODE
        if on_last and not self._danger_playing:
            if self.snd_danger2b:
                self.snd_danger2b.set_volume(
                    self._mix_volume("danger_loop", SOUND_BASE_VOLUMES["snd_danger2b"])
                )
                self.snd_danger2b.play(-1)
            self._danger_playing = True
        elif not on_last and self._danger_playing:
            if self.snd_danger2b:
                self.snd_danger2b.stop()
            self._danger_playing = False

    def _play_seal_sound(self) -> None:
        """Запустить звук блокировки (сейчас используем snd_wait).

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        if not self._seal_playing and self.snd_wait:
            self._seal_playing = True
            self._seal_timer = 0
            self.snd_wait.play()

    def _play_reopened_viewed_seal_sound(
        self,
        prev_seals: dict[str, SealState],
    ) -> None:
        """Проиграть звук заслонки, если ранее закрытый seal открылся.

        Args:
            prev_seals: Параметр типа ``dict[str, SealState]``, используемый методом ``_play_reopened_viewed_seal_sound``.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        for seal_id, prev_state in prev_seals.items():
            seal_now = self.model.seals.get(seal_id)
            if prev_state == SealState.CLOSED and seal_now == SealState.OPEN:
                self._play_vent_close_sound_for_node(VENT_SEALS.get(seal_id, -1))
                return

    def _play_vent_close_sound_for_node(self, vent_node: int) -> None:
        if not self.snd_vent_close:
            return
        volume = self._current_audio_volume(vent_node, "snd_vent_close") if vent_node > 0 else self._apply_channel_volume(SOUND_BASE_VOLUMES["snd_vent_close"], "snd_vent_close")
        channel = self.snd_vent_close.play()
        if channel is not None:
            channel.set_volume(max(0.0, min(1.0, volume)))

    def _update_seal_sound(self) -> None:
        """Обновить циклическое воспроизведение звука блокировки.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        for seal_id, prev_state in self._prev_seal_states.items():
            seal_now = self.model.seals.get(seal_id)
            vent_node = VENT_SEALS.get(seal_id, -1)
            if prev_state == SealState.CLOSED and seal_now == SealState.OPEN:
                self._play_vent_close_sound_for_node(vent_node)
            if prev_state == SealState.SEALING and seal_now == SealState.CLOSED:
                self._play_vent_close_sound_for_node(vent_node)
                self._vent_seal_just_closed = 60

        active = any(
            self.model.seals.get(s) == SealState.SEALING
            for s in VENT_SEALS
        )
        if active and not self._seal_playing:
            self._play_seal_sound()
        if not active and self._seal_playing:
            if self.snd_wait:
                self.snd_wait.stop()
            self._seal_playing = False

        if self._seal_playing:
            self._seal_timer += 1
            if self._seal_timer >= 180:
                self._seal_timer = 0
                if self.snd_wait:
                    self.snd_wait.play()

        self._prev_seal_states = dict(self.model.seals)
