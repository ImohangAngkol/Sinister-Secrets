from ursina import Entity


class Item(Entity):
    interaction_text = "[E] Pick up item"

    def __init__(self, **kwargs):
        super().__init__(shader=None, **kwargs)

    def interact(self, player):
        raise NotImplementedError(
            "Item subclasses must implement interact()."
        )
