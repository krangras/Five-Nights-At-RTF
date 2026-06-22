"""Общие фикстуры pytest для корректного завершения PyGame после тестов."""

from __future__ import annotations


def pytest_sessionfinish(session, exitstatus):
    """Останавливает PyGame/mixer, чтобы тестовый процесс закрывал игровые ресурсы."""
    try:
        import pygame

        if pygame.mixer.get_init():
            pygame.mixer.stop()
            pygame.mixer.quit()
        if pygame.display.get_init():
            pygame.display.quit()
        if pygame.font.get_init():
            pygame.font.quit()
        if pygame.get_init():
            pygame.quit()
    except Exception:
        return
