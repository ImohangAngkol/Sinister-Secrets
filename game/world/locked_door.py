from game.world.door import Door


class LockedDoor(Door):
    def __init__(
        self,
        required_key: str,
        locked_message=(
            "This door is locked."
        ),
        **kwargs,
    ):
        self.required_key = required_key
        self.locked_message = (
            locked_message
        )

        super().__init__(**kwargs)

    def interact(self, player):
        if self.opened:
            return

        if not player.inventory.has_key(
            self.required_key
        ):
            player.hud.show_message(
                self.locked_message
            )
            return

        player.hud.show_message(
            "The door unlocked."
        )

        self.open()
