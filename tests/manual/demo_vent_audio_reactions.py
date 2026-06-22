"""
Vent audio sandbox for manual testing.

Run:
    python tests/manual/demo_vent_audio_reactions.py

Use the on-screen buttons to:
    - teleport Algem into any room/camera
    - open any camera instantly
    - toggle whether Algem is "moving" or "still"
    - toggle the vent map
    - start or reset any vent seal

This lets you verify by hand:
    - distance-based vent loudness
    - direct vent view mutes crawl loop because vent cameras are static
    - crawl sound only while Algem is moving
    - one-shot hit when a sealed vent blocks Algem
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pygame

from fnar.gameplay.model import CAMERAS, GameModel, SealState
from fnar.gameplay.presenter import GamePresenter
from fnar.gameplay.view import GameView


SCREEN_SIZE = (1280, 720)
PANEL_BG = (0, 0, 0, 176)
PANEL_BORDER = (180, 180, 180, 110)
TEXT_MAIN = (236, 236, 236)
TEXT_MUTED = (180, 180, 180)
TEXT_ACCENT = (165, 228, 172)
BTN_BG = (42, 42, 42)
BTN_BG_ACTIVE = (84, 120, 84)
BTN_BG_WARN = (120, 84, 84)
BTN_BORDER = (190, 190, 190)
BTN_TEXT = (236, 236, 236)

SEAL_ORDER = ["SEAL_TOP_RIGHT", "SEAL_CENTER", "SEAL_MID_RIGHT", "SEAL_BOTTOM_LEFT"]
SEAL_LABELS = {
    "SEAL_TOP_RIGHT": "Seal 09",
    "SEAL_CENTER": "Seal 10",
    "SEAL_MID_RIGHT": "Seal 08",
    "SEAL_BOTTOM_LEFT": "Seal 11",
}


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    action: str
    value: object = None
    active: bool = False
    warn: bool = False


def _load_window_icon() -> pygame.Surface | None:
    icon_path = Path(__file__).resolve().parents[2] / "assets" / "logo" / "logo_32_rgb.png"
    if not icon_path.exists():
        return None
    try:
        return pygame.image.load(str(icon_path))
    except pygame.error:
        return None


def _camera_name_map() -> dict[int, str]:
    return {cam_idx: f"CAM {code} {name}" for cam_idx, code, name, _ in CAMERAS}


def _set_algem(model: GameModel, node: int, *, moving: bool) -> None:
    if model._ai.location != node:
        model._ai.prev_location = model._ai.location
    else:
        model._ai.prev_location = node
    model._ai.location = node
    model._ai.trigger_timer = 30 if moving else 0
    model.algem_in_office = False
    model.game_over = False
    model.kill_from_vent = False
    model.office_threat_timer = 0
    model._ai._entry_timer = 0
    model._ai._move_timer = 999999


def _reset_seals(model: GameModel, presenter: GamePresenter) -> None:
    for seal_id in model.seals:
        model.seals[seal_id] = SealState.OPEN
        model._seal_timers[seal_id] = 0
    model.currently_sealing_id = None
    presenter._vent_block_signature = None
    presenter._prev_seal_states = dict(model.seals)
    presenter._seal_playing = False
    presenter._seal_timer = 0


def _prepare_tablet(model: GameModel, view: GameView, presenter: GamePresenter) -> None:
    model.tablet_open = True
    model.tablet_animating = False
    model.tablet_anim_frame = 9
    presenter._anim_dir = 0
    model.laptop_open = False
    model.laptop_power_state = "OFF"


def _draw_text(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    pos: tuple[int, int],
    color: tuple[int, int, int],
) -> None:
    shadow = font.render(text, True, (0, 0, 0))
    fg = font.render(text, True, color)
    surface.blit(shadow, (pos[0] + 1, pos[1] + 1))
    surface.blit(fg, pos)


def _make_buttons(
    sandbox_algem_node: int,
    sandbox_camera: int,
    sandbox_moving: bool,
    view: GameView,
    model: GameModel,
) -> list[Button]:
    buttons: list[Button] = []

    left_x = 20
    top_y = 254
    col_gap = 8
    row_gap = 8
    w = 94
    h = 28

    cam_nodes = [cam_idx for cam_idx, *_rest in CAMERAS]
    for idx, cam_idx in enumerate(cam_nodes):
        row = idx // 4
        col = idx % 4
        x = left_x + col * (w + col_gap)
        y = top_y + row * (h + row_gap)
        buttons.append(
            Button(
                rect=pygame.Rect(x, y, w, h),
                label=f"VIEW {cam_idx:02d}",
                action="view_camera",
                value=cam_idx,
                active=sandbox_camera == cam_idx,
            )
        )

    tele_y = top_y + 3 * (h + row_gap) + 24
    for idx, cam_idx in enumerate(cam_nodes):
        row = idx // 4
        col = idx % 4
        x = left_x + col * (w + col_gap)
        y = tele_y + row * (h + row_gap)
        buttons.append(
            Button(
                rect=pygame.Rect(x, y, w, h),
                label=f"ALG {cam_idx:02d}",
                action="teleport_algem",
                value=cam_idx,
                active=sandbox_algem_node == cam_idx,
            )
        )

    utility_x = left_x + 4 * (w + col_gap) + 18
    utility_y = top_y
    util_w = 170

    buttons.append(
        Button(
            rect=pygame.Rect(utility_x, utility_y, util_w, h),
            label=f"MOVING: {'ON' if sandbox_moving else 'OFF'}",
            action="toggle_moving",
            active=sandbox_moving,
        )
    )
    buttons.append(
        Button(
            rect=pygame.Rect(utility_x, utility_y + 1 * (h + row_gap), util_w, h),
            label=f"VENT MAP: {'ON' if view.vent_map_mode else 'OFF'}",
            action="toggle_vent_map",
            active=view.vent_map_mode,
        )
    )
    buttons.append(
        Button(
            rect=pygame.Rect(utility_x, utility_y + 2 * (h + row_gap), util_w, h),
            label="RESET SEALS",
            action="reset_seals",
        )
    )
    buttons.append(
        Button(
            rect=pygame.Rect(utility_x, utility_y + 3 * (h + row_gap), util_w, h),
            label="STOP VENT LOOP",
            action="stop_vent_audio",
            warn=True,
        )
    )

    seal_y = utility_y + 4 * (h + row_gap) + 18
    for idx, seal_id in enumerate(SEAL_ORDER):
        state = model.seals[seal_id]
        buttons.append(
            Button(
                rect=pygame.Rect(utility_x, seal_y + idx * (h + row_gap), util_w, h),
                label=f"{SEAL_LABELS[seal_id]}: {state.name}",
                action="seal",
                value=seal_id,
                active=state in (SealState.SEALING, SealState.CLOSED),
                warn=state == SealState.CLOSED,
            )
        )

    return buttons


def _draw_button(surface: pygame.Surface, font: pygame.font.Font, button: Button) -> None:
    bg = BTN_BG_WARN if button.warn else BTN_BG_ACTIVE if button.active else BTN_BG
    pygame.draw.rect(surface, bg, button.rect)
    pygame.draw.rect(surface, BTN_BORDER, button.rect, 1)
    label = font.render(button.label, True, BTN_TEXT)
    surface.blit(
        label,
        (
            button.rect.centerx - label.get_width() // 2,
            button.rect.centery - label.get_height() // 2,
        ),
    )


def _safe_float_call(default: float, func, *args, **kwargs) -> float:
    try:
        return float(func(*args, **kwargs))
    except Exception:
        return default


def _safe_int_call(default: int, func, *args, **kwargs) -> int:
    try:
        return int(func(*args, **kwargs))
    except Exception:
        return default


def _draw_overlay(
    screen: pygame.Surface,
    title_font: pygame.font.Font,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
    model: GameModel,
    view: GameView,
    presenter: GamePresenter,
    buttons: list[Button],
    camera_names: dict[int, str],
    sandbox_algem_node: int,
    sandbox_camera: int,
    sandbox_moving: bool,
) -> None:
    panel = pygame.Surface((760, 570), pygame.SRCALPHA)
    panel.fill(PANEL_BG)
    pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 1)
    screen.blit(panel, (18, 16))

    listener_node = _safe_int_call(
        sandbox_camera,
        presenter._listener_audio_node,
        camera_idx=sandbox_camera,
        tablet_open=model.tablet_open,
        tablet_animating=model.tablet_animating,
    )
    talk_bucket = _safe_int_call(
        4,
        presenter._camera_audio_distance,
        listener_node,
        sandbox_algem_node,
    )
    talk_weight = _safe_float_call(
        9999.0,
        presenter._audio_weighted_distance,
        listener_node,
        sandbox_algem_node,
    )
    talk_target = _safe_float_call(
        0.0,
        presenter._current_audio_volume,
        sandbox_algem_node,
        "algem_talk",
    )

    vent_bucket = presenter._vent_listen_distance(
        algem_node=sandbox_algem_node,
        camera_idx=sandbox_camera,
        last_regular_cam=getattr(presenter, "_last_regular_cam", sandbox_camera),
        tablet_open=model.tablet_open,
        tablet_animating=model.tablet_animating,
    )
    vent_weight = _safe_float_call(
        9999.0,
        presenter._vent_listen_weighted_distance,
        algem_node=sandbox_algem_node,
        camera_idx=sandbox_camera,
        last_regular_cam=getattr(presenter, "_last_regular_cam", sandbox_camera),
        tablet_open=model.tablet_open,
        tablet_animating=model.tablet_animating,
    )
    vent_target = _safe_float_call(
        0.0,
        presenter._vent_listen_volume,
        algem_node=sandbox_algem_node,
        camera_idx=sandbox_camera,
        last_regular_cam=getattr(presenter, "_last_regular_cam", sandbox_camera),
        tablet_open=model.tablet_open,
        tablet_animating=model.tablet_animating,
    )
    seal_gain = _safe_float_call(
        1.0,
        presenter._source_seal_audio_gain,
        sandbox_algem_node,
    )

    vent_busy = presenter._vent_sound_channel.get_busy()
    vent_volume = presenter._vent_sound_channel.get_volume() if vent_busy else 0.0
    talk_busy = presenter._algem_talk_channel.get_busy()
    talk_volume = presenter._algem_talk_channel.get_volume() if talk_busy else 0.0
    block_signature = presenter._vent_block_signature

    _draw_text(screen, title_font, "VENT AUDIO SANDBOX", (28, 24), TEXT_MAIN)
    _draw_text(
        screen,
        small_font,
        "Teleport Algem, switch cameras, toggle moving, and seal vents by hand.",
        (28, 58),
        TEXT_ACCENT,
    )

    direct_vent_view = (
        sandbox_algem_node in {8, 9, 10, 11}
        and sandbox_camera == sandbox_algem_node
        and model.tablet_open
        and not model.tablet_animating
        and not view.vent_map_mode
    )
    if sandbox_algem_node not in {8, 9, 10, 11}:
        vent_note = "crawl N/A: Algem is not in a vent"
    elif direct_vent_view:
        vent_note = "direct vent view: crawl muted"
    elif not sandbox_moving:
        vent_note = "crawl idle: Algem is not moving"
    else:
        vent_note = "distance-based crawl"

    lines = [
        f"Viewed camera: {sandbox_camera:02d}  |  {camera_names.get(sandbox_camera, '?')}",
        f"Algem position: {sandbox_algem_node:02d}  |  {camera_names.get(sandbox_algem_node, '?')}",
        f"Listener node: {listener_node:02d}    Moving: {'ON' if sandbox_moving else 'OFF'}    Vent map: {'ON' if view.vent_map_mode else 'OFF'}",  # noqa: E501
        f"TALK target: {talk_target:.2f}    channel: {'ON' if talk_busy else 'OFF'} / {talk_volume:.2f}    bucket: {talk_bucket}    weight: {talk_weight:.2f}",  # noqa: E501
        f"VENT target: {vent_target:.2f}    channel: {'ON' if vent_busy else 'OFF'} / {vent_volume:.2f}    bucket: {vent_bucket}    weight: {vent_weight:.2f}",  # noqa: E501
        f"VENT note: {vent_note}    seal gain: {seal_gain:.2f}",
        f"Block signature: {block_signature}",
        f"Seal progress: current={model.currently_sealing_id}",
    ]

    y = 92
    for line in lines:
        _draw_text(screen, font, line, (28, y), TEXT_MAIN)
        y += 24

    _draw_text(screen, small_font, "View camera", (28, 226), TEXT_MUTED)
    _draw_text(screen, small_font, "Teleport Algem", (28, 348), TEXT_MUTED)
    _draw_text(screen, small_font, "Utility / seals", (430, 226), TEXT_MUTED)

    for button in buttons:
        _draw_button(screen, small_font, button)

    controls = "Mouse: click buttons  |  ESC: quit  |  R: reset seals  |  M: moving  |  V: vent map  |  T: force talk"
    _draw_text(screen, small_font, controls, (28, 544), TEXT_MUTED)


def _handle_button(
    button: Button,
    model: GameModel,
    view: GameView,
    presenter: GamePresenter,
    sandbox_state: dict[str, object],
) -> None:
    action = button.action

    if action == "view_camera":
        sandbox_state["camera"] = int(button.value)
        presenter._switch_camera(int(button.value))
        return

    if action == "teleport_algem":
        sandbox_state["algem_node"] = int(button.value)
        return

    if action == "toggle_moving":
        sandbox_state["moving"] = not bool(sandbox_state["moving"])
        return

    if action == "toggle_vent_map":
        view.vent_map_mode = not view.vent_map_mode
        return

    if action == "reset_seals":
        _reset_seals(model, presenter)
        return

    if action == "stop_vent_audio":
        presenter._vent_sound_channel.stop()
        presenter._vent_sound_timer = 0
        return

    if action == "seal":
        seal_id = str(button.value)
        if model.seals[seal_id] == SealState.CLOSED:
            model.seals[seal_id] = SealState.OPEN
            if model.currently_sealing_id == seal_id:
                model.currently_sealing_id = None
            presenter._prev_seal_states = dict(model.seals)
            presenter._vent_block_signature = None
            return
        if model.currently_sealing_id is None and model.seals[seal_id] == SealState.OPEN:
            model.start_seal(seal_id)
            presenter._play_seal_sound()


def main() -> None:
    pygame.init()
    pygame.mixer.set_num_channels(16)

    screen = pygame.display.set_mode(SCREEN_SIZE)
    pygame.display.set_caption("Five Nights At RTF - Vent Audio Sandbox")
    icon = _load_window_icon()
    if icon is not None:
        pygame.display.set_icon(icon)

    clock = pygame.time.Clock()
    title_font = pygame.font.Font(None, 34)
    font = pygame.font.Font(None, 28)
    small_font = pygame.font.Font(None, 24)
    camera_names = _camera_name_map()

    model = GameModel(night=2)
    view = GameView(screen)
    presenter = GamePresenter(model, view)

    presenter.snd_startnight = None
    presenter.snd_phone_call = None
    presenter.snd_ambience = None
    presenter.snd_work = None
    model.phone_call_ready = False
    model.phone_call_active = False
    model._phone_timer = 999999

    sandbox_state: dict[str, object] = {
        "algem_node": 9,
        "camera": 2,
        "moving": True,
    }

    _reset_seals(model, presenter)
    _prepare_tablet(model, view, presenter)
    view.vent_map_mode = False
    presenter._switch_camera(int(sandbox_state["camera"]))

    running = True
    while running:
        buttons = _make_buttons(
            sandbox_algem_node=int(sandbox_state["algem_node"]),
            sandbox_camera=int(sandbox_state["camera"]),
            sandbox_moving=bool(sandbox_state["moving"]),
            view=view,
            model=model,
        )

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                    continue
                if event.key == pygame.K_r:
                    _reset_seals(model, presenter)
                elif event.key == pygame.K_m:
                    sandbox_state["moving"] = not bool(sandbox_state["moving"])
                elif event.key == pygame.K_v:
                    view.vent_map_mode = not view.vent_map_mode
                elif event.key == pygame.K_t:
                    presenter._algem_talk_timer = 0
                    if presenter._algem_talk_channel.get_busy():
                        presenter._algem_talk_channel.stop()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for button in buttons:
                    if button.rect.collidepoint(event.pos):
                        _handle_button(button, model, view, presenter, sandbox_state)
                        break

        _prepare_tablet(model, view, presenter)
        presenter._switch_camera(int(sandbox_state["camera"]))
        _set_algem(
            model,
            int(sandbox_state["algem_node"]),
            moving=bool(sandbox_state["moving"]),
        )

        model.update()

        _prepare_tablet(model, view, presenter)
        presenter._switch_camera(int(sandbox_state["camera"]))
        _set_algem(
            model,
            int(sandbox_state["algem_node"]),
            moving=bool(sandbox_state["moving"]),
        )

        presenter.update()
        view.draw(model)

        buttons = _make_buttons(
            sandbox_algem_node=int(sandbox_state["algem_node"]),
            sandbox_camera=int(sandbox_state["camera"]),
            sandbox_moving=bool(sandbox_state["moving"]),
            view=view,
            model=model,
        )
        _draw_overlay(
            screen,
            title_font,
            font,
            small_font,
            model,
            view,
            presenter,
            buttons,
            camera_names,
            int(sandbox_state["algem_node"]),
            int(sandbox_state["camera"]),
            bool(sandbox_state["moving"]),
        )

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
