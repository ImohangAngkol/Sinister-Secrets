"""Asset-free menu panels; one manager routes mouse and keyboard input."""
from ursina import Entity, Text, camera, color, mouse
from game.settings import PREFERENCE_CHOICES, NEXT_GAME_SETTINGS

PANEL_COLOR = color.rgb32(9, 12, 17)
ROW_COLOR = color.rgb32(24, 30, 37)
SELECTED_COLOR = color.rgb32(52, 69, 77)
TEXT_COLOR = color.rgb32(230, 233, 230)
ACCENT_COLOR = color.rgb32(161, 189, 190)


class MenuScreen(Entity):
    def __init__(self, title, options, subtitle="", row_y=.12, row_step=.09):
        super().__init__(parent=camera.ui, enabled=False, ignore_paused=True, z=-.5)
        self.background = Entity(parent=self, model="quad", scale=(camera.aspect_ratio, 1),
                                 color=PANEL_COLOR, z=.1)
        self.content = Entity(parent=self)
        self.title_text = Text(parent=self.content, text=title, origin=(0, 0),
                               y=.35, scale=1.8, color=TEXT_COLOR)
        self.subtitle_text = Text(parent=self.content, text=subtitle, origin=(0, 0),
                                  y=.25, scale=.85, color=ACCENT_COLOR)
        self.footer = Text(parent=self.content, text="Up/Down: select   Enter: confirm   Mouse: click",
                           origin=(0, 0), y=-.42, scale=.75, color=ACCENT_COLOR)
        self.rows = []
        self.actions = []
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

    def refresh_selection(self):
        for index, (row, text) in enumerate(self.rows):
            row.color = SELECTED_COLOR if index == self.selected else ROW_COLOR
            text.color = TEXT_COLOR

    def handle(self, key):
        if not self.rows:
            return
        if key in ("up arrow", "down arrow", "tab"):
            self.selected = (self.selected + (-1 if key == "up arrow" else 1)) % len(self.rows)
            self.refresh_selection()
        elif key == "enter":
            self.actions[self.selected]()
        elif key == "left mouse down":
            for index, (row, _) in enumerate(self.rows):
                if mouse.hovered_entity == row:
                    self.selected = index
                    self.refresh_selection()
                    self.actions[index]()
                    break


class MainMenu(MenuScreen):
    def __init__(self, manager):
        super().__init__("SINISTER SECRETS", [
            ("Start Game", manager.start_game), ("Settings", manager.open_settings),
            ("Controls", manager.open_controls), ("Quit Game", manager.quit_game)],
            "A haunted house. A way out. Something listening.")


class ControlsScreen(MenuScreen):
    def __init__(self, manager):
        super().__init__("CONTROLS", [("Back", manager.close_submenu)], row_y=-.33)
        self.subtitle_text.text = ""
        Text(parent=self.content, origin=(-.5, .5), x=-.5, y=.26, scale=.9,
             color=TEXT_COLOR, text=(
                 "WASD                 Move\nMouse                Look\nShift                  Sprint\n"
                 "Ctrl                    Crouch\nE                       Interact / hide / leave hiding\n"
                 "F                       Flashlight\nTab                    Inventory\n"
                 "Up / Down           Select inventory item\nEnter                  Inspect / read / confirm\n"
                 "U                       Use selected battery (then Enter)\n"
                 "0-9 / Backspace   Combination digits / erase\n"
                 "Escape               Pause / close active interface\n"
                 "R                       Restart after loss / victory / catch"))


class SettingsMenu(MenuScreen):
    LABELS = ("Mouse sensitivity", "Visibility brightness", "Flashlight shadows *",
              "Horror frequency", "Reduced horror flicker", "Reduced camera shake",
              "Jumpscare intensity", "Ghost difficulty *", "FPS cap")

    def __init__(self, manager):
        self.manager = manager
        self.keys = list(PREFERENCE_CHOICES)
        self.draft = manager.preferences.values.copy()
        options = [(label, lambda i=i: self.adjust(i, 1)) for i, label in enumerate(self.LABELS)]
        options += [("Apply and Back", manager.apply_settings), ("Cancel", manager.close_submenu)]
        super().__init__("SETTINGS", options, "* Applies to the next new game", row_y=.24, row_step=.047)
        self.title_text.y = .4
        self.title_text.scale = 1.5
        self.subtitle_text.y = .335
        self.subtitle_text.scale = .76
        self.footer.text = "Up/Down: select   Left/Right: adjust   Enter/click: change\nEscape: cancel   Apply saves local preferences"
        self.footer.y = -.405
        self.footer.scale = .7
        self.status = Text(parent=self.content, text="", origin=(0, 0), y=-.31, scale=.72, color=ACCENT_COLOR)
        for row, text in self.rows:
            row.scale = (1.06, .042)
            text.scale = .84
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
