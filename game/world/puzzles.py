"""Lit geometric interactions on existing furniture, never across corridors."""
from ursina import Entity, color


class PuzzleProp(Entity):
    def __init__(self, definition, **kwargs):
        self.puzzle_id = definition["id"]
        self.powered_color = color.rgb32(62, 115, 78)
        super().__init__(model="cube", shader=None, collider="box",
                         position=definition["position"], scale=definition["scale"],
                         color=color.rgb32(*definition["color"]), **kwargs)
        self.interaction_text = definition["prompt"]
        if self.puzzle_id == "boards":
            for y in (-.3, .3):
                Entity(parent=self, shader=None, model="cube", scale=(1, .18, 1.1),
                       y=y, rotation_x=12, color=color.rgb32(105, 77, 49))

    def interact(self, player):
        if self.puzzle_id == "fuse_box":
            player.progression.install_fuse()
        elif self.puzzle_id == "boards":
            player.progression.remove_boards()
        elif not player.progression.power_restored:
            player.hud.show_message("Electrical lock: no power. Find the missing storage fuse.")
        elif player.progression.safe_unlocked:
            player.hud.show_message("The lockbox is empty; you already collected its crowbar.")
        else:
            player.hud.panel.open_combination(player, self)
