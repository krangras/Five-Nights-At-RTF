class GameModel:
    def __init__(self):
        self.power = 100
        self.time = 0 # От 0 до 6 (AM)
        self.algem_position = "CAM1"
        
    def update(self):
        # Тут будет логика расхода энергии и перемещения Алгема
        pass

class GameView:
    def __init__(self, screen):
        self.screen = screen
        
    def draw(self, model):
        self.screen.fill((0, 0, 0)) # Черный фон офиса
        # Тут будем рисовать камеры, двери и Алгема

class GamePresenter:
    def __init__(self, model, view):
        self.model = model
        self.view = view
        
    def handle_event(self, event):
        # Обработка нажатий на двери, фонарик, переключение камер
        pass