from ursina import color, destroy

from game.items.item import Item


class FlashlightPickup(Item):
    interaction_text = "[E] Pick up flashlight"

    def __init__(self, **kwargs):
        super().__init__(
            model="cube",
            color=color.white,
            scale=(0.22, 0.22, 0.55),
            collider="box",
            **kwargs,
        )

    def interact(self, player):
        player.obtain_flashlight()
        destroy(self)
