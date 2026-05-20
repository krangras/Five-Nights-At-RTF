import random

class MenuModel:
    def __init__(self):
        self.hovered_button = None  # Активная кнопка: "new_game", "exit" или None
        
        # Состояния анимации Кошмарного Алгема
        self.algem_state = "NORMAL"  # Может быть "NORMAL" или "GLITCH"
        self.glitch_timer = 0        # Длительность эффекта в кадрах
        
        # Индекс текущего кадра ТВ-помех
        self.noise_frame = 0

    def update(self):
        # Алгоритм случайного появления глитчей Алгема
        if self.algem_state == "NORMAL":
            # Шанс 0.3% каждый кадр, что Алгем на мгновение исказится
            if random.random() < 0.003:
                self.algem_state = "GLITCH"
                # Длительность от 10 до 20 кадров для выразительного эффекта 25-го кадра (~0.2-0.3 сек)
                self.glitch_timer = random.randint(10, 20)  
        else:
            self.glitch_timer -= 1
            if self.glitch_timer <= 0:
                self.algem_state = "NORMAL"

        # Постоянно циклически переключаем 3 кадра шума (0, 1, 2)
        self.noise_frame = (self.noise_frame + 1) % 3