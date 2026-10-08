"""Scripted checks through the actual main.py window; no human input is claimed.

Run from the project root: .venv/Scripts/python.exe -m game.tests.windowed_smoke
This opens, resizes and closes a native window, saving render_*.png evidence.
"""
from pathlib import Path
import runpy

from direct.showbase.ShowBase import ShowBase
from panda3d.core import Filename, WindowProperties, loadPrcFileData

loadPrcFileData("", "audio-library-name null\nmodel-cache-dir\n")


def verify_window(app):
    from ursina import application, held_keys, mouse, scene
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
    finally:
        app.destroy()


if __name__ == "__main__":
    ShowBase.run = verify_window
    runpy.run_path(str(Path(__file__).resolve().parents[2] / "main.py"), run_name="__main__")
