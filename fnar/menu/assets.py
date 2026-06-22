"""Загрузка и подготовка ресурсов главного меню."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from fnar.services.visual_assets import normalize_brightness, safe_font, safe_load_image


MENU_FONT_PATH = "assets/fonts/OCR-A.ttf"
MENU_NORMAL_BG = "assets/menu/algem_normal.png"
MENU_STAR = "assets/menu/star.png"
MENU_GLITCH_BACKGROUNDS = (
    "assets/menu/algem_is_trying_to_escape.jpg",
    "assets/menu/algem_is_watching_you.jpg",
    "assets/menu/empty_room.jpeg",
    "assets/menu/algem_normal.png",
)
MENU_TARGET_BRIGHTNESS = 25
MENU_TITLE_FONT_SIZE = 65
MENU_BUTTON_FONT_SIZE = 30
MENU_STAR_SIZE = 64


@dataclass(frozen=True)
class MenuFonts:
    """Loaded font bundle reused by the menu view."""
    title: pygame.font.Font
    button: pygame.font.Font


@dataclass(frozen=True)
class MenuBackgrounds:
    """Loaded background surfaces reused by the menu view."""
    normal: pygame.Surface
    glitch: list[pygame.Surface]



def scale_cover(surface: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
    """Scale a background to fill the entire window (stretch if aspect differs)."""
    if surface.get_width() <= 0 or surface.get_height() <= 0:
        fallback = pygame.Surface(size)
        fallback.fill((12, 12, 16))
        return fallback
    return pygame.transform.smoothscale(surface, size)


def load_menu_fonts(scale_y: float) -> MenuFonts:
    """Load menu fonts and fall back safely when project assets are missing."""
    title_size = int(MENU_TITLE_FONT_SIZE * scale_y)
    button_size = int(MENU_BUTTON_FONT_SIZE * scale_y)
    return MenuFonts(
        title=safe_font(MENU_FONT_PATH, title_size),
        button=safe_font(MENU_FONT_PATH, button_size),
    )


# Module-level cache: normalized originals at their native resolution.
# Populated once; subsequent calls just scale from these.
_bg_originals: dict[str, pygame.Surface] = {}

def load_menu_backgrounds(size: tuple[int, int]) -> MenuBackgrounds:
    """Load, normalize and scale backgrounds.

    Normalized originals are cached at module level on first call so that
    window resize only needs a fast smoothscale from memory (no disk / pixel loops).
    """
    global _bg_originals

    all_paths = [MENU_NORMAL_BG] + list(MENU_GLITCH_BACKGROUNDS)

    if not _bg_originals:
        for path in all_paths:
            _bg_originals[path] = safe_load_image(path, fallback_size=(1280, 720))
        normalize_brightness(
            [(img, path) for path, img in _bg_originals.items()],
            target=MENU_TARGET_BRIGHTNESS,
        )

    normal = scale_cover(_bg_originals[MENU_NORMAL_BG].copy(), size)
    glitch = [scale_cover(_bg_originals[p].copy(), size) for p in MENU_GLITCH_BACKGROUNDS]
    return MenuBackgrounds(normal=normal, glitch=glitch or [normal])


_star_original: pygame.Surface | None = None

def load_menu_star(scale_x: float, scale_y: float) -> pygame.Surface | None:
    """Load menu star and fall back safely when project assets are missing."""
    global _star_original
    if _star_original is None:
        try:
            _star_original = safe_load_image(MENU_STAR, alpha=True)
        except pygame.error:
            _star_original = False  # sentinel
    if _star_original is False:
        return None
    return pygame.transform.smoothscale(
        _star_original,
        (int(MENU_STAR_SIZE * scale_x), int(MENU_STAR_SIZE * scale_y)),
    )
