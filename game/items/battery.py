from ursina import color, destroy

from game.items.item import Item


class BatteryPickup(Item):
    interaction_text = "[E] Pick up battery"

    def __init__(
        self,
        amount=35,
        **kwargs,
    ):
        self.amount = amount

        super().__init__(
            model="cube",
            color=color.azure,
            scale=(0.22, 0.35, 0.18),
            collider="box",
            **kwargs,
        )

    def interact(self, player):
        used = player.add_battery(
            self.amount
        )

        if used:
            destroy(self)
