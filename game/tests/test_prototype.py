"""Real Ursina/Panda3D regression tests, with simulated input in an offscreen buffer.

Run: .venv/Scripts/python.exe -m unittest discover -s game/tests -v
Mouse capture is bypassed ONLY here because GraphicsBuffer has no window pointer.
"""
import importlib
import math
import random
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

from panda3d.core import Filename, FogAttrib, LightAttrib, loadPrcFileData

loadPrcFileData("", "audio-library-name null\nmodel-cache-dir\n")

from PIL import Image, ImageStat
from ursina import Entity, Ursina, Vec3, application, camera, color, destroy, held_keys, mouse, scene, time

from game.game_manager import GameManager
from game.settings import Preferences
from game.systems.save_manager import SaveManager
from game.ghost.ghost_navigation import astar
from game.ghost.ghost_hearing import can_hear_player
from game.ghost.ghost_states import GhostState
from game.ghost.ghost_vision import can_see_player, has_line_of_sight
from game.items.battery import BatteryPickup
from game.items.flashlight import FlashlightPickup
from game.items.key import KeyPickup
from game.player.interaction import get_interaction_hit
from game.settings import (FLASHLIGHT_COLOR, FLASHLIGHT_DRAIN_PER_SECOND, FLASHLIGHT_FOV,
                           FLASHLIGHT_RANGE, HOUSE_FOG_DENSITY, MAX_BATTERY,
                           GHOST_ACTIVE_SEARCH_SECONDS, STAMINA_MAX)
