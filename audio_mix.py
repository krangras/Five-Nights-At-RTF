from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable

import pygame

SOUNDS_ROOT = Path("sounds")
MAX_VOLUME = 2.0

AUDIO_ID_ALIASES: dict[str, str] = {
    "menu_music": "sounds/menu/Faulty_Ventilation.mp3",
    "menu_hover": "sounds/ui/blip3.mp3",
    "server_on": "sounds/server/server_turning_on.mp3",
    "server_loop": "sounds/server/server_is_working.mp3",
    "server_off": "sounds/server/server_turning_off.mp3",
    "tablet_toggle": "sounds/ui/blip3.mp3",
    "camera_switch": "sounds/cameras/camera_switch.wav",
    "camera_init": "sounds/cameras/camera_init.wav",
    "office_ambience": "sounds/ambience/ambience.wav",
    "algem_leave": "sounds/threats/alegem_is_leaving.wav",
    "phone_call": "sounds/ui/callnight1.mp3",
    "night_start": "sounds/ui/night_starts.wav",
    "night_end": "sounds/ui/night_ends.wav",
    "reboot_loop": "sounds/ui/wait.wav",
    "vent_close": "sounds/vents/vent_close.wav",
    "vent_knock": "sounds/vents/knock.wav",
    "danger_loop": "sounds/threats/danger2b.wav",
    "gadget_audio": "sounds/ui/gadget1.mp3",
    "algem_talk": "sounds/ambience/ambience1.mp3",
    "vent_presence": "sounds/vents/vent_closer1.wav",
    "ad_loop": "sounds/laptop/ad.wav",
    "glitch_voice": "sounds/glitches/robotvoice.wav",
    "screamer": "sounds/screamer/screamer.mp3",
    "lecture": "sounds/lectures/lecture1.mp3",
    "final_music": "sounds/final_scene/mb2.wav",
    "final_speech": "sounds/final_scene/algems' final speech.mp3",
}


def _discover_sound_files() -> list[str]:
    if not SOUNDS_ROOT.exists():
        return sorted(set(AUDIO_ID_ALIASES.values()))

    paths: list[str] = []
    for path in SOUNDS_ROOT.rglob("*"):
        if path.is_file():
            paths.append(path.as_posix())
    for alias_target in AUDIO_ID_ALIASES.values():
        if alias_target not in paths:
            paths.append(alias_target)
    return sorted(paths)


ALL_SOUND_PATHS: list[str] = _discover_sound_files()

AUDIO_MIX_DEFAULTS: dict[str, object] = {
    "master": 1.0,
    "sounds": {path: 1.0 for path in ALL_SOUND_PATHS},
}


def default_audio_mix() -> dict:
    return deepcopy(AUDIO_MIX_DEFAULTS)


def ensure_audio_settings(settings_data: dict | None) -> dict:
    if settings_data is None:
        settings_data = {}
    settings_data["audio_mix"] = normalize_audio_mix(settings_data.get("audio_mix"))
    return settings_data


def normalize_audio_mix(audio_mix: dict | None) -> dict:
    mix = default_audio_mix()
    if not isinstance(audio_mix, dict):
        return mix

    mix["master"] = _clamp_volume(audio_mix.get("master", mix["master"]))

    raw_sounds = audio_mix.get("sounds", {})
    if isinstance(raw_sounds, dict):
        migrated = _migrate_legacy_sound_keys(raw_sounds)
        for path in ALL_SOUND_PATHS:
            mix["sounds"][path] = _clamp_volume(migrated.get(path, mix["sounds"][path]))

    return mix


def effective_volume(settings_data: dict | None, sound_id: str, base: float) -> float:
    mix = normalize_audio_mix((settings_data or {}).get("audio_mix"))
    sound_path = resolve_sound_id(sound_id)
    sound_level = mix["sounds"].get(sound_path, 1.0)
    return _clamp_volume(base * mix["master"] * sound_level)


def apply_music_volume(settings_data: dict | None, sound_id: str, base: float) -> None:
    pygame.mixer.music.set_volume(effective_volume(settings_data, sound_id, base))


def resolve_sound_id(sound_id: str) -> str:
    return AUDIO_ID_ALIASES.get(sound_id, sound_id.replace("\\", "/"))


