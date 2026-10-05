
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

        # Keep this while developing the AI.
        self.ghost_state = Text(
            parent=camera.ui,
            text="Ghost: PATROL",
            x=0.62,
            y=0.46,
            origin=(-0.5, 0.5),
            scale=0.82,
            color=color.white,
        )

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

        invoke(
            self._clear_message_if_same,
            text,
            delay=seconds,
        )

    def _clear_message_if_same(
        self,
        expected: str,
    ):
        if self.message.text == expected:
            self.message.text = ""

    def set_ghost_state(
        self,
        state_name: str,
    ):
        self.ghost_state.text = (
            f"Ghost: {state_name}"
        )

    def refresh_inventory(
        self,
        player,
    ):
        self.inventory_ui.refresh(
            player
        )