from game.ghost.ghost_navigation import GhostNavigation
from game.world.environment import world_raycast
from game.systems.horror_manager import HorrorManager, EVENTS, descendants


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
        application.paused = False
        mouse.enabled = False
        self.app.render.clear_light()
        held_keys.clear()
        mouse.velocity = Vec3(0, 0, 0)
        time.dt = time.dt_unscaled = 1 / 60
        self.save_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.save_directory.cleanup)
        self.manager = GameManager(preferences=Preferences(path=None), save_manager=SaveManager(self.save_directory.name))
        self.manager.automatic_checkpoints = False  # Legacy fixtures may inject items instead of collecting them.
        self.manager.start_game()
        self.manager.update()  # Consume the first clean session frame.
        time.dt = time.dt_unscaled = 1 / 60
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

    def unlock_key_fixture(self):
        """Set up completed puzzle gates for legacy key/rendering unit checks."""
        self.player.inventory.add("fuse")
        self.player.progression.install_fuse()
        self.player.progression.try_combination(self.house.level.house["progression"]["combination"])
        self.player.progression.remove_boards()

    def finish_jumpscare(self):
        """Legacy terminal-state assertions now wait for the staged encounter."""
        self.assertEqual(self.manager.state,'jumpscare')
        self.ghost.jumpscare.update(self.ghost.jumpscare.duration)

    def prepare_horror(self, room='main_hall'):
        self.player.obtain_flashlight()
        self.player.position = Vec3(self.house.nav_nodes[room])
        self.player.rotation_y = self.player.camera_pivot.rotation_x = 0
        camera.rotation = Vec3(0,0,0)
        horror = self.manager.scene_manager.horror
        horror.next_allowed = 0
        horror.director.tension = .5
        return horror

    def test_menu_launch_has_no_gameplay_session(self):
        self.manager.return_to_menu()
        self.assertEqual(self.manager.state, 'menu')
        self.assertIsNone(self.manager.scene_manager)
        self.assertTrue(application.paused)
        self.assertFalse(mouse.locked)
        self.assertFalse(self.manager.hud.enabled)
        for _ in range(10):
            time.dt = .25
            self.app.taskMgr.step()
        self.assertIsNone(self.manager.scene_manager)
        self.assertFalse(any(not e.is_empty() and e.enabled and e.__class__.__name__ == 'Ghost'
                             for e in scene.entities))
        self.assertEqual(self.app.render.get_state().get_attrib(LightAttrib), None)

    def test_menu_keyboard_controls_and_start_create_one_session(self):
        self.manager.return_to_menu()
        for key in ('down arrow', 'down arrow', 'enter'):
            self.app.input(key, is_raw=True)
        self.assertEqual(self.manager.state, 'controls')
        self.app.input('escape', is_raw=True)
        self.assertEqual(self.manager.state, 'menu')
        self.manager.main_menu.selected = 0
        self.app.input('enter', is_raw=True)
        current = self.manager.scene_manager
        self.app.input('enter', is_raw=True)
        self.assertFalse(self.manager.start_game())
        self.assertIs(self.manager.scene_manager, current)
        self.assertTrue(mouse.locked)
        self.assertFalse(application.paused)

    def test_menu_mouse_routes_to_selected_row_without_duplicate_actions(self):
        self.manager.return_to_menu()
        with patch.object(mouse, 'hovered_entity', self.manager.main_menu.rows[2][0]):
            self.app.input('left mouse down', is_raw=True)
        self.assertEqual(self.manager.state, 'settings')
        self.assertIsNone(self.manager.scene_manager)
        self.app.input('escape', is_raw=True)
        with patch.object(mouse, 'hovered_entity', self.manager.main_menu.rows[0][0]):
            self.app.input('left mouse down', is_raw=True)
        current = self.manager.scene_manager
        self.assertEqual(self.manager.state, 'playing')
        self.assertIsNotNone(current)
        self.assertFalse(self.manager.start_game())

    def test_menu_pause_freezes_all_simulation_and_callbacks(self):
        horror = self.prepare_horror()
        self.assertTrue(horror.start_event('power_dip'))
        self.player.toggle_flashlight()
        self.player.stats.stamina = 40
        from game.world.door import Door
        door = Door(parent=self.house, position=(15,0,-14))
        door.open()
        self.ghost.enabled = True
        sequence = self.manager.hud.message_sequence
        def snapshot():
            return (tuple(self.player.position), self.player.stats.battery, self.player.stats.stamina,
                    self.player.stats.elapsed_time, tuple(self.ghost.position), self.ghost.ai.memory_age,
                    self.ghost.ai.repath_time, horror.clock, horror.active['elapsed'],
                    door.opening_time, sequence.t)
        self.app.input('escape', is_raw=True)
        before = snapshot()
        self.assertEqual(self.manager.state, 'paused')
        self.assertFalse(mouse.locked)
        for _ in range(20):
            time.dt = time.dt_unscaled = .25
            self.app.input('w', is_raw=True)
            self.app.input('f', is_raw=True)
            self.app.input('e', is_raw=True)
            self.app.taskMgr.step()
        self.assertEqual(snapshot(), before)
        self.app.input('escape', is_raw=True)
        time.dt = 9  # The first resumed entity frame must discard stale delta.
        self.manager.update()
        self.assertEqual(time.dt, 0)
        self.assertEqual(snapshot(), before)
        time.dt = time.dt_unscaled = 1/60
        self.app.taskMgr.step()
        self.assertLess(self.player.stats.battery, before[1])
        time.dt = time.dt_unscaled = 1/60
        self.app.taskMgr.step()
        self.assertGreater(horror.clock, before[7])
        self.assertTrue(mouse.locked)

    def test_menu_escape_closes_inventory_and_combination_before_pausing(self):
        for mode in ('inventory', 'combination'):
            self.manager.hud.panel._open(self.player, mode)
            self.app.input('escape', is_raw=True)
            self.assertFalse(self.manager.hud.panel.active)
            self.assertEqual(self.manager.state, 'playing')
            self.assertFalse(application.paused)
        self.app.input('escape', is_raw=True)
        self.assertEqual(self.manager.state, 'paused')

    def test_menu_focus_regain_preserves_pause_and_settings(self):
        self.manager.pause_game()
        self.manager.open_settings()
        self.manager.set_focus(False)
        self.manager.input('escape')
        self.assertEqual(self.manager.state, 'settings')
        self.manager.set_focus(True)
        self.assertTrue(application.paused)
        self.assertFalse(mouse.locked)
        self.manager.input('escape')
        self.assertEqual(self.manager.state, 'paused')
        self.manager.input('escape')
        self.assertEqual(self.manager.state, 'playing')
        self.assertTrue(mouse.locked)

    def test_menu_settings_cancel_does_not_apply_and_keyboard_cycles(self):
        self.manager.pause_game()
        self.manager.open_settings()
        self.app.input('right arrow', is_raw=True)
        self.assertEqual(self.manager.settings_menu.draft['mouse_sensitivity'], 1.25)
        self.app.input('escape', is_raw=True)
        self.assertEqual(self.manager.preferences.values['mouse_sensitivity'], 1)
        self.assertEqual(tuple(self.player.mouse_sensitivity), (40,40))
        self.assertEqual(self.manager.state, 'paused')
        self.manager.open_settings()
        self.assertEqual(self.manager.settings_menu.draft['mouse_sensitivity'], 1)

    def test_menu_live_settings_restore_effects_and_keep_flashlight_shader(self):
        horror = self.prepare_horror()
        horror.start_event('power_dip')
        horror.update(1)
        self.manager.pause_game()
        self.manager.open_settings()
        self.manager.settings_menu.draft.update(mouse_sensitivity=1.5, brightness=1.5,
                                               horror_frequency=0, reduced_flicker=False,
                                               reduced_shake=True, jumpscare_intensity=.25)
        self.assertTrue(self.manager.apply_settings())
        self.assertIsNone(horror.active)
        self.assertEqual(horror.frequency, 0)
        self.assertFalse(horror.reduced_flicker)
        self.assertEqual(tuple(self.player.mouse_sensitivity), (60,60))
        self.assertAlmostEqual(horror.lights[0].color.r, .15)
        self.assertEqual(self.player.flashlight_light._light.get_lens().get_fov().x, FLASHLIGHT_FOV)
        self.manager.resume_game()
        self.ghost.jumpscare.trigger()
        self.assertEqual(self.ghost.jumpscare.intensity, .25)
        self.assertTrue(self.ghost.jumpscare.preference_reduced_shake)

    def test_menu_shadow_and_difficulty_apply_only_to_new_sessions(self):
        self.manager.pause_game()
        self.manager.open_settings()
        self.manager.settings_menu.draft.update(shadow_quality='high', ghost_difficulty='hard')
        self.manager.apply_settings()
        self.assertEqual(self.ghost.ai.speed_multiplier, 1)
        self.assertEqual(self.player.flashlight_light._light.get_shadow_buffer_size().x, 512)
        self.manager.restart_game()
        player = self.manager.scene_manager.player
        ghost = self.manager.scene_manager.ghost
        self.assertEqual(player.flashlight_light._light.get_shadow_buffer_size().x, 1024)
        self.assertEqual(ghost.ai.speed_multiplier, 1.1)
        self.assertEqual(ghost.ai.detection_multiplier, 1.2)

    def test_menu_save_failure_keeps_settings_screen_and_preferences(self):
        self.manager.pause_game()
        self.manager.open_settings()
        self.manager.settings_menu.draft['brightness'] = 2
        with patch.object(self.manager.preferences, 'save', side_effect=PermissionError()):
            self.assertFalse(self.manager.apply_settings())
        self.assertEqual(self.manager.state, 'settings')
        self.assertEqual(self.manager.preferences.values['brightness'], 1)
        self.assertIn('Could not save', self.manager.settings_menu.status.text)

    def test_menu_new_games_cleanup_entities_lights_timers_and_handlers(self):
        from collections import Counter
        self.app.taskMgr.step()
        self.app.taskMgr.step()
        baseline = (len(scene.entities), len(scene.collidables), len(application.sequences))
        names = Counter(e.name for e in scene.entities)
        for index in range(6):
            current = self.manager.scene_manager
            current.player.inventory.add('fuse')
            current.player.progression.install_fuse()
            self.manager.pause_game()
            self.manager.return_to_menu()
            self.assertTrue(current.house.is_empty())
            self.assertFalse(self.manager.hud.panel.active)
            self.assertIsNone(self.manager.scene_manager)
            self.app.input('enter', is_raw=True)
            self.manager.scene_manager.ghost.enabled = False
            self.app.taskMgr.step()
            self.app.taskMgr.step()
            self.assertFalse(self.manager.scene_manager.player.inventory.quantities)
            self.assertFalse(self.manager.scene_manager.player.progression.power_restored)
            self.assertEqual(Counter(e.name for e in scene.entities), names)
            self.assertEqual((len(scene.entities), len(scene.collidables), len(application.sequences)), baseline)
            self.assertEqual(sum(not e.is_empty() and isinstance(e, GameManager) for e in scene.entities), 1)
            self.assertEqual(self.app.render.get_state().get_attrib(LightAttrib).get_num_on_lights(), 3)

    def test_menu_terminal_states_return_to_menu_and_restart(self):
        for terminal in (self.manager.game_over, self.manager.win_game):
            terminal()
            self.assertTrue(application.paused)
            self.assertTrue(self.manager.end_screen.enabled)
            self.manager.input('escape')
            self.assertIsNone(self.manager.scene_manager)
            self.assertFalse(self.manager.end_screen.enabled)
            self.manager.input('enter')
            self.assertEqual(self.manager.state, 'playing')
            self.manager.game_over()
            self.manager.input('r')
            self.assertEqual(self.manager.state, 'playing')

    def test_menu_return_cancels_paranormal_and_jumpscare_geometry(self):
        horror = self.prepare_horror('living')
        horror.start_event('cabinet_creak')
        temporary = horror.active['temporary'][0]
        self.manager.pause_game()
        self.manager.return_to_menu()
        self.assertTrue(temporary.is_empty())
        self.assertIsNone(horror.active)
        self.manager.start_game()
        jump = self.manager.scene_manager.ghost.jumpscare
        jump.trigger()
        proxy, overlay = jump.proxy, jump.overlay
        self.manager.return_to_menu()
        self.assertTrue(proxy.is_empty())
        self.assertTrue(overlay.is_empty())
        self.assertFalse(jump.active)

    def test_menu_resizing_fits_all_screens_and_preserves_selection(self):
        for width, height in ((640,480),(960,720),(1280,720)):
            aspect = width/height
            for screen in set(self.manager.screens.values()):
                screen.resize(aspect)
                self.assertAlmostEqual(screen.background.scale_x, aspect)
                self.assertLessEqual(1.14*screen.content.scale_x, aspect-.09)
                self.assertLessEqual(max(abs(row.y)+row.scale_y/2 for row,_ in screen.rows), .5)
            self.manager.settings_menu.selected = 4
            self.manager.settings_menu.resize(aspect)
            self.assertEqual(self.manager.settings_menu.selected, 4)

    def test_menu_pause_preserves_progression_inventory_and_hiding_timer(self):
        self.player.inventory.add('fuse')
        self.player.progression.install_fuse()
        spot = self.house.hiding_spots[0]
        self.player.position = Vec3(spot.approach)
        self.assertTrue(self.player.enter_hiding(spot))
        self.manager.pause_game()
        for _ in range(30):
            time.dt = .5
            self.app.taskMgr.step()
        self.assertEqual(self.player._hide_elapsed, 0)
        self.assertTrue(self.player.hidden)
        self.manager.resume_game()
        self.assertTrue(self.player.progression.power_restored)
        self.assertTrue(self.player.leave_hiding())
        code = self.house.level.house['progression']['combination']
        self.assertTrue(self.player.progression.try_combination(code))
        self.assertTrue(self.player.progression.remove_boards())
        self.assertEqual(self.player.inventory.count('crowbar'), 1)

    def test_menu_difficulty_preserves_wall_sweeps_and_five_states(self):
        from game.settings import GHOST_DIFFICULTY
        self.ghost.position = Vec3(0,0,-8)
        self.player.position = Vec3(5,0,-8)
        for speed, detection in GHOST_DIFFICULTY.values():
            self.ghost.ai.speed_multiplier, self.ghost.ai.detection_multiplier = speed, detection
            self.ghost.position = Vec3(0,0,-8)
            time.dt = 1
            self.ghost.ai._move_directly_toward_player()
            self.assertLess(self.ghost.x, 2)
        self.assertEqual({state.name for state in GhostState},
                         {'PATROL','INVESTIGATE','SEARCH','CHASE','JUMPSCARE'})

    def test_menu_fps_cap_uses_clock_limiter_and_unlimited_restores(self):
        from panda3d.core import ClockObject
        clock = ClockObject.get_global_clock()
        try:
            for cap in (30,60,120):
                self.manager.preferences.values['fps_cap'] = cap
                self.manager._apply_fps_cap()
                self.assertEqual(clock.get_mode(), ClockObject.MLimited)
                clock.tick()  # Flush time spent constructing the scene before measuring.
                clock.tick()
                self.assertAlmostEqual(clock.get_dt(), 1/cap, delta=.5/cap)
        finally:
            self.manager.preferences.values['fps_cap'] = 0
            self.manager._apply_fps_cap()
        self.assertEqual(clock.get_mode(), ClockObject.MNormal)

    def test_menu_modal_hud_does_not_cover_inventory_and_puzzle_text(self):
        self.manager.input('tab')
        self.assertFalse(self.manager.hud.objective.enabled)
        self.assertFalse(self.manager.hud.message.enabled)
        self.manager.hud.show_message('The ghost is checking this wardrobe. E to leave!')
        self.assertTrue(self.manager.hud.message.enabled)
        self.assertLess(self.manager.hud.message.y, -.41)
        self.manager.input('escape')
        self.assertTrue(self.manager.hud.objective.enabled)
        self.assertAlmostEqual(self.manager.hud.message.y, .28)

    def test_menu_first_resumed_engine_frame_does_not_expire_hud_callback(self):
        sequence = self.manager.hud.message_sequence
        self.manager.pause_game()
        self.manager.resume_game()
        time.dt = time.dt_unscaled = 9
        self.app.taskMgr.step()
        self.assertEqual(sequence.t, 0)
        self.assertTrue(self.manager.hud.message.text)
        self.assertEqual(self.player.stats.elapsed_time, 0)
        time.dt = time.dt_unscaled = 1/60
        self.app.taskMgr.step()
        self.assertAlmostEqual(sequence.t, 1/60)

    def test_menu_quit_button_disposes_session_before_quitting(self):
        current = self.manager.scene_manager
        self.manager.pause_game()
        self.manager.pause_menu.selected = 5
        with patch('game.game_manager.application.quit') as quit_call:
            self.app.input('enter', is_raw=True)
            quit_call.assert_called_once_with()
        self.assertIsNone(self.manager.scene_manager)
        self.assertTrue(current.house.is_empty())

    def test_horror_event_cooldown_and_single_active_effect(self):
        horror = self.prepare_horror()
        self.assertTrue(horror.start_event('power_dip'))
        self.assertFalse(horror.start_event('room_dimming'))
        horror.update(4)
        self.assertIsNone(horror.active)
        self.assertGreaterEqual(horror.next_allowed-horror.clock,28)
        self.assertFalse(horror.start_event('power_dip'))
        horror.clock = horror.next_allowed
        self.assertTrue(horror.start_event('power_dip'))
        horror.stop()

    def test_horror_seeded_schedule_is_reproducible_and_independent_of_global_rng(self):
        self.prepare_horror()
        traces=[]
        for global_seed in (10,999):
            random.seed(global_seed)
            horror = HorrorManager(self.house,self.player,self.ghost,self.manager.scene_manager.lights,seed=1729)
            for _ in range(1800): horror.update(.25)
            traces.append(list(horror.history))
            horror.stop()
        self.assertEqual(traces[0],traces[1])
        self.assertGreaterEqual(len(traces[0]),3)
        self.assertGreaterEqual(traces[0][0][0],30)

    def test_horror_scheduling_is_identical_at_four_frame_rates(self):
        self.prepare_horror()
        traces=[]
        for fps in (4,30,60,120):
            horror=HorrorManager(self.house,self.player,self.ghost,self.manager.scene_manager.lights,seed=94,frequency=2)
            for _ in range(180*fps): horror.update(1/fps)
            traces.append(list(horror.history))
            horror.stop()
        self.assertGreater(len(traces[0]),0)
        self.assertTrue(all(trace==traces[0] for trace in traces))

    def test_horror_eligibility_suppresses_interfaces_chases_hiding_and_puzzle_proximity(self):
        horror=self.prepare_horror()
        self.assertTrue(horror.eligible_events())
        self.manager.input('tab')
        self.assertFalse(horror.eligible_events())
        self.manager.input('escape')
        self.ghost.ai.state=GhostState.CHASE
        self.assertFalse(horror.eligible_events())
        self.ghost.ai.state=GhostState.PATROL
        self.player.position=Vec3(-3.2,0,8.5)
        self.assertFalse(horror.eligible_events())
        spot=self.house.hiding_spots[0]
        self.player.position=Vec3(spot.approach)
        self.player.enter_hiding(spot)
        self.assertFalse(horror.eligible_events())
        self.player.leave_hiding()
        self.manager.game_over()
        self.assertFalse(horror.eligible_events())

    def test_horror_critical_interface_immediately_restores_an_active_event(self):
        horror=self.prepare_horror()
        before=[tuple(light.color) for light in horror.lights]
        horror.start_event('power_dip')
        horror.update(2)
        self.assertNotEqual(before,[tuple(light.color) for light in horror.lights])
        self.manager.input('tab')
        self.assertIsNone(horror.active)
        self.assertEqual(before,[tuple(light.color) for light in horror.lights])

    def test_horror_lighting_restores_exactly_and_never_changes_the_flashlight(self):
        horror=self.prepare_horror()
        self.player.toggle_flashlight()
        torch=tuple(self.player.flashlight_light.color)
        for event in ('power_dip','fill_failure','room_dimming','hallway_dim'):
            horror.next_allowed=0
            original={id(e):tuple(e.color) for e in (*horror.lights,*descendants(self.house.rooms['main_hall']),*self.house.walls)}
            self.assertTrue(horror.start_event(event))
            duration=horror.active['definition'].seconds
            horror.update(duration/2)
            self.assertEqual(torch,tuple(self.player.flashlight_light.color))
            self.assertTrue(any(tuple(e.color)!=original[id(e)] for e,_ in horror.active['colors']))
            horror.update(duration/2)
            self.assertIsNone(horror.active)
            for e in (*horror.lights,*descendants(self.house.rooms['main_hall']),*self.house.walls):
                self.assertEqual(tuple(e.color),original[id(e)])

    def test_horror_environment_transforms_restore_without_moving_colliders_or_pickups(self):
        horror=self.prepare_horror('living')
        colliders={id(e):(Vec3(e.world_position),Vec3(e.world_rotation)) for e in scene.collidables}
        pickups={name:Vec3(e.world_position) for name,e in self.house.pickups.items()}
        for name in ('prop_shift','prop_vibration','cabinet_creak','distant_close'):
            horror.next_allowed=0
            horror.room_entered=horror.clock
            self.assertTrue(horror.start_event(name))
            active=horror.active
            target,position,rotation=active['transforms'][0]
            horror.update(.7)
            self.assertTrue(target.position!=position or target.rotation!=rotation)
            for e in scene.collidables:
                self.assertEqual((e.world_position,e.world_rotation),colliders[id(e)])
            for key,e in self.house.pickups.items(): self.assertEqual(e.world_position,pickups[key])
            horror.cancel_active()
            if not target.is_empty():
                self.assertEqual(target.position,position)
                self.assertEqual(target.rotation,rotation)

    def test_horror_apparition_expires_without_collision_or_damage(self):
        horror=self.prepare_horror()
        before=len(scene.collidables)
        self.assertTrue(horror.start_event('apparition'))
        apparition=horror.active['temporary'][0]
        self.assertIsNone(apparition.collider)
        self.assertEqual(len(scene.collidables),before)
        self.assertEqual(self.manager.state,'playing')
        horror.update(6)
        self.assertIsNone(horror.active)
        self.assertTrue(apparition.is_empty())

    def test_horror_apparition_disappears_when_illuminated_or_approached(self):
        horror=self.prepare_horror()
        for illuminated in (True,False):
            horror.next_allowed=0
            self.player.position=Vec3(0,0,0)
            self.player.rotation_y=0
            camera.rotation=Vec3(0,0,0)
            self.assertTrue(horror.start_event('apparition'))
            apparition=horror.active['temporary'][0]
            if illuminated:
                self.aim(apparition.world_position)
                self.player.toggle_flashlight()
            else:
                self.player.position=Vec3(apparition.world_position)+Vec3(0,-.85,-1)
            horror.update(1/30)
            self.assertIsNone(horror.active)
            self.assertTrue(apparition.is_empty())
            if illuminated: self.player.toggle_flashlight()

    def test_horror_events_leave_ghost_navigation_and_puzzle_inventory_intact(self):
        horror=self.prepare_horror('living')
        self.player.inventory.add('fuse')
        self.player.inventory.add('battery',2)
        inventory=dict(self.player.inventory.quantities)
        graph={node:tuple(edges) for node,edges in self.house.graph.items()}
        horror.start_event('cabinet_creak')
        horror.update(1)
        for a,neighbors in self.house.graph.items():
            for b in neighbors:
                self.assertTrue(self.ghost.ai.navigation.segment_clear(self.house.nav_nodes[a],self.house.nav_nodes[b]))
        self.assertEqual(graph,{node:tuple(edges) for node,edges in self.house.graph.items()})
        self.assertEqual(inventory,self.player.inventory.quantities)
        self.assertFalse(self.player.progression.power_restored)
        self.assertFalse(self.house.exit_door.opening)
        self.assertFalse(self.house.basement_door.opening)
        horror.cancel_active()

    def test_horror_repeated_effects_do_not_accumulate_entities_lights_or_sequences(self):
        horror=self.prepare_horror('living')
        self.app.taskMgr.step()  # Flush Ursina's deferred scene-list removals.
        baseline=(len(scene.entities),len(scene.collidables),len(application.sequences),self.app.render.get_state().get_attrib(LightAttrib))
        for _ in range(60):
            horror.next_allowed=0
            self.assertTrue(horror.start_event('cabinet_creak'))
            horror.update(1)
            horror.cancel_active()
            self.app.taskMgr.step()
            self.assertEqual(len(scene.entities),baseline[0])
            self.assertEqual(len(scene.collidables),baseline[1])
            self.assertLessEqual(len(application.sequences),baseline[2])
            self.assertEqual(self.app.render.get_state().get_attrib(LightAttrib),baseline[3])
        self.assertLessEqual(len(horror.history),64)

    def test_horror_restart_cleans_active_effects_and_resets_seed_and_tension(self):
        horror=self.prepare_horror('living')
        horror.start_event('cabinet_creak')
        temporary=horror.active['temporary'][0]
        self.manager.restart_game()
        fresh=self.manager.scene_manager.horror
        self.assertFalse(horror.running)
        self.assertTrue(temporary.is_empty())
        self.assertIsNone(horror.active)
        self.assertEqual(fresh.clock,0)
        self.assertEqual(fresh.director.tension,0)
        self.assertEqual(list(fresh.history),[])

    def test_horror_director_rest_periods_after_chase_and_hiding(self):
        horror=self.prepare_horror()
        self.ghost.ai.state=GhostState.CHASE
        horror.update(1)
        self.ghost.ai.state=GhostState.SEARCH
        horror.update(1/30)
        self.assertGreater(horror.director.quiet_until,horror.clock+17)
        self.assertFalse(horror.eligible_events())
        self.assertGreater(horror.director.tension,0)

    def test_horror_accessibility_frequency_and_intensity_limits(self):
        self.prepare_horror()
        horror=HorrorManager(self.house,self.player,self.ghost,self.manager.scene_manager.lights,frequency=0)
        horror.update(600)
        self.assertFalse(horror.eligible_events())
        self.assertEqual(list(horror.history),[])
        horror=self.manager.scene_manager.horror
        with patch('game.settings.HORROR_INTENSITY_LIMIT',.1):
            self.assertTrue(horror.start_event('power_dip'))
            self.assertLessEqual(horror.active['intensity'],.1)
        horror.cancel_active()

    def test_horror_jumpscare_stages_freeze_controls_and_preserve_real_ghost_position(self):
        self.prepare_horror()
        self.player.position=Vec3(0,0,-8)
        self.ghost.position=Vec3(0,0,-7.2)
        self.ghost.rotation_y=180
        original=Vec3(self.ghost.world_position)
        self.ghost.ai.state=GhostState.CHASE
        self.ghost.ai.update()
        scare=self.ghost.jumpscare
        self.assertEqual(self.manager.state,'jumpscare')
        self.assertTrue(scare.active)
        self.assertFalse(self.player.enabled)
        self.assertFalse(self.ghost.enabled)
        self.assertEqual(scare.phase,'seize')
        self.assertFalse(scare.trigger())
        self.app.input('tab',is_raw=True)
        self.app.input('e',is_raw=True)
        self.assertFalse(self.manager.hud.panel.active)
        scare.update(scare.duration*.4)
        self.assertEqual(scare.phase,'approach')
        self.assertEqual(self.ghost.world_position,original)
        self.assertGreater(scare.proxy.z-.225,.1)
        scare.update(scare.duration*.4)
        self.assertEqual(scare.phase,'fade')
        scare.update(scare.duration)
        self.assertEqual(self.manager.state,'dead')
        self.assertIsNone(scare.proxy)
        self.assertIsNone(scare.overlay)

    def test_horror_jumpscare_duration_at_four_frame_rates(self):
        from game.ghost.jumpscare import Jumpscare
        for fps in (4,30,60,120):
            completed=[]
            scare=Jumpscare()
            scare.begin(lambda:completed.append(True))
            for _ in range(math.ceil(scare.duration*fps)-1): scare.update(1/fps)
            self.assertTrue(scare.active)
            scare.update(1/fps)
            self.assertFalse(scare.active)
            self.assertEqual(completed,[True])
            scare.update(5)
            self.assertEqual(completed,[True])

    def test_horror_restart_during_jumpscare_restores_camera_and_temporary_entities(self):
        self.prepare_horror()
        self.ghost.jumpscare.trigger()
        scare=self.ghost.jumpscare
        scare.update(.8)
        proxy,overlay=scare.proxy,scare.overlay
        self.app.input('r',is_raw=True)
        self.assertEqual(self.manager.state,'playing')
        self.assertTrue(proxy.is_empty())
        self.assertTrue(overlay.is_empty())
        self.assertEqual(camera.fov,90)
        self.assertEqual(camera.rotation,Vec3(0,0,0))
        self.assertEqual(camera.parent,self.manager.scene_manager.player.camera_pivot)
        self.assertFalse(self.manager.scene_manager.ghost.jumpscare.triggered)

    def test_horror_wardrobe_cinematic_is_visible_over_world_occluders(self):
        spot=self.house.hiding_spots[0]
        self.player.position=Vec3(spot.approach)
        self.player.enter_hiding(spot)
        self.ghost.position=spot.approach+Vec3(1,0,0)
        self.ghost.ai.state=GhostState.SEARCH
        self.ghost.ai.search_time=GHOST_ACTIVE_SEARCH_SECONDS
        self.ghost.ai.recovery_time=0
        self.ghost.ai.inspection_target=spot
        self.ghost.ai.navigation.clear()
        self.ghost.ai.inspection_time=1.49
        time.dt=.03
        self.ghost.ai.update()
        self.assertEqual(self.manager.state,'jumpscare')
        image=self.capture('render_horror_wardrobe_regression.png')
        center_mean=sum(ImageStat.Stat(image.crop((600,300,680,400))).mean)/3
        self.assertGreater(center_mean,35)
        self.assertFalse(self.manager.hud.panel.active)
        self.finish_jumpscare()

    def test_horror_restart_cycles_clean_events_and_cinematic_entities(self):
        self.app.taskMgr.step()
        self.app.taskMgr.step()
        baseline=(len(scene.entities),len(scene.collidables),
                  self.app.render.get_state().get_attrib(LightAttrib).get_num_on_lights())
        for index in range(12):
            horror=self.prepare_horror('living')
            if index%2:
                self.ghost.jumpscare.trigger()
                self.ghost.jumpscare.update(.7)
            else:
                horror.start_event('cabinet_creak')
                horror.update(.7)
            self.manager.restart_game()
            self.player,self.house,self.ghost=(self.manager.scene_manager.player,self.manager.scene_manager.house,
                                              self.manager.scene_manager.ghost)
            self.ghost.enabled=False
            time.dt=1/60
            self.app.taskMgr.step()
            self.app.taskMgr.step()
            self.assertEqual((len(scene.entities),len(scene.collidables),
                              self.app.render.get_state().get_attrib(LightAttrib).get_num_on_lights()),baseline)
            self.assertEqual(camera.rotation,Vec3(0,0,0))
            self.assertFalse(self.player.inventory.quantities)
            self.assertIsNone(self.manager.scene_manager.horror.active)

    def test_horror_reduced_jumpscare_and_focus_loss_freeze_time(self):
        self.prepare_horror()
        with patch('game.settings.JUMPSCARE_INTENSITY',0):
            self.ghost.jumpscare.trigger()
        scare=self.ghost.jumpscare
        original=Vec3(camera.world_rotation)
        self.manager.set_focus(False)
        time.dt=.5
        self.manager.update()
        self.assertEqual(scare.elapsed,0)
        self.manager.set_focus(True)
        self.manager.update()  # First resume frame has zero dt.
        time.dt=.5
        self.manager.update()
        self.assertEqual(camera.world_rotation,original)
        self.assertAlmostEqual(scare.proxy.z,2.4,places=6)
        self.assertEqual(scare.overlay.color.a,0)
        self.manager.restart_game()

    def test_horror_full_puzzle_escape_with_live_director_has_no_softlocks(self):
        self._horror_during_walk=True
        self.test_progression_complete_chain_walks_real_routes_and_escapes()
        horror=self.manager.scene_manager.horror
        self.assertGreater(len(horror.history),0)
        self.assertIsNone(horror.active)
        self.assertFalse(horror.running)

    def test_progression_inventory_modal_blocks_input_but_not_simulation(self):
        self.player.obtain_flashlight()
        self.player.toggle_flashlight()
        before = Vec3(self.player.position)
        yaw = self.player.rotation_y
        self.app.input('tab', is_raw=True)
        self.assertTrue(self.manager.hud.panel.active)
        self.assertFalse(application.paused)
        self.app.input('w', is_raw=True)
        self.app.input('f', is_raw=True)
        self.app.input('e', is_raw=True)
        mouse.velocity = Vec3(.4,.2,0)
        charge = self.player.stats.battery
        time.dt = .5
        self.player.update()
        self.assertEqual(self.player.position, before)
        self.assertEqual(self.player.rotation_y, yaw)
        self.assertLess(self.player.stats.battery, charge)
        self.assertTrue(self.player.flashlight_on)
        self.app.input('escape', is_raw=True)
        self.assertFalse(self.manager.hud.panel.active)
        self.assertFalse(held_keys['w'])
        self.assertEqual(mouse.velocity, Vec3(0,0,0))
        self.assertEqual(self.manager.state, 'playing')

    def test_progression_battery_requires_confirmation_and_keeps_full_charge_item(self):
        self.player.inventory.add('battery', 2)
        self.manager.input('tab')
        panel = self.manager.hud.panel
        panel.handle('u')
        panel.handle('backspace')
        panel.handle('enter')
        self.assertEqual(self.player.inventory.count('battery'),2)
        panel.handle('u')
        panel.handle('enter')
        self.assertEqual(self.player.inventory.count('battery'),2)  # no flashlight
        self.player.obtain_flashlight()
        self.player.stats.battery = MAX_BATTERY
        panel.handle('u')
        panel.handle('enter')
        self.assertEqual(self.player.inventory.count('battery'),2)
        self.player.stats.battery = 10
        panel.handle('u')
        panel.handle('enter')
        self.assertEqual(self.player.stats.battery,45)
        self.assertEqual(self.player.inventory.count('battery'),1)
        panel.handle('enter')
        self.assertEqual(self.player.inventory.count('battery'),1)  # Enter repeat cannot spend twice

    def test_progression_fuse_commits_once_and_does_not_change_world_lighting(self):
        progression = self.player.progression
        lights = [tuple(light.color) for light in self.manager.scene_manager.lights]
        self.assertFalse(progression.install_fuse())
        self.assertFalse(progression.power_restored)
        self.assertFalse(self.house.pickups['kitchen_tally'].enabled)
        self.player.inventory.add('fuse')
        self.assertTrue(progression.install_fuse())
        self.assertEqual(self.player.inventory.count('fuse'),0)
        self.assertTrue(self.house.pickups['kitchen_tally'].enabled)
        self.assertFalse(progression.install_fuse())
        self.assertEqual(lights,[tuple(light.color) for light in self.manager.scene_manager.lights])

    def test_progression_wrong_combinations_do_not_consume_items_or_lock_out(self):
        progression = self.player.progression
        code = self.house.level.house['progression']['combination']
        self.assertFalse(progression.try_combination(code))
        self.assertFalse(self.player.inventory.count('crowbar'))
        self.player.inventory.add('fuse')
        progression.install_fuse()
        for code_attempt in ('0000','12','abcd','9999'):
            self.assertFalse(progression.try_combination(code_attempt))
        self.assertTrue(progression.try_combination(code))
        self.assertEqual(self.player.inventory.count('crowbar'),1)
        self.assertFalse(progression.try_combination(code))
        self.assertEqual(self.player.inventory.count('crowbar'),1)

    def test_progression_combination_keyboard_backspace_escape_and_retry(self):
        self.player.inventory.add('fuse')
        self.player.progression.install_fuse()
        self.player.position = Vec3(-3.2,0,8.5)
        self.house.puzzles['lockbox'].interact(self.player)
        panel = self.manager.hud.panel
        self.app.input('1',is_raw=True)
        self.app.input('backspace',is_raw=True)
        self.assertEqual(panel.digits,'')
        self.app.input('enter',is_raw=True)
        self.assertIn('all four',panel.status)
        for digit in '0000': self.app.input(digit,is_raw=True)
        self.app.input('enter',is_raw=True)
        self.assertIn('Incorrect',panel.status)
        self.assertEqual(panel.digits,'')
        self.app.input('escape',is_raw=True)
        self.house.puzzles['lockbox'].interact(self.player)
        for digit in self.house.level.house['progression']['combination']:
            self.app.input(digit,is_raw=True)
        self.app.input('enter',is_raw=True)
        self.assertFalse(panel.active)
        self.assertTrue(self.player.progression.safe_unlocked)

    def test_progression_boards_require_reusable_tool_and_guard_exit_key(self):
        boards = self.house.puzzles['boards']
        self.player.position = Vec3(7.2,0,9)
        self.aim(self.house.pickups['bedroom_exit_key'].world_position)
        self.assertIsNot(get_interaction_hit(self.player).entity,self.house.pickups['bedroom_exit_key'])
        boards.interact(self.player)
        self.assertFalse(self.player.progression.boards_removed)
        self.assertFalse(self.house.pickups['bedroom_exit_key'].enabled)
        self.unlock_key_fixture()
        self.assertFalse(boards.enabled)
        self.assertTrue(self.house.pickups['bedroom_exit_key'].enabled)
        self.assertEqual(self.player.inventory.count('crowbar'),1)
        self.assertFalse(self.player.progression.remove_boards())
        self.assertEqual(self.player.inventory.count('crowbar'),1)

    def test_progression_notes_are_collected_readable_and_unique(self):
        note = self.house.pickups['living_instructions']
        note.interact(self.player)
        panel = self.manager.hud.panel
        self.assertEqual(panel.mode,'note')
        self.assertIn('portraits, bells, cradles, chairs', ' '.join(panel.body.text.split()))
        self.assertEqual(self.player.inventory.count('household_order'),1)
        self.assertFalse(self.player.inventory.add('household_order'))
        self.app.input('e',is_raw=True)
        self.assertEqual(panel.mode,'note')
        self.app.input('escape',is_raw=True)
        self.app.input('tab',is_raw=True)
        self.app.input('enter',is_raw=True)
        self.assertEqual(panel.mode,'note')
        self.app.input('tab',is_raw=True)
        self.assertFalse(panel.active)

    def test_progression_objectives_and_restart_reset_every_puzzle(self):
        progression = self.player.progression
        self.assertIn('foyer flashlight',progression.objective)
        self.player.obtain_flashlight()
        self.assertIn('storage',progression.objective)
        self.player.inventory.add('fuse')
        progression.refresh()
        self.assertIn('Install',self.manager.hud.objective.text)
        progression.install_fuse()
        self.assertIn('clues',progression.objective)
        progression.try_combination(self.house.level.house['progression']['combination'])
        self.assertIn('crowbar',progression.objective)
        progression.remove_boards()
        self.assertIn('Collect the exit key',progression.objective)
        self.house.pickups['bedroom_exit_key'].interact(self.player)
        self.assertIn('north exit',progression.objective)
        self.manager.input('tab')
        self.manager.game_over()
        self.assertFalse(self.manager.hud.panel.active)
        self.manager.input('r')
        player = self.manager.scene_manager.player
        self.assertFalse(player.progression.power_restored)
        self.assertFalse(player.progression.safe_unlocked)
        self.assertFalse(player.progression.boards_removed)
        self.assertEqual(player.inventory.quantities,{})
        self.assertFalse(self.manager.scene_manager.house.pickups['bedroom_exit_key'].enabled)
        self.assertIn('foyer flashlight',self.manager.hud.objective.text)

    def test_progression_ghost_can_catch_during_inventory_and_closes_interface(self):
        self.player.position = Vec3(0,0,-8)
        self.ghost.position = Vec3(0,0,-7.2)
        self.ghost.rotation_y = 180
        self.manager.input('tab')
        self.ghost.ai.state = GhostState.CHASE
        self.ghost.ai.detection = 1
        self.ghost.ai.update()
        self.finish_jumpscare()
        self.assertEqual(self.manager.state,'dead')
        self.assertFalse(self.manager.hud.panel.active)

    def test_progression_focus_and_resize_preserve_modal_without_sticky_keys(self):
        self.manager.input('tab')
        panel = self.manager.hud.panel
        self.manager.set_focus(False)
        self.assertTrue(application.paused)
        self.manager.input('escape')
        self.assertTrue(panel.active)
        self.manager.set_focus(True)
        self.assertFalse(application.paused)
        for aspect in (4/3,16/9,1):
            self.manager.hud.layout(aspect)
            self.assertLessEqual(1.18*panel.scale_x,aspect-.05)
        self.manager.input('escape')
        self.assertFalse(panel.active)
        self.assertFalse(held_keys['w'])

    def test_progression_hidden_inventory_preserves_breathing_risk_and_suppresses_look(self):
        spot = self.house.hiding_spots[0]
        self.player.position = Vec3(spot.approach)
        self.assertTrue(self.player.enter_hiding(spot))
        self.manager.input('tab')
        before = Vec3(self.player.position)
        yaw = self.player.rotation_y
        mouse.velocity = Vec3(.5,.5,0)
        for _ in range(13):
            time.dt=1
            self.player.update()
        self.assertEqual(self.player.position,before)
        self.assertEqual(self.player.rotation_y,yaw)
        self.assertTrue(any(event.kind=='breathing' for event in self.player.stats.noise_events))
        self.manager.input('e')
        self.assertTrue(self.player.hidden)
        self.manager.input('escape')
        self.player.input('e')
        self.assertFalse(self.player.hidden)

    def test_progression_ghost_remains_active_during_note_and_combination(self):
        self.player.position = Vec3(0,0,-8)
        self.ghost.position = Vec3(0,0,-7.2)
        self.ghost.rotation_y = 180
        self.player.inventory.add('household_order')
        self.manager.hud.panel.open_note(self.player,'household_order')
        self.ghost.ai.state = GhostState.CHASE
        self.ghost.ai.detection = 1
        self.ghost.ai.update()
        self.finish_jumpscare()
        self.assertEqual(self.manager.state,'dead')
        self.manager.restart_game()
        player, ghost, house = (self.manager.scene_manager.player,self.manager.scene_manager.ghost,
                                self.manager.scene_manager.house)
        ghost.enabled=False
        player.position, ghost.position, ghost.rotation_y = Vec3(-3.2,0,8.5),Vec3(-3.2,0,7.7),0
        player.inventory.add('fuse')
        player.progression.install_fuse()
        house.puzzles['lockbox'].interact(player)
        self.assertEqual(self.manager.hud.panel.mode,'combination')
        ghost.ai.state=GhostState.CHASE
        ghost.ai.detection=1
        ghost.ai.update()
        self.assertEqual(self.manager.state,'jumpscare')
        ghost.jumpscare.update(ghost.jumpscare.duration)
        self.assertEqual(self.manager.state,'dead')
        self.assertFalse(self.manager.hud.panel.active)

    def test_progression_complete_chain_walks_real_routes_and_escapes(self):
        current = 'foyer'
        def visit(entry, entity):
            nonlocal current
            self.walk_route(current,entry['room'])
            self.walk_to(entry['approach'])
            self.aim(entity.world_position)
            self.assertIs(get_interaction_hit(self.player).entity,entity)
            self.player.input('e')
            if self.manager.hud.panel.mode == 'note': self.manager.input('escape')
            self.walk_to(self.house.nav_nodes[entry['room']]) if not self.manager.hud.panel.active else None
            current = entry['room']
        spawns = {entry['id']:entry for entry in self.house.level.spawns['pickups']}
        props = {entry['id']:entry for entry in self.house.level.house['progression']['props']}
        for item in ('foyer_flashlight','living_instructions','storage_fuse'):
            visit(spawns[item],self.house.pickups[item])
        visit(props['fuse_box'],self.house.puzzles['fuse_box'])
        visit(spawns['kitchen_tally'],self.house.pickups['kitchen_tally'])
        visit(props['lockbox'],self.house.puzzles['lockbox'])
        for digit in '0000': self.manager.input(digit)
        self.manager.input('enter')
        self.assertFalse(self.player.progression.safe_unlocked)
        for digit in self.house.level.house['progression']['combination']: self.manager.input(digit)
        self.manager.input('enter')
        self.walk_to(self.house.nav_nodes[current])
        visit(props['boards'],self.house.puzzles['boards'])
        visit(spawns['bedroom_exit_key'],self.house.pickups['bedroom_exit_key'])
        self.walk_route(current,'exit_approach')
        self.aim(Vec3(0,1.5,17.8))
        self.player.input('e')
        for _ in range(48):
            time.dt=1/60
            self.house.exit_door.update()
        camera.rotation=Vec3(0,0,0)
        self.player.rotation_y=0
        self.player.camera_pivot.rotation_x=0
        held_keys['w']=1
        for _ in range(60):
            time.dt=1/60
            self.player.update()
            self.house.exit_door.update()
            if self.manager.state=='escaped': break
        held_keys.clear()
        self.assertEqual(self.manager.state,'escaped')
        self.assertEqual(self.player.inventory.count('crowbar'),1)
        self.assertFalse(self.house.basement_door.opened)

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
            self.player.position = Vec3(0, 0, -8)
            start = getattr(self.player, axis)
            self.move(key, seconds=0.2)
            self.assertAlmostEqual(getattr(self.player, axis) - start, expected, delta=0.03)
        self.player.position = Vec3(0, 0, -8)
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
        self.player.position = Vec3(0.8, 0, -9)
        self.player.rotation_y = 90
        held_keys["shift"] = 1
        self.move("w", seconds=1.5, dt=0.25)
        self.assertLessEqual(self.player.x, 1.4)
        self.assertAlmostEqual(self.player.y, 0, delta=0.01)
        self.player.position = Vec3(-17, 0, -17)
        self.player.rotation_y = -135
        self.move("w", seconds=1.5, dt=0.25)
        self.assertGreater(self.player.x, -17.7)
        self.assertGreater(self.player.z, -17.7)

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
        self.player.stats.battery = FLASHLIGHT_DRAIN_PER_SECOND / 2
        self.player.input("f")
        self.player._update_flashlight()
        self.assertEqual(self.player.stats.battery, 0)
        self.assertFalse(self.player.flashlight_on)
        self.assertEqual(self.player.flashlight_light.color.r, 0)
        self.player.input("f")
        self.assertFalse(self.player.flashlight_on)

    def test_battery_and_key_pickups_with_real_rays(self):
        self.unlock_key_fixture()
        self.player.obtain_flashlight()
        battery = self.pickup(BatteryPickup)
        self.player.position = Vec3(*self.house.level.spawns["pickups"][1]["approach"])
        self.player.stats.battery = 10
        self.aim(battery.world_position)
        self.assertIs(get_interaction_hit(self.player).entity, battery)
        self.player.input("e")
        self.assertEqual(self.player.stats.battery, 10)
        self.assertEqual(self.player.inventory.count("battery"), 1)
        self.manager.input("tab")
        panel = self.manager.hud.panel
        panel.selected = panel.item_ids().index("battery")
        panel.handle("u")
        panel.handle("enter")
        panel.handle("escape")
        self.assertEqual(self.player.stats.battery, 45)
        self.player.add_battery(1000)
        self.assertEqual(self.player.stats.battery, MAX_BATTERY)
        key = self.pickup(KeyPickup)
        self.player.position = Vec3(*self.house.level.spawns["pickups"][2]["approach"])
        self.aim(key.world_position)
        self.assertIs(get_interaction_hit(self.player).entity, key)
        self.player.input("e")
        self.assertTrue(self.player.inventory.has_key("exit_key"))
        self.assertEqual(self.player.inventory.key_count(), 1)

    def test_wall_blocks_interaction_and_exit_requires_crossing(self):
        key = self.pickup(KeyPickup)
        self.player.position = Vec3(1, 0, -9)
        self.aim(key.world_position)
        self.assertIsNot(get_interaction_hit(self.player).entity, key)
        door = self.house.exit_door
        self.player.position = Vec3(0, 0, 16.3)
        self.aim(Vec3(0, 1.5, 17.8))
        self.assertIs(get_interaction_hit(self.player).entity, door)
        self.player.input("e")
        self.assertFalse(door.opened)
        self.assertIsNotNone(door.collider)
        self.player.rotation_y = 0
        camera.rotation = Vec3(0, 0, 0)
        self.move("w", seconds=0.5)
        self.assertLess(self.player.z, 17.4)
        self.player.inventory.add_key("exit_key")
        self.aim(Vec3(0, 1.5, 17.8))
        self.player.input("e")
        self.assertTrue(door.opening)
        self.assertFalse(door.opened)
        self.assertIsNotNone(door.collider)
        door.update()
        self.assertEqual(self.manager.state, "playing")
        for _ in range(48):
            time.dt = 1 / 60
            door.update()
        self.assertTrue(door.opened)
        self.assertIsNone(door.collider)
        self.player.rotation_y = 0
        camera.rotation = Vec3(0, 0, 0)
        self.move("w", seconds=0.4)
        door.update()
        self.assertEqual(self.manager.state, "escaped")
        self.assertFalse(self.player.enabled)
        self.assertFalse(self.ghost.enabled)
        self.capture("render_escape.png")

    def test_astar_and_all_house_edges_have_clearance(self):
        route = astar("foyer", "bedroom_two", self.house.nav_nodes, self.house.graph)
        self.assertTrue(route)
        self.assertEqual(route[-1], "bedroom_two")
        previous = "foyer"
        for node in route:
            self.assertIn(node, self.house.graph[previous])
            previous = node
        self.assertEqual(astar("foyer", "foyer", self.house.nav_nodes, self.house.graph), [])
        self.assertEqual(astar("foyer", "bedroom_two", self.house.nav_nodes, {}), [])
        self.assertEqual(astar("foyer", "missing", self.house.nav_nodes, self.house.graph), [])
        nav = self.ghost.ai.navigation
        for node, neighbors in self.house.graph.items():
            for other in neighbors:
                with self.subTest(edge=(node, other)):
                    self.assertTrue(nav.segment_clear(self.house.nav_nodes[node], self.house.nav_nodes[other]),
                                    f"Blocked edge {node} -> {other}")

    def test_ghost_rejoins_waypoints_and_sweeps_walls(self):
        nav = self.ghost.ai.navigation
        self.ghost.position = Vec3(1, 0, -9)
        self.assertFalse(nav.segment_clear(self.ghost.position, Vec3(3, 0, -9)))
        for _ in range(30):
            time.dt = 0.25
            nav.move_toward(Vec3(3, 0, -9), 20)
        self.assertLess(self.ghost.x, 1.4)
        nav.set_path_to_node("bedroom_one")
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
        self.assertLess((self.ghost.position - self.house.nav_nodes["bedroom_one"]).length(), 0.1)

    def test_real_ghost_vision_and_no_catch_through_wall(self):
        self.ghost.position = Vec3(1, 0, -9)
        self.ghost.rotation_y = 90
        self.player.position = Vec3(2.8, 0, -9)
        self.assertFalse(can_see_player(self.ghost, self.player))
        self.assertFalse(has_line_of_sight(self.ghost, self.player))
        self.ghost.ai.state = GhostState.CHASE
        self.ghost.ai.update()
        self.assertEqual(self.manager.state, "playing")
        self.ghost.position = Vec3(1.4, 0, -9)
        self.player.position = Vec3(2.55, 0, -9)
        self.ghost.ai.update()
        self.assertEqual(self.manager.state, "playing")
        self.player.position = Vec3(0, 0, -9)
        self.ghost.rotation_y = -90
        self.assertTrue(can_see_player(self.ghost, self.player))
        self.ghost.rotation_y = 90
        self.assertFalse(can_see_player(self.ghost, self.player))

    def test_hearing_and_frequent_investigate_replans_make_progress(self):
        self.ghost.position = Vec3(1, 0, -9)
        self.player.position = Vec3(3, 0, -9)
        self.player.stats.noise_level = 0
        self.assertFalse(can_hear_player(self.ghost, self.player))
        self.player.stats.noise_level = 8
        self.player.stats.emit_noise(self.player.world_position, 8)
        self.assertTrue(can_hear_player(self.ghost, self.player))
        ai = self.ghost.ai
        closest = float("inf")
        with patch("game.ghost.ghost_ai.can_see_player", return_value=False), \
                patch("game.ghost.ghost_ai.can_hear_player", return_value=True):
            for _ in range(900):
                time.dt = 1 / 60
                self.player.stats.advance(time.dt)
                if _ % 30 == 0:
                    self.player.stats.emit_noise(self.player.world_position, 8)
                old = Vec3(self.ghost.world_position)
                ai.update()
                self.assertTrue(ai.navigation.segment_clear(old, self.ghost.world_position))
                closest = min(closest, (self.ghost.world_position - self.player.world_position).length())
        self.assertLess(closest, 0.2)  # Reach the repeated sources, then actively search.

    def test_ai_states_and_jumpscare_once(self):
        ai = self.ghost.ai
        self.assertEqual(ai.state, GhostState.PATROL)
        self.player.position = self.ghost.position + Vec3(0, 0, 2)
        self.player.stats.emit_noise(self.player.world_position, 8)
        with patch("game.ghost.ghost_ai.can_see_player", return_value=False), \
                patch("game.ghost.ghost_ai.can_hear_player", return_value=True):
            ai.update()
            self.assertEqual(ai.state, GhostState.INVESTIGATE)
        ai.navigation.clear()
        with patch("game.ghost.ghost_ai.can_see_player", return_value=False), \
                patch("game.ghost.ghost_ai.can_hear_player", return_value=False):
            ai.update()
            self.assertEqual(ai.state, GhostState.SEARCH)
            time.dt = GHOST_ACTIVE_SEARCH_SECONDS + 1
            ai.update()
            self.assertEqual(ai.state, GhostState.PATROL)
        self.ghost.position = Vec3(-6, 0, -8)
        self.player.position = Vec3(-6, 0, -5)
        self.ghost.rotation_y = 0
        time.dt = 1 / 60
        for _ in range(120):
            ai.update()
            if ai.state == GhostState.CHASE:
                break
        self.assertEqual(ai.state, GhostState.CHASE)
        self.player.position = Vec3(6, 0, -4)  # Real wall now breaks LOS too.
        with patch("game.ghost.ghost_ai.can_see_player", return_value=False):
            time.dt = 3
            ai.update()
            self.assertEqual(ai.state, GhostState.SEARCH)
        self.ghost.position = Vec3(-6, 0, -6)
        self.player.position = self.ghost.position + Vec3(0, 0, 0.8)
        self.ghost.rotation_y = 0
        ai.state = GhostState.CHASE
        time.dt = 1 / 60
        ai.update()
        self.assertEqual(ai.state, GhostState.JUMPSCARE)
        self.assertTrue(self.ghost.jumpscare.triggered)
        self.finish_jumpscare()
        self.assertEqual(self.manager.state, "dead")
        self.assertFalse(self.player.enabled)
        self.assertEqual(self.player.flashlight_light.color.r, 0)
        self.ghost.jumpscare.trigger()
        self.capture("render_caught.png")

    def test_movement_speed_noise_and_collisions_at_four_frame_rates(self):
        for fps in (4, 30, 60, 120):
            for sprinting, speed, noise in ((False, 5, 3), (True, 8, 8)):
                with self.subTest(fps=fps, sprinting=sprinting):
                    self.player.stats.stamina = STAMINA_MAX
                    self.player.stats.sprint_exhausted = False
                    self.player.position = Vec3(0, 0, -10)
                    self.player.rotation_y = 0
                    held_keys["shift"] = int(sprinting)
                    self.move("w", seconds=1, dt=1 / fps)
                    self.assertAlmostEqual(self.player.z, -10 + speed, delta=0.002)
                    self.assertAlmostEqual(self.player.stats.noise_level, noise, delta=0.002)
                    self.player.position = Vec3(1.4, 0, -9)
                    self.player.rotation_y = 90
                    self.move("w", seconds=1, dt=1 / fps)
                    self.assertAlmostEqual(self.player.x, 1.4, delta=0.001)
                    self.assertEqual(self.player.stats.noise_level, 0)
                    self.player.position = Vec3(0.5, 0, -9)
                    self.move("w", seconds=1, dt=1 / fps)
                    # Wall face 1.85 minus the player's 0.325 half-width.
                    self.assertLessEqual(self.player.x, 1.525)
                    self.assertAlmostEqual(self.player.y, 0, delta=0.001)
                    self.player.position = Vec3(-17, 0, -17)
                    self.player.rotation_y = -135
                    self.move("w", seconds=1, dt=1 / fps)
                    self.assertGreater(self.player.x, -17.5)
                    self.assertGreater(self.player.z, -17.5)
        held_keys.clear()
        held_keys["w"] = held_keys["s"] = held_keys["shift"] = 1
        self.player.update()
        self.assertEqual(self.player.stats.noise_level, 0)

    def test_flashlight_drain_and_flicker_timeline_at_four_frame_rates(self):
        self.player.reduced_flicker = False  # Preserve the original flicker branch regression.
        reference = None
        for fps in (4, 30, 60, 120):
            self.player.has_flashlight = True
            self.player.flashlight_on = True
            self.player.stats.battery = 14
            self.player._flicker_active = False
            seeded = random.Random(81)
            samples = []
            with patch("game.player.player.random.uniform", side_effect=seeded.uniform) as uniform:
                for frame in range(2 * fps):
                    time.dt = 1 / fps
                    self.player._update_flashlight()
                    if (frame + 1) % (fps // 2) == 0:
                        samples.append(self.player._flicker_dark)
                result = (samples, uniform.call_count, self.player._flicker_dark)
            self.assertAlmostEqual(self.player.stats.battery, 14-2*FLASHLIGHT_DRAIN_PER_SECOND, delta=0.00001)
            if reference is None:
                reference = result
                remaining = self.player._flicker_remaining
            self.assertEqual(result, reference)
            self.assertAlmostEqual(self.player._flicker_remaining, remaining, delta=0.00001)

    def test_full_charge_battery_remains_until_successful_interaction(self):
        self.player.obtain_flashlight()
        pickup = self.pickup(BatteryPickup)
        self.player.position = Vec3(*self.house.level.spawns["pickups"][1]["approach"])
        self.aim(pickup.world_position)
        self.player.stats.battery = MAX_BATTERY
        self.player.input("e")
        self.assertNotIn(pickup, scene.collidables)
        self.assertEqual(self.player.inventory.count("battery"), 1)
        self.manager.input("tab")
        self.manager.hud.panel.selected = self.manager.hud.panel.item_ids().index('battery')
        self.manager.hud.panel.handle("u")
        self.manager.hud.panel.handle("enter")
        self.assertEqual(self.player.inventory.count("battery"), 1)
        self.assertIn("already full", self.manager.hud.message.text)
        self.player.stats.battery = 90
        self.manager.hud.panel.handle("u")
        self.manager.hud.panel.handle("enter")
        self.manager.hud.panel.handle("escape")
        self.assertEqual(self.player.inventory.count("battery"), 0)
        self.assertEqual(self.player.stats.battery, MAX_BATTERY)
        self.assertNotIn(pickup, scene.collidables)

    def test_door_blocks_player_and_ghost_until_animation_completes(self):
        door = self.house.exit_door
        self.player.position = Vec3(0, 0, 16.3)
        self.player.rotation_y = 0
        self.player.inventory.add_key("exit_key")
        self.ghost.position = Vec3(0, 0, 16.3)
        door.interact(self.player)
        blocker = door.doorway_blocker
        for frame in range(7):
            time.dt = 0.1
            door.update()
            elapsed = door.opening_time
            door.interact(self.player)
            self.assertEqual(door.opening_time, elapsed)
            self.assertIs(door.doorway_blocker, blocker)
            self.assertFalse(door.opened)
            self.assertFalse(self.ghost.ai.navigation.segment_clear(Vec3(0, 0, 16.3), Vec3(0, 0, 19)))
            self.move("w", seconds=0.1, dt=0.1)
            self.assertLess(self.player.z, 17.4)
        time.dt = 0.1
        door.update()
        self.assertTrue(door.opened)
        self.assertIsNone(door.collider)
        self.assertNotIn(blocker, scene.collidables)
        self.assertTrue(self.ghost.ai.navigation.segment_clear(Vec3(0, 0, 16.3), Vec3(0, 0, 19)))

    def test_navigation_replans_an_alternate_valid_route(self):
        # Isolated test geometry inside a clear quadrant; the existing house
        # and graph are preserved. An added collider invalidates the short edge.
        root = Entity()
        self.ghost.position = Vec3(-10, 0, -10)
        nodes = {0: Vec3(-10, 0, -10), 1: Vec3(-4, 0, -10),
                 2: Vec3(-10, 0, -5), 3: Vec3(-4, 0, -5)}
        graph = {0: [1, 2], 1: [0, 3], 2: [0, 3], 3: [1, 2]}
        nav = GhostNavigation(self.ghost, nodes, graph, collision_root=root, player=self.player)
        self.ghost.ai.navigation = nav
        self.ghost.ai.nav_nodes = nodes
        self.ghost.ai.graph = graph
        nav.set_path_to_node(1)
        Entity(parent=root, model="cube", collider="box", position=(-7, 1.5, -10), scale=(0.4, 3, 3))
        with patch("game.ghost.ghost_ai.can_see_player", return_value=False), \
                patch("game.ghost.ghost_ai.can_hear_player", return_value=False):
            for _ in range(600):
                time.dt = 1 / 60
                self.ghost.ai.update()
                self.assertFalse(-7.6 < self.ghost.x < -6.4 and self.ghost.z < -8.5)
                if (self.ghost.position - nodes[1]).length() < 0.1:
                    break
        self.assertLess((self.ghost.position - nodes[1]).length(), 0.1)

    def test_unreachable_route_searches_then_resumes_after_obstacle_removed(self):
        root = Entity()
        self.ghost.position = Vec3(-10, 0, -10)
        nodes = {0: Vec3(-10, 0, -10), 1: Vec3(-4, 0, -10)}
        graph = {0: [1], 1: [0]}
        nav = GhostNavigation(self.ghost, nodes, graph, collision_root=root, player=self.player)
        ai = self.ghost.ai
        ai.navigation, ai.nav_nodes, ai.graph = nav, nodes, graph
        nav.set_path_to_node(1)
        blocker = Entity(parent=root, model="cube", collider="box", position=(-7, 1.5, -10), scale=(0.4, 3, 20))
        with patch("game.ghost.ghost_ai.can_see_player", return_value=False), \
                patch("game.ghost.ghost_ai.can_hear_player", return_value=False):
            for _ in range(180):
                time.dt = 1 / 60
                ai.update()
            self.assertEqual(ai.state, GhostState.SEARCH)
            self.assertGreater(ai.search_time, 0)
            self.assertLess(self.ghost.x, -7.6)
            destroy(blocker)
            furthest_x = self.ghost.x
            for _ in range(420):
                ai.update()
                furthest_x = max(furthest_x, self.ghost.x)
            self.assertEqual(ai.state, GhostState.PATROL)
            self.assertGreater(furthest_x, -4.1)

    def test_unreachable_chase_and_noise_target_enter_bounded_recovery(self):
        root = Entity()
        nodes = {0: Vec3(-10, 0, -10), 1: Vec3(-4, 0, -10)}
        graph = {0: [1], 1: [0]}
        Entity(parent=root, model="cube", collider="box",
               position=(-7, 1.5, -10), scale=(0.4, 3, 20))
        self.player.position = nodes[1]
        ai = self.ghost.ai
        for sees_player in (False, True):
            with self.subTest(sees_player=sees_player):
                self.ghost.position = nodes[0]
                ai.navigation = GhostNavigation(self.ghost, nodes, graph,
                                                collision_root=root, player=self.player)
                ai.nav_nodes, ai.graph = nodes, graph
                ai.state = GhostState.PATROL
                ai.repath_time = ai.recovery_time = 0
                ai.detection = 1 if sees_player else 0  # An already acquired visual target.
                self.player.stats.emit_noise(self.player.world_position, 8)
                # Sensor injection isolates routing against the test-root wall.
                with patch("game.ghost.ghost_ai.can_see_player", return_value=sees_player), \
                        patch("game.ghost.ghost_ai.can_hear_player", return_value=True), \
                        patch("game.ghost.ghost_ai.heard_noise", return_value=self.player.stats.noise_events[-1]):
                    self.ghost.position = nodes[0]
                    time.dt = 1 / 30
                    ai.update()
                    self.assertEqual(ai.state, GhostState.SEARCH)
                    self.assertEqual(ai.recovery_time, 4)
                    for _ in range(30):
                        ai.update()
                    self.assertEqual(ai.state, GhostState.SEARCH)
                    self.assertAlmostEqual(ai.recovery_time, 3)
                    self.assertEqual(self.ghost.position, nodes[0])

    def test_ghost_speed_and_waypoint_budget_at_four_frame_rates(self):
        root = Entity()
        nodes = {0: Vec3(-10, 0, -10), 1: Vec3(-10, 0, -9.5),
                 2: Vec3(-10, 0, -4)}
        for fps in (4, 30, 60, 120):
            for speed in (2.1, 2.6, 4.2):
                with self.subTest(fps=fps, speed=speed):
                    self.ghost.position = nodes[0]
                    nav = GhostNavigation(self.ghost, nodes, {0: [1], 1: [2]},
                                          collision_root=root, player=self.player)
                    nav.path = [1, 2]
                    for _ in range(fps):
                        time.dt = 1 / fps
                        nav.follow_path(speed)
                    self.assertAlmostEqual(self.ghost.z, -10 + speed, delta=0.003)

    def test_door_animation_duration_at_four_frame_rates(self):
        from game.world.door import Door

        for fps in (4, 30, 60, 120):
            with self.subTest(fps=fps):
                door = Door(position=(-12, 0, -6), scale=(1, 2, 0.3))
                door.open()
                for frame in range(fps):
                    time.dt = 1 / fps
                    door.update()
                    if (frame + 1) / fps < 0.8 - 1e-9:
                        self.assertTrue(door.opening)
                        self.assertFalse(door.opened)
                        self.assertIsNotNone(door.collider)
                    else:
                        self.assertTrue(door.opened)
                        self.assertFalse(door.opening)
                        self.assertIsNone(door.collider)
                        self.assertAlmostEqual(door.rotation_y, 100)
                destroy(door)

    def test_restarts_after_win_and_loss_do_not_leak_entities_lights_or_timers(self):
        def flush_removed():
            scene.entities[:] = [e for e in scene.entities if e not in scene._entities_marked_for_removal]
            scene._entities_marked_for_removal.clear()
        flush_removed()
        baseline = (len(scene.entities), len(scene.collidables), len(application.sequences))
        for turn in range(12):
            old_player = self.manager.scene_manager.player
            old_house = self.manager.scene_manager.house
            self.manager.scene_manager.house.exit_door.open()
            (self.manager.win_game if turn % 2 else self.manager.game_over)()
            self.manager.input("r")
            flush_removed()
            self.assertTrue(old_player.is_empty())
            self.assertTrue(old_house.is_empty())
            self.assertEqual(self.manager.state, "playing")
            player = self.manager.scene_manager.player
            self.assertTrue(player.enabled)
            self.assertFalse(player.has_flashlight)
            self.assertEqual(player.inventory.key_count(), 0)
            self.assertEqual((len(scene.entities), len(scene.collidables), len(application.sequences)), baseline)
            lights = self.app.render.get_state().get_attrib(LightAttrib)
            self.assertEqual(lights.get_num_on_lights(), 3)

    def test_focus_loss_pauses_clears_input_and_releases_capture(self):
        held_keys["w"] = held_keys["shift"] = 1
        mouse.velocity = Vec3(1, 1, 0)
        self.manager.set_focus(False)
        self.assertTrue(application.paused)
        self.assertFalse(mouse.locked)
        self.assertFalse(any(held_keys.values()))
        self.assertEqual(mouse.velocity, Vec3(0, 0, 0))
        self.manager.set_focus(True)
        self.assertFalse(application.paused)
        self.assertTrue(mouse.locked)
        self.manager.game_over()
        self.manager.set_focus(False)
        self.manager.set_focus(True)
        self.assertFalse(mouse.locked)

    def test_hud_resizes_and_end_overlay_covers_four_three_and_widescreen(self):
        for aspect in (4 / 3, 16 / 9):
            self.manager.hud.layout(aspect)
            self.manager.end_screen.resize(aspect)
            self.assertAlmostEqual(self.manager.hud.inventory_ui.x, -aspect / 2 + 0.03)
            self.assertAlmostEqual(self.manager.hud.ghost_state.x, aspect / 2 - 0.03)
            self.assertAlmostEqual(self.manager.end_screen.background.scale_x, aspect)
        self.assertTrue(self.manager.hud.inventory_ui.has_ancestor(self.manager.hud))

    def test_render_visibility_colors_and_flashlight_changes_pixels(self):
        self.capture("render_spawn.png")
        self.player.position = Vec3(1, 0, -9)
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
        self.assertGreater(off_mean, 3, "Nearby geometry is completely black")
        self.assertLess(off_mean, 25, "Flashlight-off view is too bright for horror lighting")
        self.assertGreater(on_mean, off_mean + 20, "Flashlight has no visible effect")
        self.player.toggle_flashlight()
        # Palette/geometry inspection uses developer lighting: the gameplay
        # fog intentionally hides the layout from this very distant camera.
        scene.clear_fog()
        self.manager.scene_manager.lights[0].color = color.rgb(0.4, 0.4, 0.45)
        self.manager.scene_manager.lights[1].color = color.rgb(0.2, 0.2, 0.18)
        camera.world_parent = scene
        self.house.ceiling.visible = False
        camera.position = Vec3(0, 42, -32)
        camera.rotation = Vec3(0, 0, 0)
        camera.look_at(Vec3(0, 0, 0))
        overview = self.capture("render_overview.png")
        pixels = list(overview.get_flattened_data() if hasattr(overview, "get_flattened_data")
                      else overview.getdata())
        self.assertGreater(sum(r > g * 1.5 and r > b * 1.5 and r > 30 for r, g, b in pixels), 50)
        self.assertGreater(sum(g > r * 1.5 and g > b * 1.5 and g > 30 for r, g, b in pixels), 50)
        self.assertLess(sum(min(rgb) > 245 for rgb in pixels) / len(pixels), 0.05)

    def test_native_flashlight_activation_flicker_depletion_and_registration(self):
        self.player.reduced_flicker = False  # Explicitly test traditional flicker, not accessibility dimming.
        light = self.player.flashlight_light
        native = light._light
        registered = self.app.render.get_state().get_attrib(LightAttrib)
        self.assertEqual(registered.get_num_on_lights(), 3)
        self.assertAlmostEqual(native.get_lens().get_hfov(), FLASHLIGHT_FOV)
        self.assertAlmostEqual(native.get_lens().get_far(), FLASHLIGHT_RANGE)
        self.assertTrue(native.is_shadow_caster())
        self.assertEqual(native.get_color().xyz, Vec3(0, 0, 0))
        self.player.input("f")
        self.assertEqual(native.get_color().xyz, Vec3(0, 0, 0))
        self.player.obtain_flashlight()
        self.player.input("f")
        self.assertGreater(native.get_color().x, 1)
        self.player.stats.battery = 10
        self.player._flicker_active = True
        self.player._flicker_dark = True
        self.player._flicker_remaining = 0.1
        time.dt = 0
        self.player._update_flashlight()
        self.assertTrue(self.player.flashlight_on)
        self.assertEqual(native.get_color().xyz, Vec3(0, 0, 0))
        self.player.stats.battery = 0.01
        time.dt = 1 / 4
        self.player._update_flashlight()
        self.assertEqual(self.player.stats.battery, 0)
        self.assertFalse(self.player.flashlight_on)
        self.assertEqual(native.get_color().xyz, Vec3(0, 0, 0))
        self.assertEqual(self.app.render.get_state().get_attrib(LightAttrib), registered)

    def test_native_beam_follows_camera_and_simulated_mouse_without_lag(self):
        self.player.obtain_flashlight()
        self.player.input("f")
        for yaw, pitch in ((0, 0), (90, 35), (-135, -55), (179, 80)):
            self.player.rotation_y = yaw
            self.player.camera_pivot.rotation_x = pitch
            self.player._update_flashlight()
            light = self.player.flashlight_light
            direction = scene.get_relative_vector(light.get_children()[0], light._light.get_lens().get_view_vector())
            self.assertGreater(direction.normalized().dot(camera.forward.normalized()), 0.9999)
            self.assertLess((light.world_position - camera.world_position).length(), 0.00001)
        mouse.velocity = Vec3(0.2, -0.1, 0)
        self.player.update()
        light = self.player.flashlight_light
        direction = scene.get_relative_vector(light.get_children()[0], light._light.get_lens().get_view_vector())
        self.assertGreater(direction.normalized().dot(camera.forward.normalized()), 0.9999)

    def test_real_flashlight_shadow_occlusion(self):
        # Observe a receiver from a different direction to the lamp, so the
        # occluded surface remains visible to the camera. No mocked lighting.
        scene.clear_fog()
        camera.world_parent = scene
        camera.position, camera.rotation = Vec3(40, 1.5, -6), Vec3(0, 0, 0)
        root = Entity()
        root.set_shader_auto()
        Entity(parent=root, model="cube", shader=None, color=color.rgb32(130, 130, 130),
               position=(40, 1.5, 0), scale=(4, 3, 0.1))
        blocker = Entity(parent=root, model="cube", shader=None,
                         position=(41.5, 1.5, -2), scale=(0.9, 3, 0.4))
        light = self.player.flashlight_light
        light.color = color.rgb(*FLASHLIGHT_COLOR)
        light.position, light.rotation = Vec3(43, 1.5, -4), Vec3(0, -36.87, 0)
        blocked = self.capture("render_shadow_blocked.png")
        destroy(blocker)
        clear = self.capture("render_shadow_clear.png")
        crop = (590, 300, 690, 420)
        blocked_mean = sum(ImageStat.Stat(blocked.crop(crop)).mean) / 3
        clear_mean = sum(ImageStat.Stat(clear.crop(crop)).mean) / 3
        self.assertGreater(clear_mean, blocked_mean + 8, "Opaque geometry did not cast a flashlight shadow")

    def test_beam_falloff_and_dark_geometry_outside_cone(self):
        camera.world_parent = scene
        camera.position, camera.rotation = Vec3(40, 1.5, -6), Vec3(0, 0, 0)
        probe = Entity(model="cube", shader=None, color=color.rgb32(130, 130, 130),
                       position=(40, 1.5, 0), scale=(16, 10, 0.1))
        probe.set_shader_auto()
        self.player.obtain_flashlight()
        self.manager.hud.message.enabled = False
        off = self.capture("render_cone_off.png")
        self.player.input("f")
        far = self.capture("render_cone_far.png")
        centre, edge = (590, 300, 690, 420), (40, 300, 140, 420)
        mean = lambda picture, region: sum(ImageStat.Stat(picture.crop(region)).mean) / 3
        self.assertGreater(mean(far, centre), mean(off, centre) + 10)
        self.assertAlmostEqual(mean(far, edge), mean(off, edge), delta=1)
        probe.z = -3
        probe.scale = (8, 5, 0.1)
        near = self.capture("render_cone_near.png")
        self.assertGreater(mean(near, centre), mean(far, centre) + 15)

    def test_room_floor_and_furniture_receive_world_lighting(self):
        for room in self.house.rooms.values():
            self.assertIsNone(room.shader, "Room container overrides generated lighting")
            for prop in room.props:
                self.assertIsNone(prop.shader, "Furniture container overrides generated lighting")
        camera.world_parent = scene
        self.player.obtain_flashlight()
        self.manager.hud.message.enabled = False
        for name, position, target in (("floor", (-6, 1.8, -10), (-6, 0, -9)),
                                       ("table", (-5, 1.8, -11), (-5, 0.65, -9))):
            with self.subTest(surface=name):
                camera.position = Vec3(*position)
                direction = Vec3(*target) - camera.position
                camera.rotation = Vec3(math.degrees(math.atan2(-direction.y, math.hypot(direction.x, direction.z))),
                                       math.degrees(math.atan2(direction.x, direction.z)), 0)
                off = self.capture(f"render_surface_{name}_off.png")
                self.player.input("f")
                on = self.capture(f"render_surface_{name}_on.png")
                crop = (590, 300, 690, 420)
                off_mean = sum(ImageStat.Stat(off.crop(crop)).mean) / 3
                on_mean = sum(ImageStat.Stat(on.crop(crop)).mean) / 3
                self.assertLess(off_mean, 15)
                self.assertGreater(on_mean, off_mean + 10)
                self.player.input("f")

    def test_real_beam_reveals_ghost_battery_key_and_exit_door(self):
        self.unlock_key_fixture()
        camera.world_parent = scene
        self.player.obtain_flashlight()
        self.manager.hud.message.enabled = False
        self.ghost.enabled = True  # renderFrame does not advance AI.
        self.ghost.position = Vec3(0, 0, -2)
        views = [("ghost", Vec3(0, 1.8, -7), Vec3(0, 1, -2)),
                 ("battery", Vec3(-15, 1.8, 5), self.pickup(BatteryPickup).world_position),
                 ("key", Vec3(7.2, 1.8, 9), self.pickup(KeyPickup).world_position),
                 ("exit", Vec3(0, 1.8, 15), Vec3(0, 1.5, 17.8))]
        for name, position, target in views:
            with self.subTest(subject=name):
                camera.position = position
                direction = target - position
                camera.rotation = Vec3(math.degrees(math.atan2(-direction.y, math.hypot(direction.x, direction.z))),
                                       math.degrees(math.atan2(direction.x, direction.z)), 0)
                off = self.capture(f"render_subject_{name}_off.png")
                self.player.input("f")
                on = self.capture(f"render_subject_{name}_on.png")
                crop = (625, 345, 655, 375)
                off_mean = sum(ImageStat.Stat(off.crop(crop)).mean) / 3
                on_mean = sum(ImageStat.Stat(on.crop(crop)).mean) / 3
                self.assertGreater(on_mean, off_mean + 8)
                self.assertLess(off_mean, 30)
                self.player.input("f")

    def test_dark_distance_fog_is_configured_and_hud_is_unlit(self):
        fog = scene.get_state().get_attrib(FogAttrib).get_fog()
        self.assertEqual(fog.get_mode(), fog.M_exponential)
        self.assertAlmostEqual(fog.get_exp_density(), HOUSE_FOG_DENSITY)
        self.assertGreater(HOUSE_FOG_DENSITY, 0)
        self.assertFalse(camera.ui.get_top() == scene.get_top())
        # Distant identical surfaces receive less contrast than nearby ones.
        camera.world_parent = scene
        camera.position, camera.rotation = Vec3(40, 1.5, -6), Vec3(0, 0, 0)
        probe = Entity(model="cube", shader=None, color=color.rgb32(140, 140, 140),
                       position=(40, 1.5, -3), scale=(3, 3, 0.1))
        probe.set_shader_auto()
        near = self.capture("render_fog_near.png")
        probe.z = 18
        probe.scale = (24, 24, 0.1)  # Same angular size at eight times the range.
        far = self.capture("render_fog_far.png")
        crop = (500, 250, 780, 470)
        self.assertGreater(sum(ImageStat.Stat(near.crop(crop)).mean),
                           sum(ImageStat.Stat(far.crop(crop)).mean) + 3)

    def walk_to(self, point):
        """Drive the actual controller with simulated W input; never teleport."""
        point = Vec3(*point)
        held_keys.clear()
        camera.rotation = Vec3(0, 0, 0)
        self.player.camera_pivot.rotation_x = 0
        try:
            for _ in range(1200):
                delta = Vec3(point.x - self.player.x, 0, point.z - self.player.z)
                if delta.length() < 0.025:
                    return
                self.player.rotation_y = math.degrees(math.atan2(delta.x, delta.z))
                time.dt = min(1 / 30, delta.length() / 5)
                before = Vec3(self.player.position)
                held_keys["w"] = 1
                self.player.update()
                if getattr(self,'_horror_during_walk',False):
                    horror=self.manager.scene_manager.horror
                    if self.player.has_flashlight and not horror.history and not horror.protected():
                        horror.next_allowed=0
                        horror.start_event('power_dip')
                    horror.update(time.dt)
                self.assertGreater((self.player.position - before).length(), 0.000001,
                                   f"Player blocked en route to {point} at {before}")
                self.assertAlmostEqual(self.player.y, 0, delta=0.01)
            self.fail(f"Player failed to reach {point}")
        finally:
            held_keys.clear()

    def walk_route(self, start, target):
        self.walk_to(self.house.nav_nodes[start])
        route = astar(start, target, self.house.nav_nodes, self.house.graph)
        self.assertTrue(start == target or route, f"No route {start} -> {target}")
        for node in route:
            self.walk_to(self.house.nav_nodes[node])

    def test_house_player_walks_to_every_room_without_teleporting(self):
        previous = "foyer"
        for room_id in self.house.rooms:
            with self.subTest(room=room_id):
                self.walk_route(previous, room_id)
                self.assertEqual(self.house.room_at(self.player.position).room_id, room_id)
                previous = room_id

    def test_house_all_room_pairs_have_valid_astar_routes(self):
        for start in self.house.rooms:
            for target in self.house.rooms:
                with self.subTest(route=(start, target)):
                    path = astar(start, target, self.house.nav_nodes, self.house.graph)
                    if start != target:
                        self.assertTrue(path)
                        self.assertEqual(path[-1], target)

    def test_house_spawns_are_grounded_and_clear_of_colliders(self):
        for point in (self.house.player_spawn, self.house.ghost_spawn, *self.house.nav_nodes.values()):
            with self.subTest(point=point):
                floor = world_raycast(point + Vec3(0, 0.1, 0), (0, -1, 0), distance=0.2,
                                      traverse_target=self.house)
                self.assertTrue(floor.hit)
                self.assertAlmostEqual(floor.world_point.y, 0, delta=0.001)
                for direction in ((1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)):
                    self.assertFalse(world_raycast(point + Vec3(0, 1, 0), direction, distance=0.43,
                                                   traverse_target=self.house).hit)

    def test_house_player_collects_objectives_and_escapes_without_basement(self):
        self.unlock_key_fixture()
        current = "foyer"
        for spawn in self.house.level.spawns["pickups"]:
            if spawn["item"] not in ("flashlight", "battery", "exit_key"):
                continue
            self.walk_route(current, spawn["room"])
            self.walk_to(spawn["approach"])
            pickup = self.house.pickups[spawn["id"]]
            self.aim(pickup.world_position)
            self.assertIs(get_interaction_hit(self.player).entity, pickup)
            self.player.input("e")
            self.assertNotIn(pickup, scene.collidables)
            self.walk_to(self.house.nav_nodes[spawn["room"]])
            current = spawn["room"]
        self.assertTrue(self.player.has_flashlight)
        self.assertTrue(self.player.inventory.has_key("exit_key"))
        self.walk_route(current, "exit_approach")
        self.aim(Vec3(0, 1.5, 17.8))
        self.player.input("e")
        for _ in range(4):
            time.dt = 0.25
            self.house.exit_door.update()
        self.assertTrue(self.house.exit_door.opened)
        self.player.rotation_y = 0
        self.player.camera_pivot.rotation_x = 0
        camera.rotation = Vec3(0, 0, 0)
        for _ in range(30):
            time.dt = 1 / 30
            held_keys["w"] = 1
            self.player.update()
            self.house.exit_door.update()
            if self.manager.state == "escaped":
                break
        held_keys.clear()
        self.assertEqual(self.manager.state, "escaped")
        self.assertFalse(self.house.basement_door.opened)

    def test_house_basement_is_locked_and_blocks_player_and_ghost(self):
        self.player.position = Vec3(14, 0, -6)
        self.aim(Vec3(15.6, 1.5, -6))
        self.assertIs(get_interaction_hit(self.player).entity, self.house.basement_door)
        self.player.input("e")
        self.assertIn("future milestone", self.manager.hud.message.text)
        self.player.rotation_y = 90
        self.move("w", seconds=1)
        self.assertLess(self.player.x, 15.2)
        self.assertFalse(self.house.basement_door.opening)
        self.assertFalse(self.ghost.ai.navigation.segment_clear(Vec3(14, 0, -6), Vec3(17, 0, -6)))

    def test_house_perimeter_has_no_unintended_openings(self):
        ignore = [prop for room in self.house.rooms.values() for prop in room.props]
        for height in (0.5, 1.55):
            for step in range(71):
                offset = -17.5 + step * 0.5
                for start, direction in ((Vec3(-17.3, height, offset), (-1, 0, 0)),
                                         (Vec3(17.3, height, offset), (1, 0, 0)),
                                         (Vec3(offset, height, -17.3), (0, 0, -1)),
                                         (Vec3(offset, height, 17.3), (0, 0, 1))):
                    hit = world_raycast(start, direction, distance=1, traverse_target=self.house, ignore=ignore)
                    self.assertTrue(hit.hit, f"Perimeter gap at {start}")
                    self.assertIn(hit.entity, [*self.house.walls, *self.house.door_frames, self.house.exit_door])

    def test_house_all_doorways_have_player_and_ghost_clearance(self):
        nav = self.ghost.ai.navigation
        for door in self.house.level.house["connections"]:
            with self.subTest(doorway=door["id"]):
                center = (Vec3(door["line"], 0, door["at"]) if door["axis"] == "x"
                          else Vec3(door["at"], 0, door["line"]))
                direction = Vec3(1, 0, 0) if door["axis"] == "x" else Vec3(0, 0, 1)
                self.assertTrue(nav.segment_clear(center - direction, center + direction))
                self.player.position = center - direction
                self.walk_to(center + direction)

    def test_house_ghost_replans_around_a_blocked_real_doorway(self):
        self.ghost.position = self.house.nav_nodes["living"]
        ai = self.ghost.ai
        ai.state = GhostState.PATROL
        self.assertTrue(ai.navigation.set_path_to_node("storage"))
        Entity(parent=self.house, model="cube", collider="box",
               position=(-10, 1.6, -6), scale=(0.5, 3.2, 3.5))
        with patch("game.ghost.ghost_ai.can_see_player", return_value=False), \
                patch("game.ghost.ghost_ai.can_hear_player", return_value=False):
            for _ in range(1500):
                time.dt = 1 / 30
                before = Vec3(self.ghost.position)
                ai.update()
                self.assertTrue(ai.navigation.segment_clear(before, self.ghost.position))
                if (self.ghost.position - self.house.nav_nodes["storage"]).length() < 0.1:
                    break
        self.assertLess((self.ghost.position - self.house.nav_nodes["storage"]).length(), 0.1)


    def hide_in(self, spot):
        self.player.position = spot.approach
        self.player.rotation_y = 0
        self.player.camera_pivot.rotation_x = 0
        self.player.camera_pivot.y = 1.8
        camera.rotation = Vec3(0, 0, 0)
        self.aim(spot.prop.world_position + Vec3(0, 1, 0))
        self.assertIs(get_interaction_hit(self.player).entity, spot.prop)
        self.player.input("e")
        self.assertTrue(self.player.hidden)

    def test_survival_vision_visibility_and_closed_door_occlusion(self):
        self.ghost.position, self.ghost.rotation_y = Vec3(0, 0, -10), 0
        self.player.position = Vec3(0, 0, -3)
        self.assertTrue(can_see_player(self.ghost, self.player))
        self.player.crouching = True
        self.assertFalse(can_see_player(self.ghost, self.player))
        self.player.obtain_flashlight()
        self.player.toggle_flashlight()
        self.assertTrue(can_see_player(self.ghost, self.player))
        self.ghost.position = Vec3(0, 0, 16.3)
        self.player.position = Vec3(0, 0, 19)
        self.assertFalse(has_line_of_sight(self.ghost, self.player))
        self.house.exit_door.open()
        time.dt = 0.8
        self.house.exit_door.update()
        self.assertTrue(has_line_of_sight(self.ghost, self.player))

    def test_survival_detection_buildup_at_four_frame_rates(self):
        from game.settings import GHOST_DETECTION_SECONDS, GHOST_VISION_DISTANCE
        self.player.position = Vec3(0, 0, -5)
        self.player.obtain_flashlight()
        self.player.toggle_flashlight()
        expected = GHOST_DETECTION_SECONDS / (0.45 + 0.55 * (1 - 5 / GHOST_VISION_DISTANCE))
        ai = self.ghost.ai
        for fps in (4, 30, 60, 120):
            self.ghost.position, self.ghost.rotation_y = Vec3(0, 0, -10), 0
            ai.state, ai.detection, ai.recovery_time = GhostState.PATROL, 0, 0
            elapsed = 0
            while ai.state != GhostState.CHASE and elapsed < 3:
                time.dt = 1 / fps
                ai.update()
                elapsed += time.dt
            self.assertEqual(ai.state, GhostState.CHASE)
            self.assertGreaterEqual(elapsed + 1e-7, expected)
            self.assertLessEqual(elapsed, expected + 1 / fps + 1 / 30)
            self.assertEqual(ai.last_known_player_position, self.player.position)

    def test_survival_partial_detection_decays_behind_wall(self):
        self.ghost.position, self.ghost.rotation_y = Vec3(0, 0, -9), 0
        self.player.position = Vec3(0, 0, -6)
        time.dt = 0.25
        self.ghost.ai.update()
        self.assertGreater(self.ghost.ai.detection, 0)
        self.assertNotEqual(self.ghost.ai.state, GhostState.CHASE)
        self.player.position = Vec3(3, 0, -9)
        self.assertFalse(can_see_player(self.ghost, self.player))
        time.dt = 0.5
        self.ghost.ai.update()
        self.assertEqual(self.ghost.ai.detection, 0)
        self.assertNotEqual(self.manager.state, "dead")

    def test_survival_noise_snapshot_is_not_live_tracking_and_expires(self):
        from dataclasses import FrozenInstanceError
        self.ghost.position, self.ghost.rotation_y = Vec3(0, 0, -9), 180
        self.player.position = Vec3(0, 0, -6)
        event = self.player.stats.emit_noise(self.player.position, 8)
        source = Vec3(*event.position)
        with self.assertRaises(FrozenInstanceError):
            event.strength = 0
        self.player.position = Vec3(-14, 0, 6)
        self.assertTrue(can_hear_player(self.ghost, self.player))
        time.dt = 1 / 60
        self.ghost.ai.update()
        self.assertEqual(self.ghost.ai.state, GhostState.INVESTIGATE)
        self.assertEqual(self.ghost.ai.last_known_player_position, source)
        self.player.position = Vec3(14, 0, 6)
        for _ in range(30):
            self.ghost.ai.update()
        self.assertEqual(self.ghost.ai.last_known_player_position, source)
        self.player.stats.advance(1.6)
        self.assertFalse(can_hear_player(self.ghost, self.player))
        self.assertFalse(self.player.stats.noise_events)

    def test_survival_sound_strength_and_wall_attenuation(self):
        self.ghost.position = Vec3(1, 0, -9)
        source = Vec3(7, 0, -9)
        for strength, heard in ((0.7, False), (3, False), (8, True)):
            self.player.stats.noise_events.clear()
            self.player.stats.emit_noise(source, strength)
            self.assertEqual(can_hear_player(self.ghost, self.player), heard)

    def test_survival_wall_pushing_emits_no_sound_or_stamina_drain(self):
        self.player.position, self.player.rotation_y = Vec3(1.4, 0, -9), 90
        held_keys["shift"] = 1
        self.move("w", seconds=1, dt=0.25)
        self.assertEqual(self.player.stats.stamina, 100)
        self.assertEqual(self.player.stats.noise_level, 0)
        self.assertFalse(self.player.stats.noise_events)
        self.player.position, self.player.rotation_y = Vec3(0, 0, -10), 0
        self.move("w", seconds=0.5)
        self.assertTrue(self.player.stats.noise_events)
        for event in self.player.stats.noise_events:
            self.assertEqual(event.strength, 8)
            self.assertGreater(event.position[2], -10)

    def test_survival_chase_uses_last_seen_location_after_losing_sight(self):
        ai = self.ghost.ai
        self.ghost.position, self.ghost.rotation_y = Vec3(0, 0, -10), 0
        self.player.position = Vec3(0, 0, -6)
        ai.state = GhostState.CHASE
        time.dt = 1 / 60
        ai.update()
        remembered = Vec3(ai.last_known_player_position)
        self.player.position = Vec3(-14, 0, 6)
        for _ in range(90):
            before = Vec3(self.ghost.position)
            ai.update()
            self.assertTrue(ai.navigation.segment_clear(before, self.ghost.position))
        self.assertEqual(ai.last_known_player_position, remembered)
        self.assertEqual(ai.state, GhostState.SEARCH)
        self.assertEqual(self.manager.state, "playing")

    def test_survival_search_visits_waypoints_and_memory_expires(self):
        ai = self.ghost.ai
        self.player.position = Vec3(-14, 0, 6)
        self.ghost.position = Vec3(0, 0, -2)
        ai._remember(Vec3(0, 0, -2), 1.8)
        ai._start_search()
        start = Vec3(self.ghost.position)
        with patch("game.ghost.ghost_ai.can_see_player", return_value=False):
            for _ in range(240):
                time.dt = 1 / 30
                before = Vec3(self.ghost.position)
                ai.update()
                self.assertTrue(ai.navigation.segment_clear(before, self.ghost.position))
        self.assertGreater((self.ghost.position - start).length(), 1)
        self.assertGreaterEqual(len(ai.searched_nodes), 2)
        self.assertGreater(ai.memory_uncertainty, 1.8)
        ai.recovery_time = ai.search_time = 50
        time.dt = 5
        ai.update()
        self.assertIsNone(ai.last_known_player_position)

    def test_survival_hiding_entry_exit_prompts_and_body_clearance(self):
        self.assertEqual(len(self.house.hiding_spots), 2)
        for spot in self.house.hiding_spots:
            self.hide_in(spot)
            self.assertIs(spot.occupant, self.player)
            time.dt = 0.25
            held_keys["w"] = held_keys["shift"] = 1
            mouse.velocity = Vec3(100, 100, 0)
            position = Vec3(self.player.position)
            self.player.update()
            self.assertEqual(self.player.position, position)
            self.assertEqual(self.player.stats.noise_level, 0)
            self.assertLessEqual(abs(self.player.rotation_y - spot.view_yaw), 25)
            self.assertLessEqual(abs(self.player.camera_pivot.rotation_x), 20)
            self.assertFalse(can_see_player(self.ghost, self.player))
            self.capture("render_survival_hidden.png")
            self.player.input("e")
            self.assertFalse(self.player.hidden)
            self.assertIsNone(spot.occupant)
            self.assertTrue(self.player.can_occupy(self.player.position, 1))
            self.assertFalse(self.player.enter_hiding(spot))  # Reentry cooldown.
            held_keys.clear()
            mouse.velocity = Vec3(0, 0, 0)
            time.dt = 1.1
            self.player.update()

    def test_survival_hiding_exit_uses_safe_alternative_when_blocked(self):
        spot = self.house.hiding_spots[0]
        self.hide_in(spot)
        Entity(parent=self.house, model="cube", collider="box", position=spot.approach + Vec3(0, 1, 0),
               scale=(0.6, 2, 0.6))
        self.player.input("e")
        self.assertFalse(self.player.hidden)
        self.assertTrue(self.player.can_occupy(self.player.position, 1))
        self.assertGreater((self.player.position - spot.approach).length(), 0.5)

    def test_survival_unwitnessed_hiding_is_not_automatic_detection(self):
        spot = self.house.hiding_spots[0]
        self.hide_in(spot)
        self.assertIsNone(self.ghost.ai.suspected_hiding_spot)
        self.ghost.position, self.ghost.rotation_y = Vec3(4.6, 0, -11.2), -90
        self.player.stats.noise_events.clear()
        time.dt = 1 / 60
        for _ in range(120):
            self.player.update()
            self.ghost.ai.update()
        self.assertEqual(self.manager.state, "playing")
        self.assertNotEqual(self.ghost.ai.state, GhostState.CHASE)
        self.assertIsNone(self.ghost.ai.suspected_hiding_spot)

    def test_survival_witnessed_hiding_is_inspected_before_catching(self):
        spot = self.house.hiding_spots[0]
        self.ghost.position, self.ghost.rotation_y = Vec3(4.6, 0, -11.2), -90
        self.hide_in(spot)
        ai = self.ghost.ai
        self.assertIs(ai.suspected_hiding_spot, spot)
        self.assertEqual(ai.state, GhostState.INVESTIGATE)
        time.dt = 1 / 60
        for _ in range(60):
            ai.update()
        self.assertEqual(self.manager.state, "playing")
        for _ in range(240):
            ai.update()
            if self.manager.state == "jumpscare":
                break
        self.finish_jumpscare()
        self.assertEqual(self.manager.state, "dead")
        self.assertEqual(ai.state, GhostState.JUMPSCARE)

    def test_survival_breathing_creates_risk_and_guides_search(self):
        from game.settings import HIDING_SAFE_SECONDS, HIDING_NOISE_INTERVAL
        spot = self.house.hiding_spots[0]
        self.hide_in(spot)
        self.player.stats.noise_events.clear()
        time.dt = HIDING_SAFE_SECONDS - 0.1
        self.player.update()
        self.assertFalse(self.player.stats.noise_events)
        time.dt = 0.2
        self.player.update()
        event = self.player.stats.noise_events[-1]
        self.assertEqual(event.kind, "breathing")
        self.assertEqual(Vec3(*event.position), self.player.world_position)
        self.ghost.position, self.ghost.rotation_y = Vec3(4.6, 0, -11.2), -90
        time.dt = 1 / 60
        self.ghost.ai.update()
        self.assertIs(self.ghost.ai.suspected_hiding_spot, spot)
        time.dt = HIDING_NOISE_INTERVAL
        self.player.update()
        self.assertGreater(self.player.stats.noise_events[-1].sequence, event.sequence)

    def test_survival_inspection_cannot_catch_through_a_wall(self):
        spot = self.house.hiding_spots[0]
        self.hide_in(spot)
        ai = self.ghost.ai
        self.ghost.position = spot.approach - Vec3(1.2, 0, 0)
        ai.inspection_target = spot
        ai.navigation.clear()
        self.assertFalse(ai._inspection_clear(spot))
        time.dt = 2
        ai._inspect_hiding_spot()
        self.assertEqual(self.manager.state, "playing")

    def test_survival_stamina_depletion_and_recovery_at_four_frame_rates(self):
        from game.player.player_stats import PlayerStats
        from game.settings import STAMINA_DRAIN_PER_SECOND
        Entity(model="cube", collider="box", position=(60, -0.15, 0), scale=(20, 0.3, 200))
        reference = None
        for fps in (4, 30, 60, 120):
            self.player.stats = PlayerStats()
            self.player.position, self.player.rotation_y = Vec3(60, 0, -80), 0
            self.player.camera_pivot.rotation_x = 0
            held_keys["shift"] = 1
            self.move("w", seconds=5, dt=1 / fps)
            self.assertEqual(self.player.stats.stamina, 0)
            self.assertTrue(self.player.stats.sprint_exhausted)
            sprint_time = 100 / STAMINA_DRAIN_PER_SECOND
            self.assertAlmostEqual(self.player.z, -80 + sprint_time * 8 + (5 - sprint_time) * 5, delta=0.04)
            held_keys.clear()
            for _ in range(4 * fps):
                self.player.update()
            self.assertGreater(self.player.stats.stamina, 25)
            self.assertFalse(self.player.stats.sprint_exhausted)
            result = (self.player.z, self.player.stats.stamina)
            if reference is None:
                reference = result
            for value, expected in zip(result, reference):
                self.assertAlmostEqual(value, expected, delta=0.04)

    def test_survival_crouch_speed_camera_noise_and_low_ceiling(self):
        from game.settings import PLAYER_CROUCH_SPEED, PLAYER_CROUCH_NOISE
        reference = None
        for fps in (4, 30, 60, 120):
            self.player.position, self.player.rotation_y = Vec3(0, 0, -10), 0
            self.player.camera_pivot.y = 1.8
            self.player.camera_pivot.rotation_x = 0
            self.player.set_body_height(1.8)
            held_keys["control"] = held_keys["shift"] = 1
            self.move("w", seconds=1, dt=1 / fps)
            self.assertAlmostEqual(self.player.z, -10 + PLAYER_CROUCH_SPEED, delta=0.002)
            self.assertAlmostEqual(self.player.stats.noise_level, PLAYER_CROUCH_NOISE, delta=0.002)
            self.assertAlmostEqual(self.player.camera_pivot.y, 1, delta=0.001)
            self.assertFalse(self.player.sprinting)
            if reference is None:
                reference = self.player.camera_pivot.y
            self.assertAlmostEqual(self.player.camera_pivot.y, reference, delta=0.001)
        roof = Entity(model="cube", collider="box", position=(0, 1.35, -7.8), scale=(2, 0.2, 2))
        held_keys.clear()
        self.player.update()
        self.assertTrue(self.player.crouching)
        self.assertFalse(self.player.can_stand())
        self.assertLessEqual(self.player.height, 1.01)
        destroy(roof)
        for _ in range(120):
            time.dt = 1 / 60
            self.player.update()
        self.assertFalse(self.player.crouching)
        self.assertEqual(self.player.height, 1.8)

    def test_survival_restart_cleans_hidden_stamina_memory_and_events(self):
        for won in (False, True):
            player = self.manager.scene_manager.player
            spot = self.manager.scene_manager.house.hiding_spots[0]
            player.position = spot.approach
            self.assertTrue(player.enter_hiding(spot))
            player.stats.stamina = 0
            player.stats.sprint_exhausted = True
            (self.manager.win_game if won else self.manager.game_over)()
            self.assertIsNone(spot.occupant)
            self.manager.input("r")
            fresh = self.manager.scene_manager.player
            self.assertFalse(fresh.hidden or fresh.crouching)
            self.assertEqual(fresh.stats.stamina, 100)
            self.assertFalse(fresh.stats.noise_events)
            self.assertIsNone(self.manager.scene_manager.ghost.ai.last_known_player_position)
            self.assertTrue(fresh.enabled)

    def test_survival_empty_wardrobe_search_does_not_reveal_another_occupant(self):
        first, second = self.house.hiding_spots
        self.hide_in(second)
        self.player.stats.noise_events.clear()
        self.ghost.position = Vec3(4.6, 0, -11.2)
        ai = self.ghost.ai
        ai._remember(first.approach, 1.8)
        ai._start_search()
        self.assertIs(ai.inspection_target, first)
        for _ in range(180):
            time.dt = 1 / 60
            ai.update()
        self.assertEqual(self.manager.state, "playing")
        self.assertTrue(self.player.hidden)
        self.assertIsNot(ai.inspection_target, first)
        self.assertEqual(ai.last_known_player_position, first.approach)

    def test_survival_player_can_leave_during_a_witnessed_inspection(self):
        spot = self.house.hiding_spots[0]
        self.ghost.enabled = True  # Real ghost collider blocks the front exit.
        self.ghost.position, self.ghost.rotation_y = Vec3(4.6, 0, -11.2), -90
        self.hide_in(spot)
        for _ in range(60):
            time.dt = 1 / 60
            self.ghost.ai.update()
        self.assertEqual(self.manager.state, "playing")
        self.player.input("e")
        self.assertFalse(self.player.hidden)
        held_keys["shift"] = held_keys["d"] = 1
        for _ in range(30):
            self.player.update()
            self.ghost.ai.update()
        self.assertEqual(self.manager.state, "playing")
        self.assertGreater((self.player.position - self.ghost.position).length(), 1.25)

    def test_survival_all_obstructed_exits_wait_then_clear_without_wall_escape(self):
        spot = self.house.hiding_spots[0]
        self.hide_in(spot)
        blockers = [Entity(parent=self.house, model="cube", collider="box",
                           position=point + Vec3(0, 1, 0), scale=(0.8, 2, 0.8))
                    for point in spot.exit_candidates()]
        self.player.input("e")
        self.assertTrue(self.player.hidden)
        self.assertIn("obstructed", self.manager.hud.message.text)
        self.assertEqual(self.player.position, spot.prop.world_position)
        for blocker in blockers:
            destroy(blocker)
        self.player.input("e")
        self.assertFalse(self.player.hidden)

    def test_survival_noise_cooldown_and_focus_clear_stale_events(self):
        self.ghost.position, self.ghost.rotation_y = Vec3(0, 0, -9), 180
        ai = self.ghost.ai
        source = Vec3(0, 0, -6)
        self.player.position = source
        self.player.stats.emit_noise(source, 8)
        self.player.position = Vec3(-14, 0, 6)
        time.dt = 1 / 60
        ai.update()
        self.assertEqual(ai.last_known_player_position, source)
        self.player.stats.emit_noise(Vec3(0, 0, -5), 8)
        ai.update()
        self.assertEqual(ai.last_known_player_position, source)
        self.assertGreater(ai.noise_cooldown, 0)
        self.manager.set_focus(False)
        self.assertFalse(self.player.stats.noise_events)
        self.manager.set_focus(True)

    def test_survival_lowering_camera_cannot_enter_a_low_ceiling_early(self):
        roof = Entity(model="cube", collider="box", position=(0, 1.35, -8.7), scale=(2, 0.2, 2))
        self.player.position, self.player.rotation_y = Vec3(0, 0, -10.1), 0
        self.player.camera_pivot.rotation_x = 0
        held_keys["control"] = held_keys["w"] = 1
        for _ in range(30):
            time.dt = 1 / 120
            self.player.update()
            if self.player.z + 0.325 > -9.7:
                self.assertLess(self.player.height, 1.25)
        self.assertGreater(self.player.z, -10.1)
        destroy(roof)

    def test_survival_reentering_watched_wardrobe_does_not_restart_inspection(self):
        spot = self.house.hiding_spots[0]
        self.ghost.position, self.ghost.rotation_y = Vec3(4.6, 0, -11.2), -90
        self.hide_in(spot)
        ai = self.ghost.ai
        ai._start_search()
        self.assertIs(ai.inspection_target, spot)
        ai.inspection_time = 0.7
        self.player.input("e")
        self.assertFalse(self.player.hidden)
        time.dt = 1.1
        self.player.update()  # Fixture freezes AI to isolate the reentry event.
        self.player.input("e")
        self.assertTrue(self.player.hidden)
        self.assertEqual(ai.inspection_time, 0.7)
        self.assertIs(ai.inspection_target, spot)
        self.assertEqual(ai.state, GhostState.SEARCH)


    # Milestone 7 uses real level pickups, not injected inventory rewards.
    def persistence_fixture(self, complete=False):
        for name in ('foyer_flashlight','living_instructions','storage_fuse'):
            self.house.pickups[name].interact(self.player)
            self.manager.hud.panel.close()
        self.player.progression.install_fuse()
        if complete:
            self.house.pickups['kitchen_tally'].interact(self.player)
            self.manager.hud.panel.close()
            self.player.progression.try_combination(self.house.level.house['progression']['combination'])
            self.player.progression.remove_boards()
            self.house.pickups['bedroom_exit_key'].interact(self.player)
        self.player.position=Vec3(0,0,-8)
        self.player.rotation_y=31
        self.player.camera_pivot.rotation_x=-17
        camera.rotation=Vec3(2,3,0)
        self.ghost.position=Vec3(self.house.ghost_spawn)
        self.player.stats.battery=42
        self.player.stats.stamina=38
        self.player.stats.regen_delay=.5
        self.player.toggle_flashlight()

    def rebind_session_refs(self):
        self.player,self.house,self.ghost=(self.manager.scene_manager.player,self.manager.scene_manager.house,self.manager.scene_manager.ghost)
        self.ghost.enabled=False
        self.manager.update()
        time.dt=time.dt_unscaled=1/60

    def test_save_restores_authoritative_player_inventory_notes_and_power(self):
        self.persistence_fixture()
        self.manager.pause_game()
        self.assertTrue(self.manager.save_game())
        data=self.manager.save_manager.load()
        self.player.stats.battery=1
        self.manager.return_to_menu()
        self.assertNotIn(1,self.manager.main_menu.disabled_rows)
        self.assertTrue(self.manager.continue_game())
        self.rebind_session_refs()
        self.assertEqual(list(self.player.position),data['player']['position'])
        self.assertEqual(self.player.rotation_y,31)
        self.assertEqual(self.player.camera_pivot.rotation_x,-17)
        self.assertEqual(list(camera.rotation),[2,3,0])
        self.assertEqual(self.player.stats.battery,42)
        self.assertEqual(self.player.stats.stamina,38)
        self.assertAlmostEqual(self.player.stats.regen_delay,.5)
        self.assertTrue(self.player.flashlight_on)
        self.assertGreater(self.player.flashlight_light.color.r,0)
        self.assertEqual(self.player.inventory.quantities,data['inventory'])
        self.assertTrue(self.player.progression.power_restored)
        self.assertEqual(self.player.inventory.count('fuse'),0)
        self.assertTrue(self.house.pickups['storage_fuse'].is_empty())
        self.assertTrue(self.house.pickups['kitchen_tally'].enabled)
        self.manager.hud.panel.open_note(self.player,'household_order')
        self.assertTrue(self.manager.hud.panel.body.text)
        self.assertIn('lockbox',self.player.progression.objective)

    def test_save_safety_blocks_danger_hidden_modal_door_and_terminal_states(self):
        self.persistence_fixture()
        self.manager.pause_game()
        for state in (GhostState.CHASE,GhostState.JUMPSCARE):
            self.ghost.ai.state=state
            self.assertFalse(self.manager.save_game())
        self.ghost.ai.state=GhostState.PATROL
        self.ghost.ai.detection=.3
        self.assertFalse(self.manager.save_game())
        self.ghost.ai.detection=0
        self.house.exit_door.opening=True
        self.assertFalse(self.manager.save_game())
        self.house.exit_door.opening=False
        self.player.hiding_spot=self.house.hiding_spots[0]
        self.assertFalse(self.manager.save_game())
        self.player.hiding_spot=None
        self.manager.hud.panel.open_inventory(self.player)
        self.assertFalse(self.manager.save_game())
        self.manager.hud.panel.close()
        for state in ('playing','jumpscare','dead','escaped','menu'):
            self.manager.state=state
            self.assertFalse(self.manager.save_game())
        self.assertFalse(self.manager.save_manager.exists())

    def test_save_success_only_after_write_and_cooldown_prevents_spam(self):
        self.persistence_fixture()
        self.manager.pause_game()
        with patch.object(self.manager.save_manager,'save',side_effect=PermissionError('fixture')):
            self.assertFalse(self.manager.save_game())
        self.assertIn('failed',self.manager.pause_menu.subtitle_text.text.lower())
        self.assertFalse(self.manager.save_manager.exists())
        self.assertTrue(self.manager.save_game())
        before=self.manager.save_manager.path('manual').read_bytes()
        self.player.stats.battery=2
        self.assertFalse(self.manager.save_game())
        self.assertEqual(self.manager.save_manager.path('manual').read_bytes(),before)
        self.assertEqual(self.manager.state,'paused')
        self.assertTrue(application.paused)

    def test_save_continue_disabled_without_data_and_new_game_requires_confirmation(self):
        self.assertIn(1,self.manager.main_menu.disabled_rows)
        self.persistence_fixture()
        self.manager.automatic_checkpoints=True
        self.manager._checkpoints()
        self.manager.pause_game()
        self.assertTrue(self.manager.save_game())
        manual=self.manager.save_manager.path('manual').read_bytes()
        self.manager.return_to_menu()
        self.assertFalse(self.manager.start_game())
        self.assertEqual(self.manager.state,'confirm_new')
        self.assertIsNone(self.manager.scene_manager)
        self.manager.cancel_new_game()
        self.assertTrue(self.manager.save_manager.path('checkpoint').exists())
        self.manager.start_game()
        self.manager.confirm_new_game()
        self.rebind_session_refs()
        self.assertFalse(self.player.inventory.quantities)
        self.assertFalse(self.player.progression.power_restored)
        self.assertFalse(self.manager.save_manager.path('checkpoint').exists())
        self.assertEqual(self.manager.save_manager.path('manual').read_bytes(),manual)

    def test_save_invalid_data_never_mutates_current_session(self):
        self.manager.pause_game()
        original=self.manager.scene_manager
        parent=camera.parent
        for content in ('{','[]','{"version":99}'):
            self.manager.save_manager.path('manual').write_text(content)
            self.assertFalse(self.manager.load_game())
            self.assertIs(self.manager.scene_manager,original)
            self.assertEqual(camera.parent,parent)
            self.assertEqual(self.manager.state,'paused')

    def test_save_obstructed_position_rolls_back_staging_without_light_or_entity_leak(self):
        self.persistence_fixture()
        self.manager.pause_game()
        data=SaveManager.capture(self.manager.scene_manager,self.manager.session_id)
        data['player']['position']=[2,0,-8]  # Authored hall boundary wall.
        self.manager.save_manager.save(data)
        self.app.taskMgr.step()
        original=self.manager.scene_manager
        original_hud=self.manager.hud
        parent=camera.parent
        before=sum(not e.is_empty() for e in scene.entities)
        lights=self.app.render.get_state().get_attrib(LightAttrib)
        self.assertFalse(self.manager.load_game())
        self.app.taskMgr.step()
        self.assertIs(self.manager.scene_manager,original)
        self.assertIs(self.manager.hud,original_hud)
        self.assertEqual(camera.parent,parent)
        self.assertEqual(sum(not e.is_empty() for e in scene.entities),before)
        self.assertEqual(self.app.render.get_state().get_attrib(LightAttrib),lights)

    def test_save_constructor_failure_preserves_outgoing_camera_world_and_lights(self):
        self.persistence_fixture()
        self.manager.pause_game()
        self.manager.save_game()
        self.app.taskMgr.step()
        before=sum(not e.is_empty() for e in scene.entities)
        original=self.manager.scene_manager
        lights=self.app.render.get_state().get_attrib(LightAttrib)
        def broken(*args):
            from ursina import AmbientLight
            AmbientLight(parent=scene)
            Entity(parent=scene,model='cube')
            raise RuntimeError('constructor fixture')
        with patch('game.game_manager.SceneManager',side_effect=broken):
            self.assertFalse(self.manager.load_game())
        self.app.taskMgr.step()
        self.assertIs(self.manager.scene_manager,original)
        self.assertEqual(camera.parent,original.player.camera_pivot)
        self.assertEqual(sum(not e.is_empty() for e in scene.entities),before)
        self.assertEqual(self.app.render.get_state().get_attrib(LightAttrib),lights)

    def test_save_checkpoint_defers_danger_and_records_safe_resource_snapshot(self):
        self.persistence_fixture()
        self.manager.automatic_checkpoints=True
        self.ghost.ai.state=GhostState.CHASE
        self.manager._checkpoints()
        self.assertIsNone(self.manager.save_manager.load('checkpoint'))
        self.ghost.ai.state=GhostState.PATROL
        self.ghost.position=Vec3(0,0,-14)
        self.manager._checkpoints()
        self.assertIsNone(self.manager.save_manager.load('checkpoint'))
        self.ghost.position=Vec3(self.house.ghost_spawn)
        self.manager._checkpoints()
        data=self.manager.save_manager.load('checkpoint')
        self.assertEqual(data['milestone'],'power')
        self.assertEqual(data['player']['position'],list(self.house.nav_nodes['foyer']))
        self.assertTrue(self.player.can_occupy(Vec3(*data['player']['position'])))
        self.assertEqual(data['player']['battery'],42)
        self.assertEqual(data['player']['stamina'],38)
        before=self.manager.save_manager.path('checkpoint').read_bytes()
        self.manager._checkpoints()
        self.assertEqual(self.manager.save_manager.path('checkpoint').read_bytes(),before)
        self.player.progression.try_combination(self.house.level.house['progression']['combination'])
        self.manager._checkpoints()
        self.assertEqual(self.manager.save_manager.load('checkpoint')['milestone'],'lockbox')
        self.player.progression.remove_boards()
        self.house.pickups['bedroom_exit_key'].interact(self.player)
        self.manager._checkpoints()
        self.assertEqual(self.manager.save_manager.load('checkpoint')['milestone'],'exit_key')

    def test_save_retry_clears_ghost_horror_and_restores_without_duplicate_rewards(self):
        self.persistence_fixture(complete=True)
        self.manager.automatic_checkpoints=True
        self.manager._checkpoints()
        data=self.manager.save_manager.load('checkpoint')
        self.ghost.ai.detection=1
        self.ghost.ai.last_known_player_position=Vec3(self.player.position)
        self.player.stats.emit_noise(self.player.position,8,'fixture')
        self.manager.game_over()
        self.assertNotIn(2,self.manager.end_screen.disabled_rows)
        self.assertTrue(self.manager.retry_checkpoint())
        self.rebind_session_refs()
        self.assertEqual(self.ghost.ai.state,GhostState.PATROL)
        self.assertEqual(self.ghost.ai.detection,0)
        self.assertIsNone(self.ghost.ai.last_known_player_position)
        self.assertFalse(self.player.stats.noise_events)
        self.assertEqual(self.ghost.ai.grace_time,5)
        self.assertGreaterEqual((self.ghost.position-self.player.position).length(),12)
        self.assertIsNone(self.manager.scene_manager.horror.active)
        self.assertEqual(self.manager.scene_manager.horror.director.tension,0)
        self.assertIsNone(self.ghost.jumpscare.proxy)
        self.assertEqual(self.player.stats.battery,data['player']['battery'])
        self.assertEqual(self.player.inventory.count('crowbar'),1)
        self.assertEqual(self.player.inventory.count('exit_key'),1)
        self.assertFalse(self.player.progression.try_combination('2417'))
        self.assertTrue(self.house.pickups['bedroom_exit_key'].is_empty())
        self.ghost.position=self.player.position+Vec3(0,0,.8)
        time.dt=1
        self.ghost.ai.update()
        self.assertEqual(self.manager.state,'playing')
        self.assertEqual(self.ghost.ai.state,GhostState.PATROL)

    def test_save_load_cancels_active_paranormal_effects_and_callback(self):
        self.persistence_fixture()
        self.manager.pause_game()
        self.assertTrue(self.manager.save_game())
        self.manager.resume_game()
        self.manager.update()
        horror=self.manager.scene_manager.horror
        horror.next_allowed=0
        horror.director.tension=.9
        self.player.position=Vec3(self.house.nav_nodes['main_hall'])
        self.assertTrue(horror.start_event('apparition'))
        temporary=horror.active['temporary'][0]
        self.manager.pause_game()
        self.assertTrue(self.manager.load_game())
        self.assertTrue(temporary.is_empty())
        self.assertFalse(horror.running)
        self.assertIsNone(self.manager.scene_manager.horror.active)

    def test_save_complete_progression_and_open_exit_survive_load_then_escape(self):
        self.persistence_fixture(complete=True)
        self.house.exit_door.interact(self.player)
        time.dt=.8
        self.house.exit_door.update()
        self.manager.pause_game()
        self.assertTrue(self.manager.save_game())
        self.assertTrue(self.manager.load_game())
        self.rebind_session_refs()
        self.assertTrue(self.house.exit_door.opened)
        self.assertIsNone(self.house.exit_door.collider)
        self.assertTrue(self.house.pickups['bedroom_exit_key'].is_empty())
        self.assertFalse(self.house.puzzles['boards'].enabled)
        self.assertFalse(self.house.basement_door.opened)
        self.player.position=Vec3(0,0,18.2)
        self.house.exit_door.update()
        self.assertEqual(self.manager.state,'escaped')

    def test_save_repeated_load_pause_and_retry_have_stable_entity_light_task_counts(self):
        self.persistence_fixture()
        self.manager.automatic_checkpoints=True
        self.manager._checkpoints()
        self.manager.pause_game()
        self.assertTrue(self.manager.save_game())
        counts=[]
        for cycle in range(12):
            if cycle%2:
                self.manager.game_over()
                self.assertTrue(self.manager.retry_checkpoint())
            else:
                self.manager.pause_game()
                self.assertTrue(self.manager.load_game())
            self.ghost=self.manager.scene_manager.ghost
            self.ghost.enabled=False
            self.manager.update()
            time.dt=0
            self.app.taskMgr.step()
            self.app.taskMgr.step()
            active=[e for e in scene.entities if not e.is_empty()]
            counts.append((len(active),len(scene.collidables),self.app.render.get_state().get_attrib(LightAttrib).get_num_on_lights(),len(self.app.taskMgr.getAllTasks())))
            self.assertEqual(sum(e.__class__.__name__=='Ghost' for e in active),1)
        self.assertEqual(len(set(counts)),1,counts)

    def test_save_rebind_movement_interact_flashlight_inventory_use_and_escape(self):
        bindings=self.manager.preferences.values['bindings'].copy()
        bindings.update(forward='i',sprint='o',crouch='c',interact='q',flashlight='g',inventory='b',use_item='j',pause='p')
        self.manager.preferences.save(dict(self.manager.preferences.values,bindings=bindings))
        self.manager.apply_live_preferences()
        self.player.input('q')
        self.assertTrue(self.player.has_flashlight)
        self.player.input('g')
        self.assertTrue(self.player.flashlight_on)
        self.player.position=Vec3(0,0,-10)
        self.player.rotation_y=0
        self.player.camera_pivot.rotation_x=0
        camera.rotation=Vec3(0,0,0)
        self.move('i',1,1/30)
        self.assertAlmostEqual(self.player.z,-5,places=3)
        self.assertFalse(held_keys['w'])
        self.house.pickups['kitchen_battery'].interact(self.player)
        self.player.stats.battery=40
        self.app.input('b',is_raw=True)
        self.assertEqual(self.manager.hud.panel.mode,'inventory')
        self.manager.hud.panel.selected=self.manager.hud.panel.item_ids().index('battery')
        self.app.input('j',is_raw=True)
        self.assertTrue(self.manager.hud.panel.confirming)
        self.app.input('enter',is_raw=True)
        self.assertEqual(self.player.inventory.count('battery'),0)
        self.assertEqual(self.player.stats.battery,75)
        self.app.input('b',is_raw=True)
        self.assertFalse(self.manager.hud.panel.active)
        self.app.input('p',is_raw=True)
        self.assertEqual(self.manager.state,'paused')
        self.app.input('escape',is_raw=True)
        self.assertEqual(self.manager.state,'playing')

    def test_save_controls_capture_conflict_cancel_reset_and_nested_settings(self):
        self.manager.pause_game()
        self.manager.open_settings()
        self.manager.open_controls()
        self.manager.controls_screen.capture_binding(0)
        self.app.input('s',is_raw=True)
        self.assertEqual(self.manager.controls_screen.waiting,'forward')
        self.assertIn('Conflicting',self.manager.controls_screen.status.text)
        self.app.input('escape',is_raw=True)
        self.assertEqual(self.manager.state,'controls')
        self.manager.controls_screen.capture_binding(0)
        self.app.input('i',is_raw=True)
        self.assertEqual(self.player.bindings['forward'],'i')
        self.assertIn('I',self.manager.controls_screen.rows[0][1].text)
        self.manager.controls_screen.reset_defaults()
        self.assertEqual(self.player.bindings['forward'],'w')
        self.app.input('escape',is_raw=True)
        self.assertEqual(self.manager.state,'settings')
        self.app.input('escape',is_raw=True)
        self.assertEqual(self.manager.state,'paused')

    def test_save_text_scaling_and_note_pagination_at_three_window_aspects(self):
        self.persistence_fixture()
        for factor in (1,1.25,1.5):
            self.manager.preferences.save(dict(self.manager.preferences.values,text_scale=factor))
            self.manager.apply_live_preferences()
            for width,height in ((640,480),(960,720),(1280,720)):
                aspect=width/height
                self.manager.hud.layout(aspect)
                for screen in set(self.manager.screens.values()):
                    screen.resize(aspect)
                    self.assertAlmostEqual(screen.title_text.scale_x,getattr(screen.title_text,'base_font',1.8)*factor,places=5)
                self.manager.hud.panel.open_note(self.player,'household_order')
                self.manager.hud.panel.layout(aspect)
                self.assertGreater(self.manager.hud.inventory_ui.y-self.manager.hud.inventory_ui.height*self.manager.hud.inventory_ui.scale_y,
                                   self.manager.hud.panel.title.y*self.manager.hud.panel.scale_y)
                self.assertAlmostEqual(self.manager.hud.panel.body.scale_x,.95*factor,places=5)
                self.assertLessEqual(len(self.manager.hud.panel.body.text.splitlines()),int(13/factor))
                self.manager.hud.panel.handle('page down')
                self.assertTrue(self.manager.hud.panel.body.text)
                self.manager.hud.panel.close()

    def test_save_reduced_low_battery_flicker_is_steady_and_depletion_turns_light_off(self):
        self.player.obtain_flashlight()
        self.player.stats.battery=14
        self.player.toggle_flashlight()
        self.player.reduced_flicker=True
        for fps in (4,30,60,120):
            self.player.stats.battery=14
            self.player.flashlight_on=True
            colors=set()
            for _ in range(fps*2):
                time.dt=1/fps
                self.player._update_flashlight()
                colors.add(round(self.player.flashlight_light.color.r,5))
            self.assertEqual(colors,{FLASHLIGHT_COLOR[0]*.75})
            self.assertAlmostEqual(self.player.stats.battery,14-2*FLASHLIGHT_DRAIN_PER_SECOND)
        self.player.stats.battery=.01
        time.dt=1
        self.player._update_flashlight()
        self.assertEqual(self.player.stats.battery,0)
        self.assertFalse(self.player.flashlight_on)
        self.assertEqual(self.player.flashlight_light.color.r,0)

    def test_save_battery_budget_is_finite_and_chase_stamina_defaults_unchanged(self):
        from game import settings
        self.assertEqual(settings.MAX_BATTERY,100)
        supply=settings.FLASHLIGHT_START_BATTERY+self.house.level.items['battery']['restore']
        self.assertEqual(supply,100)
        self.assertEqual(supply/settings.FLASHLIGHT_DRAIN_PER_SECOND,400)
        self.assertGreater(settings.PLAYER_SPRINT_SPEED,settings.GHOST_CHASE_SPEED)
        self.assertGreater(settings.GHOST_CHASE_SPEED,settings.PLAYER_SPEED)
        self.assertEqual(settings.STAMINA_MAX/settings.STAMINA_DRAIN_PER_SECOND,100/22)

    def test_save_rebound_movement_retains_four_fps_speeds_noise_and_wall_sweeps(self):
        from game import settings
        bindings=dict(self.player.bindings,forward='i',backward='k',left='j',right='l',sprint='o',crouch='c',use_item='u')
        self.manager.preferences.save(dict(self.manager.preferences.values,bindings=bindings))
        self.manager.apply_live_preferences()
        for fps in (4,30,60,120):
            for key,axis,delta in (('i','z',1),('k','z',-1),('j','x',-1),('l','x',1)):
                self.player.position=Vec3(0,0,-7)
                self.player.rotation_y=self.player.camera_pivot.rotation_x=0
                camera.rotation=Vec3(0,0,0)
                # One quarter second is representable at all four frame rates.
                self.move(key,.25,1/fps)
                elapsed=round(.25*fps)/fps
                self.assertAlmostEqual(getattr(self.player,axis),(-7 if axis=='z' else 0)+delta*5*elapsed,places=3)
            self.player.position=Vec3(0,0,-10)
            held_keys['o']=1
            self.player.stats.stamina=100
            self.player.stats.sprint_exhausted=False
            self.move('i',1,1/fps)
            self.assertAlmostEqual(self.player.z,-10+settings.PLAYER_SPRINT_SPEED,places=3)
            self.player.position=Vec3(1.4,0,-8)
            self.player.rotation_y=90
            self.move('i',1,1/fps)
            self.assertLess(self.player.x,2)
            self.assertEqual(self.player.stats.noise_level,0)
            held_keys.clear()

    def test_save_checkpoint_of_another_run_is_not_a_death_retry(self):
        self.persistence_fixture()
        self.manager.automatic_checkpoints=True
        self.manager._checkpoints()
        self.manager.restart_game()
        self.rebind_session_refs()
        self.manager.game_over()
        self.assertIn(2,self.manager.end_screen.disabled_rows)
        self.assertFalse(self.manager.retry_checkpoint())

if __name__ == "__main__":
    unittest.main()
