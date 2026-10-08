
from ursina import Entity, Text, camera, color, invoke
from game.ui.interaction_prompt import InteractionPrompt
from game.ui.inventory_ui import InventoryUI


class HUD(Entity):
    def __init__(self):
        super().__init__(
            parent=camera.ui
        )

        self.interaction_prompt = (
            InteractionPrompt()
        )

        self.inventory_ui = (
            InventoryUI()
        )

        self.message = Text(
            parent=camera.ui,
            text="",
            origin=(0, 0),
            y=0.28,
            scale=1.15,
        )
        self.message_revision = 0
        self.message_sequence = None
        self._aspect = camera.aspect_ratio

        # Keep this while developing the AI.
        self.ghost_state = Text(
            parent=camera.ui,
            text="Ghost: PATROL",
            x=camera.aspect_ratio / 2 - 0.03,
            y=0.46,
            origin=(0.5, 0.5),
            scale=0.82,
            color=color.white,
        )
        self.ghost_state.create_background(padding=0.025, color=color.black66)
        for element in (self.interaction_prompt, self.inventory_ui, self.message, self.ghost_state):
            element.parent = self
        self.interaction_prompt.enabled = False

    def layout(self, aspect):
        self._aspect = aspect
        self.inventory_ui.x = -aspect / 2 + 0.03
        self.ghost_state.x = aspect / 2 - 0.03
        self.message.scale = min(1.15, (aspect - 0.08) / max(self.message.width, 0.001))

    def on_destroy(self):
        if self.message_sequence:
            self.message_sequence.kill()

    def set_prompt(self, text: str):
        if text:
            self.interaction_prompt.show(
                text
            )
        else:
            self.interaction_prompt.clear()

    def show_message(
        self,
        text: str,
        seconds: float = 2.0,
    ):
        self.message.text = text
        self.layout(self._aspect)
        self.message.enabled = True
        self.message.create_background(padding=0.025, color=color.black66)
        self.message_revision += 1

        if self.message_sequence:
            self.message_sequence.kill()
        self.message_sequence = invoke(
            self._clear_message_if_same,
            self.message_revision,
            delay=seconds,
        )

    def _clear_message_if_same(
        self,
        expected: int,
    ):
        if self.message_revision == expected:
            self.message.text = ""
            self.message.enabled = False

    def set_ghost_state(
        self,
        state_name: str,
    ):
        self.ghost_state.text = (
            f"Ghost: {state_name}"
        )
        self.ghost_state.create_background(padding=0.025, color=color.black66)

    def refresh_inventory(
        self,
        player,
    ):
        self.inventory_ui.refresh(
            player
        )
