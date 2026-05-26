import pygame
from gameplay_model import GameModel
from gameplay_view import GameView
from gameplay_presenter import GamePresenter

pygame.init()
screen = pygame.display.set_mode((1280, 720))
clock = pygame.time.Clock()

model = GameModel()
view = GameView(screen)
presenter = GamePresenter(model, view)

model.server_state = "ON"
model.tablet_open = True
model.camera_idx = 3
model.algem_move_timer = 9999

frame = 0
while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            exit()
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            pygame.quit()
            exit()

    model.update()
    presenter.update()

    # каждые 10 сек (600 кадров) переключаем: алгем пришёл / ушёл
    prev = model.algem_location
    if (frame // 600) % 2 == 0 and prev != 3:
        model.algem_prev_location = prev
        model.algem_location = 3
        model.algem_trigger = 60
    elif (frame // 600) % 2 == 1 and prev != 4:
        model.algem_prev_location = prev
        model.algem_location = 4
        model.algem_trigger = 60

    view.draw(model)
    pygame.display.flip()
    clock.tick(60)
    frame += 1
