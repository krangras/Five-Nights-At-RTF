"""
demo_vent_seal_flow.py — ручной demo-прогон seal-механики.

Запуск:
    python tests/manual/demo_vent_seal_flow.py

Сценарий:
1. Скрипт сам открывает планшет и карту вентиляции
2. Ты сам кликаешь по seal на vent map
3. В момент старта закрытия Алгем появляется на связанной vent-камере
4. Камера автоматически показывается, пока seal закрывается
5. После закрытия ещё 2 секунды показывается закрытый вент
6. Затем demo возвращает тебя обратно на vent map для следующего клика

ESC - выход.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pygame

pygame.init()
pygame.mixer.set_num_channels(16)
screen = pygame.display.set_mode((1280, 720))
pygame.display.set_caption("Five Nights At RTF")
_icon_path = Path(__file__).resolve().parents[2] / "assets" / "logo" / "logo_32_rgb.png"
if _icon_path.exists():
    try:
        _icon = pygame.image.load(str(_icon_path))
        pygame.display.set_icon(_icon)
    except pygame.error:
        pass
clock = pygame.time.Clock()

from fnar.gameplay.model import GameModel, SEAL_CAMERA_MAP, SealState, BASE_GRAPH  # noqa: E402
from fnar.gameplay.view import GameView  # noqa: E402
from fnar.gameplay.presenter import GamePresenter  # noqa: E402
from fnar.gameplay.algem_ai import bfs_path  # noqa: E402

m = GameModel(night=2)
v = GameView(screen)
p = GamePresenter(m, v)

CAMERA_BY_SEAL: dict[str, int] = {seal_id: cam_idx for cam_idx, seal_id in SEAL_CAMERA_MAP.items()}

SEAL_ORDER = [
    "SEAL_TOP_RIGHT",
    "SEAL_CENTER",
    "SEAL_BOTTOM_LEFT",
    "SEAL_MID_RIGHT",
]

BOOT = "BOOT"
OPENING_TABLET = "OPENING_TABLET"
OPENING_MAP = "OPENING_MAP"
WAIT_FOR_USER = "WAIT_FOR_USER"
SEALING_CAMERA = "SEALING_CAMERA"
SHOW_CLOSED_CAMERA = "SHOW_CLOSED_CAMERA"

phase = BOOT
phase_timer = 0
prev_currently_sealing: str | None = None
active_seal: str | None = None
active_cam: int | None = None

font = pygame.font.Font(None, 30)

KNOCK_SOUND_PATH = r"c:\Users\ko4ki\Downloads\FNaF 1 Audio\FNaF 1 Audio\knock2.wav"
_knock_sound: pygame.mixer.Sound | None = None
_knock_channel: pygame.mixer.Channel | None = None

DIST_VOLUME: dict[int, float] = {
    0: 1.0,
    1: 0.6,
    2: 0.35,
    3: 0.22,
    4: 0.15,
}

OFFICE_VOLUME = 0.1
VENT_MAP_VOLUME = 0.35


def _calc_knock_volume() -> float:
    if active_cam is None:
        return 0.0
    if not m.tablet_open or m.tablet_animating:
        return OFFICE_VOLUME
    if v.vent_map_mode:
        return VENT_MAP_VOLUME
    if m.camera_idx == active_cam:
        return 1.0
    path = bfs_path(m.camera_idx, active_cam, BASE_GRAPH)
    dist = len(path) - 1 if path else 99
    for d in sorted(DIST_VOLUME, reverse=True):
        if dist >= d:
            return DIST_VOLUME[d]
    return 0.0


def _play_knock() -> None:
    global _knock_sound, _knock_channel
    if _knock_sound is None:
        try:
            _knock_sound = pygame.mixer.Sound(KNOCK_SOUND_PATH)
        except Exception:
            _knock_sound = False
            return
    vol = _calc_knock_volume()
    if vol <= 0.0:
        return
    _knock_channel = pygame.mixer.find_channel()
    if _knock_channel is not None:
        _knock_channel.set_volume(vol)
        _knock_channel.play(_knock_sound)


def _rect_center(rect: pygame.Rect) -> tuple[int, int]:
    return (rect.centerx, rect.centery)


def _click(pos: tuple[int, int]) -> None:
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
    pygame.event.post(ev)


def _press_key(key: int) -> None:
    ev = pygame.event.Event(pygame.KEYDOWN, key=key)
    pygame.event.post(ev)


def _pin_algem(node: int) -> None:
    """Жёстко зафиксировать позицию Алгема (AI не сможет его двигать)."""
    if m._ai.location != node:
        m._ai.prev_location = m._ai.location
    m._ai.location = node
    m._ai.trigger_timer = 0


def _draw_debug() -> None:
    lines = [
        f"Phase: {phase} ({phase_timer})",
        f"Algem: node {m.algem_location}",
        f"Camera: {m.camera_idx}",
        f"vent_map_mode: {v.vent_map_mode}",
        f"tablet_open: {m.tablet_open}",
        f"Active seal: {active_seal or '-'}",
        f"currently_sealing_id: {m.currently_sealing_id}",
        "",
        "Seal states:",
    ]
    for sid in SEAL_ORDER:
        state = m.seals[sid]
        marker = " <-- SEALING" if sid == m.currently_sealing_id else ""
        if state == SealState.CLOSED:
            marker = " [CLOSED]"
        lines.append(f"  {sid}: {state.name}{marker}")

    lines.append("")
    knock_vol = _calc_knock_volume()
    if _knock_sound is not False:
        lines.append(f"Knock vol: {knock_vol:.2f}")
    else:
        lines.append("Knock: not loaded")
    lines.append("")
    lines.append("Click any OPEN seal on the vent map to start")

    y = 12
    for line in lines:
        surf = font.render(line, True, (0, 255, 0))
        bg = font.render(line, True, (0, 0, 0))
        screen.blit(bg, (12, y + 1))
        screen.blit(surf, (10, y))
        y += 28


running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False
        p.handle_event(event)

    phase_timer += 1

    # ─── BOOT → открываем планшет ───────────────────────────────
    if phase == BOOT:
        if phase_timer >= 60:
            _press_key(pygame.K_TAB)
            phase = OPENING_TABLET
            phase_timer = 0

    # ─── OPENING_TABLET → ждём открытия → клик map btn ──────────
    elif phase == OPENING_TABLET:
        if m.tablet_open and not m.tablet_animating:
            v.draw(m)
            _click(_rect_center(v._map_btn_rect))
            phase = OPENING_MAP
            phase_timer = 0

    # ─── OPENING_MAP → ждём vent_map_mode → пользователь ────────
    elif phase == OPENING_MAP:
        if v.vent_map_mode and phase_timer >= 20:
            _pin_algem(1)
            phase = WAIT_FOR_USER
            phase_timer = 0

    # ─── WAIT_FOR_USER → ждём клик по seal на vent map ──────────
    elif phase == WAIT_FOR_USER:
        _pin_algem(1)
        cur = m.currently_sealing_id
        if prev_currently_sealing is None and cur is not None:
            active_seal = cur
            active_cam = CAMERA_BY_SEAL.get(cur)
            if active_cam is not None:
                _pin_algem(active_cam)
                p._switch_camera(active_cam)
                v.vent_map_mode = False
                phase = SEALING_CAMERA
                phase_timer = 0

    # ─── SEALING_CAMERA → показываем камеру с закрытием вента ──
    elif phase == SEALING_CAMERA:
        if active_seal is not None:
            _pin_algem(active_cam or 8)
        if active_seal is not None and m.seals[active_seal] == SealState.CLOSED:
            phase = SHOW_CLOSED_CAMERA
            phase_timer = 0

    # ─── SHOW_CLOSED_CAMERA → 3 сек → knock → ещё 2 сек → vent map ──
    elif phase == SHOW_CLOSED_CAMERA:
        if phase_timer == 180:
            _play_knock()
        if phase_timer >= 300:
            _pin_algem(1)
            v.vent_map_mode = True
            if active_cam is not None:
                p._switch_camera(active_cam)
            active_seal = None
            active_cam = None
            phase = WAIT_FOR_USER
            phase_timer = 0

    # ─── тик модели / presenter ─────────────────────────────────
    prev_currently_sealing = m.currently_sealing_id

    m.update()
    p.update()
    v.draw(m)
    _draw_debug()
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
