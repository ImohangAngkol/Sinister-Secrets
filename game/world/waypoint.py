from dataclasses import dataclass

from ursina import Vec3


@dataclass(frozen=True)
class Waypoint:
    node_id: int
    position: Vec3
