import pygame

from model import MenuModel
from presenter import MenuPresenter
from view import MenuView


def main():
    pygame.init()
    pygame.mixer.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.display.set_caption("Five Nights at RTF")
    clock = pygame.time.Clock()

    # Инициализируем компоненты MVP
    model = MenuModel()
    view = MenuView(screen)
    presenter = MenuPresenter(model, view)

    current_state = "MENU"

    # Основной цикл приложения
    while True:
        if current_state == "MENU":
            current_state = presenter.handle_events()
            model.update()
            view.draw_menu(model)
        elif current_state == "START_GAME":
            # Сюда мы позже добавим вызов логики самой игры (Офиса)
            screen.fill((20, 20, 20))
            font = pygame.font.SysFont("Arial", 40)
            text = font.render(
                "Загрузка Ночи 1... (Тут будет Офис)", True, (255, 255, 255)
            )
            screen.blit(text, (300, 350))
            pygame.display.flip()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return

        clock.tick(60)


if __name__ == "__main__":
    main()
