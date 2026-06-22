"""Pygame asset helpers used by view classes.

The view decides what to draw, while this module owns low-level safe loading,
font fallback, and brightness normalization.
"""

from __future__ import annotations

import os

import pygame


def _ensure_pygame_ready() -> None:
    """Initialize display and font subsystems before creating fallback assets."""
    if not pygame.get_init():
        pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    if not pygame.display.get_init():
        pygame.display.init()


def safe_load_image(
    path: str,
    alpha: bool = False,
    fallback_size: tuple[int, int] = (1280, 720),
) -> pygame.Surface:
    """Load an image or return a visible placeholder with the missing file name."""
    _ensure_pygame_ready()
    try:
        raw = pygame.image.load(path)
        if pygame.display.get_surface() is None:
            return raw.convert_alpha() if alpha else raw.copy()
        return raw.convert_alpha() if alpha else raw.convert()
    except (FileNotFoundError, pygame.error):
        flags = pygame.SRCALPHA if alpha else 0
        surf = pygame.Surface(fallback_size, flags)
        surf.fill((12, 12, 16, 255) if alpha else (12, 12, 16))
        try:
            font = pygame.font.SysFont("consolas", 24, bold=True)
            label = font.render(
                f"MISSING: {os.path.basename(path)}",
                True,
                (220, 80, 80),
            )
            surf.blit(
                label,
                label.get_rect(center=(fallback_size[0] // 2, fallback_size[1] // 2)),
            )
        except pygame.error:
            return surf
        return surf


def safe_font(path: str, size: int) -> pygame.font.Font:
    """Load a project font and fall back to a system monospace font."""
    _ensure_pygame_ready()
    try:
        return pygame.font.Font(path, size)
    except (FileNotFoundError, pygame.error):
        return pygame.font.SysFont("consolas", size)


def normalize_brightness(surfaces_with_paths, target=25):
    """Normalize background brightness once and cache processed surfaces."""
    cache_dir = os.path.join(os.environ.get("APPDATA", "."), "FiveNightsAtRTF", "cache", "norm")
    for img, src_path in surfaces_with_paths:
        if src_path:
            cache_name = f"{os.path.basename(src_path)}_{img.get_width()}x{img.get_height()}"
            cache_path = f"{cache_dir}/{cache_name}"
            if os.path.exists(cache_path):
                cached = safe_load_image(cache_path)
                if cached.get_size() == img.get_size():
                    img.blit(cached, (0, 0))
                    continue
        w, h = img.get_size()
        total = 0
        count = 0
        for y in range(0, h, 4):
            for x in range(0, w, 4):
                r, g, b, _ = img.get_at((x, y))
                total += int(0.299 * r + 0.587 * g + 0.114 * b)
                count += 1
        avg = total / count if count else target
        if avg > 0:
            factor = target / avg
            for y in range(h):
                for x in range(w):
                    r, g, b, a = img.get_at((x, y))
                    img.set_at(
                        (x, y),
                        (
                            min(255, int(r * factor)),
                            min(255, int(g * factor)),
                            min(255, int(b * factor)),
                            a,
                        ),
                    )
        if src_path:
            os.makedirs(cache_dir, exist_ok=True)
            pygame.image.save(img, cache_path)
