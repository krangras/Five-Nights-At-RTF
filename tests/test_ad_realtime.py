"""
test_ad_realtime.py — Демонстрация работы рекламы на ноутбуке в реальном времени.

Запуск:  python -m pytest tests/test_ad_realtime.py -v
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


def _setup_laptop_ready(model: GameModel) -> None:
    """Настроить ноутбук в состояние, при котором реклама может появиться."""
    model.laptop_power_state = "ON"
    model.laptop_open = True
    model.laptop_app = "claude_mythos"
    model.hack_active = True
    model.server_state = "ON"
    model.hack_progress = 0.0


# ── 1. Таймер спавна рекламы ──────────────────────────────────────────────

class TestAdSpawnTimer:
    def test_spawn_timer_decrements(self):
        m = GameModel(night=1)
        _setup_laptop_ready(m)
        m.ad_spawn_timer = 100
        m.ad_active = False
        m._update_ad()
        assert m.ad_spawn_timer == 99

    def test_ad_spawns_when_timer_reaches_zero(self):
        m = GameModel(night=1)
        _setup_laptop_ready(m)
        m.ad_spawn_timer = 1
        m.ad_active = False
        m._update_ad()
        assert m.ad_active is True
        assert m.ad_image_key in m._AD_IMAGES
        assert m.ad_timer == 0

    def test_spawn_timer_resets_after_spawn(self):
        m = GameModel(night=1)
        _setup_laptop_ready(m)
        m.ad_spawn_timer = 1
        m.ad_active = False
        m._update_ad()
        assert m.ad_spawn_timer > 0


# ── 2. Таймер активной рекламы ────────────────────────────────────────────

class TestAdTimer:
    def test_ad_timer_increments_while_active(self):
        m = GameModel(night=1)
        _setup_laptop_ready(m)
        m.ad_active = True
        m.ad_timer = 0
        m._update_ad()
        assert m.ad_timer == 1

    def test_ad_timer_keeps_counting(self):
        m = GameModel(night=1)
        _setup_laptop_ready(m)
        m.ad_active = True
        m.ad_timer = 50
        for _ in range(10):
            m._update_ad()
        assert m.ad_timer == 60


# ── 3. Условия появления рекламы ──────────────────────────────────────────

class TestAdConditions:
    def test_no_ad_when_laptop_off(self):
        m = GameModel(night=1)
        m.laptop_power_state = "OFF"
        m.laptop_open = True
        m.hack_active = True
        m.server_state = "ON"
        m.ad_spawn_timer = 0
        m.ad_active = False
        m._update_ad()
        assert m.ad_active is False

    def test_no_ad_when_hack_inactive(self):
        m = GameModel(night=1)
        _setup_laptop_ready(m)
        m.hack_active = False
        m.ad_spawn_timer = 0
        m.ad_active = False
        m._update_ad()
        assert m.ad_active is False

    def test_no_ad_when_server_off(self):
        m = GameModel(night=1)
        _setup_laptop_ready(m)
        m.server_state = "OFF"
        m.ad_spawn_timer = 0
        m.ad_active = False
        m._update_ad()
        assert m.ad_active is False

    def test_no_ad_when_hack_complete(self):
        m = GameModel(night=1)
        _setup_laptop_ready(m)
        m.hack_progress = 1.0
        m.ad_spawn_timer = 0
        m.ad_active = False
        m._update_ad()
        assert m.ad_active is False

    def test_ad_active_forcefully_deactivated_when_conditions_fail(self):
        m = GameModel(night=1)
        _setup_laptop_ready(m)
        m.ad_active = True
        m.ad_timer = 10
        m.server_state = "OFF"
        m._update_ad()
        assert m.ad_active is False
        assert m.ad_image_key is None
        assert m.ad_timer == 0


# ── 4. Полный цикл: спавн → активна → закрытие ────────────────────────────

class TestAdLifecycle:
    def test_full_cycle_spawn_then_close(self):
        m = GameModel(night=1)
        _setup_laptop_ready(m)

        # Тикаем до спавна
        m.ad_spawn_timer = 2
        m.ad_active = False
        m._update_ad()
        assert m.ad_active is False
        m._update_ad()
        assert m.ad_active is True

        key = m.ad_image_key

        # Тикаем пока активна
        for _ in range(30):
            m._update_ad()
            assert m.ad_active is True
            assert m.ad_image_key == key

        # Закрываем через presenter
        p = _make_presenter()
        p.model = m
        p._close_ad()
        assert m.ad_active is False
        assert m.ad_image_key is None

    def test_ad_respawns_after_being_closed(self):
        m = GameModel(night=1)
        _setup_laptop_ready(m)

        m.ad_spawn_timer = 1
        m._update_ad()
        assert m.ad_active is True

        p = _make_presenter()
        p.model = m
        p._close_ad()
        assert m.ad_active is False

        # Новый таймер запущен, ждём следующий спавн
        assert m.ad_spawn_timer > 0
        m.ad_spawn_timer = 1
        m._update_ad()
        assert m.ad_active is True


# ── 5. Закрытие рекламы при shutdown ноутбука ─────────────────────────────

class TestAdOnShutdown:
    def test_ad_cleared_on_laptop_shutdown(self):
        m = GameModel(night=1)
        _setup_laptop_ready(m)
        m.ad_active = True
        m.ad_image_key = "ad_hhru"
        m.ad_timer = 42

        p = _make_presenter()
        p.model = m
        p._start_laptop_shutdown()

        assert m.ad_active is False
        assert m.ad_image_key is None
        assert m.laptop_power_state == "SHUTTING_DOWN"

    def test_ad_cleared_on_laptop_boot(self):
        m = GameModel(night=1)
        m.laptop_power_state = "OFF"
        m.laptop_open = False
        m.hack_active = True
        m.server_state = "ON"
        m.ad_active = True
        m.ad_image_key = "ad_sber"

        p = _make_presenter()
        p.model = m
        p._start_laptop_boot()

        assert m.ad_active is False
        assert m.ad_image_key is None
        assert m.laptop_power_state == "BOOTING"
