import textwrap
from ursina import Entity, Text, Vec3, camera, color, held_keys, mouse


class InventoryUI(Text):

    def __init__(self):

        super().__init__(
            parent=camera.ui,

            text=(
                "Flashlight: NOT FOUND\n"
                "Keys: 0"
            ),

            x=-camera.aspect_ratio / 2 + 0.03,
            y=0.46,

            origin=(-0.5, 0.5),

            scale=1.05,

            color=color.white,
        )
        self.create_background(padding=0.025, color=color.black66)

    def refresh(
        self,
        player,
    ):

        if player.has_flashlight:

            flashlight_text = (
                f"Flashlight: "
                f"{int(player.stats.battery)}% "
                f"({'ON' if player.flashlight_on else 'OFF'})"
            )

        else:

            flashlight_text = (
                "Flashlight: NOT FOUND"
            )

        text = (
            f"{flashlight_text}\n"
            f"Keys: "
            f"{player.inventory.key_count()}"
            f" | Batteries: {player.inventory.count('battery')} | Tab: inventory"
            f"\nStamina: {int(player.stats.stamina)}%"
            f"{' (exhausted)' if player.stats.sprint_exhausted else ''}"
            f"{'\nHidden: E to leave' if player.hidden else '\nCrouching' if player.crouching else ''}"
        )
        if self.text != text:
            self.text = text
            self.create_background(padding=0.025, color=color.black66)


class GameplayPanel(Entity):
    """Keyboard-only modal. Simulation stays active; pointer stays captured."""
    def __init__(self, parent):
        super().__init__(parent=parent, enabled=False)
        self.mode = None
        self.player = None
        self.selected = 0
        self.confirming = False
        self.digits = ""
        self.status = ""
        Entity(parent=self, model="quad", scale=(1.18, .82), color=color.rgba32(9, 12, 17, 246), z=.01)
        self.title = Text(parent=self, origin=(-.5,.5), x=-.53, y=.34, scale=1.2)
        self.body = Text(parent=self, origin=(-.5,.5), x=-.53, y=.23, scale=.95)
        self.detail = Text(parent=self, origin=(-.5,.5), x=-.53, y=-.04, scale=.88)
        self.footer = Text(parent=self, origin=(-.5,.5), x=-.53, y=-.32, scale=.82)

    @property
    def active(self):
        return self.mode is not None

    def layout(self, aspect):
        self.scale = min(1, (aspect - .06) / 1.18)

    def _open(self, player, mode):
        if hasattr(player,'horror'):
            player.horror.cancel_active()
        self.player, self.mode = player, mode
        self.enabled = True
        self.confirming = False
        self.status = ""
        held_keys.clear()
        mouse.velocity = Vec3(0, 0, 0)
        player.cursor.enabled = False
        player.hud.set_prompt("")
        self.layout(camera.aspect_ratio)

    def open_inventory(self, player):
        self._open(player, "inventory")
        self.selected = 0
        self.refresh()

    def open_note(self, player, item_id):
        self._open(player, "note")
        self.note_id = item_id
        self.refresh()

    def open_combination(self, player, prop):
        self._open(player, "combination")
        self.prop = prop
        self.digits = ""
        self.refresh()

    def close(self):
        if not self.active:
            return
        self.mode = None
        self.enabled = False
        self.confirming = False
        held_keys.clear()
        mouse.velocity = Vec3(0, 0, 0)
        if self.player and self.player.enabled:
            self.player.cursor.enabled = True
        self.player = None

    def item_ids(self):
        return list(self.player.inventory.quantities)

    @staticmethod
    def wrap(text):
        return "\n".join(textwrap.fill(line, width=55) for line in text.split("\n"))

    def refresh(self):
        inventory = self.player.inventory
        if self.mode == "inventory":
            ids = self.item_ids()
            self.selected = min(self.selected, max(0, len(ids)-1))
            self.title.text = "INVENTORY"
            start = self.selected // 5 * 5
            self.body.text = "\n".join(
                f"{'>' if i == self.selected else ' '} {inventory.definitions.get(item, {}).get('name', item)}  x{inventory.count(item)}"
                for i, item in enumerate(ids[start:start+5], start)) or "No items collected."
            definition = inventory.definitions.get(ids[self.selected], {}) if ids else {}
            self.detail.text = self.wrap(self.status or definition.get("description", "Explore to collect useful items."))
            self.footer.text = ("Enter: confirm battery | Backspace: cancel | Esc/Tab: close" if self.confirming else
                                "Up/Down: select | Enter: inspect/read | U: use battery\nEsc/Tab: close | The ghost and flashlight remain active.")
        elif self.mode == "note":
            definition = inventory.definitions[self.note_id]
            self.title.text = definition["name"]
            self.body.text = self.wrap(definition["text"])
            self.detail.text = ""
            self.footer.text = "Esc/Tab: close | Note kept in inventory. Gameplay continues."
        else:
            self.title.text = "DINING LOCKBOX"
            self.body.text = f"Four wheels:  {self.digits.ljust(4, '_')}\n\n" + self.wrap(self.status or "The keeper's instructions and kitchen tally explain the order.")
            self.detail.text = ""
            self.footer.text = "0-9: enter digits | Backspace: erase | Enter: submit\nEsc/Tab: close | Gameplay continues."

    def handle(self, key):
        if key in ("escape", "tab"):
            self.close()
            return
        if self.mode == "combination":
            if key.isdigit() and len(key) == 1 and len(self.digits) < 4:
                self.digits += key
            elif key == "backspace":
                self.digits = self.digits[:-1]
            elif key == "enter":
                if len(self.digits) != 4:
                    self.status = "Enter all four digits."
                elif (self.player.world_position - self.prop.world_position).length() > 2.5:
                    self.status = "Move back to the lockbox."
                elif self.player.progression.try_combination(self.digits):
                    self.close()
                    return
                else:
                    self.status = "Incorrect combination. Read the clues and try again."
                    self.digits = ""
        elif self.mode == "inventory":
            ids = self.item_ids()
            if ids:
                item_id = ids[self.selected]
                if key in ("up arrow", "down arrow"):
                    self.selected = (self.selected + (1 if key == "down arrow" else -1)) % len(ids)
                    self.confirming = False
                    self.status = ""
                elif key == "backspace":
                    self.confirming = False
                    self.status = ""
                elif key == "u" and item_id == "battery":
                    self.confirming = True
                    self.status = "Use one battery? Enter confirms; Backspace cancels."
                elif key == "enter":
                    if self.confirming and item_id == "battery":
                        if not self.player.has_flashlight:
                            self.status = "Collect a flashlight first. Battery kept."
                        elif self.player.add_battery(self.player.inventory.definitions['battery']['restore']):
                            self.player.inventory.consume("battery")
                            self.player.hud.refresh_inventory(self.player)
                            self.status = f"Battery used: {int(self.player.stats.battery)}% charge."
                        else:
                            self.status = "Flashlight already full. Battery kept."
                        self.confirming = False
                    elif self.player.inventory.definitions.get(item_id, {}).get("type") == "note":
                        self.open_note(self.player, item_id)
                        return
                    else:
                        definition = self.player.inventory.definitions.get(item_id, {})
                        self.status = f"Inspecting {definition.get('name',item_id)}\n{definition.get('description','')}"
        self.refresh()
