import math

# Camera definitions: (idx, display_name, filename)
CAMERAS = [
    (1, "01A", "MAIN HALL",  "main_hall.png"),
    (2, "05",  "COWORKING",  "coworking.png"),
    (3, "03",  "WEST HALL",  "westhall.png"),
    (4, "04A", "TOILETS",    "toilets.png"),
]
CAMERA_COUNT = len(CAMERAS)


class GameModel:
    def __init__(self):
        self.power = 100.0
        self.hour = 0
        self.timer = 0
        self.door_left_closed = False
        self.door_right_closed = False
        self.target_look = 0.0
        self.current_look = 0.0
        self.server_state = "OFF"
        self.server_blink = None
        self.tablet_open = False
        self.tablet_animating = False
        self.tablet_anim_frame = 0
        self.camera_idx = 1
        self.cam_look = -1.0
        self.cam_state = "HOLDING"
        self.cam_hold_timer = 0
        self.cam_move_progress = 0.0
        self.cam_dir = 1

    def update(self):
        self.current_look += (self.target_look - self.current_look) * 0.12

        if self.cam_state == "HOLDING":
            self.cam_hold_timer += 1
            if self.cam_hold_timer >= 180:
                self.cam_state = "MOVING"
                self.cam_move_progress = 0.0
        elif self.cam_state == "MOVING":
            self.cam_move_progress += 0.006
            if self.cam_move_progress >= 1.0:
                self.cam_state = "HOLDING"
                self.cam_hold_timer = 0
                self.cam_dir = -self.cam_dir
            else:
                t = self.cam_move_progress
                eased = t * t * (3 - 2 * t)
                self.cam_look = eased * self.cam_dir + (1 - eased) * (-self.cam_dir)

        drain = 0.05
        if self.door_left_closed: drain += 0.1
        if self.door_right_closed: drain += 0.1
        self.power = max(0, self.power - drain)

        self.timer += 1
        if self.timer >= 600:
            self.hour += 1
            self.timer = 0