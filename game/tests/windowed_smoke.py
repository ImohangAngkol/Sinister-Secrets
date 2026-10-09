"""Scripted checks through the actual main.py window; no human input is claimed.

Run from the project root: .venv/Scripts/python.exe -m game.tests.windowed_smoke
This opens, resizes and closes a native window, saving render_*.png evidence.
"""
from pathlib import Path
import math
import runpy
import statistics
import tempfile
import json
import gc
import tracemalloc
import ctypes
import sys
import time as wall_clock

from direct.showbase.ShowBase import ShowBase
from panda3d.core import Filename, WindowProperties, loadPrcFileData
from PIL import Image, ImageStat

loadPrcFileData("", "audio-library-name null\nmodel-cache-dir\n")


def verify_window(app):
    from ursina import Vec3, application, camera, held_keys, mouse, scene, time
    from game.game_manager import GameManager
    from game.settings import Preferences

    manager = next(entity for entity in scene.entities if isinstance(entity, GameManager))
    # Deterministic defaults without overwriting the player's local preferences.
    manager.preferences = Preferences(path=None)
    from game.systems.save_manager import SaveManager
    save_folder = tempfile.TemporaryDirectory()
    manager.save_manager = SaveManager(save_folder.name)
    manager.automatic_checkpoints = False
    manager.main_menu.refresh_saves()
    manager.apply_live_preferences()

    def frames(count=12):
        for _ in range(count):
            app.taskMgr.step()
            app.graphicsEngine.renderFrame()

    def capture(name):
        path = Path(__file__).parent / name
        assert app.win.saveScreenshot(Filename.from_os_specific(str(path.resolve())))
        return Image.open(path).convert("RGB")

    def resize(width,height):
        properties=WindowProperties()
        properties.set_size(width,height)
        app.win.request_properties(properties)
        # Native WM requests are asynchronous; allow delivery before asserting.
        for _ in range(100):
            frames(1)
            if (app.win.get_x_size(),app.win.get_y_size())==(width,height):
                frames(2)
                return
            wall_clock.sleep(.01)
        raise AssertionError(('Resize not applied',width,height,app.win.get_properties()))

    def pose(position, target):
        camera.position = Vec3(*position)
        direction = Vec3(*target) - camera.position
        camera.rotation = Vec3(math.degrees(math.atan2(-direction.y, math.hypot(direction.x, direction.z))),
                               math.degrees(math.atan2(direction.x, direction.z)), 0)

    def capture_gameplay_accessibility():
        player,house=manager.scene_manager.player,manager.scene_manager.house
        manager.scene_manager.ghost.enabled=False  # Stationary UI fixture only.
        player.inventory.add('household_order')  # UI-only fixture after reset.
        for factor in (1.,1.25,1.5):
            manager.preferences.save(dict(manager.preferences.values,text_scale=factor))
            manager.apply_live_preferences()
            for width,height in ((640,480),(960,720),(1280,720)):
                resize(width,height)
                for mode in ('inventory','note','combination'):
                    if mode=='inventory': manager.hud.panel.open_inventory(player)
                    elif mode=='note': manager.hud.panel.open_note(player,'household_order')
                    else: manager.hud.panel.open_combination(player,house.puzzles['lockbox'])
                    frames(2)
                    capture(f'render_access_{mode}_{factor}_{width}x{height}.png')
                    manager.hud.panel.close()
                manager.hud.show_message('Checkpoint restored. Escape pauses; Tab opens inventory.')
                frames(2)
                capture(f'render_access_hud_{factor}_{width}x{height}.png')
                app.input('escape',is_raw=True)
                frames(2)
                capture(f'render_access_pause_{factor}_{width}x{height}.png')
                app.input('escape',is_raw=True)
                manager.end_screen.show('CAUGHT!','Retry restores your checkpoint. R: restart; Escape: menu')
                manager.end_screen.enabled=True
                frames(2)
                capture(f'render_access_end_{factor}_{width}x{height}.png')
                manager.end_screen.enabled=False
        manager.preferences=Preferences(path=None)
        manager.apply_live_preferences()
        resize(1280,720)

    try:
        frames(60)
        assert manager.state == "menu" and manager.scene_manager is None
        assert application.paused and not mouse.locked
        manager.set_focus(True)
        for width, height in ((640,480),(960,720),(1280,720)):
            resize(width,height)
            capture(f'render_menu_main_{width}x{height}.png')
            app.input('down arrow',is_raw=True)
            app.input('enter',is_raw=True)
            assert manager.state=='settings' and manager.scene_manager is None
            frames(2)
            capture(f'render_menu_settings_{width}x{height}.png')
            app.input('right arrow',is_raw=True)
            assert manager.settings_menu.draft['mouse_sensitivity']==1.25
            app.input('escape',is_raw=True)
            assert manager.preferences.values['mouse_sensitivity']==1
            app.input('down arrow',is_raw=True)
            app.input('enter',is_raw=True)
            assert manager.state=='controls'
            frames(2)
            capture(f'render_menu_controls_{width}x{height}.png')
            app.input('escape',is_raw=True)
            manager.main_menu.selected=0
            app.input('enter',is_raw=True)
            frames(2)
            assert manager.state=='playing' and mouse.locked
            current=manager.scene_manager
            assert not manager.start_game()
            app.input('escape',is_raw=True)
            assert manager.state=='paused' and application.paused and not mouse.locked
            battery=current.player.stats.battery
            stamina=current.player.stats.stamina
            clock=current.horror.clock
            position=Vec3(current.ghost.position)
            frames(30)
            assert (current.player.stats.battery,current.player.stats.stamina,current.horror.clock)==(battery,stamina,clock)
            assert current.ghost.position==position
            capture(f'render_menu_pause_{width}x{height}.png')
            manager.pause_menu.selected=1
            app.input('enter',is_raw=True)
            app.input('right arrow',is_raw=True)
            manager.settings_menu.selected=11  # Apply and Back.
            app.input('enter',is_raw=True)
            assert manager.state=='paused' and tuple(current.player.mouse_sensitivity)==(50,50)
            app.input('escape',is_raw=True)
            assert manager.state=='playing' and mouse.locked
            app.input('tab',is_raw=True)
            frames(2)
            capture(f'render_menu_inventory_{width}x{height}.png')
            app.input('escape',is_raw=True)
            assert manager.state=='playing'
            manager.game_over()
            frames(2)
            capture(f'render_menu_game_over_{width}x{height}.png')
            app.input('escape',is_raw=True)
            assert manager.state=='menu' and manager.scene_manager is None and current.house.is_empty()
            # Restore defaults in memory for the existing lighting/survival fixtures.
            manager.preferences=Preferences(path=None)
        # All accessibility views use the same real native-window panels.
        for factor in (1.,1.25,1.5):
            manager.preferences.save(dict(manager.preferences.values,text_scale=factor))
            manager.apply_live_preferences()
            for width,height in ((640,480),(960,720),(1280,720)):
                resize(width,height)
                frames(2)
                capture(f'render_access_main_{factor}_{width}x{height}.png')
                manager.open_settings()
                for page in (0,9):
                    manager.settings_menu.selected=page
                    manager.settings_menu.refresh_selection()
                    frames(2)
                    capture(f'render_access_settings_{factor}_{width}x{height}_p{page//9+1}.png')
                manager.open_controls()
                frames(2)
                capture(f'render_access_controls_{factor}_{width}x{height}.png')
                manager.close_submenu()
                manager.close_submenu()
        manager.open_controls()
        app.input('enter',is_raw=True)
        app.input('s',is_raw=True)
        assert manager.controls_screen.waiting=='forward'
        capture('render_persistence_rebind_conflict.png')
        app.input('escape',is_raw=True)
        app.input('enter',is_raw=True)
        app.input('i',is_raw=True)
        assert manager.preferences.values['bindings']['forward']=='i'
        frames(2)
        capture('render_persistence_rebind.png')
        manager.controls_screen.reset_defaults()
        app.input('escape',is_raw=True)
        manager.preferences=Preferences(path=None)
        manager.apply_live_preferences()
        resize(1280,720)
        manager.main_menu.selected=0
        manager.main_menu.refresh_selection()
        # Exercise the native mouse ray rather than just assigning hovered_entity.
        app.win.move_pointer(0,640,round(720*(.5-.12)))
        frames(4)
        assert mouse.hovered_entity==manager.main_menu.rows[0][0], mouse.hovered_entity
        app.input('left mouse down',is_raw=True)
        app.input('left mouse up',is_raw=True)
        frames(2)
        assert manager.state=='playing' and manager.scene_manager is not None
        print('MENU_WINDOW_OK: three sizes; menu/settings/controls/pause/inventory/end; native mouse ray Start; resource freeze; resume; fresh-session cleanup')
        if '--accessibility-only' in sys.argv:
            capture_gameplay_accessibility()
            print('ACCESSIBILITY_WINDOW_OK: real native 3 sizes x 3 scales, menus/HUD/inventory/notes/combination/pause/end; scripted fixture')
            return
        assert manager.state == "playing"
        assert mouse.locked
        capture("render_windowed.png")
        costs = []
        for _ in range(120):
            before = wall_clock.perf_counter()
            app.taskMgr.step()
            costs.append((wall_clock.perf_counter() - before) * 1000)
        print(f"FRAME_TIMING: median={statistics.median(costs):.2f}ms "
              f"p95={sorted(costs)[113]:.2f}ms (native scripted run, not a laptop benchmark)")
        for width, height in ((640, 480), (960, 720), (1280, 720)):
            resize(width,height)
            assert app.win.get_x_size() == width and app.win.get_y_size() == height
            assert abs(manager.hud.inventory_ui.x - (-width / height / 2 + 0.03)) < 0.001
            manager.hud.show_message("Flashlight battery is already full. Leave this battery for later.")
            frames(2)
            capture(f"render_windowed_{width}x{height}.png")

        # Exercise native foreground requests. Some desktop environments refuse
        # programmatic focus changes; report that separately from direct events.
        properties = WindowProperties()
        properties.set_foreground(False)
        app.win.request_properties(properties)
        frames()
        native_focus_loss = not app.win.get_properties().get_foreground()
        if native_focus_loss:
            assert application.paused and not mouse.locked
        else:
            manager.set_focus(False)
        assert application.paused and not mouse.locked
        held_keys["w"] = 1
        properties.set_foreground(True)
        app.win.request_properties(properties)
        frames()
        # Direct event fallback is explicit; a human Alt-Tab test is still needed.
        manager.set_focus(True)
        frames()
        assert not application.paused and mouse.locked
        assert not held_keys["w"]
        print("FOCUS_CHECK: native focus loss observed =", native_focus_loss)
        # The WM can send further focus changes while scripted keyboard input
        # runs. After validating real/fallback focus handling above, pin focus
        # for deterministic fixtures; physical Alt-Tab still needs human testing.
        manager.window_events.ignore('window-event')

        for cycle in range(6):
            (manager.win_game if cycle % 2 else manager.game_over)()
            frames(2)
            if cycle < 2:
                capture("render_windowed_win.png" if cycle else "render_windowed_loss.png")
            app.input("r", is_raw=True)
            frames()
            assert manager.state == "playing"
            assert manager.scene_manager.player.enabled and mouse.locked
            assert manager.scene_manager.player.inventory.key_count() == 0
        print("WINDOWED_SMOKE_OK: native resize, six scripted R restarts, mouse capture, screenshots")

        # Capture the data-authored room views through the actual main entry
        # point. Pose the developer camera and freeze gameplay only for these
        # images; this is visual verification, not a claimed human playthrough.
        house = manager.scene_manager.house
        player = manager.scene_manager.player
        app.input("e", is_raw=True)  # Spawn view faces the foyer flashlight.
        assert player.has_flashlight
        app.input("f", is_raw=True)
        assert player.flashlight_on and player.flashlight_light.color.r > 0
        charge = player.stats.battery
        frames()
        assert player.stats.battery < charge
        app.input("f", is_raw=True)
        assert not player.flashlight_on and player.flashlight_light.color.r == 0
        charge = player.stats.battery
        frames(2)
        assert player.stats.battery == charge
        # Survival checks use simulated input and fixed elapsed time in the
        # actual main.py window. Pose fixtures explicitly; this is not manual play.
        ghost = manager.scene_manager.ghost
        live_update = ghost.update
        ghost.update = lambda: None
        mouse_enabled = mouse.enabled
        calculate_dt = application.calculate_dt
        mouse.enabled = False
        application.calculate_dt = False

        def simulated_frames(count):
            for _ in range(count):
                time.dt = time.dt_unscaled = 1 / 60
                frames(1)

        # Force eligible effects for same-pose visual evidence; normal scheduling
        # is tested separately. The real ghost is frozen only for these fixtures.
        horror = manager.scene_manager.horror
        player.position,player.rotation_y = Vec3(0,0,-7),0
        player.camera_pivot.rotation_x = 0
        camera.rotation = Vec3(0,0,0)
        simulated_frames(2)
        normal = capture('render_horror_hallway_normal.png')
        horror.next_allowed=0
        horror.director.tension=.9
        assert horror.start_event('power_dip')
        lighting_before = [tuple(light.color) for light in horror.lights]
        simulated_frames(120)
        disturbed = capture('render_horror_lighting_disturbance.png')
        region=(160,180,1120,640)
        normal_mean=statistics.mean(ImageStat.Stat(normal.crop(region)).mean)
        dim_mean=statistics.mean(ImageStat.Stat(disturbed.crop(region)).mean)
        assert dim_mean < normal_mean-.2,(normal_mean,dim_mean)
        assert not player.flashlight_on and player.flashlight_light.color.r==0
        horror.cancel_active()
        assert [tuple(light.color) for light in horror.lights]==lighting_before
        print(f'HORROR_LIGHTING_PIXELS normal={normal_mean:.2f}, disturbed={dim_mean:.2f}')
        horror.next_allowed=0
        horror.director.tension=.9
        assert horror.start_event('apparition')
        apparition=horror.active['temporary'][0]
        camera.look_at(apparition.world_position)
        simulated_frames(2)
        capture('render_horror_apparition.png')
        app.input('f',is_raw=True)
        simulated_frames(2)
        assert horror.active is None and apparition.is_empty()
        app.input('f',is_raw=True)

        player.position,player.rotation_y = Vec3(-6,0,-6),0
        player.camera_pivot.rotation_x=0
        camera.rotation=Vec3(0,0,0)
        simulated_frames(2)
        horror.next_allowed=0
        horror.director.tension=.9
        assert horror.start_event('cabinet_creak')
        leaf=horror.active['temporary'][0]
        camera.look_at(leaf.world_position)
        app.input('f',is_raw=True)
        simulated_frames(150)
        capture('render_horror_environment.png')
        assert leaf.rotation_y>1 and leaf.collider is None
        costs=[]
        for _ in range(90):
            before=wall_clock.perf_counter()
            simulated_frames(1)
            costs.append((wall_clock.perf_counter()-before)*1000)
        print(f'HORROR_ACTIVE_TIMING median={statistics.median(costs):.2f}ms p95={sorted(costs)[85]:.2f}ms '
              '(native fixed-dt fixture, flashlight ON, ghost frozen, includes explicit renderFrame)')
        horror.cancel_active()
        assert leaf.is_empty()
        costs=[]
        for _ in range(90):
            before=wall_clock.perf_counter()
            simulated_frames(1)
            costs.append((wall_clock.perf_counter()-before)*1000)
        print(f'HORROR_QUIET_TIMING median={statistics.median(costs):.2f}ms p95={sorted(costs)[85]:.2f}ms '
              '(same native fixed-dt fixture, flashlight ON, ghost frozen, explicit renderFrame)')
        app.input('f',is_raw=True)
        # Reset pacing for the survival fixture; upcoming puzzle exploration
        # retains the live director with ordinary seeded scheduling.
        horror.stop()
        from game.systems.horror_manager import HorrorManager
        manager.scene_manager.horror = HorrorManager(house,player,ghost,manager.scene_manager.lights)
        player.horror=manager.scene_manager.horror
        print('HORROR_WINDOW_OK: reversible dimming, same-pose pixel comparison, apparition/beam cleanup, decorative cabinet motion')

        player.position, player.rotation_y = Vec3(0, 0, -10), 0
        player.camera_pivot.rotation_x = 10
        camera.rotation = Vec3(0, 0, 0)
        app.input("control", is_raw=True)
        app.input("w", is_raw=True)
        simulated_frames(30)
        assert player.crouching and abs(player.z + 8.9) < 0.02
        capture("render_survival_crouch.png")
        app.input("w up", is_raw=True)
        app.input("control up", is_raw=True)
        simulated_frames(30)
        assert not player.crouching and player.height > 1.79
        app.input("shift", is_raw=True)
        app.input("w", is_raw=True)
        simulated_frames(60)
        assert 77.9 < player.stats.stamina < 78.1
        capture("render_survival_sprint.png")
        app.input("w up", is_raw=True)
        app.input("shift up", is_raw=True)
        simulated_frames(120)
        assert player.stats.stamina > 92.9

        spot = house.hiding_spots[0]
        player.position, player.rotation_y = spot.approach, 0
        player.camera_pivot.rotation_x = math.degrees(math.atan2(player.height - 1, 1.2))
        app.input("f", is_raw=True)
        simulated_frames(2)
        capture("render_survival_wardrobe.png")
        app.input("f", is_raw=True)
        app.input("e", is_raw=True)
        assert player.hidden and spot.occupant == player
        hidden_position = Vec3(player.position)
        app.input("w", is_raw=True)
        simulated_frames(30)
        assert player.position == hidden_position
        capture("render_survival_hidden.png")
        app.input("w up", is_raw=True)
        app.input("e", is_raw=True)
        assert not player.hidden and player.can_occupy(player.position, 1)
        simulated_frames(90)

        # The live AI witnesses an entry, routes to that wardrobe and inspects
        # it; normal hidden-player LOS stays false throughout.
        player.position, player.rotation_y = spot.approach, 0
        player.camera_pivot.rotation_x = math.degrees(math.atan2(player.height - 1, 1.2))
        ghost.position, ghost.rotation_y = Vec3(4.6, 0, -11.2), -90
        app.input("e", is_raw=True)
        assert player.hidden and ghost.ai.suspected_hiding_spot == spot
        ghost.update = live_update
        simulated_frames(65)
        assert manager.state == "playing" and ghost.ai.inspection_target == spot
        capture("render_survival_inspection.png")
        staged_capture=False
        for _ in range(300):
            simulated_frames(1)
            if (manager.state=='jumpscare' and ghost.jumpscare.elapsed>=.7 and not staged_capture):
                staged=capture('render_horror_jumpscare.png')
                assert statistics.mean(ImageStat.Stat(staged.crop((600,300,680,400))).mean)>35
                staged_capture=True
            if manager.state == "dead":
                break
        assert manager.state == "dead"
        assert staged_capture and ghost.jumpscare.proxy is None and ghost.jumpscare.overlay is None
        capture("render_survival_caught.png")
        capture('render_horror_game_over.png')
        app.input("r", is_raw=True)
        simulated_frames(2)
        assert manager.state == "playing"
        player, house, ghost = (manager.scene_manager.player, manager.scene_manager.house,
                                manager.scene_manager.ghost)
        assert not player.hidden and player.stats.stamina == 100
        assert all(spot.occupant is None for spot in house.hiding_spots)
        # Complete the authored puzzle chain using real W movement/rays and
        # engine keyboard dispatch. Disable the ghost ONLY for this deterministic
        # route fixture; the live survival/capture sequence above remains intact.
        ghost.enabled = False
        from game.ghost.ghost_navigation import astar
        from game.player.interaction import get_interaction_hit
        current_room = 'foyer'

        route_seconds = 0.0

        def restore_refs():
            nonlocal player,house,ghost
            player,house,ghost=(manager.scene_manager.player,manager.scene_manager.house,manager.scene_manager.ghost)
            ghost.enabled=False
            ghost.position=Vec3(house.ghost_spawn)  # Frozen route fixture, away from foyer.
            simulated_frames(2)

        def manual_save_continue(label):
            nonlocal current_room
            player.toggle_flashlight()
            simulated_frames(2)
            app.input('escape',is_raw=True)
            manager.pause_menu.selected=2
            manager.pause_menu.refresh_selection()
            while wall_clock.monotonic()-manager._last_manual_save<10:
                frames(1)
                wall_clock.sleep(.05)
            app.input('enter',is_raw=True)
            assert 'Game saved' in manager.pause_menu.subtitle_text.text
            snapshot=manager.save_manager.load()
            frames(2)
            capture(f'render_persistence_save_{label}.png')
            manager.pause_menu.selected=4
            app.input('enter',is_raw=True)
            assert manager.state=='menu' and 1 not in manager.main_menu.disabled_rows
            manager.main_menu.selected=1
            manager.main_menu.refresh_selection()
            frames(2)
            capture(f'render_persistence_continue_{label}.png')
            app.input('enter',is_raw=True)
            assert manager.state=='playing'
            assert list(manager.scene_manager.player.position)==snapshot['player']['position']
            assert manager.scene_manager.player.inventory.quantities==snapshot['inventory']
            assert manager.scene_manager.player.stats.battery==snapshot['player']['battery']
            assert manager.scene_manager.player.flashlight_on
            restore_refs()
            capture(f'render_persistence_restored_{label}.png')
            app.input('f',is_raw=True)

        def walk_to(point):
            nonlocal route_seconds
            point = Vec3(*point)
            camera.rotation = Vec3(0,0,0)
            player.camera_pivot.rotation_x = 0
            held_keys.clear()
            app.input('w',is_raw=True)
            try:
                for _ in range(1400):
                    delta = Vec3(point.x-player.x,0,point.z-player.z)
                    if delta.length() < .025:
                        return
                    player.rotation_y = math.degrees(math.atan2(delta.x,delta.z))
                    before = Vec3(player.position)
                    time.dt = time.dt_unscaled = min(1/30,delta.length()/5)
                    route_seconds += time.dt
                    frames(1)
                    assert (player.position-before).length() > .000001, (
                        point,before,'W',held_keys['w'],'dt',time.dt,'focused',manager._focused,
                        'paused',application.paused,'enabled',player.enabled,'state',manager.state,
                        'panel',manager.hud.panel.mode)
                raise AssertionError(f'Route did not reach {point}')
            finally:
                app.input('w up',is_raw=True)

        def visit(entry, entity):
            nonlocal current_room
            walk_to(house.nav_nodes[current_room])
            for node in astar(current_room,entry['room'],house.nav_nodes,house.graph):
                walk_to(house.nav_nodes[node])
            walk_to(entry['approach'])
            camera.look_at(entity.world_position)
            assert get_interaction_hit(player).entity == entity, entry['id']
            app.input('e',is_raw=True)
            current_room = entry['room']

        for playthrough in range(2):
            if playthrough:
                app.input('escape',is_raw=True)
                assert manager.state=='menu' and manager.scene_manager is None
                app.input('enter',is_raw=True)
                assert manager.state=='confirm_new'
                app.input('enter',is_raw=True)
                simulated_frames(2)
                player,house,ghost=(manager.scene_manager.player,manager.scene_manager.house,
                                    manager.scene_manager.ghost)
                assert not player.inventory.quantities and not player.progression.power_restored
                ghost.enabled=False
                current_room='foyer'
            spawns = {entry['id']:entry for entry in house.level.spawns['pickups']}
            props = {entry['id']:entry for entry in house.level.house['progression']['props']}
            visit(spawns['foyer_flashlight'],house.pickups['foyer_flashlight'])
            visit(spawns['living_instructions'],house.pickups['living_instructions'])
            simulated_frames(2)
            capture('render_progression_note.png')
            app.input('escape',is_raw=True)
            visit(spawns['storage_fuse'],house.pickups['storage_fuse'])
            app.input('tab',is_raw=True)
            assert manager.hud.panel.mode == 'inventory' and mouse.locked
            simulated_frames(2)
            capture('render_progression_inventory.png')
            # Check compact screen layout in the actual window, not only arithmetic.
            resize(640,480)
            simulated_frames(8)
            capture('render_progression_inventory_640x480.png')
            resize(1280,720)
            simulated_frames(8)
            app.input('tab',is_raw=True)
            visit(props['fuse_box'],house.puzzles['fuse_box'])
            assert player.progression.power_restored and player.inventory.count('fuse') == 0
            manager.automatic_checkpoints=True
            manager._checkpoints()
            assert manager.save_manager.load('checkpoint')['milestone']=='power'
            manual_save_continue('power')
            app.input('escape',is_raw=True)
            assert manager.state=='paused'
            charge,clock=player.stats.battery,manager.scene_manager.horror.clock
            simulated_frames(60)
            assert (player.stats.battery,manager.scene_manager.horror.clock)==(charge,clock)
            app.input('escape',is_raw=True)
            simulated_frames(2)
            app.input('f',is_raw=True)
            simulated_frames(2)
            capture('render_progression_fuse_box.png')
            app.input('f',is_raw=True)
            visit(spawns['kitchen_battery'],house.pickups['kitchen_battery'])
            assert player.inventory.count('battery') == 1
            charge = player.stats.battery
            app.input('tab',is_raw=True)
            panel = manager.hud.panel
            while panel.item_ids()[panel.selected] != 'battery':
                app.input('down arrow',is_raw=True)
            app.input('u',is_raw=True)
            simulated_frames(2)
            capture('render_progression_battery_confirmation.png')
            app.input('enter',is_raw=True)
            assert player.inventory.count('battery') == 0 and player.stats.battery > charge
            app.input('escape',is_raw=True)
            visit(spawns['kitchen_tally'],house.pickups['kitchen_tally'])
            simulated_frames(2)
            capture('render_progression_tally.png')
            app.input('escape',is_raw=True)
            visit(props['lockbox'],house.puzzles['lockbox'])
            for digit in '0000': app.input(digit,is_raw=True)
            app.input('enter',is_raw=True)
            assert not player.progression.safe_unlocked
            simulated_frames(2)
            capture('render_progression_combination.png')
            for digit in house.level.house['progression']['combination']: app.input(digit,is_raw=True)
            app.input('enter',is_raw=True)
            assert player.progression.safe_unlocked and player.inventory.count('crowbar') == 1
            simulated_frames(2)
            checkpoint=manager.save_manager.load('checkpoint')
            assert checkpoint['milestone']=='lockbox'
            # Live capture from a close, unobstructed CHASE fixture; actual AI
            # and staged jumpscare run to completion, rather than calling death.
            ghost.enabled=True
            ghost.ai.grace_time=0
            from game.ghost.ghost_states import GhostState
            ghost.ai.state=GhostState.CHASE
            ghost.ai.detection=1
            ghost.position=player.position+Vec3(0,0,-.8)
            ghost.look_at_2d(player.position,'y')
            for _ in range(200):
                simulated_frames(1)
                if manager.state=='dead': break
            assert manager.state=='dead'
            manager.end_screen.selected=2
            manager.end_screen.refresh_selection()
            frames(2)
            capture('render_persistence_checkpoint_retry.png')
            app.input('enter',is_raw=True)
            assert manager.state=='playing'
            assert manager.scene_manager.player.inventory.quantities==checkpoint['inventory']
            assert manager.scene_manager.player.stats.battery==checkpoint['player']['battery']
            assert manager.scene_manager.player.position==Vec3(house.nav_nodes['foyer'])
            assert manager.scene_manager.ghost.ai.grace_time==5
            assert manager.scene_manager.ghost.ai.detection==0
            restore_refs()
            current_room='foyer'
            capture('render_persistence_checkpoint_restored.png')
            visit(props['boards'],house.puzzles['boards'])
            assert player.progression.boards_removed and player.inventory.count('crowbar') == 1
            visit(spawns['bedroom_exit_key'],house.pickups['bedroom_exit_key'])
            assert player.inventory.has_key('exit_key')
            simulated_frames(2)
            assert manager.save_manager.load('checkpoint')['milestone']=='exit_key'
            manual_save_continue('key')
            app.input('f',is_raw=True)
            simulated_frames(2)
            manager.hud.message.enabled = False
            capture('render_progression_objective.png')
            app.input('f',is_raw=True)
            walk_to(house.nav_nodes[current_room])
            for node in astar(current_room,'exit_approach',house.nav_nodes,house.graph):
                walk_to(house.nav_nodes[node])
            camera.look_at(Vec3(0,1.5,17.8))
            app.input('e',is_raw=True)
            simulated_frames(50)
            assert house.exit_door.opened
            camera.rotation = Vec3(0,0,0)
            player.camera_pivot.rotation_x, player.rotation_y = 0,0
            app.input('w',is_raw=True)
            for _ in range(60):
                simulated_frames(1)
                if manager.state == 'escaped': break
            app.input('w up',is_raw=True)
            assert manager.state == 'escaped'
            capture('render_progression_escape.png')
        app.input('r',is_raw=True)
        simulated_frames(2)
        player, house, ghost = (manager.scene_manager.player, manager.scene_manager.house,
                                manager.scene_manager.ghost)
        assert not player.progression.power_restored and not player.inventory.quantities
        manager.automatic_checkpoints=False
        print(f'PERSISTENCE_ROUTE: two full routes, {route_seconds:.2f}s walking simulation; excludes human clue reading/search/detours')
        print('PROGRESSION_WINDOW_OK: two full puzzle escapes via victory/menu/new game, pause after fuse, W/rays/E, notes, inventory/resize, fuse, wrong/correct code, reusable crowbar, key, exit, R reset; ghost disabled for route fixture')
        capture_gameplay_accessibility()
        application.calculate_dt = calculate_dt
        mouse.enabled = mouse_enabled
        held_keys.clear()
        # Restore the flashlight for the unchanged OFF/ON visual comparisons.
        app.input("e", is_raw=True)
        assert player.has_flashlight
        # Completed-gate fixture lets legacy light comparisons still inspect the
        # real exit-key geometry. The full locked progression was tested above.
        player.inventory.add('fuse')
        player.progression.install_fuse()
        player.progression.try_combination(house.level.house['progression']['combination'])
        player.progression.remove_boards()
        print("SURVIVAL_WINDOW_OK: engine Ctrl/W/Shift/E, stamina, safe exit, live inspection/catch, R cleanup")
        player.enabled = False
        manager.scene_manager.horror.stop()  # Keep baseline lighting comparisons stationary.
        ghost.update = lambda: None  # Freeze AI only during image comparisons.
        ghost.position = (0, 0, -2)
        mouse.locked = False
        manager.hud.set_prompt("")
        manager.hud.message.enabled = False
        camera.world_parent = scene
        views = dict(house.level.house["views"])
        overview = views.pop("overview")
        views.update({
            "ghost": {"position": (0, 1.8, -7), "target": (0, 1, -2)},
            "battery": {"position": (-15, 1.8, 5), "target": (-16.6, 1.2, 5)},
            "key": {"position": (7.2, 1.8, 9), "target": (8.7, 0.9, 9)},
            "exit": {"position": (0, 1.8, 15), "target": (0, 1.5, 17.8)},
        })
        views["overview"] = overview
        print("LIGHTING_GPU:", app.win.get_gsg().get_driver_renderer())
        for name, view in views.items():
            house.ceiling.visible = name != "overview"
            pose(view["position"], view["target"])
            if name == "overview":
                # Developer inspection lighting, not the gameplay atmosphere.
                from ursina import color
                scene.clear_fog()
                manager.scene_manager.lights[0].color = color.rgb(0.4, 0.4, 0.45)
                manager.scene_manager.lights[1].color = color.rgb(0.2, 0.2, 0.18)
                frames(4)
                capture("render_house_overview.png")
                continue
            player._set_flashlight_light(False)
            frames(4)
            off = capture(f"render_lighting_{name}_off.png")
            player.toggle_flashlight()
            frames(4)
            on = capture(f"render_lighting_{name}_on.png")
            if name in house.level.house["views"]:
                capture(f"render_house_{name}.png")
            # Ignore HUD; measure the same stationary world geometry.
            region = (160, 180, 1120, 640)
            off_mean = statistics.mean(ImageStat.Stat(off.crop(region)).mean)
            on_mean = statistics.mean(ImageStat.Stat(on.crop(region)).mean)
            assert on_mean > off_mean + 2, (name, off_mean, on_mean)
            print(f"LIGHTING_PIXELS {name}: OFF={off_mean:.2f}, ON={on_mean:.2f}")
            player.toggle_flashlight()
            if name == "main_hall":
                for enabled in (False, True):
                    player._set_flashlight_light(enabled)
                    frames(12)
                    costs = []
                    for _ in range(120):
                        before = wall_clock.perf_counter()
                        app.taskMgr.step()
                        costs.append((wall_clock.perf_counter() - before) * 1000)
                    print(f"LIGHTING_TIMING {'ON' if enabled else 'OFF'}: "
                          f"median={statistics.median(costs):.2f}ms p95={sorted(costs)[113]:.2f}ms "
                          "(native 1280x720, frozen camera/AI)")
                player._set_flashlight_light(False)
        print(f"HOUSE_VIEWS_OK: {len(house.rooms)} areas, {len(house.nav_nodes)} nodes, "
              f"{len(house.level.navigation['edges'])} edges, "
              f"{len(scene.collidables)} colliders, six authored screenshots and nine OFF/ON pairs")
        manager.return_to_menu()
        assert manager.continue_game()
        restore_refs()
        mouse.enabled=False
        application.calculate_dt=False
        manager.automatic_checkpoints=False
        tracemalloc.start()

        def private_memory():
            from ctypes import wintypes
            class MemoryCounters(ctypes.Structure):
                _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
            counters=MemoryCounters();counters.cb=ctypes.sizeof(counters)
            process=ctypes.windll.kernel32.GetCurrentProcess
            process.restype=wintypes.HANDLE
            query=ctypes.windll.psapi.GetProcessMemoryInfo
            query.argtypes=(wintypes.HANDLE,ctypes.POINTER(MemoryCounters),wintypes.DWORD)
            assert query(process(),ctypes.byref(counters),counters.cb)
            return counters.PrivateUsage,counters.WorkingSetSize

        def sample():
            gc.collect()
            active=[e for e in scene.entities if not e.is_empty()]
            from panda3d.core import LightAttrib
            return dict(entities=len(active),colliders=len(scene.collidables),ghosts=sum(e.__class__.__name__=='Ghost' for e in active),managers=sum(isinstance(e,GameManager) for e in active),lights=app.render.get_state().get_attrib(LightAttrib).get_num_on_lights(),tasks=len(app.taskMgr.getAllTasks()),sequences=len(application.sequences),python_bytes=tracemalloc.get_traced_memory()[0],private_working_bytes=private_memory())

        samples=[]
        for cycle in range(25):
            app.input('escape',is_raw=True)
            # Backend writes exercise IO/restore repeatedly; UI cooldown is
            # tested above and is deliberately not bypassed through the UI.
            manager.save_manager.save(SaveManager.capture(manager.scene_manager,manager.session_id))
            assert manager.load_game()
            restore_refs()
            samples.append(sample())
        stable_keys=('entities','colliders','ghosts','managers','lights','tasks','sequences')
        assert all(samples[-1][key]==samples[4][key] for key in stable_keys),(samples[4],samples[-1])
        for _ in range(25):
            app.input('escape',is_raw=True)
            app.input('escape',is_raw=True)
            simulated_frames(2)
        costs=[]
        for _ in range(1200):
            time.dt=time.dt_unscaled=.5
            before=wall_clock.perf_counter()
            frames(1)
            costs.append((wall_clock.perf_counter()-before)*1000)
        end=sample()
        report=dict(warmup=samples[4],after_25_loads=samples[-1],after_600_simulated_seconds=end,
                    frame_median_ms=statistics.median(costs),frame_p95_ms=sorted(costs)[1139],frame_max_ms=max(costs),python_peak_bytes=tracemalloc.get_traced_memory()[1],gpu=app.win.get_gsg().get_driver_renderer(),limitations='Scripted native window; ghost frozen for route/profiling. Tracemalloc adds overhead. Simulated time is not 10 minutes of human play. Process deltas include caches/driver allocations.')
        Path(__file__).with_name('render_persistence_profile.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('PERSISTENCE_PROFILE',json.dumps(report))
        print('PERSISTENCE_WINDOW_OK: temporary slots only; fuse/manual/Continue; lockbox/live CHASE/catch/Retry; key/manual/Continue/escape twice; confirmation/reset; 25 loads and pause cycles; 600 simulated seconds; all scale/size screenshots')
        tracemalloc.stop()
    finally:
        app.destroy()
        save_folder.cleanup()


if __name__ == "__main__":
    ShowBase.run = verify_window
    runpy.run_path(str(Path(__file__).resolve().parents[2] / "main.py"), run_name="__main__")
