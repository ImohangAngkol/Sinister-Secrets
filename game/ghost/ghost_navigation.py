import heapq
import math

from ursina import Vec3, scene, time
from game.world.environment import world_raycast as raycast


def _distance(a, b):
    return math.hypot(a.x - b.x, a.z - b.z)


def nearest_node(position, nodes):
    if not nodes:
        raise ValueError("Navigation requires at least one waypoint")
    return min(nodes, key=lambda node_id: _distance(position, nodes[node_id]))


def astar(start, goal, nodes, graph):
    """Return nodes after start, or [] for an invalid/unreachable destination."""
    if start not in nodes or goal not in nodes or start == goal:
        return []
    open_heap = [(0.0, start)]
    came_from = {}
    g_score = {start: 0.0}
    visited = set()
    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current in visited:
            continue
        visited.add(current)
        if current == goal:
            path = []
            while current != start:
                path.append(current)
                current = came_from[current]
            return path[::-1]
        for neighbor in graph.get(current, []):
            if neighbor not in nodes:
                continue
            tentative = g_score[current] + _distance(nodes[current], nodes[neighbor])
            if tentative < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                heapq.heappush(open_heap, (tentative + _distance(nodes[neighbor], nodes[goal]), neighbor))
    return []


class GhostNavigation:
    def __init__(self, ghost, nodes, graph, collision_root=None, player=None):
        self.ghost = ghost
        self.nav_nodes = nodes
        self.graph = graph
        self.collision_root = collision_root if collision_root is not None else scene
        self.ignore = [ghost] + ([player] if player is not None else [])
        self.radius = 0.42
        self.path = []
        self.path_index = 0
        self.final_target = None
        self.blocked = False
        self.stuck_time = 0.0
        self.target_node = None
        self.target_position = None

    def segment_clear(self, start, target):
        """Sweep the ghost's width at feet and eye height against world colliders."""
        delta = Vec3(target.x - start.x, 0, target.z - start.z)
        length = delta.length()
        if length < 0.001:
            return True
        direction = delta / length
        sideways = Vec3(-direction.z, 0, direction.x)
        for height in (0.5, 1.55):
            for offset in (-self.radius, 0, self.radius):
                hit = raycast(
                    Vec3(start.x, start.y + height, start.z) + sideways * offset,
                    direction, distance=length + self.radius,
                    traverse_target=self.collision_root, ignore=self.ignore,
                )
                if hit.hit:
                    return False
        return True

    def _reachable_node(self, position):
        candidates = sorted(self.nav_nodes, key=lambda n: _distance(position, self.nav_nodes[n]))
        for node_id in candidates:
            if self.segment_clear(position, self.nav_nodes[node_id]):
                return node_id
        return None

    def set_path_to_node(self, target_node):
        self.clear()
        self.target_node = target_node
        if target_node not in self.nav_nodes:
            self.blocked = True
            return False
        # Validate graph edges against actual geometry, including closed doors.
        safe_graph = {
            node: [other for other in neighbors if other in self.nav_nodes
                   and self.segment_clear(self.nav_nodes[node], self.nav_nodes[other])]
            for node, neighbors in self.graph.items() if node in self.nav_nodes
        }
        candidates = []
        for start_node in self.nav_nodes:
            if not self.segment_clear(self.ghost.world_position, self.nav_nodes[start_node]):
                continue
            route = astar(start_node, target_node, self.nav_nodes, safe_graph)
            if start_node != target_node and not route:
                continue
            path = [start_node] + route
            cost = _distance(self.ghost.world_position, self.nav_nodes[start_node])
            cost += sum(_distance(self.nav_nodes[a], self.nav_nodes[b])
                        for a, b in zip(path, path[1:]))
            candidates.append((cost, path))
        if not candidates:
            self.blocked = True
            return False
        # Include the entry node: omitting it cuts corners from off-graph positions.
        self.path = min(candidates, key=lambda candidate: candidate[0])[1]
        # Frequent chase/hearing replans must not send the ghost back to a node
        # behind it. Skip entry nodes only when the entire shortcut is clear.
        while len(self.path) > 1 and self.segment_clear(
                self.ghost.world_position, self.nav_nodes[self.path[1]]):
            self.path.pop(0)
        return True

    def set_path_to_position(self, position):
        target = Vec3(position.x, self.ghost.world_y, position.z)
        if self.segment_clear(self.ghost.world_position, target):
            self.clear()
            self.final_target = target
            self.target_position = target
            return True
        target_node = self._reachable_node(target)
        if target_node is None:
            self.clear()
            self.blocked = True
            self.target_position = target
            return False
        self.set_path_to_node(target_node)
        self.target_position = target
        if not self.blocked:
            self.final_target = target
        return not self.blocked

    def path_finished(self):
        return self.path_index >= len(self.path) and self.final_target is None

    def clear(self):
        self.path = []
        self.path_index = 0
        self.final_target = None
        self.blocked = False
        self.stuck_time = 0.0
        self.target_node = None
        self.target_position = None

    def replan(self):
        target_position = self.target_position
        target_node = self.target_node
        if target_position is not None:
            return self.set_path_to_position(target_position)
        if target_node is not None:
            return self.set_path_to_node(target_node)
        return False

    def move_toward(self, target, speed, dt=None):
        start = self.ghost.world_position
        target = Vec3(target.x, start.y, target.z)
        delta = target - start
        length = delta.length()
        if length < 0.001:
            return True
        frame_dt = max(time.dt if dt is None else dt, 0)
        remaining = min(length, speed * frame_dt)
        self.ghost.look_at_2d(target, "y")
        while remaining > 1e-9:
            position = self.ghost.world_position
            step = min(remaining, speed / 60)
            destination = position + delta / length * step
            if not self.segment_clear(position, destination):
                self.blocked = True
                self.stuck_time += frame_dt
                return False
            self.ghost.world_position = destination
            remaining -= step
        self.blocked = False
        self.stuck_time = 0.0
        return True

    def follow_path(self, speed):
        remaining = max(time.dt, 0)
        while remaining > 1e-9 and not self.path_finished():
            if self.path_index < len(self.path):
                target = self.nav_nodes[self.path[self.path_index]]
            else:
                target = self.final_target
            length = _distance(self.ghost.world_position, target)
            if length < 0.001:
                if self.path_index < len(self.path):
                    self.path_index += 1
                else:
                    self.final_target = None
                continue
            duration = min(remaining, length / speed)
            if not self.move_toward(target, speed, dt=duration):
                return
            remaining -= duration
