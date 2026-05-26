import heapq
import random
from collections import deque

CAMERAS = [
    (1, "01", "MAIN HALL",   "main_hall.png"),
    (2, "02", "ALGEM'S ROOM", "algems' room.png"),
    (3, "03", "TOILETS",     "toilets.png"),
    (4, "04", "WEST HALL",   "westhall.png"),
    (5, "05", "CANTEEN",    "canteen.png"),
    (6, "06", "COWORKING",  "coworking.png"),
    (7, "07", "SERVICE ROOM", "service_room.png"),
]
CAMERA_COUNT = len(CAMERAS)

GRAPH: dict[int, list[int]] = {
    0: [],
    1: [2, 3, 4],
    2: [1],
    3: [1, 4],
    4: [1, 3, 5, 0],
    5: [4, 6],
    6: [5, 7],
    7: [6, 0],
}

def bfs_path(start: int, goal: int, graph: dict) -> list[int] | None:
    if start == goal:
        return [start]
    queue: deque[list[int]] = deque([[start]])
    visited: set[int] = {start}
    while queue:
        path = queue.popleft()
        current = path[-1]
        for neighbor in graph[current]:
            if neighbor in visited:
                continue
            new_path = path + [neighbor]
            if neighbor == goal:
                return new_path
            visited.add(neighbor)
            queue.append(new_path)
    return None

def _precompute_bfs_distances() -> dict[int, int]:
    distances: dict[int, int] = {}
    for node in GRAPH:
        path = bfs_path(node, 0, GRAPH)
        distances[node] = (len(path) - 1) if path else 999
    return distances

BFS_DIST_TO_OFFICE: dict[int, int] = _precompute_bfs_distances()

def astar_path(start, goal, graph, edge_weight_fn, heuristic=None):
    if heuristic is None:
        heuristic = BFS_DIST_TO_OFFICE
    if start == goal:
        return [start]
    open_heap: list = []
    h0 = heuristic.get(start, 999)
    heapq.heappush(open_heap, (h0, 0.0, start, [start]))
    best_g: dict[int, float] = {start: 0.0}
    while open_heap:
        f, g, current, path = heapq.heappop(open_heap)
        if g > best_g.get(current, float("inf")):
            continue
        if current == goal:
            return path
        for neighbor in graph[current]:
            w = edge_weight_fn(current, neighbor)
            new_g = g + w
            if new_g < best_g.get(neighbor, float("inf")):
                best_g[neighbor] = new_g
                h = heuristic.get(neighbor, 999)
                heapq.heappush(open_heap, (new_g + h, new_g, neighbor, path + [neighbor]))
    return None

NIGHT_CONFIG = {
    1: {"move_lo": 480, "move_hi": 720, "algo_chance": 0.0, "algo": "none"},
    2: {"move_lo": 360, "move_hi": 600, "algo_chance": 0.2, "algo": "bfs"},
    3: {"move_lo": 300, "move_hi": 480, "algo_chance": 0.4, "algo": "bfs"},
    4: {"move_lo": 180, "move_hi": 360, "algo_chance": 0.6, "algo": "bfs"},
    5: {"move_lo": 120, "move_hi": 240, "algo_chance": 0.8, "algo": "astar"},
}

class GameModel:
    def __init__(self, night: int = 1):
        self.night = night
        self.power = 100.0
        self.power_drain_timer = 0
        self.hour = 0
        self.timer = 0

        self.target_look = 0.0
        self.current_look = 0.0

        self.server_state = "OFF"
        self.server_blink = None

        self.tablet_open = False
        self.tablet_animating = False
        self.tablet_anim_frame = 0

        self.camera_idx = 1
        self.cam_look = -1.0
        self.cam_state = "HOLDING"
        self.cam_hold_timer = 0
        self.cam_move_progress = 0.0
        self.cam_dir = 1

        self.camera_watch_ticks: dict[int, int] = {i: 0 for i in range(1, 8)}

        self.algem_location = 2
        self.algem_prev_location = 2
        self.algem_move_timer = self._initial_move_delay()
        self.algem_trigger = 0
        self.algem_main_hall_sprite = 0

        self.game_over = False
        self.night_complete = False

    def _initial_move_delay(self) -> int:
        base = max(300, 900 - self.night * 120)
        return random.randint(base, base + 180)

    def _move_interval(self) -> int:
        cfg = NIGHT_CONFIG.get(self.night, NIGHT_CONFIG[5])
        lo = max(60, cfg["move_lo"] - self.hour * 20)
        hi = max(90, cfg["move_hi"] - self.hour * 20)
        return random.randint(lo, hi)

    def _edge_weight(self, u: int, v: int) -> float:
        weight = 1.0
        watch = self.camera_watch_ticks.get(u, 0)
        if watch > 0 and u != 0:
            observed = min(1.0, watch / 300.0)
            weight += observed * 2.0
        return weight

    def _choose_next_node(self) -> int:
        cfg = NIGHT_CONFIG.get(self.night, NIGHT_CONFIG[5])
        neighbors = GRAPH.get(self.algem_location, [])
        if not neighbors:
            return self.algem_location

        roll = random.random()

        if roll < cfg["algo_chance"]:
            if cfg["algo"] == "astar":
                path = astar_path(self.algem_location, 0, GRAPH, self._edge_weight)
            else:
                path = bfs_path(self.algem_location, 0, GRAPH)
            if path and len(path) > 1 and path[1] in neighbors:
                return path[1]

        safe = [n for n in neighbors if n != 0]
        return random.choice(safe if safe else neighbors)

    def update(self):
        if self.game_over or self.night_complete:
            return

        self.current_look += (self.target_look - self.current_look) * 0.12

        if self.cam_state == "HOLDING":
            self.cam_hold_timer += 1
            if self.cam_hold_timer >= 180:
                self.cam_state = "MOVING"
                self.cam_move_progress = 0.0
        elif self.cam_state == "MOVING":
            self.cam_move_progress += 0.006
            if self.cam_move_progress >= 1.0:
                self.cam_state = "HOLDING"
                self.cam_hold_timer = 0
                self.cam_dir = -self.cam_dir
            else:
                t = self.cam_move_progress
                eased = t * t * (3 - 2 * t)
                self.cam_look = eased * self.cam_dir + (1 - eased) * (-self.cam_dir)

        if self.power > 0:
            self.power_drain_timer += 1
            if self.power_drain_timer >= 60:
                self.power_drain_timer = 0
                drain = 0.08
                if self.tablet_open:
                    drain += 0.08
                self.power = max(0.0, self.power - drain)

        self.timer += 1
        if self.timer >= 3600:
            self.hour += 1
            self.timer = 0
            if self.hour >= 6:
                self.night_complete = True
                return

        if self.tablet_open and not self.tablet_animating:
            self.camera_watch_ticks[self.camera_idx] = self.camera_watch_ticks.get(self.camera_idx, 0) + 1

        if self.algem_trigger > 0:
            self.algem_trigger -= 1

        self.algem_move_timer -= 1
        if self.algem_move_timer <= 0:
            next_node = self._choose_next_node()
            if next_node == 0:
                self.game_over = True
                return
            if next_node != self.algem_location:
                self.algem_prev_location = self.algem_location
                self.algem_location = next_node
                self.algem_trigger = 60
                if next_node == 1:
                    self.algem_main_hall_sprite = random.randint(0, 1)
            self.algem_move_timer = self._move_interval()
