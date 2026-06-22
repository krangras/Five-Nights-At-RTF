"""
Тест скримеров: O — офисный, V — вентиляционный, ESC — выход.
Запуск: python tests/manual/screamer_keys_demo.py
"""
import os
import sys
import pygame

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fnar.gameplay.screamer import ScreamerPlayer

pygame.init()
screen = pygame.display.set_mode((1280, 720))
pygame.display.set_caption("Screamer Test — O=office, V=vent, ESC=quit")
clock = pygame.time.Clock()

SCREEN_SIZE = (1280, 720)

screamer_office = ScreamerPlayer(
    frames_dir="assets/screamer/office_screamer",
    screen_size=SCREEN_SIZE,
    scream_frame=20,
    red_start=52,
    red_duration=0.5,
)
screamer_vent = ScreamerPlayer(
    frames_dir="assets/screamer/vent_screamer",
    screen_size=SCREEN_SIZE,
    scream_frame=40,
    red_start=62,
    red_duration=0.5,
    hold_last=0.8,
)

snd_screamer = None
try:
    snd_screamer = pygame.mixer.Sound("sounds/screamer/screamer.mp3")
    snd_screamer.set_volume(0.7)
except pygame.error:
    print("Warning: sounds/screamer/screamer.mp3 not found")

print(f"Office screamer: {len(screamer_office._frames)} frames")
print(f"Vent screamer:   {len(screamer_vent._frames)} frames")
print("O — office screamer | V — vent screamer | ESC — quit")

screamer = None
state = "IDLE"
font = pygame.font.Font(None, 36)

running = True
while running:
    dt = clock.tick(60) / 1000.0

    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False
            break
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                running = False
                break
            if state == "IDLE":
                if e.key == pygame.K_o:
                    screamer = screamer_office
                    screamer.reset()
                    state = "SCREAMER"
                    print("Playing office screamer...")
                elif e.key == pygame.K_v:
                    screamer = screamer_vent
                    screamer.reset()
                    state = "SCREAMER"
                    print("Playing vent screamer...")

    if state == "SCREAMER" and screamer:
        screamer.update(dt)
        if screamer.scream_triggered and snd_screamer:
            snd_screamer.play()
            screamer.scream_triggered = False
            screamer.scream_frame = 999999
        screamer.draw(screen)
        pygame.display.flip()
        if screamer.done:
            state = "IDLE"
            screamer = None
            print("Done. Press O or V.")
    elif state == "IDLE":
        screen.fill((20, 20, 30))
        t1 = font.render("Press O — office screamer", True, (255, 255, 255))
        t2 = font.render("Press V — vent screamer", True, (255, 255, 255))
        screen.blit(t1, (640 - t1.get_width() // 2, 320))
        screen.blit(t2, (640 - t2.get_width() // 2, 370))
        pygame.display.flip()

pygame.quit()
sys.exit()
