"""Asset-free menu panels; one manager routes mouse and keyboard input."""
from ursina import Entity, Text, camera, color, mouse
from game.settings import PREFERENCE_CHOICES, NEXT_GAME_SETTINGS, BINDING_DEFAULTS, validate_bindings

PANEL_COLOR = color.rgb32(9, 12, 17)
ROW_COLOR = color.rgb32(24, 30, 37)
SELECTED_COLOR = color.rgb32(52, 69, 77)
TEXT_COLOR = color.rgb32(230, 233, 230)
ACCENT_COLOR = color.rgb32(161, 189, 190)


class MenuScreen(Entity):
    def __init__(self, title, options, subtitle="", row_y=.12, row_step=.09, visible_count=6):
        super().__init__(parent=camera.ui, enabled=False, ignore_paused=True, z=-.5)
        self.background = Entity(parent=self, model="quad", scale=(camera.aspect_ratio, 1),
                                 color=PANEL_COLOR, z=.1)
        self.content = Entity(parent=self)
        self.title_text = Text(parent=self.content, text=title, origin=(0, 0),
                               y=.35, scale=1.8, color=TEXT_COLOR)
        self.subtitle_text = Text(parent=self.content, text=subtitle, origin=(0, 0),
                                  y=.25, scale=.85, color=ACCENT_COLOR)
        if subtitle:
            self.subtitle_text.wordwrap = 50
        self.footer = Text(parent=self.content, text="Up/Down: select   Enter: confirm   Mouse: click",
                           origin=(0, 0), y=-.42, scale=.75, color=ACCENT_COLOR)
        self.rows = []
        self.actions = []
        self.disabled_rows = set()
        self.visible_count, self.row_y, self.row_step = visible_count, row_y, row_step
        self.text_scale = 1.0
        self.selected = 0
        for index, (label, action) in enumerate(options):
            row = Entity(parent=self.content, model="quad", collider="box", color=ROW_COLOR,
                         scale=(.86, .067), y=row_y-index*row_step)
            text = Text(parent=self.content, text=label, origin=(0, 0),
                        y=row.y, z=-.01, scale=1, color=TEXT_COLOR)
            self.rows.append((row, text))
            self.actions.append(action)
        self.refresh_selection()
        self.resize(camera.aspect_ratio)

    def resize(self, aspect):
        self.background.scale = (aspect, 1)
        self.content.scale = min(1, (aspect-.1)/1.14)
        for text, default in ((self.title_text,1.8),(self.subtitle_text,.85),(self.footer,.75)):
            text.scale = getattr(text,'base_font',default)*self.text_scale
        for _, text in self.rows:
            text.scale = getattr(text,'base_font',1)*self.text_scale
        if hasattr(self,'status'):
            self.status.scale = .72*self.text_scale

    def refresh_selection(self):
        for index, (row, text) in enumerate(self.rows):
            visible = index//self.visible_count == self.selected//self.visible_count
            row.enabled = text.enabled = visible
            row.y = text.y = self.row_y-(index%self.visible_count)*self.row_step
            row.color = SELECTED_COLOR if index == self.selected else ROW_COLOR
            text.color = color.rgb32(110,117,119) if index in self.disabled_rows else TEXT_COLOR

    def handle(self, key):
        if not self.rows:
            return
        if key in ("up arrow", "down arrow", "tab", "page up", "page down"):
            direction = -1 if key in ('up arrow','page up') else 1
            step = self.visible_count if key in ('page up','page down') else 1
            self.selected = (self.selected+direction*step) % len(self.rows)
            for _ in self.rows:
                if self.selected not in self.disabled_rows:
                    break
                self.selected = (self.selected+direction) % len(self.rows)
            self.refresh_selection()
        elif key == "enter":
            if self.selected not in self.disabled_rows:
                self.actions[self.selected]()
        elif key == "left mouse down":
            for index, (row, _) in enumerate(self.rows):
                if mouse.hovered_entity == row and row.enabled and index not in self.disabled_rows:
                    self.selected = index
                    self.refresh_selection()
                    self.actions[index]()
                    break


class MainMenu(MenuScreen):
    def __init__(self, manager):
        self.manager = manager
        super().__init__("SINISTER SECRETS", [
            ("New Game", manager.start_game), ("Continue Game", manager.continue_game), ("Settings", manager.open_settings),
            ("Controls", manager.open_controls), ("Quit Game", manager.quit_game)],
            "A haunted house. A way out. Something listening.")

    def refresh_saves(self):
        available = self.manager.save_manager.available()
        self.disabled_rows = set() if available else {1}
        self.rows[1][1].text = 'Continue Game' if available and available[0]=='manual' else 'Continue (checkpoint)' if available else 'Continue (no valid save)'
        self.refresh_selection()


