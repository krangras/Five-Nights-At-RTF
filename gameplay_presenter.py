import pygame
import random
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

        try:
            self.snd_phone_call = pygame.mixer.Sound("sounds/night1/callnight1.mp3")
        except pygame.error:
            print("sounds/night1/callnight1.mp3 не найден")
            self.snd_phone_call = None
        self._phone_channel = None

        # Звуки приманки (gadget1-4)
        self._gadget_sounds = []
        for i in range(1, 5):
            try:
                self._gadget_sounds.append(pygame.mixer.Sound(f"sounds/gadget{i}.mp3"))
            except pygame.error:
                pass

        self._bait_timer = 0
        self._bait_cam_timer = 0

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
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

            # DEBUG: F1 — принудительный game_over (для теста скримера)
            if event.key == pygame.K_F1:
                self.model.game_over = True

            # Цифровые клавиши 1-7 — переключение камер (без автооткрытия планшета)
            key_to_cam = {
                pygame.K_1: 1, pygame.K_2: 2, pygame.K_3: 3,
                pygame.K_4: 4, pygame.K_5: 5, pygame.K_6: 6,
                pygame.K_7: 7,
            }
            if event.key in key_to_cam and self.model.tablet_open:
                self.model.camera_idx = key_to_cam[event.key]
                if self.snd_cam_switch:
                    self.snd_cam_switch.play()

            # 0 — возврат на камеру 1 (MAIN HALL), сброс панорамирования в центр
            if event.key == pygame.K_0 and self.model.tablet_open:
                self.model.camera_idx = 1
                self.model.cam_look = 0.0
                self.model.cam_state = "HOLDING"
                self.model.cam_hold_timer = 0
                if self.snd_cam_switch:
                    self.snd_cam_switch.play()

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

            # Клик по Mute Call
            phone_on = self.model.phone_call_active or self._phone_channel
            if phone_on and not self.model.phone_muted:
                if self.view.is_mutecall_clicked(event.pos):
                    self.model.phone_muted = True
                    self.model.phone_call_active = False
                    if self.snd_phone_call:
                        self.snd_phone_call.stop()
                    self._phone_channel = None
                    return

            # Клик по BAIT / MAP
            if self.model.tablet_open and not self.model.tablet_animating:
                if self.view.is_bait_clicked(event.pos):
                    if not self.model.bait_active and self.model.camera_idx not in self.model.bait_cooldown and self._gadget_sounds:
                        random.choice(self._gadget_sounds).play()
                        self.model.bait_active = True
                        self.model.bait_step = 0
                        self.model.bait_target_node = self.model.camera_idx
                        self.model.bait_attract_timer = 480
                        self.model.bait_cooldown[self.model.camera_idx] = 480
                        self._bait_timer = 0
                    return
                if self.view.is_map_clicked(event.pos):
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
        if self.model.game_over or self.model.night_complete:
            self.model.bait_active = False
            self.model.bait_target_node = None
            self.model.bait_attract_timer = 0
            self.model.bait_cooldown.clear()
            self.model.algem_in_office = False
            if self.model.phone_call_active or self._phone_channel:
                self.model.phone_call_active = False
                if self.snd_phone_call:
                    self.snd_phone_call.stop()
                self._phone_channel = None
            return

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
                        if self.model.algem_in_office:
                            self.model.game_over = True
                else:
                    self._anim_timer = 2

        # Анимация приманки (6 шагов по ~80 кадров = ~8 сек)
        if self.model.bait_active:
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
                if self.model.bait_cam_step < 4:
                    self.model.bait_cam_step += 1

        # Телефонный звонок
        if self.model.phone_call_active and self._phone_channel is None:
            if self.snd_phone_call:
                self._phone_channel = self.snd_phone_call.play()
            else:
                self.model.phone_call_active = False
                self._phone_channel = None
        if self._phone_channel and not self._phone_channel.get_busy():
            self._phone_channel = None
            self.model.phone_call_active = False

        # Звук помех при перемещении Алгема
        if self.model.algem_trigger > 0 and self._prev_algem_trigger == 0:
            if self.snd_algem_leave:
                self.snd_algem_leave.play(-1)
        elif self.model.algem_trigger == 0 and self._prev_algem_trigger > 0:
            if self.snd_algem_leave:
                self.snd_algem_leave.stop()
        self._prev_algem_trigger = self.model.algem_trigger
