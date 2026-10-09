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
        if not player.inventory.add_key(self.key_id):
            player.hud.show_message("You already have this key.")
            return
        if player.progression:
            player.progression.refresh()

        player.hud.refresh_inventory(
            player
        )

        player.hud.show_message(
            f"Picked up: {self.key_name}"
        )

        destroy(self)
