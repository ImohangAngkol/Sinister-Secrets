from ursina import Entity


class Item(Entity):
    interaction_text = "[E] Pick up item"

    def interact(self, player):
        raise NotImplementedError(
            "Item subclasses must implement interact()."
        )
