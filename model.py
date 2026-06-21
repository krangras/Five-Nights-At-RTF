import random
from save import load_save

class MenuModel:
    def __init__(self):
        self.hovered_button = None

        self.saved_night = load_save()
        self.continue_available = self.saved_night > 0
        self.game_completed = self.saved_night >= 5
        
        # Состояния анимации Кошмарного Алгема
        self.algem_state = "NORMAL"
        self.glitch_cooldown = random.randint(180, 420)
        self.glitch_burst_left = 0
        self.glitch_frame_idx = 0
        self._prev_glitch_idx = -1
        
        # Индекс текущего кадра ТВ-помех
        self.noise_frame = 0

    def update(self):
        if self.algem_state == "NORMAL":
            self.glitch_cooldown -= 1
            if self.glitch_cooldown <= 0:
                self.algem_state = "GLITCH"
                self.glitch_burst_left = random.randint(8, 24)
                idx = random.randint(0, 3)
                self.glitch_frame_idx = idx
                self._prev_glitch_idx = idx
        else:
            self.glitch_burst_left -= 1
            if self.glitch_burst_left <= 0:
                self.algem_state = "NORMAL"
                self.glitch_cooldown = random.randint(180, 420)
            else:
                choices = [i for i in range(4) if i != self._prev_glitch_idx]
                idx = random.choice(choices)
                self.glitch_frame_idx = idx
                self._prev_glitch_idx = idx

        self.noise_frame = (self.noise_frame + 1) % 3