class ControlsScreen(MenuScreen):
    def __init__(self, manager):
        self.manager, self.waiting = manager, None
        self.actions_order = list(BINDING_DEFAULTS)
        options = [(action,lambda i=i:self.capture_binding(i)) for i, action in enumerate(self.actions_order)]
        options += [('Reset to Defaults',self.reset_defaults),('Back',manager.close_submenu)]
        super().__init__('CONTROLS / REBIND',options,'Mouse: look   Select an action to change its key',
                         row_y=.21,row_step=.057,visible_count=8)
        self.title_text.base_font = 1.5
        self.subtitle_text.base_font = .7
        self.subtitle_text.y = .3
        self.footer.base_font = .65
        self.footer.text = 'Up/Down: select   PgUp/PgDn: pages   Enter/click: rebind\nEscape: cancel/back (always available)   R: terminal restart\nInventory: arrows/Enter; combination: digits/Backspace/Enter'
        self.status = Text(parent=self.content, origin=(0,0),y=-.31,scale=.72,color=ACCENT_COLOR)
        for row, _ in self.rows:
            row.scale_y = .042
        self.refresh_bindings()

    def refresh_bindings(self):
        for index,action in enumerate(self.actions_order):
            self.rows[index][1].text = f"{action.replace('_',' ').title()}: {self.manager.preferences.values['bindings'][action].upper()}"
        self.refresh_selection()

    def capture_binding(self,index):
        self.waiting = self.actions_order[index]
        self.status.text = 'Press a supported key. Escape cancels.'

    def apply_binding(self,values):
        try:
            proposed = dict(self.manager.preferences.values,bindings=validate_bindings(values))
            self.manager.preferences.save(proposed)
        except (OSError,ValueError) as error:
            self.status.text = str(error)[:75]
            return False
        self.manager.apply_live_preferences()
        self.manager.settings_menu.draft['bindings'] = values.copy()
        self.status.text = 'Controls saved.'
        self.waiting = None
        self.refresh_bindings()
        return True

    def reset_defaults(self):
        self.apply_binding(BINDING_DEFAULTS.copy())

    def handle(self,key):
        if self.waiting:
            if key == 'escape':
                self.waiting = None
                self.status.text = 'Rebind cancelled.'
            elif not key.endswith((' up',' hold')):
                values = self.manager.preferences.values['bindings'].copy()
                values[self.waiting] = key
                self.apply_binding(values)
        else:
            super().handle(key)


class SettingsMenu(MenuScreen):
    LABELS = ("Mouse sensitivity", "Visibility brightness", "Flashlight shadows *",
              "Horror frequency", "Reduced flicker (horror/torch)", "Reduced camera shake",
              "Jumpscare intensity", "Ghost difficulty *", "FPS cap", "UI text size")

    def __init__(self, manager):
        self.manager = manager
        self.keys = list(PREFERENCE_CHOICES)
        self.draft = manager.preferences.values.copy()
        options = [(label, lambda i=i: self.adjust(i, 1)) for i, label in enumerate(self.LABELS)]
        options += [("Rebind Controls", manager.open_controls),("Apply and Back", manager.apply_settings), ("Cancel", manager.close_submenu)]
        super().__init__("SETTINGS", options, "* Next new game   PgUp/PgDn: pages", row_y=.24, row_step=.057, visible_count=9)
        self.title_text.y = .4
        self.title_text.scale = 1.5
        self.title_text.base_font = 1.5
        self.subtitle_text.y = .335
        self.subtitle_text.scale = .76
        self.subtitle_text.base_font = .76
        self.footer.text = "Up/Down: select   Left/Right: adjust   Enter/click: change\nEscape: cancel   Apply saves local preferences"
        self.footer.y = -.405
        self.footer.scale = .7
        self.footer.base_font = .6
        self.status = Text(parent=self.content, text="", origin=(0, 0), y=-.31, scale=.72, color=ACCENT_COLOR)
        for row, text in self.rows:
            row.scale = (1.06, .042)
            text.scale = .84
            text.base_font = .84
        self.refresh_values()

    def open(self):
        self.draft = self.manager.preferences.values.copy()
        self.status.text = self.manager.preferences.error
        if (not self.status.text and self.manager.scene_manager and
                any(self.draft[key] != self.manager.session_preferences[key] for key in NEXT_GAME_SETTINGS)):
            self.status.text = "Saved shadow/difficulty changes await a new game."
        self.selected = 0
        self.refresh_values()
        self.enabled = True

    def refresh_values(self):
        for index, key in enumerate(self.keys):
            value = self.draft[key]
            if type(value) is bool:
                value = "On" if value else "Off"
            elif key == "fps_cap" and value == 0:
                value = "Unlimited"
            elif key == 'text_scale':
                value = f'{int(value*100)}%'
            elif key == "shadow_quality":
                value = {"off": "Off (light leaks)", "low": "Low / 512", "high": "High / 1024"}[value]
            self.rows[index][1].text = f"{self.LABELS[index]}:  {value}"
        self.refresh_selection()

    def adjust(self, index, direction):
        if index >= len(self.keys):
            return
        key = self.keys[index]
        choices = PREFERENCE_CHOICES[key]
        current = self.draft[key]
        nearest = min(range(len(choices)), key=lambda i: abs(choices[i]-current)) if type(current) in (int, float) else choices.index(current)
        self.draft[key] = choices[(nearest+direction) % len(choices)]
        self.status.text = "Unsaved changes"
        self.refresh_values()

    def handle(self, key):
        if key in ("left arrow", "right arrow"):
            self.adjust(self.selected, -1 if key == "left arrow" else 1)
        else:
            super().handle(key)
