from ursina import Entity, Vec2, Vec3, application, color, held_keys, mouse, scene, time
from direct.showbase.DirectObject import DirectObject
from panda3d.core import ClockObject

from game import settings
from game.scene_manager import SceneManager
from game.ui.game_over import EndScreen
from game.ui.hud import HUD
from game.ui.main_menu import MainMenu, ControlsScreen, SettingsMenu
from game.ui.pause_menu import PauseMenu


class GameManager(Entity):
    def __init__(self, preferences=None):
        super().__init__(ignore_paused=True)
        self.preferences = preferences if preferences is not None else settings.Preferences()
        self.state = "menu"
        self.scene_manager = None
        self._focused = True
        self._focus_paused = False
        self._skip_resume_frame = False
        self._fps_applied = None
        self._submenu_parent = "menu"
        self.hud = HUD()
        self.hud.enabled = False
        self.main_menu = MainMenu(self)
        self.pause_menu = PauseMenu(self)
        self.settings_menu = SettingsMenu(self)
        self.controls_screen = ControlsScreen(self)
        self.end_screen = EndScreen(self)
        self.screens = {"menu": self.main_menu, "paused": self.pause_menu,
                        "settings": self.settings_menu, "controls": self.controls_screen,
                        "dead": self.end_screen, "escaped": self.end_screen}
        self.window_events = DirectObject()
        self.window_events.accept("window-event", self._window_event)
        self.on_destroy = self.window_events.ignore_all
        self._layout_size = None
        self._show_screen("menu")
        self._apply_fps_cap()

    @staticmethod
    def _clear_input():
        held_keys.clear()
        mouse.velocity = Vec3(0, 0, 0)

    def _sync_pause(self):
        application.paused = not self._focused or self.state not in ("playing", "jumpscare")
        mouse.locked = self._focused and self.state == "playing"
        if self.scene_manager:
            self.scene_manager.player.cursor.enabled = (self.state == "playing"
                                                       and self._focused and not self.hud.panel.active)
        self._clear_input()
        self._skip_resume_frame = True
        # Ursina updates sequences before entities. Keep our HUD callback paused
        # through the first resumed frame, then release it after discarding dt.
        if self.hud.message_sequence:
            self.hud.message_sequence.pause()

    def _show_screen(self, state):
        self.state = state
        for screen in set(self.screens.values()):
            screen.enabled = screen == self.screens.get(state)
        self.hud.enabled = state == "playing"
        self._sync_pause()

    def input(self, key):
        if not self._focused:
            self._clear_input()
            return True
        if self.state == "playing":
            if self.hud.panel.active:
                self.hud.panel.handle(key)
                return True
            if key == "tab":
                self.hud.panel.open_inventory(self.scene_manager.player)
                return True
            if key == "escape":
                self.pause_game()
                return True
            return
        if key == "r" and self.state in ("dead", "escaped", "jumpscare"):
            self.restart_game()
            return True
        if key == "escape":
            if self.state == "paused":
                self.resume_game()
            elif self.state in ("settings", "controls"):
                self.close_submenu()
            elif self.state in ("dead", "escaped"):
                self.return_to_menu()
        else:
            screen = self.screens.get(self.state)
            if screen:
                screen.handle(key)
        self._clear_input()
        return True

    def start_game(self):
        if self.state != "menu":
            return False
        self._create_session()
        return True

    def _create_session(self):
        if self.scene_manager:
            self.scene_manager.dispose()
            self.scene_manager = None
        self.hud.panel.close()
        if self.hud.message_sequence:
            self.hud.message_sequence.kill()
            self.hud.message_sequence = None
        self.hud.set_prompt("")
        self._clear_input()
        self.scene_manager = SceneManager(self.hud, self.win_game, self.begin_jumpscare)
        values = self.preferences.values
        self.session_preferences = values.copy()
        light = self.scene_manager.player.flashlight_light._light
        resolution = 1024 if values["shadow_quality"] == "high" else 512
        light.set_shadow_caster(values["shadow_quality"] != "off", resolution, resolution)
        ai = self.scene_manager.ghost.ai
        ai.speed_multiplier, ai.detection_multiplier = settings.GHOST_DIFFICULTY[values["ghost_difficulty"]]
        self.apply_live_preferences()
        self._show_screen("playing")
        self.hud.show_message("Find the flashlight. Read the living-room note; Tab opens inventory. Esc pauses.", seconds=4)
        self.hud.message_sequence.pause()

    def restart_game(self):
        if self.scene_manager is not None:
            self._create_session()

    def pause_game(self):
        if self.state != "playing" or self.hud.panel.active:
            return False
        self.pause_menu.selected = 0
        self.pause_menu.refresh_selection()
        self._show_screen("paused")
        return True

    def resume_game(self):
        if self.state == "paused":
            time.dt = time.dt_unscaled = 0
            self._show_screen("playing")

    def return_to_menu(self):
        if self.scene_manager:
            self.scene_manager.dispose()
            self.scene_manager = None
        self.hud.panel.close()
        if self.hud.message_sequence:
            self.hud.message_sequence.kill()
            self.hud.message_sequence = None
        self.hud.message.text = ""
        self.hud.set_prompt("")
        scene.clear_fog()
        self.main_menu.selected = 0
        self.main_menu.refresh_selection()
        self._show_screen("menu")

    def open_settings(self):
        if self.state not in ("menu", "paused"):
            return
        self._submenu_parent = self.state
        self._show_screen("settings")
        self.settings_menu.open()

    def open_controls(self):
        if self.state == "menu":
            self._submenu_parent = self.state
            self._show_screen("controls")

    def close_submenu(self):
        if self.state in ("settings", "controls"):
            self._show_screen(self._submenu_parent)

    def apply_settings(self):
        try:
            self.preferences.save(self.settings_menu.draft)
        except (OSError, ValueError) as error:
            self.settings_menu.status.text = f"Could not save settings: {type(error).__name__}"
            return False
        self.apply_live_preferences()
        self.close_submenu()
        return True

    def _apply_fps_cap(self):
        cap = self.preferences.values["fps_cap"]
        if cap != self._fps_applied:
            clock = ClockObject.get_global_clock()
            clock.set_mode(ClockObject.MLimited if cap else ClockObject.MNormal)
            if cap:
                clock.set_frame_rate(cap)
            self._fps_applied = cap

    def apply_live_preferences(self):
        self._apply_fps_cap()
        if self.scene_manager is None:
            return
        values = self.preferences.values
        player = self.scene_manager.player
        player.mouse_sensitivity = Vec2(40, 40) * values["mouse_sensitivity"]
        horror = self.scene_manager.horror
        horror.cancel_active()
        old = horror.frequency
        horror.frequency = values["horror_frequency"]
        if old != horror.frequency:
            ratio = max(old, .01) / max(horror.frequency, .01)
            if old == 0:
                horror.next_check = horror.next_allowed = horror.clock + settings.HORROR_INITIAL_QUIET_SECONDS/max(horror.frequency, .01)
            else:
                horror.next_check = horror.clock + max(0, horror.next_check-horror.clock)*ratio
                horror.next_allowed = horror.clock + max(0, horror.next_allowed-horror.clock)*ratio
        horror.reduced_flicker = values["reduced_flicker"]
        jump = self.scene_manager.ghost.jumpscare
        for attribute, key in (("preference_intensity", "jumpscare_intensity"),
                               ("preference_reduced_shake", "reduced_shake")):
            if values[key] == settings.PREFERENCE_DEFAULTS[key]:
                jump.__dict__.pop(attribute, None)
            else:
                setattr(jump, attribute, values[key])
        for light, baseline in zip(self.scene_manager.lights, (settings.HOUSE_AMBIENT_COLOR, settings.HOUSE_FILL_COLOR)):
            light.color = color.rgb(*(channel*values["brightness"] for channel in baseline))

    def quit_game(self):
        if self.scene_manager:
            self.scene_manager.dispose()
            self.scene_manager = None
        application.quit()

    def _window_event(self, graphics_window):
        if graphics_window == application.base.win and hasattr(graphics_window, "get_properties"):
            self.set_focus(graphics_window.get_properties().get_foreground())

    def set_focus(self, focused):
        if self._focused == focused:
            return
        self._focused = focused
        if self.scene_manager:
            self.scene_manager.player.stats.noise_level = 0
            if not focused:
                self.scene_manager.player.stats.noise_events.clear()
        if not focused:
            self._mouse_before_focus = mouse.enabled
            self._focus_paused = True
            mouse.enabled = False
        elif self._focus_paused:
            mouse.enabled = self._mouse_before_focus
            self._focus_paused = False
            time.dt = time.dt_unscaled = 0
        self._sync_pause()

    def update(self):
        if self._skip_resume_frame:
            time.dt = time.dt_unscaled = 0
            self._skip_resume_frame = False
            if self._focused and self.state == "playing" and self.hud.message_sequence:
                self.hud.message_sequence.resume()
        size = (application.base.win.get_x_size(), application.base.win.get_y_size())
        if size != self._layout_size:
            self._layout_size = size
            aspect = size[0]/max(size[1], 1)
            self.hud.layout(aspect)
            for screen in set(self.screens.values()):
                screen.resize(aspect)
        if self._focused and not application.paused and self.scene_manager:
            if self.state == "playing":
                self.scene_manager.horror.update(time.dt)
            elif self.state == "jumpscare":
                self.scene_manager.ghost.jumpscare.update(time.dt)

    def begin_jumpscare(self):
        if self.state != "playing":
            return
        self.scene_manager.stop_gameplay()
        self.scene_manager.ghost.ai.navigation.clear()
        self._show_screen("jumpscare")
        self.scene_manager.ghost.jumpscare.begin(self.game_over)

    def game_over(self):
        if self.state not in ("playing", "jumpscare"):
            return
        self.scene_manager.stop_gameplay()
        self._show_screen("dead")
        self.end_screen.show("CAUGHT!", "The ghost found you.\nR: restart   Escape: main menu")

    def win_game(self):
        if self.state != "playing":
            return
        self.scene_manager.stop_gameplay()
        self._show_screen("escaped")
        self.end_screen.show("YOU ESCAPED", "You made it out of the house.\nR: restart   Escape: main menu")
