"""Тест скримера: пустой офис 5 секунд → скример"""
import pygame
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

pygame.init()
screen = pygame.display.set_mode((1280, 720))
clock = pygame.time.Clock()
pygame.display.set_caption("TEST SCREAMER — ждите 5 секунд")

from screamer import ScreamerPlayer

# Офис
bg = pygame.image.load("assets/office/server_is_off.png").convert()
scale = 720 / bg.get_height()
bg = pygame.transform.smoothscale(bg, (int(bg.get_width() * scale), 720))
max_off = max(0, bg.get_width() - 1280)

timer = 0
phase = "OFFICE"
screamer = None

running = True
while running:
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            running = False

    if phase == "OFFICE":
        offset = int((pygame.time.get_ticks() % 4000) / 4000 * max_off)
        screen.blit(bg, (-offset, 0))
        txt = pygame.font.Font("assets/fonts/OCR-A.ttf", 24).render(
            "SCREAMER IN 5...", True, (255, 255, 255)
        )
        screen.blit(txt, (540, 680))
        pygame.display.flip()

        timer += 1
        if timer >= 300:  # 5 сек при 60 FPS
            phase = "SCREAMER"
            pygame.mixer.stop()
            screamer = ScreamerPlayer("assets/office/screamer.mp4")
            screamer.extract_audio()
            screamer.play_audio()

        clock.tick(60)

    elif phase == "SCREAMER":
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                running = False

        if not running:
            break

        frame = screamer.get_frame()
        if frame is None:
            screamer.close()
            running = False
        else:
            screen.blit(frame, (0, 0))
            pygame.display.flip()

        clock.tick(screamer.fps)

pygame.quit()
