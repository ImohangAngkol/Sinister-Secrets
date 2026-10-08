from ursina import Entity, color, destroy, time


class Door(Entity):
    interaction_text = "[E] Open door"

    def __init__(self, **kwargs):
        self.opened = False
        self.opening = False
        self.opening_time = 0.0
        self.opening_duration = 0.8
        self.doorway_blocker = None

        super().__init__(
            model="cube",
            shader=None,
            color=color.rgb32(
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
        if self.opened or self.opening:
            return

        self.opening = True
        self.closed_rotation_y = self.rotation_y
        # The panel collider rotates with the visual. A fixed doorway collider
        # prevents early passage through the gap until the full animation ends.
        self.doorway_blocker = Entity(
            parent=self.parent, model="cube", shader=None, visible=False,
            position=self.position, rotation=self.rotation, scale=self.scale,
            origin=self.origin, collider="box",
        )

    def update(self):
        if not self.opening:
            return
        self.opening_time = min(self.opening_duration, self.opening_time + max(time.dt, 0))
        progress = self.opening_time / self.opening_duration
        self.rotation_y = self.closed_rotation_y + 100 * progress
        if self.opening_time >= self.opening_duration - 1e-9:
            self.opening = False
            self.opened = True
            self.collider = None
            destroy(self.doorway_blocker)
            self.doorway_blocker = None
