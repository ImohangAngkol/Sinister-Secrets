from ursina import invoke

from game.world.locked_door import LockedDoor


class ExitDoor(LockedDoor):
    interaction_text = "[E] Open exit door"

    def __init__(
        self,
        on_escape=None,
        **kwargs,
    ):
        self.on_escape = on_escape
        super().__init__(**kwargs)

    def interact(self, player):
        was_open = self.opened

        super().interact(player)

        if (
            not was_open
            and self.opened
            and self.on_escape
        ):
            invoke(
                self.on_escape,
                delay=1.0,
            )
