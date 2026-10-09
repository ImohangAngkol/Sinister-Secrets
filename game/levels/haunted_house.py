"""Load the authored placeholder house using the existing level/data files."""
from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class LevelData:
    house: dict
    navigation: dict
    spawns: dict
    doors: dict
    items: dict


def load_level():
    root = Path(__file__).resolve().parents[1]

    def read(relative):
        return json.loads((root / relative).read_text(encoding="utf-8"))

    level = LevelData(read("levels/haunted_house.json"), read("levels/navigation.json"),
                      read("data/spawn_points.json"), read("data/doors.json"),
                      read("data/items.json"))
    validate_level(level)
    return level


def room_connections(house):
    graph = {room["id"]: set() for room in house["rooms"]}
    for connection in house["connections"]:
        graph[connection["a"]].add(connection["b"])
        graph[connection["b"]].add(connection["a"])
    return graph


def reachable(graph, start):
    visited, pending = set(), [start]
    while pending:
        current = pending.pop()
        if current not in visited:
            visited.add(current)
            pending.extend(graph.get(current, ()))
    return visited


def validate_level(level):
    """Reject disconnected or inconsistent authored data before building geometry."""
    house, nav, spawns = level.house, level.navigation, level.spawns
    rooms = {room["id"]: room for room in house["rooms"]}
    if len(rooms) != len(house["rooms"]):
        raise ValueError("Duplicate room ID")
    bounds = house["bounds"]
    area = 0
    for room in rooms.values():
        x0, z0, x1, z1 = room["bounds"]
        if not (bounds[0] <= x0 < x1 <= bounds[2] and bounds[1] <= z0 < z1 <= bounds[3]):
            raise ValueError(f"Invalid room bounds: {room['id']}")
        area += (x1 - x0) * (z1 - z0)
    for index, room in enumerate(house["rooms"]):
        a = room["bounds"]
        for other in house["rooms"][index + 1:]:
            b = other["bounds"]
            if min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1]):
                raise ValueError("Room interiors overlap")
    if area != (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]):
        raise ValueError("Room floors must cover the complete house")
    ids = set()
    for c in house["connections"]:
        if c["id"] in ids or c["a"] not in rooms or c["b"] not in rooms or c["width"] < 2:
            raise ValueError("Invalid doorway connection")
        ids.add(c["id"])
        a, b = rooms[c["a"]]["bounds"], rooms[c["b"]]["bounds"]
        if c["axis"] == "x":
            shared = (a[2] == b[0] == c["line"] or b[2] == a[0] == c["line"])
            low, high = max(a[1], b[1]), min(a[3], b[3])
        elif c["axis"] == "z":
            shared = (a[3] == b[1] == c["line"] or b[3] == a[1] == c["line"])
            low, high = max(a[0], b[0]), min(a[2], b[2])
        else:
            raise ValueError("Doorway axis must be x or z")
        if not shared or not low <= c["at"] - c["width"] / 2 < c["at"] + c["width"] / 2 <= high:
            raise ValueError(f"Doorway is outside the shared room wall: {c['id']}")
    graph = room_connections(house)
    if reachable(graph, spawns["player"]["room"]) != set(rooms):
        raise ValueError("Every room must be reachable from player spawn")
    nav_graph = {node: set() for node in nav["nodes"]}
    for a, b in nav["edges"]:
        if a not in nav_graph or b not in nav_graph or a == b:
            raise ValueError("Invalid navigation edge")
        nav_graph[a].add(b)
        nav_graph[b].add(a)
    if reachable(nav_graph, spawns["player"]["room"]) != set(nav_graph):
        raise ValueError("Disconnected waypoint graph")
    if not set(nav["patrol_targets"]) <= set(rooms) & set(nav_graph):
        raise ValueError("Patrol destinations must be room waypoints")
    for entry in (spawns["player"], spawns["ghost"], *spawns["pickups"], *level.doors.values()):
        x, _, z = entry["position"]
        x0, z0, x1, z1 = rooms[entry["room"]]["bounds"]
        if not (x0 <= x <= x1 and z0 <= z <= z1):
            raise ValueError("Spawn is outside its room")
    if len({item["id"] for item in spawns["pickups"]}) != len(spawns["pickups"]):
        raise ValueError("Duplicate pickup ID")
    if any(item["item"] not in level.items for item in spawns["pickups"]):
        raise ValueError("Unknown pickup definition")
    exit_key = level.doors["exit_door"]["required_key"]
    if not any(item["item"] == exit_key for item in spawns["pickups"]):
        raise ValueError("The exit key must be available without unlocking the basement")


def wall_segments(house):
    """Merge shared rectangle edges and subtract only authored doorway openings."""
    lines = {}
    for room in house["rooms"]:
        x0, z0, x1, z1 = room["bounds"]
        for axis, line, low, high in (("x", x0, z0, z1), ("x", x1, z0, z1),
                                      ("z", z0, x0, x1), ("z", z1, x0, x1)):
            lines.setdefault((axis, line), []).append((low, high))
    openings = [*house["connections"], house["exit_opening"]]
    for (axis, line), ranges in lines.items():
        merged = []
        for low, high in sorted(ranges):
            if merged and low <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(high, merged[-1][1]))
            else:
                merged.append((low, high))
        for opening in openings:
            if (opening["axis"], opening["line"]) != (axis, line):
                continue
            left = opening["at"] - opening["width"] / 2
            right = opening["at"] + opening["width"] / 2
            pieces = []
            for low, high in merged:
                if right <= low or left >= high:
                    pieces.append((low, high))
                else:
                    if low < left:
                        pieces.append((low, left))
                    if right < high:
                        pieces.append((right, high))
            merged = pieces
        for low, high in merged:
            if high - low > 0.001:
                yield axis, line, low, high
