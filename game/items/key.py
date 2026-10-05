from ursina import color, destroy

from game.items.item import Item


class KeyPickup(Item):
    def __init__(
        self,
        key_id: str,
        key_name: str,
        **kwargs,
    ):
        self.key_id = key_id
        self.key_name = key_name

        self.interaction_text = (
            f"[E] Pick up {key_name}"
        )

        super().__init__(
            model="cube",
            color=color.yellow,
            scale=(0.25, 0.12, 0.45),
            collider="box",
            **kwargs,
        )

    def interact(self, player):
        player.inventory.add_key(
            self.key_id
        )

        player.hud.refresh_inventory(
            player
        )

        player.hud.show_message(
            f"Picked up: {self.key_name}"
        )

        destroy(self)
