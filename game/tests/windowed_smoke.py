"""Scripted checks through the actual main.py window; no human input is claimed.

Run from the project root: .venv/Scripts/python.exe -m game.tests.windowed_smoke
This opens, resizes and closes a native window, saving render_*.png evidence.
"""
from pathlib import Path
import math
import runpy
import statistics
import time as wall_clock

from direct.showbase.ShowBase import ShowBase
from panda3d.core import Filename, WindowProperties, loadPrcFileData
from PIL import Image, ImageStat

loadPrcFileData("", "audio-library-name null\nmodel-cache-dir\n")


def verify_window(app):
    from ursina import Vec3, application, camera, held_keys, mouse, scene, time
    from game.game_manager import GameManager

    manager = next(entity for entity in scene.entities if isinstance(entity, GameManager))

    def frames(count=12):
        for _ in range(count):
            app.taskMgr.step()
            app.graphicsEngine.renderFrame()

    def capture(name):
        path = Path(__file__).parent / name
        assert app.win.saveScreenshot(Filename.from_os_specific(str(path.resolve())))
        return Image.open(path).convert("RGB")

    def pose(position, target):
        camera.position = Vec3(*position)
        direction = Vec3(*target) - camera.position
        camera.rotation = Vec3(math.degrees(math.atan2(-direction.y, math.hypot(direction.x, direction.z))),
                               math.degrees(math.atan2(direction.x, direction.z)), 0)

    try:
        frames(60)
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
            properties = WindowProperties()
            properties.set_size(width, height)
            app.win.request_properties(properties)
            frames()
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
        for _ in range(240):
            simulated_frames(1)
            if manager.state == "dead":
                break
        assert manager.state == "dead"
        capture("render_survival_caught.png")
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

        def walk_to(point):
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
                    frames(1)
                    assert (player.position-before).length() > .000001, (point,before)
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
        properties = WindowProperties()
        properties.set_size(640,480)
        app.win.request_properties(properties)
        simulated_frames(8)
        capture('render_progression_inventory_640x480.png')
        properties.set_size(1280,720)
        app.win.request_properties(properties)
        simulated_frames(8)
        app.input('tab',is_raw=True)
        visit(props['fuse_box'],house.puzzles['fuse_box'])
        assert player.progression.power_restored and player.inventory.count('fuse') == 0
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
        visit(props['boards'],house.puzzles['boards'])
        assert player.progression.boards_removed and player.inventory.count('crowbar') == 1
        visit(spawns['bedroom_exit_key'],house.pickups['bedroom_exit_key'])
        assert player.inventory.has_key('exit_key')
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
        print('PROGRESSION_WINDOW_OK: W/rays/E, notes, inventory/resize, fuse, wrong/correct code, reusable crowbar, key, exit, R reset; ghost disabled for route fixture')
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
    finally:
        app.destroy()


if __name__ == "__main__":
    ShowBase.run = verify_window
    runpy.run_path(str(Path(__file__).resolve().parents[2] / "main.py"), run_name="__main__")
