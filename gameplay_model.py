class GameModel:
    def __init__(self):
        self.power = 100.0
        self.hour = 0
        self.timer = 0
        self.door_left_closed = False
        self.door_right_closed = False
        self.target_look = 0.0
        self.current_look = 0.0

    def update(self):
        self.current_look += (self.target_look - self.current_look) * 0.12
        
        drain = 0.05
        if self.door_left_closed: drain += 0.1
        if self.door_right_closed: drain += 0.1
        self.power = max(0, self.power - drain)
        
        self.timer += 1
        if self.timer >= 600:
            self.hour += 1
            self.timer = 0