"""Authored-layout validation independent of rendering and user input."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from game.levels.haunted_house import load_level, reachable, room_connections, validate_level


class LevelDataTests(unittest.TestCase):
    def setUp(self):
        self.level = load_level()

    def test_all_required_areas_are_connected_from_the_foyer(self):
        graph = room_connections(self.level.house)
        required = {"foyer", "main_hall", "living", "dining", "kitchen", "bedroom_one",
                    "bedroom_two", "bathroom", "storage", "basement_entrance", "exit_area"}
        self.assertTrue(required <= reachable(graph, "foyer"))
        self.assertEqual(len(graph), 15)

    def test_every_room_connection_has_an_alternate_route(self):
        for connection in self.level.house["connections"]:
            with self.subTest(doorway=connection["id"]):
                graph = room_connections(self.level.house)
                a, b = connection["a"], connection["b"]
                graph[a].remove(b)
                graph[b].remove(a)
                self.assertEqual(reachable(graph, "foyer"), set(graph))

    def test_key_and_exit_remain_reachable_without_entering_basement(self):
        graph = room_connections(self.level.house)
        graph.pop("basement_entrance")
        for neighbors in graph.values():
            neighbors.discard("basement_entrance")
        visited = reachable(graph, "foyer")
        for pickup in self.level.spawns["pickups"]:
            self.assertIn(pickup["room"], visited)
        self.assertIn(self.level.doors["exit_door"]["room"], visited)
        self.assertFalse(any(p["item"] == "basement_key" for p in self.level.spawns["pickups"]))

    def test_bad_doorway_and_missing_key_fail_loading_validation(self):
        level = deepcopy(self.level)
        level.house["connections"][0]["at"] = 100
        with self.assertRaisesRegex(ValueError, "Doorway"):
            validate_level(level)
        level = deepcopy(self.level)
        level.spawns["pickups"][:] = [p for p in level.spawns["pickups"] if p["item"] != "exit_key"]
        with self.assertRaisesRegex(ValueError, "exit key"):
            validate_level(level)

    def test_disconnected_navigation_is_rejected(self):
        level = deepcopy(self.level)
        level.navigation["edges"][:] = [edge for edge in level.navigation["edges"] if "kitchen" not in edge]
        with self.assertRaisesRegex(ValueError, "Disconnected waypoint"):
            validate_level(level)

    def test_level_loading_is_independent_of_current_directory(self):
        root = str(Path(__file__).resolve().parents[2])
        with tempfile.TemporaryDirectory() as elsewhere:
            command = [sys.executable, "-c", f"import sys; sys.path.insert(0, {root!r}); "
                       "from game.levels.haunted_house import load_level; print(load_level().house['id'])"]
            result = subprocess.run(command, cwd=elsewhere, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), "haunted_house")
