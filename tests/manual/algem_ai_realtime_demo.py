from __future__ import annotations

import copy
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pygame

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fnar.gameplay.algem_ai import AIState, astar_path, bfs_path
from fnar.gameplay.model import (
    BASE_GRAPH,
    CAMERAS,
    PATROL_GRAPH,
    SEAL_CAMERA_MAP,
    VENT_CAMERAS,
    VENT_SEALS,
    GameModel,
    SealState,
)

WIDTH = 1180
HEIGHT = 760
FPS = 60

BG = (15, 16, 20)
PANEL = (27, 30, 38)
PANEL_2 = (35, 39, 49)
TEXT = (232, 236, 244)
MUTED = (155, 164, 180)
LINE = (73, 79, 94)
GREEN = (91, 209, 132)
YELLOW = (238, 194, 85)
RED = (236, 94, 94)
BLUE = (100, 161, 255)
VENT = (187, 122, 255)
OFFICE = (255, 137, 93)

NODE_POS = {
    0: (1040, 360),
    1: (165, 185),
    2: (325, 145),
    3: (325, 265),
    4: (500, 265),
    5: (650, 265),
    6: (795, 265),
    7: (890, 420),
    8: (220, 435),
    9: (455, 475),
    10: (785, 475),
    11: (620, 420),
}

CAMERA_NAMES = {idx: name for idx, _label, name, _image in CAMERAS}
CAMERA_NAMES[0] = "OFFICE / BREACH"


@dataclass
class Button:
    rect: pygame.Rect
    text: str
    action: Callable[[], None]

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, active: bool = False) -> None:
        color = BLUE if active else PANEL_2
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        pygame.draw.rect(surface, LINE, self.rect, width=1, border_radius=8)
        label = font.render(self.text, True, TEXT)
        surface.blit(label, label.get_rect(center=self.rect.center))

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.action()
                return True
        return False


