"""Geometry builder for the fixed, data-authored haunted house."""
from ursina import Entity, Vec3, color

from game.items.battery import BatteryPickup
from game.items.flashlight import FlashlightPickup
from game.items.key import KeyPickup
from game.items.item import InventoryPickup
from game.levels.haunted_house import load_level, room_connections, wall_segments
from game.world.exit_door import ExitDoor
from game.world.locked_door import LockedDoor
from game.world.room import Room
from game.world.waypoint import Waypoint
from game.world.puzzles import PuzzleProp


class House(Entity):
    def __init__(self, on_escape):
        super().__init__()
        self.set_shader_auto()
        self.level = load_level()
        data = self.level.house
        self.room_graph = room_connections(data)
        self.rooms = {room["id"]: Room(room, parent=self) for room in data["rooms"]}
        self.hiding_spots = tuple(prop.hiding_spot for room in self.rooms.values()
                                  for prop in room.props if hasattr(prop, "hiding_spot"))
        self.player_spawn = Vec3(*self.level.spawns["player"]["position"])
        self.ghost_spawn = Vec3(*self.level.spawns["ghost"]["position"])
        self.walls = []
        self.door_frames = []
        self.pickups = {}
        height, thickness = data["wall_height"], data["wall_thickness"]
        for axis, line, low, high in wall_segments(data):
            center, length = (low + high) / 2, high - low
            position = (line, height / 2, center) if axis == "x" else (center, height / 2, line)
            scale = (thickness, height, length) if axis == "x" else (length, height, thickness)
            self.walls.append(self._wall(position, scale))
        for definition in data["extra_walls"]:
            self.walls.append(self._wall(definition["position"], definition["scale"]))
        for opening in (*data["connections"], data["exit_opening"]):
            self._door_frame(opening)
        x0, z0, x1, z1 = data["bounds"]
        self.ceiling = Entity(parent=self, model="cube", shader=None, collider="box",
                              position=((x0 + x1) / 2, height + 0.1, (z0 + z1) / 2),
                              scale=(x1 - x0, 0.2, z1 - z0), color=color.rgb32(73, 75, 80))
        # A short landing keeps the exit crossing grounded before the win callback.
        Entity(parent=self, model="cube", shader=None, collider="box",
               position=(0, -0.15, 19.5), scale=(4, 0.3, 3), color=color.rgb32(60, 63, 66))
        self._build_navigation()
        self._place_items(on_escape)
        self.puzzles = {definition["id"]: PuzzleProp(definition, parent=self)
                        for definition in data["progression"]["props"]}

    def _wall(self, position, scale):
        return Entity(parent=self, model="cube", shader=None, collider="box",
                      position=position, scale=scale, color=color.rgb32(110, 112, 119))

    def _door_frame(self, opening):
        axis, line, center, width = (opening[key] for key in ("axis", "line", "at", "width"))
        for offset in (-width / 2 - 0.06, width / 2 + 0.06):
            position = (line, 1.6, center + offset) if axis == "x" else (center + offset, 1.6, line)
            scale = (0.38, 3.2, 0.18) if axis == "x" else (0.18, 3.2, 0.38)
            # Exterior trim overlaps the door edge to seal collider seams.
            # Interior frames share existing walls and need no extra collider.
            self.door_frames.append(Entity(parent=self, model="cube", shader=None,
                                           position=position, scale=scale,
                                           collider="box" if "id" not in opening else None,
                                           color=color.rgb32(77, 65, 57)))
        position = (line, 3.06, center) if axis == "x" else (center, 3.06, line)
        scale = (0.38, 0.28, width) if axis == "x" else (width, 0.28, 0.38)
        self.door_frames.append(Entity(parent=self, model="cube", shader=None,
                                       position=position, scale=scale, color=color.rgb32(77, 65, 57)))

    def _build_navigation(self):
        # Preserve Panda3D Entity.nodes; level IDs live in nav_nodes.
        self.waypoints = {node: Waypoint(node, Vec3(*position))
                          for node, position in self.level.navigation["nodes"].items()}
        self.nav_nodes = {node: waypoint.position for node, waypoint in self.waypoints.items()}
        self.graph = {node: [] for node in self.nav_nodes}
        for a, b in self.level.navigation["edges"]:
            self.graph[a].append(b)
            self.graph[b].append(a)
        self.patrol_targets = tuple(self.level.navigation["patrol_targets"])

    def _place_items(self, on_escape):
        for spawn in self.level.spawns["pickups"]:
            kind = spawn["item"]
            args = {"parent": self, "position": spawn["position"]}
            if kind == "flashlight":
                item = FlashlightPickup(**args)
            elif kind == "battery":
                item = BatteryPickup(amount=self.level.items[kind]["restore"], **args)
            elif self.level.items[kind]["type"] == "key":
                item = KeyPickup(key_id=kind, key_name="Exit Key", **args)
            else:
                item = InventoryPickup(kind, self.level.items[kind], **args)
            item.spawn_id = spawn["id"]
            item.enabled = not spawn.get("requires")
            self.pickups[spawn["id"]] = item
        exit_data, basement_data = self.level.doors["exit_door"], self.level.doors["basement_door"]

        def door_args(definition):
            return {key: definition[key] for key in
                    ("position", "scale", "rotation_y", "required_key", "locked_message")}

        self.exit_door = ExitDoor(parent=self, on_escape=on_escape, **door_args(exit_data))
        self.basement_door = LockedDoor(parent=self, **door_args(basement_data))
        self.basement_door.interaction_text = "[E] Basement entrance (sealed)"

    def room_at(self, position):
        return next((room for room in self.rooms.values() if room.contains(position)), None)
