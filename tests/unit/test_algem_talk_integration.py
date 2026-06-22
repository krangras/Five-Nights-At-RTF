"""
test_algem_talk_integration.py — Интеграционные тесты звука Алгема.

Запуск:  python -m pytest tests/unit/test_algem_talk_integration.py -v
          python tests/unit/test_algem_talk_integration.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pytest

import pygame

pygame.init()
pygame.mixer.set_num_channels(16)
screen = pygame.display.set_mode((1280, 720))

from fnar.gameplay.model import GameModel, BASE_GRAPH
from fnar.gameplay.view import GameView
from fnar.gameplay.presenter import GamePresenter


@pytest.fixture()
def game():
    m = GameModel(night=2)
    v = GameView(screen)
    p = GamePresenter(m, v)
    m.night_start_ticks = 0
    return m, v, p


def _force_talk(p: GamePresenter) -> None:
    """Принудительно запустить звук Алгема (таймер = 0)."""
    p._algem_talk_timer = 0
    p.update()


def _get_volume(p: GamePresenter) -> float:
    """Получить текущую громкость канала Алгема."""
    return p._algem_talk_channel.get_volume()


VOL_TOL = 0.01


def _is_playing(p: GamePresenter) -> bool:
    return p._algem_talk_channel.get_busy()


class TestTalkVolumeByDistance:
    def test_talk_plays_when_timer_zero(self, game):
        m, v, p = game
        m._ai.location = 7
        m.tablet_open = False
        _force_talk(p)
        assert _is_playing(p)

    def test_volume_full_when_viewing_algem(self, game):
        m, v, p = game
        m._ai.location = 7
        m.tablet_open = True
        m.tablet_animating = False
        m.camera_idx = 7
        _force_talk(p)
        vol_same = _get_volume(p)

        m.camera_idx = 1
        p.update()
        vol_far = _get_volume(p)

        assert vol_same > vol_far

    def test_volume_distant_when_viewing_far_camera(self, game):
        m, v, p = game
        m._ai.location = 7
        m.tablet_open = True
        m.tablet_animating = False
        m.camera_idx = 1
        _force_talk(p)
        vol_far = _get_volume(p)

        m.camera_idx = 7
        p.update()
        vol_same = _get_volume(p)

        assert vol_far < vol_same

    def test_volume_office_when_tablet_closed(self, game):
        m, v, p = game
        m._ai.location = 7
        m.tablet_open = False
        _force_talk(p)
        vol_office = _get_volume(p)

        m.tablet_open = True
        m.tablet_animating = False
        m.camera_idx = 7
        p.update()
        vol_same = _get_volume(p)

        assert vol_office < vol_same

    def test_volume_adjacent_camera(self, game):
        m, v, p = game
        m._ai.location = 7
        m.tablet_open = True
        m.tablet_animating = False
        m.camera_idx = 4
        _force_talk(p)
        vol_mid = _get_volume(p)

        m.camera_idx = 1
        p.update()
        vol_far = _get_volume(p)

        m.camera_idx = 7
        p.update()
        vol_same = _get_volume(p)

        assert vol_same > vol_mid > vol_far


class TestDynamicVolumeChange:
    def test_volume_changes_on_camera_switch(self, game):
        m, v, p = game
        m._ai.location = 7
        m.tablet_open = True
        m.tablet_animating = False

        m.camera_idx = 1
        _force_talk(p)
        vol_far = _get_volume(p)

        m.camera_idx = 7
        p.update()
        vol_near = _get_volume(p)

        assert vol_near > vol_far

    def test_volume_drops_when_leaving_algem_camera(self, game):
        m, v, p = game
        m._ai.location = 3
        m.tablet_open = True
        m.tablet_animating = False
        m.camera_idx = 3
        _force_talk(p)
        vol_same = _get_volume(p)

        m.camera_idx = 6
        p.update()
        vol_diff = _get_volume(p)

        assert vol_same > vol_diff


class TestMuffledVariants:
    def test_variants_exist_for_all_distances(self, game):
        m, v, p = game
        for dist in range(5):
            assert dist in p._talk_variants
            assert len(p._talk_variants[dist]) > 0

    def test_direct_variant_is_original(self, game):
        m, v, p = game
        originals = p._algem_talk_sounds
        direct = p._talk_variants[0]
        for d, o in zip(direct, originals):
            assert d is o

    def test_muffled_variants_differ_from_original(self, game):
        m, v, p = game
        originals = p._algem_talk_sounds
        for dist in (1, 2, 3, 4):
            for muffled, orig in zip(p._talk_variants[dist], originals):
                assert muffled is not orig


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