class AlgemRealtimeTest:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Algem AI realtime test")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 18)
        self.big_font = pygame.font.SysFont("consolas", 25, bold=True)
        self.small_font = pygame.font.SysFont("consolas", 15)

        self.model = GameModel(night=5)
        self.ai = self.model._ai
        self.mode = "PATROL"
        self.last_action = "ready"
        self.running = True
        self._sync_ai()
        self.buttons = self._make_buttons()

    def _make_buttons(self) -> list[Button]:
        buttons: list[Button] = []
        x = 850
        y = 24
        w = 145
        h = 38
        gap = 10
        buttons.append(Button(pygame.Rect(x, y, w, h), "PATROL", lambda: self.set_mode("PATROL")))
        buttons.append(Button(pygame.Rect(x + w + gap, y, w, h), "ATTACK", lambda: self.set_mode("ATTACK")))
        y += 54
        buttons.append(Button(pygame.Rect(x, y, w * 2 + gap, h + 8), "NEXT STEP / SPACE", self.manual_step))
        y += 66
        buttons.append(Button(pygame.Rect(x, y, w, h), "RESET", self.reset))
        buttons.append(Button(pygame.Rect(x + w + gap, y, w, h), "TO OFFICE", lambda: self.set_location(0)))
        y += 58
        for seal_id, vent_node in VENT_SEALS.items():
            buttons.append(Button(pygame.Rect(x, y, w * 2 + gap, h), f"toggle {vent_node}", lambda sid=seal_id: self.toggle_seal(sid)))
            y += h + 8
        y += 10
        for node in range(1, 12):
            col = (node - 1) % 3
            row = (node - 1) // 3
            bx = x + col * 98
            by = y + row * 34
            buttons.append(Button(pygame.Rect(bx, by, 88, 28), f"CAM {node}", lambda n=node: self.set_location(n)))
        return buttons

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.last_action = f"mode -> {mode}"
        if mode == "PATROL":
            self.ai.state = AIState.PATROL
            self.ai.attention = 0.0
            self.ai.hack_attraction = 0.0
            self.ai.cancel_audio_lure()
        else:
            self.ai.state = AIState.ATTACK
            self.ai.attention = 100.0
            self.ai.hack_attraction = 1.0
            self.ai.cancel_audio_lure()
        self._sync_ai()

    def reset(self) -> None:
        self.model = GameModel(night=5)
        self.ai = self.model._ai
        self.mode = "PATROL"
        self.last_action = "reset"
        self._sync_ai()

    def set_location(self, node: int) -> None:
        if node not in BASE_GRAPH:
            return
        old = self.ai.location
        self.ai.prev_location = old
        self.ai.location = node
        self.ai.trigger_timer = 30
        self.ai._last_path = []
        self.ai._reset_patrol_memory()
        if node == 0:
            self.ai.state = AIState.BREACH
        else:
            self.set_mode(self.mode)
        self.last_action = f"manual teleport {old} -> {node}"

    def toggle_seal(self, seal_id: str) -> None:
        state = self.model.seals[seal_id]
        self.model.seals[seal_id] = SealState.CLOSED if state == SealState.OPEN else SealState.OPEN
        self.model.currently_sealing_id = None
        self.model._seal_timers[seal_id] = 0
        self._sync_ai()
        self.last_action = f"{seal_id} -> {self.model.seals[seal_id].name}"

    def _sync_ai(self) -> dict[int, list[int]]:
        graph = self.model._build_current_graph()
        self.ai.update_graph(graph, copy.deepcopy(PATROL_GRAPH))
        return graph

    def manual_step(self) -> None:
        graph = self._sync_ai()
        before = self.ai.location

        if before == 0:
            self.last_action = "already in office / breach"
            return

        if self.mode == "PATROL":
            self.ai.state = AIState.PATROL
            self.ai.attention = 0.0
            self.ai.hack_attraction = 0.0
            self.ai.cancel_audio_lure()
            if PATROL_GRAPH.get(before):
                self.ai._step_patrol()
            else:
                target = self._nearest_patrol_node(graph)
                path = bfs_path(before, target, graph) if target is not None else None
                if path and len(path) > 1:
                    self.ai.state = AIState.RETREAT
                    self.ai._move_to(path[1], graph)
                else:
                    self.ai.state = AIState.PATROL
        else:
            self.ai.state = AIState.ATTACK if self.ai.location not in VENT_CAMERAS else AIState.VENT_STALK
            self.ai.attention = 100.0
            self.ai.hack_attraction = 1.0
            self.ai.cancel_audio_lure()
            self.ai._step_attack()

        after = self.ai.location
        self.last_action = f"step {self.mode}: {before} -> {after}"
        self._sync_ai()

    def _nearest_patrol_node(self, graph: dict[int, list[int]]) -> int | None:
        if self.ai.location in range(1, 7):
            return self.ai.location
        best: tuple[int, int] | None = None
        for node in range(1, 7):
            path = bfs_path(self.ai.location, node, graph)
            if path is None:
                continue
            candidate = (len(path), node)
            if best is None or candidate < best:
                best = candidate
        return best[1] if best else None

    def _attack_path(self, graph: dict[int, list[int]]) -> list[int]:
        path = astar_path(self.ai.location, 0, graph, self.ai._edge_weight, self.ai._base_heuristic)
        return path or []

    def _patrol_candidates(self, graph: dict[int, list[int]]) -> list[int]:
        loc = self.ai.location
        if PATROL_GRAPH.get(loc):
            return list(PATROL_GRAPH.get(loc, []))
        target = self._nearest_patrol_node(graph)
        path = bfs_path(loc, target, graph) if target is not None else None
        if path and len(path) > 1:
            return [path[1]]
        return []

    def _mode_candidates(self, graph: dict[int, list[int]]) -> tuple[list[int], list[int]]:
        if self.mode == "PATROL":
            candidates = self._patrol_candidates(graph)
            path = []
            if self.ai.location not in range(1, 7):
                target = self._nearest_patrol_node(graph)
                path = bfs_path(self.ai.location, target, graph) or [] if target is not None else []
            return candidates, path
        path = self._attack_path(graph)
        candidates = [path[1]] if len(path) > 1 else []
        return candidates, path

    def _node_label(self, node: int) -> str:
        if node == 0:
            return "OFFICE"
        name = CAMERA_NAMES.get(node, "UNKNOWN")
        tag = "VENT" if node in VENT_CAMERAS else "CAM"
        return f"{tag} {node}: {name}"

    def _seal_for_node(self, node: int) -> str:
        seal_id = SEAL_CAMERA_MAP.get(node)
        if not seal_id:
            return ""
        return self.model.seals[seal_id].name

    def _draw_text(self, text: str, pos: tuple[int, int], color: tuple[int, int, int] = TEXT, font: pygame.font.Font | None = None) -> None:
        surface = (font or self.font).render(text, True, color)
        self.screen.blit(surface, pos)

    def _draw_panel(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=10)
        pygame.draw.rect(self.screen, LINE, rect, width=1, border_radius=10)

    def _draw_graph(self, graph: dict[int, list[int]], candidates: list[int], path: list[int]) -> None:
        graph_rect = pygame.Rect(20, 20, 790, 520)
        self._draw_panel(graph_rect)
        self._draw_text("Algem graph", (38, 36), TEXT, self.big_font)

        edges = set()
        for src, dsts in graph.items():
            for dst in dsts:
                if src in NODE_POS and dst in NODE_POS:
                    edges.add(tuple(sorted((src, dst))))

        path_edges = {tuple(sorted((a, b))) for a, b in zip(path, path[1:])}
        for a, b in edges:
            color = YELLOW if (a, b) in path_edges else LINE
            width = 4 if (a, b) in path_edges else 2
            pygame.draw.line(self.screen, color, NODE_POS[a], NODE_POS[b], width)

        for node, pos in NODE_POS.items():
            if node == self.ai.location:
                fill = GREEN
            elif node in candidates:
                fill = YELLOW
            elif node == 0:
                fill = OFFICE
            elif node in VENT_CAMERAS:
                fill = VENT
            else:
                fill = PANEL_2

            radius = 29 if node == self.ai.location else 24
            pygame.draw.circle(self.screen, fill, pos, radius)
            pygame.draw.circle(self.screen, TEXT, pos, radius, 2)
            label = self.big_font.render(str(node), True, BG if fill in (GREEN, YELLOW) else TEXT)
            self.screen.blit(label, label.get_rect(center=pos))

            if node in VENT_CAMERAS:
                seal = self._seal_for_node(node)
                seal_color = RED if seal == "CLOSED" else GREEN
                pygame.draw.circle(self.screen, seal_color, (pos[0] + 25, pos[1] - 22), 7)

    def _draw_info(self, graph: dict[int, list[int]], candidates: list[int], path: list[int]) -> None:
        info = pygame.Rect(20, 560, 790, 180)
        self._draw_panel(info)
        loc = self.ai.location
        neighbors = graph.get(loc, [])
        vent_neighbors = [n for n in neighbors if n in VENT_CAMERAS]
        next_text = ", ".join(map(str, candidates)) if candidates else "none"
        neighbors_text = ", ".join(map(str, neighbors)) if neighbors else "none"
        vent_text = ", ".join(map(str, vent_neighbors)) if vent_neighbors else "none"
        path_text = " -> ".join(map(str, path)) if path else "none"

        lines = [
            f"Current: {self._node_label(loc)}",
            f"AI state: {self.ai.state.name} | mode: {self.mode} | prev: {self.ai.prev_location} | trigger: {self.ai.trigger_timer}",
            f"Available physical neighbors: {neighbors_text}",
            f"Possible next for current mode: {next_text}",
            f"Vent next nodes from here: {vent_text}",
            f"Predicted path: {path_text}",
            f"Last action: {self.last_action}",
        ]
        y = info.y + 14
        for line in lines:
            color = YELLOW if line.startswith("Possible") or line.startswith("Predicted") else TEXT
            self._draw_text(line, (info.x + 18, y), color)
            y += 23

    def _draw_buttons(self) -> None:
        panel = pygame.Rect(830, 20, 330, 720)
        self._draw_panel(panel)
        self._draw_text("Controls", (848, 36), TEXT, self.big_font)
        for button in self.buttons:
            active = button.text == self.mode
            button.draw(self.screen, self.font, active)

        y = 488
        self._draw_text("Seals", (848, y), TEXT, self.big_font)
        y += 32
        for seal_id, vent_node in VENT_SEALS.items():
            state = self.model.seals[seal_id]
            color = RED if state == SealState.CLOSED else GREEN
            self._draw_text(f"{vent_node}: {seal_id} = {state.name}", (848, y), color)
            y += 24

        y += 18
        self._draw_text("Keys", (848, y), TEXT, self.big_font)
        y += 32
        key_lines = [
            "SPACE - next step",
            "TAB   - patrol / attack",
            "R     - reset",
            "8/9/0/1 - toggle vents 8/9/10/11",
        ]
        for line in key_lines:
            self._draw_text(line, (848, y), MUTED)
            y += 23

    def draw(self) -> None:
        self.screen.fill(BG)
        graph = self._sync_ai()
        candidates, path = self._mode_candidates(graph)
        self._draw_graph(graph, candidates, path)
        self._draw_info(graph, candidates, path)
        self._draw_buttons()
        pygame.display.flip()

    def handle_key(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_ESCAPE:
            self.running = False
        elif event.key == pygame.K_SPACE:
            self.manual_step()
        elif event.key == pygame.K_TAB:
            self.set_mode("ATTACK" if self.mode == "PATROL" else "PATROL")
        elif event.key == pygame.K_r:
            self.reset()
        elif event.key == pygame.K_8:
            self.toggle_seal("SEAL_MID_RIGHT")
        elif event.key == pygame.K_9:
            self.toggle_seal("SEAL_TOP_RIGHT")
        elif event.key == pygame.K_0:
            self.toggle_seal("SEAL_CENTER")
        elif event.key == pygame.K_1:
            self.toggle_seal("SEAL_BOTTOM_LEFT")

    def run(self) -> None:
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    self.handle_key(event)
                else:
                    for button in self.buttons:
                        if button.handle(event):
                            break
            self.draw()
            self.clock.tick(FPS)
        pygame.quit()


def main() -> int:
    app = AlgemRealtimeTest()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
