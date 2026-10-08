"""Real Ursina/Panda3D regression tests, with simulated input in an offscreen buffer.

Run: .venv/Scripts/python.exe -m unittest discover -s game/tests -v
Mouse capture is bypassed ONLY here because GraphicsBuffer has no window pointer.
"""
import importlib
from pathlib import Path
import unittest
from unittest.mock import patch

from panda3d.core import Filename, loadPrcFileData

loadPrcFileData("", "audio-library-name null\nmodel-cache-dir\n")

from PIL import Image, ImageStat
from ursina import Ursina, Vec3, application, camera, destroy, held_keys, mouse, scene, time

from game.game_manager import GameManager
from game.ghost.ghost_navigation import astar
from game.ghost.ghost_hearing import can_hear_player
from game.ghost.ghost_states import GhostState
from game.ghost.ghost_vision import can_see_player, has_line_of_sight
from game.items.battery import BatteryPickup
from game.items.flashlight import FlashlightPickup
from game.items.key import KeyPickup
from game.player.interaction import get_interaction_hit
from game.settings import FLASHLIGHT_DRAIN_PER_SECOND, MAX_BATTERY


class PrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Ursina(window_type="offscreen", size=(1280, 720),
                         editor_ui_enabled=False, development_mode=False,
                         fullscreen=False, borderless=False)
        camera.ui_lens.set_film_size(20 * 1280 / 720, 20)
        cls.lock_patch = patch.object(type(mouse), "locked", False)
        cls.lock_patch.start()
        mouse.enabled = False
        application.calculate_dt = False

    @classmethod
    def tearDownClass(cls):
        cls.lock_patch.stop()
        cls.app.destroy()

    def setUp(self):
        # Detach the eternal camera before destroying its former parent. Destroy
        # leaves before roots; scene.clear() iterates in creation order in 8.3.
        camera.world_parent = scene
        for entity in reversed(scene.entities[:]):
            if not entity.eternal and not entity.is_empty():
                destroy(entity)
        scene.entities = [e for e in scene.entities if e.eternal]
        scene._entities_marked_for_removal.clear()
        application.sequences.clear()
        self.app.render.clear_light()
        held_keys.clear()
        mouse.velocity = Vec3(0, 0, 0)
        time.dt = time.dt_unscaled = 1 / 60
        self.manager = GameManager()
        self.player = self.manager.scene_manager.player
        self.house = self.manager.scene_manager.house
        self.ghost = self.manager.scene_manager.ghost
        self.ghost.enabled = False

    def move(self, key, seconds=1, dt=1 / 60):
        held_keys[key] = 1
        for _ in range(round(seconds / dt)):
            time.dt = dt
            self.player.update()
        held_keys[key] = 0

    def aim(self, target):
        camera.look_at(target)

    def pickup(self, kind):
        return next(e for e in self.house.children if isinstance(e, kind))

    def capture(self, name):
        # Render real frames; no mocked shaders, lighting, models or textures.
        for _ in range(4):
            self.app.graphicsEngine.renderFrame()
        path = Path(__file__).parent / name
        self.assertTrue(self.app.win.saveScreenshot(Filename.from_os_specific(str(path))))
        return Image.open(path).convert("RGB")

    def test_all_existing_modules_import(self):
        root = Path(__file__).resolve().parents[1]
        for path in root.rglob("*.py"):
            if "tests" in path.parts:
                continue
            module = ".".join(path.relative_to(root.parent).with_suffix("").parts)
            importlib.import_module(module)
        self.assertNotIsInstance(self.house.nodes, dict)  # Preserve Panda3D's API.

    def test_wasd_mouse_and_sprint(self):
        self.player.rotation_y = 0
        self.player.camera_pivot.rotation_x = 0
        for key, axis, expected in (("w", "z", 1), ("s", "z", -1),
                                    ("a", "x", -1), ("d", "x", 1)):
            self.player.position = Vec3(-8, 0, -8)
            start = getattr(self.player, axis)
            self.move(key, seconds=0.2)
            self.assertAlmostEqual(getattr(self.player, axis) - start, expected, delta=0.03)
        self.player.position = Vec3(-8, 0, -8)
        held_keys["shift"] = 1
        self.move("w", seconds=0.2)
        self.assertAlmostEqual(self.player.z, -6.4, delta=0.03)
        held_keys.clear()
        mouse.velocity = Vec3(0.1, 0.2, 0)
        time.dt = 0.1
        self.player.update()
        self.assertAlmostEqual(self.player.rotation_y, 4, delta=0.01)
        self.assertAlmostEqual(self.player.camera_pivot.rotation_x, -8, delta=0.01)
        mouse.velocity = Vec3(0, 100, 0)
        self.player.update()
        self.assertEqual(self.player.camera_pivot.rotation_x, -90)

    def test_player_collisions_at_slow_frame_rate_and_corners(self):
        self.player.position = Vec3(-1.2, 0, -9)
        self.player.rotation_y = 90
        held_keys["shift"] = 1
        self.move("w", seconds=1.5, dt=0.25)
        self.assertLessEqual(self.player.x, -0.65)
        self.assertAlmostEqual(self.player.y, 0, delta=0.01)
        self.player.position = Vec3(-14, 0, -14)
        self.player.rotation_y = -135
        self.move("w", seconds=1.5, dt=0.25)
        self.assertGreater(self.player.x, -14.7)
        self.assertGreater(self.player.z, -14.7)

    def test_flashlight_pickup_toggle_drain_and_depletion(self):
        self.player.input("f")
        self.assertFalse(self.player.flashlight_on)
        pickup = self.pickup(FlashlightPickup)
        self.aim(pickup.world_position)
        self.assertIs(get_interaction_hit(self.player).entity, pickup)
        self.player.input("e")
        self.assertTrue(self.player.has_flashlight)
        self.assertNotIn(pickup, scene.collidables)
        self.player.input("f")
        start = self.player.stats.battery
        time.dt = 1
        self.player._update_flashlight()
        self.assertAlmostEqual(self.player.stats.battery, start - FLASHLIGHT_DRAIN_PER_SECOND)
        self.assertGreater(self.player.flashlight_light.color.r, 0)
        self.player.input("f")
        start = self.player.stats.battery
        self.player._update_flashlight()
        self.assertEqual(self.player.stats.battery, start)
        self.assertEqual(self.player.flashlight_light.color.r, 0)
        self.player.stats.battery = 1
        self.player.input("f")
        self.player._update_flashlight()
        self.assertEqual(self.player.stats.battery, 0)
        self.assertFalse(self.player.flashlight_on)
        self.assertEqual(self.player.flashlight_light.color.r, 0)
        self.player.input("f")
        self.assertFalse(self.player.flashlight_on)

    def test_battery_and_key_pickups_with_real_rays(self):
        battery = self.pickup(BatteryPickup)
        self.player.position = Vec3(-10, 0, 7)
        self.player.stats.battery = 10
        self.aim(battery.world_position)
        self.assertIs(get_interaction_hit(self.player).entity, battery)
        self.player.input("e")
        self.assertEqual(self.player.stats.battery, 45)
        self.player.add_battery(1000)
        self.assertEqual(self.player.stats.battery, MAX_BATTERY)
        key = self.pickup(KeyPickup)
        self.player.position = Vec3(10, 0, -11)
        self.aim(key.world_position)
        self.assertIs(get_interaction_hit(self.player).entity, key)
        self.player.input("e")
        self.assertTrue(self.player.inventory.has_key("exit_key"))
        self.assertEqual(self.player.inventory.key_count(), 1)

    def test_wall_blocks_interaction_and_exit_requires_crossing(self):
        key = self.pickup(KeyPickup)
        self.player.position = Vec3(-1, 0, -9)
        self.aim(key.world_position)
        self.assertIsNot(get_interaction_hit(self.player).entity, key)
        door = self.house.exit_door
        self.player.position = Vec3(10, 0, 13)
        self.aim(Vec3(10, 1.5, 14.75))
        self.assertIs(get_interaction_hit(self.player).entity, door)
        self.player.input("e")
        self.assertFalse(door.opened)
        self.assertIsNotNone(door.collider)
        self.player.rotation_y = 0
        camera.rotation = Vec3(0, 0, 0)
        self.move("w", seconds=0.5)
        self.assertLess(self.player.z, 14.2)
        self.player.inventory.add_key("exit_key")
        self.aim(Vec3(10, 1.5, 14.75))
        self.player.input("e")
        self.assertTrue(door.opened)
        self.assertIsNone(door.collider)
        door.update()
        self.assertEqual(self.manager.state, "playing")
        self.player.rotation_y = 0
        camera.rotation = Vec3(0, 0, 0)
        self.move("w", seconds=0.4)
        door.update()
        self.assertEqual(self.manager.state, "escaped")
        self.assertFalse(self.player.enabled)
        self.assertFalse(self.ghost.enabled)
        self.capture("render_escape.png")

    def test_astar_and_all_house_edges_have_clearance(self):
        route = astar(0, 7, self.house.nav_nodes, self.house.graph)
        self.assertEqual(route, [1, 2, 5, 6, 7])
        self.assertEqual(astar(0, 0, self.house.nav_nodes, self.house.graph), [])
        self.assertEqual(astar(0, 7, self.house.nav_nodes, {}), [])
        self.assertEqual(astar(0, 99, self.house.nav_nodes, self.house.graph), [])
        nav = self.ghost.ai.navigation
        for node, neighbors in self.house.graph.items():
            for other in neighbors:
                self.assertTrue(nav.segment_clear(self.house.nav_nodes[node], self.house.nav_nodes[other]),
                                f"Blocked edge {node} -> {other}")

    def test_ghost_rejoins_waypoints_and_sweeps_walls(self):
        nav = self.ghost.ai.navigation
        self.ghost.position = Vec3(-1, 0, -9)
        self.assertFalse(nav.segment_clear(self.ghost.position, Vec3(1, 0, -9)))
        for _ in range(30):
            time.dt = 0.25
            nav.move_toward(Vec3(1, 0, -9), 20)
        self.assertLess(self.ghost.x, -0.6)
        nav.set_path_to_node(4)
        self.assertFalse(nav.blocked)
        self.assertTrue(nav.path)
        time.dt = 1 / 30
        for _ in range(1500):
            if nav.path_finished():
                break
            old = Vec3(self.ghost.world_position)
            nav.follow_path(4.2)
            self.assertTrue(nav.segment_clear(old, self.ghost.world_position))
        self.assertTrue(nav.path_finished())
        self.assertLess((self.ghost.position - self.house.nav_nodes[4]).length(), 0.1)

    def test_real_ghost_vision_and_no_catch_through_wall(self):
        self.ghost.position = Vec3(-1, 0, -9)
        self.ghost.rotation_y = 90
        self.player.position = Vec3(0.8, 0, -9)
        self.assertFalse(can_see_player(self.ghost, self.player))
        self.assertFalse(has_line_of_sight(self.ghost, self.player))
        self.ghost.ai.state = GhostState.CHASE
        self.ghost.ai.update()
        self.assertEqual(self.manager.state, "playing")
        self.ghost.position = Vec3(-0.65, 0, -9)
        self.player.position = Vec3(0.55, 0, -9)
        self.ghost.ai.update()
        self.assertEqual(self.manager.state, "playing")
        self.player.position = Vec3(-2, 0, -9)
        self.ghost.rotation_y = -90
        self.assertTrue(can_see_player(self.ghost, self.player))
        self.ghost.rotation_y = 90
        self.assertFalse(can_see_player(self.ghost, self.player))

    def test_hearing_and_frequent_investigate_replans_make_progress(self):
        self.ghost.position = Vec3(-2, 0, -9)
        self.player.position = Vec3(2, 0, -9)
        self.player.stats.noise_level = 0
        self.assertFalse(can_hear_player(self.ghost, self.player))
        self.player.stats.noise_level = 8
        self.assertTrue(can_hear_player(self.ghost, self.player))
        ai = self.ghost.ai
        with patch("game.ghost.ghost_ai.can_see_player", return_value=False), \
                patch("game.ghost.ghost_ai.can_hear_player", return_value=True):
            for _ in range(900):
                time.dt = 1 / 60
                old = Vec3(self.ghost.world_position)
                ai.update()
                self.assertTrue(ai.navigation.segment_clear(old, self.ghost.world_position))
        self.assertLess((self.ghost.world_position - self.player.world_position).length(), 0.2)

    def test_ai_states_and_jumpscare_once(self):
        ai = self.ghost.ai
        self.assertEqual(ai.state, GhostState.PATROL)
        with patch("game.ghost.ghost_ai.can_see_player", return_value=False), \
                patch("game.ghost.ghost_ai.can_hear_player", return_value=True):
            ai.update()
            self.assertEqual(ai.state, GhostState.INVESTIGATE)
        ai.navigation.clear()
        with patch("game.ghost.ghost_ai.can_see_player", return_value=False), \
                patch("game.ghost.ghost_ai.can_hear_player", return_value=False):
            ai.update()
            self.assertEqual(ai.state, GhostState.SEARCH)
            time.dt = 5
            ai.update()
            self.assertEqual(ai.state, GhostState.PATROL)
        self.ghost.position = Vec3(-6, 0, -8)
        self.player.position = Vec3(-6, 0, -5)
        self.ghost.rotation_y = 0
        time.dt = 1 / 60
        ai.update()
        self.assertEqual(ai.state, GhostState.CHASE)
        self.player.position = Vec3(-6, 0, -4)
        with patch("game.ghost.ghost_ai.can_see_player", return_value=False):
            time.dt = 3
            ai.update()
            self.assertEqual(ai.state, GhostState.SEARCH)
        self.player.position = self.ghost.position + Vec3(0, 0, 0.8)
        self.ghost.rotation_y = 0
        ai.state = GhostState.CHASE
        time.dt = 1 / 60
        ai.update()
        self.assertEqual(ai.state, GhostState.JUMPSCARE)
        self.assertTrue(self.ghost.jumpscare.triggered)
        self.assertEqual(self.manager.state, "dead")
        self.assertFalse(self.player.enabled)
        self.assertEqual(self.player.flashlight_light.color.r, 0)
        self.ghost.jumpscare.trigger()
        self.capture("render_caught.png")

    def test_render_visibility_colors_and_flashlight_changes_pixels(self):
        self.capture("render_spawn.png")
        self.player.position = Vec3(-3, 0, -9)
        self.player.rotation_y = 90
        self.player.camera_pivot.rotation_x = 15
        self.player.obtain_flashlight()
        off = self.capture("render_flashlight_off.png")
        self.player.toggle_flashlight()
        self.player._update_flashlight()
        on = self.capture("render_flashlight_on.png")
        crop = (400, 220, 880, 580)
        off_mean = sum(ImageStat.Stat(off.crop(crop)).mean) / 3
        on_mean = sum(ImageStat.Stat(on.crop(crop)).mean) / 3
        self.assertGreater(off_mean, 20, "World is too dark with flashlight off")
        self.assertGreater(on_mean, off_mean + 5, "Flashlight has no visible effect")
        self.player.toggle_flashlight()
        camera.world_parent = scene
        camera.position = Vec3(0, 28, -22)
        camera.rotation = Vec3(0, 0, 0)
        camera.look_at(Vec3(0, 0, 0))
        overview = self.capture("render_overview.png")
        pixels = list(overview.get_flattened_data() if hasattr(overview, "get_flattened_data")
                      else overview.getdata())
        self.assertGreater(sum(r > g * 1.5 and r > b * 1.5 and r > 30 for r, g, b in pixels), 50)
        self.assertGreater(sum(g > r * 1.5 and g > b * 1.5 and g > 30 for r, g, b in pixels), 50)
        self.assertLess(sum(min(rgb) > 245 for rgb in pixels) / len(pixels), 0.05)


if __name__ == "__main__":
    unittest.main()
