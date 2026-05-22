import pygame

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
                    self.model.camera_idx = (self.model.camera_idx + 1) % 10
                if event.key == pygame.K_LEFT:
                    self.model.camera_idx = (self.model.camera_idx - 1) % 10

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
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
                        self.model.camera_idx = 9
                    else:
                        self.model.tablet_open = False
                else:
                    self._anim_timer = 2
