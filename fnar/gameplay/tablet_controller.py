"""Tablet animation, camera switching, and bait presentation."""

from .camera_graph import SEAL_CAMERA_MAP, VENT_CAMERAS
from .vent_seal import SealState


class TabletControllerMixin:
    """Control tablet state without owning domain data."""

    def _update_tablet_anim(self) -> None:
        """Advance the tablet open/close animation one frame at a fixed cadence."""
        if not self.model.tablet_animating:
            return

        self._anim_timer -= 1
        if self._anim_timer > 0:
            return

        self.model.tablet_anim_frame += self._anim_dir
        if self.model.tablet_anim_frame >= 10 or self.model.tablet_anim_frame < 0:
            self.model.tablet_animating = False
            if self._anim_dir == 1:
                self.model.tablet_anim_frame = 9  # полностью открыт
            else:
                self.model.tablet_open = False
        else:
            self._anim_timer = 2

    def _update_bait_anim(self) -> None:
        """Advance the lure progress bar and pulsing audio icon while PLAY AUDIO runs."""
        if not self.model.bait_active:
            return

        self._bait_timer += 1
        if self._bait_timer >= 80:
            self._bait_timer = 0
            self.model.bait_step += 1
            if self.model.bait_step >= 6:
                self.model.bait_active = False
                self.model.bait_step = 0
                self.model.bait_cam_step = 0

        self._bait_cam_timer += 1
        if self._bait_cam_timer >= 40:
            self._bait_cam_timer = 0
            if self.model.bait_cam_step < 3:
                self.model.bait_cam_step += 1

    def _toggle_tablet(self) -> None:
        """Request a tablet open/close transition, respecting seal locks and game over."""
        self._check_node5_attack()
        if self.model.game_over:
            return
        if not self.model.tablet_open:
            self._open_tablet()
        elif not self.model.tablet_animating:
            # Нельзя закрывать планшет, если идёт процесс закрывания seal'а
            if self.model.currently_sealing_id is not None:
                return
            self._close_tablet()

    def _open_tablet(self) -> None:
        """Start tablet opening, initialize cameras once, and play the UI cue."""
        self.model.tablet_open = True
        self.model.tablet_animating = True
        self._anim_dir = 1
        self.model.tablet_anim_frame = 0
        self._anim_timer = 2

        if self._cam_init_channel.get_busy():
            self._cam_init_channel.set_volume(1.0)
        elif not self._camera_inited:
            self._camera_inited = True
            if self.snd_cam_init:
                self._cam_init_channel.play(self.snd_cam_init)

        if self.snd_tablet:
            self.snd_tablet.play()

    def _close_tablet(self) -> None:
        """Start tablet closing and mute the camera boot channel during the drop."""
        self.model.tablet_animating = True
        self._anim_dir = -1
        self.model.tablet_anim_frame = 9
        self._anim_timer = 2
        self._cam_init_channel.set_volume(0.0)

        if self.snd_tablet:
            self.snd_tablet.play()

    def _switch_camera(self, idx: int) -> None:
        """Switch the selected camera and suppress static when a closed vent hides Algem."""
        if self.model.camera_idx == idx:
            return
        self.model.camera_idx = idx
        if idx in VENT_CAMERAS:
            self._last_vent_cam = idx
        else:
            self._last_regular_cam = idx
        play_switch_sound = True
        if idx in VENT_CAMERAS:
            seal_id = SEAL_CAMERA_MAP.get(idx)
            seal_state = self.model.seals.get(seal_id) if seal_id is not None else None
            if seal_state == SealState.CLOSED and idx == self.model.algem_location:
                play_switch_sound = False
        if play_switch_sound and self.snd_cam_switch:
            self._cam_switch_channel.play(self.snd_cam_switch)
