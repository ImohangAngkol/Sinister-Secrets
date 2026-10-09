from ursina import Entity, color, destroy


class Item(Entity):
    interaction_text = "[E] Pick up item"

    def __init__(self, **kwargs):
        super().__init__(shader=None, **kwargs)

    def interact(self, player):
        raise NotImplementedError(
            "Item subclasses must implement interact()."
        )


class InventoryPickup(Item):
    """Data-authored puzzle items and notes, using lit placeholder cubes."""
    def __init__(self, item_id, definition, **kwargs):
        self.item_id, self.definition = item_id, definition
        self.interaction_text = f"[E] Collect {definition['name']}"
        super().__init__(model="cube", collider="box", scale=definition.get("scale", (.3, .15, .4)),
                         color=color.rgb32(*definition.get("color", [150, 120, 70])), **kwargs)

    def interact(self, player):
        if not player.inventory.add(self.item_id):
            player.hud.show_message("You already have this unique item.")
            return False
        player.hud.show_message(f"Collected: {self.definition['name']}")
        player.progression.refresh()
        player.hud.refresh_inventory(player)
        destroy(self)
        if self.definition["type"] == "note":
            player.hud.panel.open_note(player, self.item_id)
        return True
