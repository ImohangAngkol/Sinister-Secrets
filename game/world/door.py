from ursina import Entity, color


class Door(Entity):
    interaction_text = "[E] Open door"

    def __init__(self, **kwargs):
        self.opened = False

        super().__init__(
            model="cube",
            color=color.rgb(
                85,
                55,
                35,
            ),
            collider="box",
            origin_x=-0.5,
            origin_y=-0.5,
            **kwargs,
        )

    def interact(self, player):
        self.open()

    def open(self):
        if self.opened:
            return

        self.opened = True

        # Stop blocking player/raycast.
        self.collider = None

        self.animate_rotation_y(
            self.rotation_y + 100,
            duration=0.8,
        )
