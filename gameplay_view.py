import pygame

class GameView:
    def __init__(self, screen):
        self.screen = screen
        raw = pygame.image.load("assets/office/office_main.png").convert()
        screen_w, screen_h = screen.get_size()
        scale = screen_h / raw.get_height()
        new_w = int(raw.get_width() * scale)
        self.bg = pygame.transform.smoothscale(raw, (new_w, screen_h))
        self.max_offset = max(0, new_w - screen_w)
        self.screen_w = screen_w
        self.font = pygame.font.SysFont("OCR-A", 30)

    def draw(self, model):
        offset = int((model.current_look + 1) / 2 * self.max_offset)
        self.screen.blit(self.bg, (-offset, 0))

        if model.door_left_closed:
            pygame.draw.rect(self.screen, (0, 0, 0), (0, 0, 300, 720))
        if model.door_right_closed:
            pygame.draw.rect(self.screen, (0, 0, 0), (980, 0, 300, 720))

        status = f"Power: {int(model.power)}% | Time: {model.hour} AM"
        self.screen.blit(self.font.render(status, True, (255, 255, 255)), (20, 20))
