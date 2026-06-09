"""
test_vent_seal_flow.py - end-to-end прогон вентиляций и seal-механики.

Запуск:
    python -m pytest tests/test_vent_seal_flow.py -v
    python tests/test_vent_seal_flow.py
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pytest

import pygame

pygame.init()
pygame.mixer.set_num_channels(16)
SCREEN = pygame.display.set_mode((1280, 720))

from gameplay_model import GameModel, SEAL_CAMERA_MAP, SealState, VENT_SEALS
from gameplay_presenter import GamePresenter
from gameplay_view import GameView

SEAL_ORDER = [
    "SEAL_TOP_RIGHT",
    "SEAL_CENTER",
    "SEAL_BOTTOM_LEFT",
    "SEAL_MID_RIGHT",
]
CAMERA_BY_SEAL = {seal_id: cam_idx for cam_idx, seal_id in SEAL_CAMERA_MAP.items()}
VENT_ROUTE = [8, 9, 10, 11]


class SoundSpy:
    def __init__(self) -> None:
        self.play_calls = 0
        self.stop_calls = 0
        self.volume = 0.0

    def play(self, *_args, **_kwargs) -> None:
        self.play_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def set_volume(self, volume: float) -> None:
        self.volume = volume

    def get_length(self) -> float:
        return 0.0


@pytest.fixture()
def game():
    random.seed(0)
    model = GameModel(night=2)
    model.night_start_ticks = 0
    view = GameView(SCREEN)
    presenter = GamePresenter(model, view)

    presenter.snd_wait = SoundSpy()
    presenter.snd_vent_close = SoundSpy()
    presenter.snd_startnight = None
    presenter.snd_ambience = None
    presenter.snd_work = None
    presenter.snd_off = None
    presenter.snd_phone_call = None
    presenter.snd_danger2b = None
    presenter.snd_algem_leave = None
    presenter.snd_endnight = None

    return model, view, presenter


def _set_algem_on_route(model: GameModel, frame_idx: int) -> None:
    prev = model._ai.location
    model._ai.prev_location = prev
    model._ai.location = VENT_ROUTE[frame_idx % len(VENT_ROUTE)]
    model._ai.trigger_timer = 0


def _advance_frames(
    model: GameModel,
    view: GameView,
    presenter: GamePresenter,
    frames: int,
    frame_idx: int,
) -> int:
    for _ in range(frames):
        model.update()
        _set_algem_on_route(model, frame_idx)
        presenter.update()
        view.draw(model)
        frame_idx += 1
    return frame_idx


def _press_key(presenter: GamePresenter, key: int) -> None:
    presenter.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def _click(presenter: GamePresenter, pos: tuple[int, int]) -> None:
    presenter.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            button=1,
            pos=pos,
        )
    )


def _rect_center(rect: pygame.Rect) -> tuple[int, int]:
    return (rect.centerx, rect.centery)


def test_full_vent_seal_autoplay_flow(game):
    model, view, presenter = game
    frame_idx = 0

    _press_key(presenter, pygame.K_TAB)
    frame_idx = _advance_frames(model, view, presenter, 30, frame_idx)
    assert model.tablet_open
    assert not model.tablet_animating

    view.draw(model)
    _click(presenter, _rect_center(view._map_btn_rect))
    frame_idx = _advance_frames(model, view, presenter, 2, frame_idx)
    assert view.vent_map_mode

    view.draw(model)
    assert set(view._seal_rects) == set(SEAL_ORDER)
    assert set(view._closed_vent_surfaces) >= set(CAMERA_BY_SEAL.values())

    closed_once: set[str] = set()
    previous_seal: str | None = None
    previous_cam: int | None = None

    for seal_id in SEAL_ORDER:
        target_cam = CAMERA_BY_SEAL[seal_id]
        viewed_cam = previous_cam if previous_cam is not None else target_cam

        presenter._switch_camera(viewed_cam)
        frame_idx = _advance_frames(model, view, presenter, 2, frame_idx)
        view.draw(model)

        prev_close_calls = presenter.snd_vent_close.play_calls
        prev_wait_calls = presenter.snd_wait.play_calls
        previous_states = dict(model.seals)

        _click(presenter, _rect_center(view._seal_rects[seal_id]))

        assert model.seals[seal_id] == SealState.SEALING
        assert presenter.snd_wait.play_calls == prev_wait_calls + 1

        if previous_seal is not None:
            assert previous_states[previous_seal] == SealState.CLOSED
            assert model.seals[previous_seal] == SealState.OPEN
            assert presenter.snd_vent_close.play_calls == prev_close_calls + 1
        else:
            assert presenter.snd_vent_close.play_calls == prev_close_calls

        presenter._switch_camera(target_cam)
        frame_idx = _advance_frames(model, view, presenter, 305, frame_idx)

        assert model.seals[seal_id] == SealState.CLOSED
        closed_once.add(seal_id)

        expected_close_calls = prev_close_calls + 1
        if previous_seal is not None:
            expected_close_calls += 1
        assert presenter.snd_vent_close.play_calls == expected_close_calls
        assert not model.game_over

        active_closed = {
            sid for sid, state in model.seals.items() if state == SealState.CLOSED
        }
        assert active_closed == {seal_id}

        previous_seal = seal_id
        previous_cam = target_cam

    assert closed_once == set(SEAL_ORDER)


def test_reroute_from_trap(game):
    model, view, presenter = game
    frame_idx = 0

    _press_key(presenter, pygame.K_TAB)
    frame_idx = _advance_frames(model, view, presenter, 30, frame_idx)
    assert model.tablet_open

    view.draw(model)
    _click(presenter, _rect_center(view._map_btn_rect))
    frame_idx = _advance_frames(model, view, presenter, 2, frame_idx)
    assert view.vent_map_mode

    for seal_id in SEAL_ORDER:
        target_cam = CAMERA_BY_SEAL[seal_id]

        presenter._switch_camera(target_cam)
        frame_idx = _advance_frames(model, view, presenter, 2, frame_idx)

        _click(presenter, _rect_center(view._seal_rects[seal_id]))
        assert model.seals[seal_id] == SealState.SEALING

        model._ai.location = target_cam
        model._ai._idle_ticks_left = 0
        model._ai._move_timer = 0
        for _ in range(305):
            model.update()
            presenter.update()
            view.draw(model)
            frame_idx += 1

        assert model.seals[seal_id] == SealState.CLOSED
        assert model._ai.location != target_cam

    assert not model.game_over


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
