"""
test_algem_talk_sound.py — Тесты механики звука Алгема (distance-based audio).

Запуск:  python -m pytest tests/unit/test_algem_talk_sound.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pytest

from fnar.gameplay.algem_ai import bfs_path
from fnar.gameplay.model import BASE_GRAPH
from fnar.gameplay.presenter import GamePresenter


# ─────────────────────────────────────────────────────────────────────────────
# Расстояния BFS от офиса (node 0)
# ─────────────────────────────────────────────────────────────────────────────

OFFICE_DISTANCES: dict[int, int] = {}
for _node in range(1, 8):
    _path = bfs_path(_node, 0, BASE_GRAPH)
    OFFICE_DISTANCES[_node] = len(_path) - 1 if _path else 4


def test_office_distances() -> None:
    assert OFFICE_DISTANCES == {1: 3, 2: 2, 3: 3, 4: 3, 5: 3, 6: 2, 7: 2}


# ─────────────────────────────────────────────────────────────────────────────
# Расстояния «камера → Алгем» для разных позиций
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "algem_node,expected",
    [
        (1, {1: 0, 2: 1, 3: 1, 4: 1, 5: 2, 6: 3, 7: 3}),
        (3, {1: 1, 2: 1, 3: 0, 4: 1, 5: 1, 6: 2, 7: 3}),
        (7, {1: 3, 2: 4, 3: 3, 4: 2, 5: 3, 6: 2, 7: 0}),
    ],
)
def test_camera_to_algem_distances(algem_node: int, expected: dict[int, int]) -> None:
    for cam in range(1, 8):
        path = bfs_path(cam, algem_node, BASE_GRAPH)
        dist = len(path) - 1 if path else 4
        assert dist == expected[cam], f"cam={cam}, algem={algem_node}"


# ─────────────────────────────────────────────────────────────────────────────
# Маппинг дистанции → (kernel, volume)
# ─────────────────────────────────────────────────────────────────────────────

DIST_PARAMS: dict[int, tuple[int, float]] = {
    0: (0, 1.0),
    1: (5, 0.70),
    2: (15, 0.42),
    3: (25, 0.25),
    4: (40, 0.12),
}


def test_volume_monotonically_decreases() -> None:
    volumes = [DIST_PARAMS[d][1] for d in range(5)]
    for i in range(len(volumes) - 1):
        assert volumes[i] > volumes[i + 1], f"dist {i} not louder than {i + 1}"


def test_direct_view_full_volume() -> None:
    assert DIST_PARAMS[0] == (0, 1.0)


def test_all_distances_have_params() -> None:
    for d in range(5):
        assert d in DIST_PARAMS
        kernel, vol = DIST_PARAMS[d]
        assert kernel >= 0
        assert 0.0 < vol <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Low-pass фильтр (_make_muffled)
# ─────────────────────────────────────────────────────────────────────────────


def _lowpass(raw_int16: np.ndarray, kernel_size: int) -> np.ndarray:
    """Копия логики _make_muffled для тестирования без pygame."""
    if kernel_size <= 1:
        return raw_int16
    arr = raw_int16.astype(np.float64)
    kernel = np.ones(kernel_size, dtype=np.float64) / kernel_size
    filtered = np.convolve(arr, kernel, mode="same")
    np.clip(filtered, -32768, 32767, out=filtered)
    return filtered.astype(np.int16)


def test_lowpass_preserves_length() -> None:
    original = np.zeros(1000, dtype=np.int16)
    original[500] = 10000
    for ks in (1, 5, 15, 25, 40):
        result = _lowpass(original, ks)
        assert len(result) == len(original)


def test_lowpass_reduces_amplitude() -> None:
    original = np.zeros(100, dtype=np.int16)
    original[50] = 10000
    filtered = _lowpass(original, 15)
    assert abs(filtered[50]) < abs(original[50])


def test_lowpass_kernel_1_returns_original() -> None:
    original = np.array([100, -200, 300], dtype=np.int16)
    result = _lowpass(original, 1)
    np.testing.assert_array_equal(result, original)


def test_lowpass_kernel_0_returns_original() -> None:
    original = np.array([100, -200, 300], dtype=np.int16)
    result = _lowpass(original, 0)
    np.testing.assert_array_equal(result, original)


def test_lowpass_more_kernel_more_smoothing() -> None:
    original = np.zeros(200, dtype=np.int16)
    original[100] = 10000
    peak_5 = abs(_lowpass(original, 5)[100])
    peak_40 = abs(_lowpass(original, 40)[100])
    assert peak_5 > peak_40


# ─────────────────────────────────────────────────────────────────────────────
# Сценарии: какая дистанция и громкость при переключении камер
# ─────────────────────────────────────────────────────────────────────────────


def _volume_for_scenario(algem_node: int, camera_idx: int) -> float:
    """Симуляция: определить громкость при given позиции алгема и камере."""
    dist = GamePresenter._camera_audio_distance(camera_idx, algem_node)
    return DIST_PARAMS.get(dist, (0, 0.18))[1]


def test_scenario_algem_at_7_camera_7() -> None:
    assert _volume_for_scenario(7, 7) == 1.0


def test_scenario_algem_at_7_camera_4() -> None:
    assert _volume_for_scenario(7, 7) > _volume_for_scenario(7, 4)


def test_scenario_algem_at_7_camera_1() -> None:
    assert _volume_for_scenario(7, 4) > _volume_for_scenario(7, 1)


def test_scenario_algem_at_3_camera_2() -> None:
    assert _volume_for_scenario(3, 2) > _volume_for_scenario(3, 6)


def test_scenario_algem_at_3_camera_6() -> None:
    assert _volume_for_scenario(3, 6) < _volume_for_scenario(3, 3)


def test_volume_changes_when_switching_camera() -> None:
    """Алгем в node 7: переключение cam 7 → 4 → 1 должно менять громкость."""
    volumes = [_volume_for_scenario(7, cam) for cam in (7, 4, 1)]
    assert volumes[0] > volumes[1] > volumes[2]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
