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

loadPrcFileData("", "audio-library-name null\nmodel-cache-dir\n")


def verify_window(app):
    from ursina import Vec3, application, camera, held_keys, mouse, scene
    from game.game_manager import GameManager

    manager = next(entity for entity in scene.entities if isinstance(entity, GameManager))

    def frames(count=12):
        for _ in range(count):
            app.taskMgr.step()
            app.graphicsEngine.renderFrame()

    def capture(name):
        path = Path(__file__).parent / name
        assert app.win.saveScreenshot(Filename.from_os_specific(str(path.resolve())))

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
        manager.scene_manager.player.enabled = False
        manager.scene_manager.ghost.enabled = False
        mouse.locked = False
        manager.hud.set_prompt("")
        camera.world_parent = scene
        for name, view in house.level.house["views"].items():
            house.ceiling.visible = name != "overview"
            camera.position = Vec3(*view["position"])
            direction = Vec3(*view["target"]) - camera.position
            camera.rotation = Vec3(math.degrees(math.atan2(-direction.y, math.hypot(direction.x, direction.z))),
                                   math.degrees(math.atan2(direction.x, direction.z)), 0)
            room_id = "bedroom_two" if name == "bedroom" else name
            manager.hud.show_message("House layout" if name == "overview" else house.rooms[room_id].title)
            frames(4)
            capture(f"render_house_{name}.png")
        print(f"HOUSE_VIEWS_OK: {len(house.rooms)} areas, {len(house.nav_nodes)} nodes, "
              f"{len(house.level.navigation['edges'])} edges, "
              f"{len(scene.collidables)} colliders, six authored screenshots")
    finally:
        app.destroy()


if __name__ == "__main__":
    ShowBase.run = verify_window
    runpy.run_path(str(Path(__file__).resolve().parents[2] / "main.py"), run_name="__main__")
