from ursina import Entity, Vec3, application, held_keys, mouse, time
from direct.showbase.DirectObject import DirectObject

from game.scene_manager import SceneManager
from game.ui.game_over import EndScreen
from game.ui.hud import HUD


class GameManager(Entity):
    def __init__(self):
        super().__init__()

        self.state = "playing"
        self._focused = True
        self._focus_paused = False
        self._skip_resume_frame = False
        self.ignore_paused = True

        self.hud = HUD()
        self.end_screen = EndScreen()

        self.scene_manager = SceneManager(
            hud=self.hud,
            on_escape=self.win_game,
            on_caught=self.begin_jumpscare,
        )

        self.hud.show_message(
            "Find the flashlight. Tab opens inventory; E interacts. Read the living-room note.",
            seconds=4,
        )
        self.window_events = DirectObject()
        self.window_events.accept("window-event", self._window_event)
        self.on_destroy = self.window_events.ignore_all
        self._layout_size = None

    def input(self, key):
        player = self.scene_manager.player
        if not self._focused:
            return True
        if self.state == "playing" and self.hud.panel.active:
            self.hud.panel.handle(key)
            return True
        if key == "tab" and self.state == "playing":
            self.hud.panel.open_inventory(player)
            return True
        if key == "escape":
            application.quit()

        if key == "r" and self.state != "playing" and self._focused:
            self.restart_game()
            return True
        if self.state == "jumpscare":
            return True

    def restart_game(self):
        self.scene_manager.dispose()
        held_keys.clear()
        mouse.velocity = Vec3(0, 0, 0)
        self.state = "playing"
        self.end_screen.enabled = False
        self.hud.enabled = True
        self.hud.set_prompt("")
        self.scene_manager = SceneManager(self.hud, self.win_game, self.begin_jumpscare)
        self.hud.show_message("Find the flashlight. Read the living-room note; Tab opens inventory.", seconds=4)
        if not self._focused:
            mouse.locked = False

    def _window_event(self, graphics_window):
        if graphics_window == application.base.win and hasattr(graphics_window, "get_properties"):
            self.set_focus(graphics_window.get_properties().get_foreground())

    def set_focus(self, focused):
        if self._focused == focused:
            return
        self._focused = focused
        held_keys.clear()
        mouse.velocity = Vec3(0, 0, 0)
        self.scene_manager.player.stats.noise_level = 0
        if not focused:
            self.scene_manager.player.stats.noise_events.clear()
            self._paused_before_focus = application.paused
            self._mouse_before_focus = mouse.enabled
            self._focus_paused = True
            application.paused = True
            mouse.locked = False
            mouse.enabled = False
        else:
            if self._focus_paused:
                application.paused = self._paused_before_focus
                mouse.enabled = self._mouse_before_focus
                self._focus_paused = False
            mouse.locked = self.state == "playing" and not application.paused
            self._skip_resume_frame = True

    def update(self):
        if self._skip_resume_frame:
            time.dt = 0
            self._skip_resume_frame = False
        size = (application.base.win.get_x_size(), application.base.win.get_y_size())
        if size != self._layout_size:
            self._layout_size = size
            self.hud.layout(size[0] / max(size[1], 1))
            self.end_screen.resize(size[0] / max(size[1], 1))
        if self._focused and not application.paused:
            if self.state == "playing":
                self.scene_manager.horror.update(time.dt)
            elif self.state == "jumpscare":
                self.scene_manager.ghost.jumpscare.update(time.dt)

    def begin_jumpscare(self):
        if self.state != "playing":
            return
        self.state = "jumpscare"
        self.scene_manager.stop_gameplay()
        self.scene_manager.ghost.ai.navigation.clear()
        held_keys.clear()
        mouse.velocity = Vec3(0,0,0)
        mouse.locked = False
        self.hud.enabled = False
        self.scene_manager.ghost.jumpscare.begin(self.game_over)

    def game_over(self):
        if self.state not in ("playing","jumpscare"):
            return

        self.state = "dead"
        self.scene_manager.stop_gameplay()
        mouse.locked = False
        self.hud.set_prompt("")
        self.hud.enabled = False

        self.end_screen.show(
            "CAUGHT!",
            "The ghost found you.\nPress R to restart.",
        )

    def win_game(self):
        if self.state != "playing":
            return

        self.state = "escaped"
        self.scene_manager.stop_gameplay()
        mouse.locked = False
        self.hud.set_prompt("")
        self.hud.enabled = False

        self.end_screen.show(
            "YOU ESCAPED",
            "Sinister Secrets prototype complete.\nPress R to restart.",
        )
