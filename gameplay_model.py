import math
import random

# Camera definitions: (idx, display_name, filename)
CAMERAS = [
    (1, "01", "MAIN HALL",   "main_hall.png"),
    (2, "02", "ALGEM'S ROOM", "algems' room.png"),
    (3, "03", "TOILETS",     "toilets.png"),
    (4, "04", "WEST HALL",   "westhall.png"),
    (5, "05", "CANTEEN",    "canteen.png"),
    (6, "06", "COWORKING",  "coworking.png"),
    (7, "07", "SERVICE ROOM", "service_room.png"),
]
CAMERA_COUNT = len(CAMERAS)

# Маршрут движения Алгема по карте (соседние камеры)
MOVEMENT_PATHS = {
    2: [1],       # Комната → Main Hall
    1: [3],       # Main Hall → Toilets
    3: [4],       # Toilets → West Hall
    4: [5],       # West Hall → Canteen
    5: [6],       # Canteen → Coworking
    6: [7],       # Coworking → Service Room
    7: [2],       # Service Room → Комната (цикл)
}


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
        self.power_drain_timer = 0  # счётчик кадров для посекундного расхода
        self.algem_location = 2  # стартует в своей комнате (камера 2)
        self.algem_move_timer = random.randint(120, 360)  # кадров до след. шага
        self.algem_prev_location = 2  # для триггера помех на конкретной камере
        self.algem_trigger = 0  # счётчик эффекта помех при перемещении
        self.algem_main_hall_sprite = 0  # 0 или 1 — выбор спрайта на камере 1

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

        # Power drain: 1 раз в секунду (60 кадров)
        if self.power > 0:
            self.power_drain_timer += 1
            if self.power_drain_timer >= 60:
                self.power_drain_timer = 0
                drain = 0.08            # база 0.08/сек
                if self.door_left_closed:  drain += 0.12   # +0.12/сек
                if self.door_right_closed: drain += 0.12   # +0.12/сек
                if self.tablet_open:       drain += 0.08   # +0.08/сек
                self.power = max(0, self.power - drain)

        self.timer += 1
        if self.timer >= 3600:  # 60 сек × 60 FPS = 1 игровой час, ночь 6 мин
            self.hour += 1
            self.timer = 0

        # Алгем: перемещение каждые N кадров
        self.algem_move_timer -= 1
        if self.algem_move_timer <= 0:
            paths = MOVEMENT_PATHS.get(self.algem_location, [1])
            new_loc = random.choice(paths)
            if new_loc != self.algem_location:
                self.algem_prev_location = self.algem_location
                self.algem_location = new_loc
                self.algem_trigger = 60  # 1 сек помех при перемещении
                if new_loc == 1:
                    self.algem_main_hall_sprite = random.randint(0, 1)
            self.algem_move_timer = random.randint(120, 360)  # 2-6 сек

        if self.algem_trigger > 0:
            self.algem_trigger -= 1