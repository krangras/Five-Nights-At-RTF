import pygame
from model import MenuModel
from presenter import MenuPresenter
from view import MenuView
from gameplay_model import GameModel
from gameplay_view import GameView
from gameplay_presenter import GamePresenter

def main():
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    clock = pygame.time.Clock()

    menu_m, menu_v = MenuModel(), MenuView(screen)
    menu_p = MenuPresenter(menu_m, menu_v)
    
    game_m, game_v = GameModel(), GameView(screen)
    game_p = GamePresenter(game_m, game_v)

    state = "MENU"
    while True:
        if state == "MENU":
            state = menu_p.handle_events()
            menu_m.update()
            menu_v.draw_menu(menu_m)
        elif state == "START_GAME":
            state = "GAME"
        elif state == "GAME":
            for e in pygame.event.get():
                if e.type == pygame.QUIT: return
                game_p.handle_event(e)
            
            game_m.update()
            game_p.update()
            game_v.draw(game_m)
            pygame.display.flip()
        
        clock.tick(60)

if __name__ == "__main__": main()