"""Визуальные эффекты главного меню: шум, сканлайны, виньетка и глитч-полосы."""

from __future__ import annotations

import random

import pygame


MENU_NOISE_FRAME_COUNT = 3
MENU_NOISE_DENSITY = 8000
MENU_SCANLINE_STEP = 3
MENU_SCANLINE_ALPHA = 40
MENU_VIGNETTE_ALPHA = 150


def generate_static_noise(size: tuple[int, int], scale_x: float, scale_y: float) -> list[pygame.Surface]:
    """Generate a random static-noise surface for the menu background."""
    width, height = size
    frames = []
    density = int(MENU_NOISE_DENSITY * scale_x * scale_y)
    for _ in range(MENU_NOISE_FRAME_COUNT):
        noise_surface = pygame.Surface(size, pygame.SRCALPHA)
        for _ in range(density):
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)
            gray = random.randint(50, 180)
            alpha = random.randint(30, 80)
            noise_surface.set_at((x, y), (gray, gray, gray, alpha))
        frames.append(noise_surface)
    return frames


def create_scanlines(size: tuple[int, int]) -> pygame.Surface:
    """Create a transparent scanline overlay for CRT-style menu rendering."""
    width, height = size
    scanlines = pygame.Surface(size, pygame.SRCALPHA)
    for y in range(0, height, MENU_SCANLINE_STEP):
        scanlines.fill((0, 0, 0, MENU_SCANLINE_ALPHA), (0, y, width, 1))
    return scanlines


def create_vignette(size: tuple[int, int]) -> pygame.Surface:
    """Create a dark radial vignette overlay for the menu."""
    width, height = size
    vignette = pygame.Surface(size, pygame.SRCALPHA)
    for i in range(height):
        alpha = int(MENU_VIGNETTE_ALPHA * (i / height))
        vignette.fill((0, 0, 0, alpha), (0, i, width, 1))
        vignette.fill((0, 0, 0, alpha), (0, height - i - 1, width, 1))
    return vignette


def draw_glitch_bars(screen: pygame.Surface) -> None:
    """Draw random horizontal glitch bars over the current surface."""
    width, height = screen.get_size()
    for _ in range(random.randint(2, 5)):
        y = random.randint(0, height - 1)
        bar_height = random.randint(1, 4)
        bar = pygame.Surface((width, bar_height), pygame.SRCALPHA)
        bar.fill((255, 255, 255, random.randint(20, 60)))
        screen.blit(bar, (0, y))
