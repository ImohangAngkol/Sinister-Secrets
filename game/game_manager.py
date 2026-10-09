from ursina import Entity, Vec2, Vec3, application, camera, color, held_keys, mouse, scene, time
from uuid import uuid4
import time as wall_time
import logging
from direct.showbase.DirectObject import DirectObject
from panda3d.core import ClockObject, LightAttrib, FogAttrib

from game import settings
from game.scene_manager import SceneManager
from game.ui.game_over import EndScreen
from game.ui.hud import HUD
from game.ui.main_menu import MainMenu, ControlsScreen, SettingsMenu, MenuScreen
from game.ui.pause_menu import PauseMenu
from game.systems.save_manager import SaveManager, SaveError
from game.systems.horror_manager import destroy_temporary
from game.ghost.ghost_states import GhostState


class GameManager(Entity):
    def __init__(self, preferences=None, save_manager=None):
        super().__init__(ignore_paused=True)
        self.preferences = preferences if preferences is not None else settings.Preferences()
        self.save_manager = save_manager if save_manager is not None else SaveManager()
        self.automatic_checkpoints = True
        self._checkpoint_recorded = set()
        self._last_manual_save = -1000
        self._submenu_stack = []
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
        self.new_game_confirmation = MenuScreen('START A NEW GAME?',[
            ('Confirm New Game', self.confirm_new_game),('Cancel', self.cancel_new_game)],
            'Checkpoint resets. The next Save replaces manual progress.')
        self.screens = {"menu": self.main_menu, "paused": self.pause_menu,
                        "settings": self.settings_menu, "controls": self.controls_screen,
                        "dead": self.end_screen, "escaped": self.end_screen,
                        'confirm_new': self.new_game_confirmation}
        self.window_events = DirectObject()
        self.window_events.accept("window-event", self._window_event)
        self.on_destroy = self.window_events.ignore_all
        self._layout_size = None
        self._show_screen("menu")
        self.main_menu.refresh_saves()
        self.apply_live_preferences()

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
            if key == self.preferences.values['bindings']['inventory']:
                self.hud.panel.open_inventory(self.scene_manager.player)
                return True
            if key in ('escape', self.preferences.values['bindings']['pause']):
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
                if self.state=='controls' and self.controls_screen.waiting:
                    self.controls_screen.handle(key)
                else:
                    self.close_submenu()
            elif self.state == 'confirm_new':
                self.cancel_new_game()
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
        if self.save_manager.exists():
            self._show_screen('confirm_new')
            return False
        self._create_session()
        return True

    def confirm_new_game(self):
        if self.state != 'confirm_new':
            return
        try:
            self.save_manager.clear_checkpoint()
        except OSError as error:
            self.new_game_confirmation.subtitle_text.text = f'Could not reset checkpoint: {type(error).__name__}'
            return
        self._create_session()

    def cancel_new_game(self):
        self._show_screen('menu')

    def continue_game(self):
        if self.state != 'menu':
            return False
        available = self.save_manager.available()
        if not available:
            self.main_menu.subtitle_text.text = 'No valid save. Invalid files are preserved.'
            self.main_menu.refresh_saves()
            return False
        return self.load_game(available[0])

    def retry_checkpoint(self):
        if self.state != 'dead' or not self._valid_checkpoint():
            return False
        return self.load_game('checkpoint')

    def _valid_checkpoint(self):
        data = self.save_manager.load('checkpoint')
        return bool(data and data['session'] == getattr(self,'session_id',None))

    def _safe_to_save(self):
        if not self.scene_manager or self.state not in ('playing','paused'):
            return False
        p, ghost = self.scene_manager.player, self.scene_manager.ghost
        return (not self.hud.panel.active and not p.hidden and
                ghost.ai.state not in (GhostState.CHASE,GhostState.JUMPSCARE) and ghost.ai.detection < .2
                and (ghost.position-p.position).length() >= 3
                and not any(getattr(self.scene_manager.house,name).opening for name in self.scene_manager.house.level.doors))

    def save_game(self):
        if self.state!='paused' or not self._safe_to_save():
            self.pause_menu.subtitle_text.text = 'Cannot save during danger, hiding, interfaces, or door motion.'
            return False
        if wall_time.monotonic()-self._last_manual_save < settings.SAVE_COOLDOWN_SECONDS:
            self.pause_menu.subtitle_text.text = 'Please wait 10 seconds before saving again.'
            return False
        try:
            document = self.save_manager.capture(self.scene_manager, self.session_id)
            self.save_manager.save(document)
        except (OSError,ValueError) as error:
            self.pause_menu.subtitle_text.text = f'Save failed: {error}'
            logging.getLogger(__name__).warning('Manual save failed: %s',error)
            return False
        self._last_manual_save = wall_time.monotonic()
        self.pause_menu.subtitle_text.text = 'Game saved locally. Resume when ready.'
        self.main_menu.refresh_saves()
        return True

    def _checkpoints(self):
        if not self.automatic_checkpoints or not self._safe_to_save():
            return
        p = self.scene_manager.player
        completed = set()
        if p.progression.power_restored: completed.add('power')
        if p.progression.safe_unlocked: completed.add('lockbox')
        if p.inventory.has_key('exit_key'): completed.add('exit_key')
        pending = completed-self._checkpoint_recorded
        if not pending:
            return
        order = ['power','lockbox','exit_key']
        milestone = max(pending,key=order.index)
        existing = self.save_manager.load('checkpoint')
        if existing and existing['session']==self.session_id and order.index(existing['milestone'])>=order.index(milestone):
            self._checkpoint_recorded.update(completed)
            return
        house, ghost = self.scene_manager.house, self.scene_manager.ghost
        if (ghost.position-house.nav_nodes['foyer']).length()<settings.LOAD_GHOST_MIN_DISTANCE:
            return
        if not p.can_occupy(house.nav_nodes['foyer']):
            return
        try:
            data = self.save_manager.capture(self.scene_manager, self.session_id,'checkpoint',milestone)
            self.save_manager.save(data,'checkpoint')
        except (OSError,ValueError) as error:
            # Retry only after another milestone; avoid per-frame IO/log spam.
            self._checkpoint_recorded.update(completed)
            logging.getLogger(__name__).warning('Checkpoint failed: %s',error)
            self.hud.show_message('Checkpoint could not be saved. Manual Save remains available.')
            return
        self._checkpoint_recorded.update(completed)
        self.hud.show_message('Checkpoint saved. Retry restores this snapshot; resources are not refilled.')

    def load_game(self, slot='manual'):
        if self.state not in ('menu','paused','dead'):
            return False
        data = self.save_manager.load(slot)
        if data is None:
            self.screens[self.state].subtitle_text.text = 'Load failed. Save file preserved.'
            return False
        previous = self.scene_manager
        previous_camera = (camera.parent,Vec3(camera.world_position),Vec3(camera.world_rotation),camera.fov)
        old_hud = self.hud
        previous_entities = set(scene.entities)
        previous_lights = application.base.render.get_state().get_attrib(LightAttrib)
        previous_fog = scene.get_state().get_attrib(FogAttrib)
        new_hud = HUD()
        new_hud.enabled = False
        staged = None
        try:
            staged = SceneManager(new_hud,self.win_game,self.begin_jumpscare)
            self.save_manager.restore(staged,data)
        except Exception as error:
            camera.world_parent = scene
            if staged:
                staged.dispose()
            # Constructors can fail before returning an object. Remove every
            # new entity, including loose cursors/lights, without touching the
            # outgoing session; children precede their parents in Ursina 8.3.
            created = [entity for entity in scene.entities if entity not in previous_entities
                       and not entity.eternal and not entity.is_empty()]
            for entity in sorted(created,key=lambda entity:entity.get_num_nodes(),reverse=True):
                if not entity.is_empty():
                    destroy_temporary(entity)
            if previous_lights is None:
                application.base.render.clear_light()
            else:
                application.base.render.set_attrib(previous_lights)
            scene.clear_fog()
            if previous_fog is not None:
                scene.set_attrib(previous_fog)
            camera.parent = previous_camera[0]
            camera.world_position, camera.world_rotation, camera.fov = previous_camera[1:]
            self._sync_pause()
            self.screens[self.state].subtitle_text.text = 'Load failed validation; previous session preserved.'
            logging.getLogger(__name__).warning('Load staging failed: %s',error)
            return False
        if previous:
            previous.dispose()
        # Outgoing player cleanup detaches the eternal camera. Reattach only
        # after it has finished, retaining the newly restored local view.
        camera.parent = staged.player.camera_pivot
        camera.position = Vec3(0,0,0)
        camera.rotation = Vec3(*data['player']['camera_rotation'])
        destroy_temporary(old_hud)
        self.hud, self.scene_manager = new_hud, staged
        self.session_id = data['session']
        self.session_preferences = self.preferences.values.copy()
        self._checkpoint_recorded = {'power'} if staged.player.progression.power_restored else set()
        if staged.player.progression.safe_unlocked: self._checkpoint_recorded.add('lockbox')
        if staged.player.inventory.has_key('exit_key'): self._checkpoint_recorded.add('exit_key')
        self._submenu_stack.clear()
        self._configure_session()
        self._show_screen('playing')
        staged.player._set_flashlight_light(staged.player.flashlight_on)
        self.hud.show_message('Progress restored. The ghost patrols elsewhere; 5 seconds of safety.')
        self.hud.message_sequence.pause()
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
        self.session_id = uuid4().hex
        self._checkpoint_recorded.clear()
        self._submenu_stack.clear()
        self._last_manual_save = -1000
        self._configure_session()
        self._show_screen("playing")
        self.hud.show_message("Find the flashlight. Read the living-room note; Tab opens inventory. Esc pauses.", seconds=4)
        self.hud.message_sequence.pause()

    def _configure_session(self):
        values = self.preferences.values
        self.session_preferences = values.copy()
        light = self.scene_manager.player.flashlight_light._light
        resolution = 1024 if values["shadow_quality"] == "high" else 512
        light.set_shadow_caster(values["shadow_quality"] != "off", resolution, resolution)
        ai = self.scene_manager.ghost.ai
        ai.speed_multiplier, ai.detection_multiplier = settings.GHOST_DIFFICULTY[values["ghost_difficulty"]]
        self.apply_live_preferences()

    def restart_game(self):
        if self.scene_manager is not None:
            self._create_session()

    def pause_game(self):
        if self.state != "playing" or self.hud.panel.active:
            return False
        self.pause_menu.selected = 0
        self.pause_menu.subtitle_text.text = 'The house waits. Escape resumes.'
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
        self._submenu_stack.clear()
        self.main_menu.refresh_saves()
        self.main_menu.refresh_selection()
        self._show_screen("menu")

    def open_settings(self):
        if self.state not in ("menu", "paused"):
            return
        self._submenu_parent = self.state
        self._submenu_stack.append(self.state)
        self._show_screen("settings")
        self.settings_menu.open()

    def open_controls(self):
        if self.state in ('menu','settings'):
            self._submenu_parent = self.state
            self._submenu_stack.append(self.state)
            self.controls_screen.waiting = None
            self.controls_screen.refresh_bindings()
            self._show_screen("controls")

    def close_submenu(self):
        if self.state in ("settings", "controls"):
            self._show_screen(self._submenu_stack.pop() if self._submenu_stack else 'menu')

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
        values = self.preferences.values
        self.hud.text_scale = values['text_scale']
        self.hud.bindings = values['bindings'].copy()
        for screen in set(self.screens.values()):
            screen.text_scale = values['text_scale']
            screen.resize(camera.aspect_ratio)
        self.hud.layout(camera.aspect_ratio)
        if self.hud.panel.active:
            self.hud.panel.refresh()
        if self.scene_manager is None:
            return
        player = self.scene_manager.player
        player.bindings = values['bindings'].copy()
        player.reduced_flicker = values['reduced_flicker']
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
        player.progression.refresh()
        player.hud.refresh_inventory(player)

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
                self._checkpoints()
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
        self.end_screen.configure_checkpoint(self._valid_checkpoint())

    def win_game(self):
        if self.state != "playing":
            return
        self.scene_manager.stop_gameplay()
        self._show_screen("escaped")
        self.end_screen.show("YOU ESCAPED", "You made it out of the house.\nR: restart   Escape: main menu")
        self.end_screen.configure_checkpoint(False)