class AudioCalibrationOverlay:
    def __init__(
        self,
        settings_data: dict,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self.settings_data = ensure_audio_settings(settings_data)
        self.on_change = on_change
        self.visible = False
        self.selected_index = 0
        self.scroll_offset = 0
        self.dragging_index: int | None = None
        self._font = pygame.font.Font(None, 28)
        self._small_font = pygame.font.Font(None, 22)
        self._tiny_font = pygame.font.Font(None, 18)
        self._rows = self._build_rows()
        self._sidebar_rect = pygame.Rect(0, 0, 0, 0)
        self._row_hitboxes: list[tuple[pygame.Rect, int, str]] = []
        self._preview_cache: dict[str, pygame.mixer.Sound | None] = {}
        self._preview_channel: pygame.mixer.Channel | None = None
        self._preview_sound_id: str | None = None
        self._preview_base_volume: float = 1.0

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.KEYDOWN:
            return self._handle_keydown(event)

        if not self.visible:
            return False

        if event.type == pygame.MOUSEWHEEL:
            self.scroll_offset = max(0, min(self._max_scroll(), self.scroll_offset - event.y * 2))
            return True
        if event.type == pygame.MOUSEMOTION and self.dragging_index is not None:
            return self._handle_drag(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                return self._handle_click(event.pos)
            if event.button == 4:
                self.scroll_offset = max(0, self.scroll_offset - 2)
                return True
            if event.button == 5:
                self.scroll_offset = min(self._max_scroll(), self.scroll_offset + 2)
                return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragging_index is not None:
            self.dragging_index = None
            return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return

        sw, sh = surface.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((5, 8, 12, 120))
        surface.blit(overlay, (0, 0))

        sidebar_w = min(760, sw - 40)
        panel = pygame.Rect(sw - sidebar_w - 20, 20, sidebar_w, sh - 40)
        self._sidebar_rect = panel
        self._row_hitboxes = []
        pygame.draw.rect(surface, (10, 15, 24), panel, border_radius=14)
        pygame.draw.rect(surface, (110, 180, 235), panel, 2, border_radius=14)

        title = self._font.render("All Sounds", True, (240, 248, 255))
        hint = self._tiny_font.render(
            "F10/F9 toggle  Mouse wheel scroll  Click +/-  PLAY previews file  Enter plays selected  F5 reset",
            True,
            (165, 190, 210),
        )
        surface.blit(title, (panel.x + 20, panel.y + 18))
        surface.blit(hint, (panel.x + 20, panel.y + 48))

        viewport_top = panel.y + 88
        viewport_bottom = panel.bottom - 42
        row_h = 34
        visible_rows = max(1, (viewport_bottom - viewport_top) // row_h)
        start = min(self.scroll_offset, max(0, len(self._rows) - visible_rows))
        end = min(len(self._rows), start + visible_rows)
        row_y = viewport_top
        for index in range(start, end):
            row = self._rows[index]
            self._draw_row(surface, panel.x + 16, row_y, panel.w - 32, row, index, index == self.selected_index)
            row_y += row_h

        footer = self._tiny_font.render(
            "Range: 0% to 200%. Names are the real files from sounds/.",
            True,
            (170, 190, 205),
        )
        surface.blit(footer, (panel.x + 20, panel.bottom - 28))
        self._draw_scrollbar(surface, panel, visible_rows)

    def _handle_keydown(self, event: pygame.event.Event) -> bool:
        if event.key in (pygame.K_F10, pygame.K_F9, pygame.K_BACKQUOTE):
            self.visible = not self.visible
            return True

        if not self.visible:
            return False

        if event.key == pygame.K_ESCAPE:
            self.visible = False
            return True
        if event.key == pygame.K_UP:
            self.selected_index = max(0, self.selected_index - 1)
            self._ensure_selected_visible()
            return True
        if event.key == pygame.K_DOWN:
            self.selected_index = min(len(self._rows) - 1, self.selected_index + 1)
            self._ensure_selected_visible()
            return True
        if event.key == pygame.K_PAGEUP:
            self.selected_index = max(0, self.selected_index - 10)
            self._ensure_selected_visible()
            return True
        if event.key == pygame.K_PAGEDOWN:
            self.selected_index = min(len(self._rows) - 1, self.selected_index + 10)
            self._ensure_selected_visible()
            return True
        if event.key == pygame.K_LEFT:
            self._adjust_selected(-self._step_for_mods(event.mod))
            return True
        if event.key == pygame.K_RIGHT:
            self._adjust_selected(self._step_for_mods(event.mod))
            return True
        if event.key == pygame.K_r:
            self._reset_selected()
            return True
        if event.key == pygame.K_F5:
            self.settings_data["audio_mix"] = default_audio_mix()
            self._notify_change()
            return True
        if event.key == pygame.K_RETURN:
            self._play_selected()
            return True
        return True

    def _draw_row(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        width: int,
        row: dict[str, str],
        index: int,
        is_selected: bool,
    ) -> None:
        row_rect = pygame.Rect(x, y - 2, width, 30)
        label_color = (250, 250, 250) if is_selected else (205, 220, 230)
        bar_color = (85, 200, 240) if is_selected else (70, 125, 170)
        if is_selected:
            pygame.draw.rect(surface, (28, 44, 64), row_rect, border_radius=6)

        key = row["key"]
        value = self._get_value(row)
        label_font = self._tiny_font if row["kind"] == "sound" else self._small_font
        label = label_font.render(row["label"], True, label_color)
        value_text = self._small_font.render(f"{int(value * 100):3d}%", True, label_color)
        surface.blit(label, (x + 4, y + 2))
        surface.blit(value_text, (x + width - 72, y + 2))

        play_rect = pygame.Rect(x + width - 44, y + 3, 44, 22)
        plus_rect = pygame.Rect(play_rect.x - 29, y + 3, 24, 22)
        minus_rect = pygame.Rect(plus_rect.x - 27, y + 3, 24, 22)
        bar_rect = pygame.Rect(minus_rect.x - 128, y + 10, 120, 8)
        pygame.draw.rect(surface, (38, 52, 68), bar_rect, border_radius=5)
        fill_rect = pygame.Rect(bar_rect.x, bar_rect.y, int(bar_rect.w * (value / MAX_VOLUME)), bar_rect.h)
        pygame.draw.rect(surface, bar_color, fill_rect, border_radius=5)
        pygame.draw.rect(surface, (120, 145, 165), bar_rect, 1, border_radius=5)

        self._draw_button(surface, minus_rect, "-", is_selected)
        self._draw_button(surface, plus_rect, "+", is_selected)
        self._draw_button(surface, play_rect, "PLAY", is_selected, small=True)

        self._row_hitboxes.append((row_rect, index, "select"))
        self._row_hitboxes.append((bar_rect, index, "drag"))
        self._row_hitboxes.append((minus_rect, index, "minus"))
        self._row_hitboxes.append((plus_rect, index, "plus"))
        self._row_hitboxes.append((play_rect, index, "play"))
        _ = key

    def _draw_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        text: str,
        highlighted: bool,
        small: bool = False,
    ) -> None:
        fill = (40, 70, 96) if highlighted else (28, 46, 64)
        edge = (120, 175, 220) if highlighted else (88, 130, 166)
        pygame.draw.rect(surface, fill, rect, border_radius=5)
        pygame.draw.rect(surface, edge, rect, 1, border_radius=5)
        font = self._tiny_font if small else self._small_font
        txt = font.render(text, True, (240, 248, 255))
        surface.blit(txt, (rect.centerx - txt.get_width() // 2, rect.centery - txt.get_height() // 2))

    def _build_rows(self) -> list[dict[str, str]]:
        rows = [{"kind": "master", "key": "master", "label": "MASTER"}]
        for sound_path in ALL_SOUND_PATHS:
            rows.append({"kind": "sound", "key": sound_path, "label": sound_path})
        return rows

    def _get_value(self, row: dict[str, str]) -> float:
        mix = self.settings_data["audio_mix"]
        if row["kind"] == "master":
            return mix["master"]
        return mix["sounds"][row["key"]]

    def _set_value(self, row: dict[str, str], value: float) -> None:
        mix = self.settings_data["audio_mix"]
        if row["kind"] == "master":
            mix["master"] = _clamp_volume(value)
        else:
            mix["sounds"][row["key"]] = _clamp_volume(value)
        self._notify_change()

    def _adjust_selected(self, delta: float) -> None:
        row = self._rows[self.selected_index]
        self._set_value(row, self._get_value(row) + delta)

    def _reset_selected(self) -> None:
        defaults = default_audio_mix()
        row = self._rows[self.selected_index]
        if row["kind"] == "master":
            self._set_value(row, defaults["master"])
        else:
            self._set_value(row, defaults["sounds"].get(row["key"], 1.0))

    def _notify_change(self) -> None:
        self.settings_data["audio_mix"] = normalize_audio_mix(self.settings_data["audio_mix"])
        self._refresh_preview_volume()
        if self.on_change is not None:
            self.on_change()

    def _play_selected(self) -> None:
        row = self._rows[self.selected_index]
        if row["kind"] == "sound":
            self._play_preview(row["key"])

    def _play_preview(self, sound_path: str) -> None:
        snd = self._preview_cache.get(sound_path)
        if snd is None:
            try:
                snd = pygame.mixer.Sound(sound_path)
            except pygame.error:
                snd = None
            self._preview_cache[sound_path] = snd
        if snd is None:
            return
        self._preview_sound_id = sound_path
        self._preview_base_volume = 1.0
        snd.set_volume(effective_volume(self.settings_data, sound_path, self._preview_base_volume))
        if self._preview_channel is None:
            self._preview_channel = pygame.mixer.Channel(15)
        self._preview_channel.stop()
        self._preview_channel.play(snd)

    def _handle_click(self, pos: tuple[int, int]) -> bool:
        if not self._sidebar_rect.collidepoint(pos):
            self.dragging_index = None
            self.visible = False
            return True

        for rect, index, action in reversed(self._row_hitboxes):
            if not rect.collidepoint(pos):
                continue
            self.selected_index = index
            self._ensure_selected_visible()
            row = self._rows[index]
            step = 0.02
            if action == "minus":
                self._set_value(row, self._get_value(row) - step)
            elif action == "plus":
                self._set_value(row, self._get_value(row) + step)
            elif action == "play" and row["kind"] == "sound":
                self._play_preview(row["key"])
            elif action == "drag":
                self.dragging_index = index
                self._handle_drag(pos)
            return True
        return True

    def _handle_drag(self, pos: tuple[int, int]) -> bool:
        if self.dragging_index is None:
            return False
        target = None
        for rect, index, action in reversed(self._row_hitboxes):
            if index == self.dragging_index and action == "drag":
                target = rect
                break
        if target is None:
            return False

        row = self._rows[self.dragging_index]
        relative = (pos[0] - target.x) / max(1, target.w)
        self._set_value(row, _clamp_volume(relative * MAX_VOLUME))
        if row["kind"] == "sound":
            if self._preview_sound_id != row["key"] or self._preview_channel is None or not self._preview_channel.get_busy():
                self._play_preview(row["key"])
            else:
                self._refresh_preview_volume()
        else:
            self._refresh_preview_volume()
        return True

    def _refresh_preview_volume(self) -> None:
        if self._preview_sound_id is None or self._preview_channel is None:
            return
        if not self._preview_channel.get_busy():
            return
        self._preview_channel.set_volume(
            effective_volume(
                self.settings_data,
                self._preview_sound_id,
                self._preview_base_volume,
            )
        )

    def _draw_scrollbar(self, surface: pygame.Surface, panel: pygame.Rect, visible_rows: int) -> None:
        if len(self._rows) <= visible_rows:
            return
        track = pygame.Rect(panel.right - 10, panel.y + 90, 4, panel.h - 140)
        pygame.draw.rect(surface, (28, 46, 64), track, border_radius=4)
        thumb_h = max(24, int(track.h * (visible_rows / len(self._rows))))
        max_scroll = max(1, self._max_scroll())
        thumb_y = track.y + int((track.h - thumb_h) * (self.scroll_offset / max_scroll))
        pygame.draw.rect(surface, (110, 180, 235), (track.x, thumb_y, track.w, thumb_h), border_radius=4)

    def _ensure_selected_visible(self) -> None:
        viewport_rows = 15
        if self.selected_index < self.scroll_offset:
            self.scroll_offset = self.selected_index
        elif self.selected_index >= self.scroll_offset + viewport_rows:
            self.scroll_offset = self.selected_index - viewport_rows + 1

    def _max_scroll(self) -> int:
        return max(0, len(self._rows) - 15)

    @staticmethod
    def _step_for_mods(mod: int) -> float:
        if mod & pygame.KMOD_SHIFT:
            return 0.01
        if mod & pygame.KMOD_CTRL:
            return 0.10
        return 0.02


def _migrate_legacy_sound_keys(raw_sounds: dict) -> dict[str, object]:
    migrated: dict[str, object] = {}
    for key, value in raw_sounds.items():
        migrated[resolve_sound_id(str(key))] = value
    return migrated


def _clamp_volume(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(MAX_VOLUME, number))
