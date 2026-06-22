"""Laptop perspective projection and its in-game calibration overlay."""

import json
import os

import cv2
import numpy as np
import pygame


DEFAULT_LAPTOP_PROJECTION_CORNERS = [
    [419, 494],
    [567, 474],
    [593, 576],
    [445, 610],
]
LAPTOP_PROJECTION_CONFIG_PATH = os.path.join(
    os.environ.get("APPDATA", "."), "FiveNightsAtRTF", "laptop_projection.json"
)


class LaptopProjectionMixin:
    """Provide projection persistence, geometry, and editor rendering."""

    def load_laptop_projection(self) -> None:
        """Load laptop projection corners from a JSON config if it exists.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        if not os.path.exists(self._projection_config_path):
            return
        try:
            with open(self._projection_config_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            corners = data.get("corners")
            if not isinstance(corners, list) or len(corners) != 4:
                return
            parsed = []
            for pair in corners:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    return
                parsed.append([float(pair[0]), float(pair[1])])
            self._lp_base_corners = np.float32(parsed)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    def save_laptop_projection(self) -> None:
        """Save current laptop projection corners to disk.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        data = {
            "corners": [
                [int(round(x)), int(round(y))]
                for x, y in self._lp_base_corners.tolist()
            ]
        }
        with open(self._projection_config_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=True, indent=2)

    def reset_laptop_projection(self) -> None:
        """Reset the laptop projection to the default tuned trapezoid.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        self._lp_base_corners = np.float32(DEFAULT_LAPTOP_PROJECTION_CORNERS)
        self._rebuild_laptop_projection()

    def _rebuild_laptop_projection(self) -> None:
        """Recompute the perspective transform after any corner edit.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        dst = self._lp_base_corners * self.scale
        x_min, y_min = dst.min(axis=0).astype(int)
        x_max, y_max = dst.max(axis=0).astype(int)
        self._lp_out_w = max(1, int(x_max - x_min))
        self._lp_out_h = max(1, int(y_max - y_min))
        self._lp_blit_origin = (int(x_min), int(y_min))

        src_c = np.float32(
            [
                [0, 0],
                [self._lp_out_w, 0],
                [self._lp_out_w, self._lp_out_h],
                [0, self._lp_out_h],
            ]
        )
        dst_c = (dst - np.array([x_min, y_min])).astype(np.float32)
        self._lp_M = cv2.getPerspectiveTransform(src_c, dst_c)

    def get_laptop_projection_corners_screen(
        self, offset: int = 0
    ) -> list[tuple[int, int]]:
        """Return projection corners in active screen coordinates.

        Args:
            offset: Параметр типа ``int``, используемый методом ``get_laptop_projection_corners_screen``.

        Returns:
            Значение типа ``list[tuple[int, int]]``."""
        return [
            (int(round(x * self.scale)) - offset, int(round(y * self.scale)))
            for x, y in self._lp_base_corners.tolist()
        ]

    def get_laptop_projection_corner_hit(
        self, mouse_pos: tuple[int, int], offset: int = 0, radius: int = 18
    ) -> int | None:
        """Return the nearest projection corner index under the mouse.

        Args:
            mouse_pos: Параметр типа ``tuple[int, int]``, используемый методом ``get_laptop_projection_corner_hit``.
            offset: Параметр типа ``int``, используемый методом ``get_laptop_projection_corner_hit``.
            radius: Параметр типа ``int``, используемый методом ``get_laptop_projection_corner_hit``.

        Returns:
            Значение типа ``int | None``."""
        mx, my = mouse_pos
        best_idx = None
        best_dist_sq = radius * radius
        for idx, (cx, cy) in enumerate(
            self.get_laptop_projection_corners_screen(offset)
        ):
            dx = mx - cx
            dy = my - cy
            dist_sq = dx * dx + dy * dy
            if dist_sq <= best_dist_sq:
                best_idx = idx
                best_dist_sq = dist_sq
        return best_idx

    def move_laptop_projection_corner(
        self, corner_idx: int, mouse_pos: tuple[int, int], offset: int = 0
    ) -> None:
        """Move one projection corner using current screen coordinates.

        Args:
            corner_idx: Параметр типа ``int``, используемый методом ``move_laptop_projection_corner``.
            mouse_pos: Параметр типа ``tuple[int, int]``, используемый методом ``move_laptop_projection_corner``.
            offset: Параметр типа ``int``, используемый методом ``move_laptop_projection_corner``.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        x = (mouse_pos[0] + offset) / self.scale
        y = mouse_pos[1] / self.scale
        self._lp_base_corners[corner_idx] = [x, y]
        self._rebuild_laptop_projection()

    def nudge_laptop_projection_corner(
        self, corner_idx: int, dx: float, dy: float
    ) -> None:
        """Fine-tune one projection corner in source-image pixels.

        Args:
            corner_idx: Параметр типа ``int``, используемый методом ``nudge_laptop_projection_corner``.
            dx: Параметр типа ``float``, используемый методом ``nudge_laptop_projection_corner``.
            dy: Параметр типа ``float``, используемый методом ``nudge_laptop_projection_corner``.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        self._lp_base_corners[corner_idx][0] += dx
        self._lp_base_corners[corner_idx][1] += dy
        self._rebuild_laptop_projection()

    def draw_laptop_projection_editor(
        self,
        surface: pygame.Surface,
        offset: int,
        active_corner: int | None,
        dragging: bool,
    ) -> None:
        """Draw an in-game overlay for live laptop projection editing.

        Args:
            surface: Параметр типа ``pygame.Surface``, используемый методом ``draw_laptop_projection_editor``.
            offset: Параметр типа ``int``, используемый методом ``draw_laptop_projection_editor``.
            active_corner: Параметр типа ``int | None``, используемый методом ``draw_laptop_projection_editor``.
            dragging: Параметр типа ``bool``, используемый методом ``draw_laptop_projection_editor``.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        corners = self.get_laptop_projection_corners_screen(offset)
        if len(corners) == 4:
            pygame.draw.lines(surface, (70, 220, 255), True, corners, 2)

        labels = ["TL", "TR", "BR", "BL"]
        for idx, (cx, cy) in enumerate(corners):
            color = (255, 210, 60) if idx == active_corner else (255, 110, 110)
            radius = 7 if idx == active_corner else 5
            pygame.draw.circle(surface, color, (cx, cy), radius)
            pygame.draw.circle(surface, (20, 20, 20), (cx, cy), radius, 2)
            tag = self._ctext(self._ui_font_bold, labels[idx], (255, 255, 255))
            surface.blit(tag, (cx + 12, cy - 10))

        panel = pygame.Rect(18, 18, 355, 178)
        panel_bg = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
        panel_bg.fill((8, 12, 18, 210))
        surface.blit(panel_bg, panel.topleft)
        pygame.draw.rect(surface, (70, 220, 255), panel, 2, border_radius=8)

        title = self._ctext(
            self._ui_font_bold, "Laptop Projection Editor [F8]", (255, 255, 255)
        )
        surface.blit(title, (panel.x + 12, panel.y + 10))

        status = "Drag corners with mouse"
        if dragging:
            status = "Dragging selected corner"
        status_surf = self._ctext(self._ui_font_sm, status, (180, 220, 235))
        surface.blit(status_surf, (panel.x + 12, panel.y + 34))

        hint = self._ctext(
            self._ui_font_sm,
            "1-4 select, arrows move, Shift=faster, S save, R reset",
            (160, 185, 200),
        )
        surface.blit(hint, (panel.x + 12, panel.y + 54))

        for idx, (x, y) in enumerate(self._lp_base_corners.tolist()):
            line_color = (255, 225, 130) if idx == active_corner else (210, 210, 210)
            text = self._ctext(
                self._ui_font_sm,
                f"{idx + 1}. {labels[idx]}  x={int(round(x))}  y={int(round(y))}",
                line_color,
            )
            surface.blit(text, (panel.x + 12, panel.y + 82 + idx * 20))
