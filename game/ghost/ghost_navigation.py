import heapq
import math

from ursina import Vec3, distance_xz, time


def _distance(a, b) -> float:
    return math.hypot(
        a.x - b.x,
        a.z - b.z,
    )


def nearest_node(
    position,
    nodes,
):
    return min(
        nodes,
        key=lambda node_id: _distance(
            position,
            nodes[node_id],
        ),
    )


def astar(
    start,
    goal,
    nodes,
    graph,
):
    if start == goal:
        return []

    open_heap = [
        (0.0, start)
    ]

    came_from = {}

    g_score = {
        start: 0.0
    }

    visited = set()

    while open_heap:
        _, current = (
            heapq.heappop(
                open_heap
            )
        )

        if current in visited:
            continue

        visited.add(current)

        if current == goal:
            path = [current]

            while current in came_from:
                current = (
                    came_from[current]
                )

                path.append(current)

            path.reverse()

            if (
                path
                and path[0] == start
            ):
                path = path[1:]

            return path

        for neighbor in graph.get(
            current,
            [],
        ):
            tentative = (
                g_score[current]
                + _distance(
                    nodes[current],
                    nodes[neighbor],
                )
            )

            if tentative < g_score.get(
                neighbor,
                float("inf"),
            ):
                came_from[neighbor] = (
                    current
                )

                g_score[neighbor] = (
                    tentative
                )

                estimated_total = (
                    tentative
                    + _distance(
                        nodes[neighbor],
                        nodes[goal],
                    )
                )

                heapq.heappush(
                    open_heap,
                    (
                        estimated_total,
                        neighbor,
                    ),
                )

    return []


class GhostNavigation:
    def __init__(
        self,
        ghost,
        nodes,
        graph,
    ):
        self.ghost = ghost
        self.nodes = nodes
        self.graph = graph

        self.path = []
        self.path_index = 0

    def set_path_to_node(
        self,
        target_node,
    ):
        start_node = nearest_node(
            self.ghost.position,
            self.nodes,
        )

        self.path = astar(
            start_node,
            target_node,
            self.nodes,
            self.graph,
        )

        self.path_index = 0

    def set_path_to_position(
        self,
        position,
    ):
        target_node = nearest_node(
            position,
            self.nodes,
        )

        self.set_path_to_node(
            target_node
        )

    def path_finished(self):
        return (
            self.path_index
            >= len(self.path)
        )

    def clear(self):
        self.path = []
        self.path_index = 0

    def follow_path(
        self,
        speed,
    ):
        if self.path_finished():
            return

        node_id = self.path[
            self.path_index
        ]

        target = self.nodes[
            node_id
        ]

        flat_target = Vec3(
            target.x,
            self.ghost.y,
            target.z,
        )

        if distance_xz(
            self.ghost.position,
            flat_target,
        ) < 0.45:
            self.path_index += 1
            return

        self.ghost.look_at_2d(
            flat_target,
            "y",
        )

        self.ghost.position += (
            self.ghost.forward
            * speed
            * time.dt
        )
