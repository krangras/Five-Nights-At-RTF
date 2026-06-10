"""
test_glitch.py — Тесты механики случайного глитча.

Запуск:  python -m pytest tests/test_glitch.py -v
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygame
import pytest

from gameplay_model import GameModel
from gameplay_presenter import GamePresenter


@pytest.fixture(autouse=True)
def _init_pygame():
    pygame.init()
    pygame.mixer.set_num_channels(16)
    yield
    pygame.quit()


def _make_presenter(night: int = 1) -> GamePresenter:
    model = GameModel(night=night)
    view = MagicMock()
    view.screen_rect = pygame.Rect(0, 0, 1280, 720)
    view.screen_w = 1280
    view.screen_h = 720
    view.max_offset = 0
    view.font = pygame.font.Font(None, 30)
    view.font_small = pygame.font.Font(None, 18)
    view.font_very_small = pygame.font.Font(None, 11)
    return GamePresenter(model, view)


# ── 1. Инициализация ──────────────────────────────────────────────────────

class TestGlitchModelFields:
    def test_initial_state(self):
        m = GameModel(night=1)
        assert m._glitch_active is False
        assert m._glitch_timer == 0
        assert m._glitch_frame == 0
        assert m._glitch_frame_timer == 0
        assert m._glitch_triggered is False

    def test_delay_in_range(self):
        for _ in range(50):
            m = GameModel(night=1)
            assert 1800 <= m._glitch_delay <= 10800


# ── 2. Обратный отсчёт delay ──────────────────────────────────────────────

class TestGlitchDelay:
    def test_delay_counts_down(self):
        p = _make_presenter()
        initial = p.model._glitch_delay
        for _ in range(100):
            p._update_glitch()
        assert p.model._glitch_delay == initial - 100
        assert p.model._glitch_triggered is False

    def test_delay_reaches_zero_marks_triggered(self):
        p = _make_presenter()
        p.model._glitch_delay = 5
        for _ in range(5):
            p._update_glitch()
        assert p.model._glitch_triggered is True


# ── 3. Шанс 10% ──────────────────────────────────────────────────────────

class TestGlitchChance:
    def test_01_percent_chance(self):
        p = _make_presenter()
        p.model._glitch_delay = 0
        p.model._glitch_triggered = False
        with patch("gameplay_presenter.random.random", return_value=0.0005), \
             patch("pygame.sndarray.array", return_value=[0]*2400):
            p._update_glitch()
        assert p.model._glitch_active is True
        assert p.model._glitch_timer == 90

    def test_no_trigger_above_01_percent(self):
        p = _make_presenter()
        p.model._glitch_delay = 0
        p.model._glitch_triggered = False
        with patch("gameplay_presenter.random.random", return_value=0.5):
            p._update_glitch()
        assert p.model._glitch_active is False
        assert p.model._glitch_triggered is True

    def test_only_triggers_once(self):
        p = _make_presenter()
        p.model._glitch_delay = 0
        p.model._glitch_triggered = False
        with patch("gameplay_presenter.random.random", return_value=0.0005), \
             patch("pygame.sndarray.array", return_value=[0]*2400):
            p._update_glitch()
        assert p.model._glitch_active is True
        p.model._glitch_active = False
        p.model._glitch_triggered = True
        p._update_glitch()
        assert p.model._glitch_active is False


# ── 4. Таймер глитча ─────────────────────────────────────────────────────

class TestGlitchTimer:
    def _start_glitch(self, p):
        p.model._glitch_active = True
        p.model._glitch_triggered = True
        p.model._glitch_delay = 0
        p.model._glitch_timer = 90
        p.model._glitch_frame = 0
        p.model._glitch_frame_timer = 99

    def test_timer_counts_down(self):
        p = _make_presenter()
        self._start_glitch(p)
        p._update_glitch()
        assert p.model._glitch_timer == 89
        assert p.model._glitch_active is True

    def test_glitch_deactivates_at_zero(self):
        p = _make_presenter()
        self._start_glitch(p)
        p.model._glitch_timer = 1
        p._update_glitch()
        assert p.model._glitch_timer == 0
        assert p.model._glitch_active is False

    def test_full_duration(self):
        p = _make_presenter()
        self._start_glitch(p)
        for i in range(90):
            assert p.model._glitch_active is True, f"Активен на тике {i}"
            p._update_glitch()
        assert p.model._glitch_active is False


# ── 5. Чередование кадров ─────────────────────────────────────────────────

class TestGlitchFrame:
    def test_frame_alternates(self):
        p = _make_presenter()
        p.model._glitch_active = True
        p.model._glitch_triggered = True
        p.model._glitch_delay = 0
        p.model._glitch_timer = 90
        p.model._glitch_frame = 0
        p.model._glitch_frame_timer = 0

        p._update_glitch()
        assert p.model._glitch_frame == 1

        p._update_glitch()
        assert p.model._glitch_frame == 0

        p._update_glitch()
        assert p.model._glitch_frame == 1

    def test_frame_bounces_0_1(self):
        p = _make_presenter()
        p.model._glitch_active = True
        p.model._glitch_triggered = True
        p.model._glitch_delay = 0
        p.model._glitch_timer = 90
        p.model._glitch_frame = 0
        p.model._glitch_frame_timer = 0

        seen_frames = set()
        for _ in range(90):
            p._update_glitch()
            seen_frames.add(p.model._glitch_frame)
            assert p.model._glitch_frame in (0, 1)
        assert seen_frames == {0, 1}


# ── 6. Блокировка ввода ───────────────────────────────────────────────────

class TestGlitchInputBlock:
    def test_events_blocked_during_glitch(self):
        p = _make_presenter()
        p.model._glitch_active = True
        event = MagicMock()
        event.type = pygame.KEYDOWN
        event.key = pygame.K_TAB
        assert p.model.tablet_open is False
        p.handle_event(event)
        assert p.model.tablet_open is False

    def test_events_work_after_glitch(self):
        p = _make_presenter()
        p.model._glitch_active = False
        event = MagicMock()
        event.type = pygame.KEYDOWN
        event.key = pygame.K_TAB
        p.handle_event(event)
        assert p.model.tablet_open is True


# ── 7. game_over / night_complete ──────────────────────────────────────────

class TestGlitchEndGame:
    def test_no_glitch_after_game_over(self):
        p = _make_presenter()
        p.model.game_over = True
        p.model._glitch_delay = 0
        p.model._glitch_triggered = False
        p._update_glitch()
        assert p.model._glitch_active is False

    def test_no_glitch_after_night_complete(self):
        p = _make_presenter()
        p.model.night_complete = True
        p.model._glitch_delay = 0
        p.model._glitch_triggered = False
        p._update_glitch()
        assert p.model._glitch_active is False


# ── 8. Интеграция ─────────────────────────────────────────────────────────

class TestGlitchIntegration:
    def test_full_scenario_with_forced_trigger(self):
        p = _make_presenter()
        p.model._glitch_delay = 3

        for _ in range(2):
            p._update_glitch()
        assert p.model._glitch_triggered is False

        with patch("gameplay_presenter.random.random", return_value=0.0005), \
             patch("pygame.sndarray.array", return_value=[0]*2400):
            p._update_glitch()
        assert p.model._glitch_triggered is True
        assert p.model._glitch_active is True
        assert p.model._glitch_timer == 90

        for _ in range(90):
            assert p.model._glitch_active is True
            p._update_glitch()
        assert p.model._glitch_active is False

    def test_delay_not_negative(self):
        p = _make_presenter()
        p.model._glitch_delay = 2
        for _ in range(10):
            p._update_glitch()
        assert p.model._glitch_delay == 0 or p.model._glitch_triggered is True
