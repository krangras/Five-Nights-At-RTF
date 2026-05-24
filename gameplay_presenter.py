import pygame
from gameplay_model import CAMERA_COUNT

class GamePresenter:
    def __init__(self, model, view):
        self.model = model
        self.view = view
        self._transition_frames = 0
        self._on_phase = 0
        self._on_phase_frames = 0
        self._anim_timer = 0
        self._anim_dir = 1
        try:
            self.snd_on = pygame.mixer.Sound("sounds/night1/server_turning_on.mp3")
            self.snd_work = pygame.mixer.Sound("sounds/night1/server_is_working.mp3")
            self.snd_off = pygame.mixer.Sound("sounds/night1/server_turning_off.mp3")
            self._off_frames = int(self.snd_off.get_length() * 60) + 1
        except pygame.error:
            print("Серверные звуки не найдены")
            self.snd_on = self.snd_work = self.snd_off = None
            self._off_frames = 60
        try:
            self.snd_tablet = pygame.mixer.Sound("sounds/blip3.mp3")
        except pygame.error:
            print("sounds/blip3.mp3 не найден")
            self.snd_tablet = None
        try:
            self.snd_cam_switch = pygame.mixer.Sound("sounds/camera_switch.wav")
        except pygame.error:
            print("sounds/camera_switch.wav не найден")
            self.snd_cam_switch = None
        try:
            self.snd_cam_init = pygame.mixer.Sound("sounds/camera_init.wav")
        except pygame.error:
            print("sounds/camera_init.wav не найден")
            self.snd_cam_init = None
        self._camera_inited = False
        self._tab_prev_hovered = False

        try:
            self.snd_ambience = pygame.mixer.Sound("sounds/ambience.wav")
            self.snd_ambience.set_volume(0.35)
            self.snd_ambience.play(-1)
        except pygame.error:
            print("sounds/ambience.wav не найден")
            self.snd_ambience = None

        try:
            self.snd_algem_leave = pygame.mixer.Sound("sounds/alegem_is_leaving.wav")
        except pygame.error:
            print("sounds/alegem_is_leaving.wav не найден")
            self.snd_algem_leave = None
        self._prev_algem_trigger = 0

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q:
                self.model.door_left_closed = not self.model.door_left_closed
            if event.key == pygame.K_e:
                self.model.door_right_closed = not self.model.door_right_closed
            if event.key == pygame.K_ESCAPE:
                pygame.mouse.set_visible(not pygame.mouse.get_visible())
            if event.key == pygame.K_TAB:
                if not self.model.tablet_open:
                    self.model.tablet_open = True
                    self.model.tablet_animating = True
                    self._anim_dir = 1
                    self.model.tablet_anim_frame = 0
                    self._anim_timer = 2
                    if not self._camera_inited:
                        self._camera_inited = True
                        if self.snd_cam_init:
                            self.snd_cam_init.play()
                    if self.snd_tablet:
                        self.snd_tablet.play()
                elif not self.model.tablet_animating:
                    self.model.tablet_animating = True
                    self._anim_dir = -1
                    self.model.tablet_anim_frame = 9
                    self._anim_timer = 2
                    if self.snd_tablet:
                        self.snd_tablet.play()

            if self.model.tablet_open:
                if event.key == pygame.K_RIGHT:
                    self.model.camera_idx = (self.model.camera_idx % CAMERA_COUNT) + 1
                    if self.snd_cam_switch:
                        self.snd_cam_switch.play()
                if event.key == pygame.K_LEFT:
                    self.model.camera_idx = ((self.model.camera_idx - 2) % CAMERA_COUNT) + 1
                    if self.snd_cam_switch:
                        self.snd_cam_switch.play()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Клик по мини-карте
            hit = self.view.get_minimap_hotspot(event.pos)
            if hit is not None:
                cam_idx, _ = hit
                if not self.model.tablet_open:
                    self.model.tablet_open = True
                    self.model.tablet_animating = True
                    self._anim_dir = 1
                    self.model.tablet_anim_frame = 0
                    self._anim_timer = 2
                    if self.snd_tablet:
                        self.snd_tablet.play()
                self.model.camera_idx = cam_idx
                if self.snd_cam_switch:
                    self.snd_cam_switch.play()
                return

            # Когда планшет открыт — клики не проходят к серверу
            if self.model.tablet_open and not self.model.tablet_animating:
                if self.view.screen_rect.collidepoint(event.pos):
                    return

            if self.model.server_state in ("OFF", "ON"):
                offset = int((self.model.current_look + 1) / 2 * self.view.max_offset)
                if self.view.is_server_clicked(event.pos, offset):
                    if self.model.server_state == "OFF":
                        self.model.server_state = "TURNING_ON"
                        self.model.server_blink = "red"
                        self._on_phase = 0
                        self._on_phase_frames = 10
                        if self.snd_on:
                            self.snd_on.play()
                    else:
                        self.model.server_state = "TURNING_OFF"
                        self._transition_frames = self._off_frames
                        self.model.server_blink = None
                        if self.snd_work:
                            self.snd_work.stop()
                        if self.snd_off:
                            self.snd_off.play()

        if event.type == pygame.MOUSEMOTION:
            w = self.view.screen_w
            self.model.target_look = (event.pos[0] / w) * 2 - 1
            self.model.target_look = max(-1.0, min(1.0, self.model.target_look))
            # Ховер кнопки TAB — переключение планшета
            if not self.model.tablet_animating:
                offset = int((self.model.current_look + 1) / 2 * self.view.max_offset)
                self.view.tab_button_hovered = self.view.is_tabbutton_clicked(event.pos)
                if self.view.tab_button_hovered and not self._tab_prev_hovered:
                    if not self.model.tablet_open:
                        self.model.tablet_open = True
                        self.model.tablet_animating = True
                        self._anim_dir = 1
                        self.model.tablet_anim_frame = 0
                        self._anim_timer = 2
                        if not self._camera_inited:
                            self._camera_inited = True
                            if self.snd_cam_init:
                                self.snd_cam_init.play()
                        if self.snd_tablet:
                            self.snd_tablet.play()
                    else:
                        self.model.tablet_animating = True
                        self._anim_dir = -1
                        self.model.tablet_anim_frame = 9
                        self._anim_timer = 2
                        if self.snd_tablet:
                            self.snd_tablet.play()
                self._tab_prev_hovered = self.view.tab_button_hovered
            else:
                self.view.tab_button_hovered = False
                self._tab_prev_hovered = False

    def update(self):
        if self.model.server_state == "TURNING_ON":
            self._on_phase_frames -= 1
            if self._on_phase_frames <= 0:
                self._on_phase += 1
                if self._on_phase >= 8:
                    self.model.server_state = "ON"
                    self.model.server_blink = None
                    if self.snd_work:
                        self.snd_work.play(-1)
                    return
                blink_seq = ["red", None, "red", None, "green", None, "green", None]
                self.model.server_blink = blink_seq[self._on_phase]
                self._on_phase_frames = 10

        elif self.model.server_state == "TURNING_OFF":
            self._transition_frames -= 1
            if self._transition_frames <= 0:
                self.model.server_state = "OFF"

        if self.model.tablet_animating:
            self._anim_timer -= 1
            if self._anim_timer <= 0:
                self.model.tablet_anim_frame += self._anim_dir
                if self.model.tablet_anim_frame >= 10 or self.model.tablet_anim_frame < 0:
                    self.model.tablet_animating = False
                    if self._anim_dir == 1:
                        self.model.tablet_anim_frame = 9
                    else:
                        self.model.tablet_open = False
                else:
                    self._anim_timer = 2

        # Звук помех при уходе Алгема
        if self.model.algem_trigger > 0 and self._prev_algem_trigger == 0:
            if self.snd_algem_leave:
                self.snd_algem_leave.play(-1)
        elif self.model.algem_trigger == 0 and self._prev_algem_trigger > 0:
            if self.snd_algem_leave:
                self.snd_algem_leave.stop()
        self._prev_algem_trigger = self.model.algem_trigger
