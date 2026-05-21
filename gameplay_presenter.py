import pygame

class GamePresenter:
    def __init__(self, model, view):
        self.model = model
        self.view = view

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q:
                self.model.door_left_closed = not self.model.door_left_closed
            if event.key == pygame.K_e:
                self.model.door_right_closed = not self.model.door_right_closed
            if event.key == pygame.K_ESCAPE:
                pygame.mouse.set_visible(not pygame.mouse.get_visible())

        if event.type == pygame.MOUSEMOTION:
            w = self.view.screen_w
            self.model.target_look = (event.pos[0] / w) * 2 - 1
            self.model.target_look = max(-1.0, min(1.0, self.model.target_look))
