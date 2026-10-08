from ursina import Vec3

from game.world.locked_door import LockedDoor


class ExitDoor(LockedDoor):
    interaction_text = "[E] Unlock exit door"

    def __init__(
        self,
        on_escape=None,
        **kwargs,
    ):
        self.on_escape = on_escape
        self.escape_player = None
        self.escape_triggered = False
        super().__init__(**kwargs)
        # Save the doorway plane before the hinged door rotates.
        self.exit_position = Vec3(self.world_position)
        self.exit_forward = Vec3(self.forward).normalized()
        self.exit_right = Vec3(self.right).normalized()
        self.exit_width = self.world_scale_x

    def interact(self, player):
        super().interact(player)
        if self.opened:
            self.escape_player = player
            player.hud.show_message("Exit unlocked. Walk through the doorway to escape.")

    def update(self):
        if not self.opened or self.escape_player is None or self.escape_triggered:
            return
        player = self.escape_player
        if not player.enabled:
            return
        offset = player.world_position - self.exit_position
        across = offset.dot(self.exit_right)
        if (0.2 <= across <= self.exit_width - 0.2
                and offset.dot(self.exit_forward) > 0.4
                and abs(offset.y) < 1):
            self.escape_triggered = True
            if self.on_escape:
                self.on_escape()
