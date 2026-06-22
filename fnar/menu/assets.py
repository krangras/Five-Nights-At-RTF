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
    """Набор шрифтов главного меню, загруженных один раз при старте.

    Args:
        title: Крупный шрифт заголовка.
        button: Шрифт пунктов меню.
    """
    title: pygame.font.Font
    button: pygame.font.Font


@dataclass(frozen=True)
class MenuBackgrounds:
    """Фоны главного меню в нормальном и затемнённом вариантах.

    Args:
        normal: Основной фон меню.
        glitch: Список альтернативных фонов для glitch-состояния.
    """
    normal: pygame.Surface
    glitch: list[pygame.Surface]


def load_menu_fonts(scale_y: float) -> MenuFonts:
    title_size = int(MENU_TITLE_FONT_SIZE * scale_y)
    button_size = int(MENU_BUTTON_FONT_SIZE * scale_y)
    return MenuFonts(
        title=safe_font(MENU_FONT_PATH, title_size),
        button=safe_font(MENU_FONT_PATH, button_size),
    )


def load_menu_backgrounds(size: tuple[int, int]) -> MenuBackgrounds:
    normal = pygame.transform.smoothscale(
        safe_load_image(MENU_NORMAL_BG, fallback_size=size),
        size,
    )
    glitch_images = [
        pygame.transform.smoothscale(safe_load_image(path, fallback_size=size), size)
        for path in MENU_GLITCH_BACKGROUNDS
    ]
    normalize_brightness(
        [(normal, MENU_NORMAL_BG)]
        + list(zip(glitch_images, MENU_GLITCH_BACKGROUNDS)),
        target=MENU_TARGET_BRIGHTNESS,
    )
    return MenuBackgrounds(normal=normal, glitch=glitch_images or [normal])


def load_menu_star(scale_x: float, scale_y: float) -> pygame.Surface | None:
    try:
        raw = safe_load_image(MENU_STAR, alpha=True)
        return pygame.transform.smoothscale(
            raw,
            (int(MENU_STAR_SIZE * scale_x), int(MENU_STAR_SIZE * scale_y)),
        )
    except pygame.error:
        return None
