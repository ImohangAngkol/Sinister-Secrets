"""Lit geometric interactions on existing furniture, never across corridors."""
from ursina import Entity, Vec3, color, destroy, time


class PuzzleProp(Entity):
    def __init__(self, definition, **kwargs):
        self.puzzle_id = definition["id"]
        self.powered_color = color.rgb32(62, 115, 78)
        super().__init__(model="cube", shader=None, collider="box",
                         position=definition["position"], scale=definition["scale"],
                         color=color.rgb32(*definition["color"]), **kwargs)
        self.interaction_text = definition["prompt"]
        self.completed = False
        self.visual_elapsed = 0.0
        self.moving = False
        self.leaf = None
        if self.puzzle_id in ('fuse_box','lockbox'):
            self.leaf = Entity(parent=self,shader=None,model='cube',origin_x=-.5,
                               position=(-.43,0,-.56),scale=(.86,.82,.055),
                               color=color.rgb32(74,79,72),collider=None)
            self.leaf.material_name = 'metal'
            self.indicator = Entity(parent=self.leaf,shader=None,model='cube',
                                    position=(.75,.3,-.55),scale=(.06,.07,.07),
                                    color=color.rgb32(83,55,35),collider=None)
        if self.puzzle_id == "boards":
            for y in (-.3, .3):
                Entity(parent=self, shader=None, model="cube", scale=(1, .18, 1.1),
                       y=y, rotation_x=12, color=color.rgb32(105, 77, 49))

    def set_completed(self, completed, animate=False):
        self.completed = bool(completed)
        self.visual_elapsed = 0 if animate else .45
        self.moving = bool(animate)
        self._pose()

    def _pose(self):
        if self.leaf:
            fraction = min(1,self.visual_elapsed/.45) if self.completed else 0
            fraction = fraction*fraction*(3-2*fraction)
            self.leaf.rotation_y = -75*fraction if self.puzzle_id=='lockbox' else -12*fraction
            self.indicator.color = self.powered_color if self.completed else color.rgb32(83,55,35)

    def update(self):
        if self.moving:
            self.visual_elapsed = min(.45,self.visual_elapsed+max(0,time.dt))
            self._pose()
            self.moving = self.visual_elapsed < .45

    def release_boards(self):
        # Very short collider-free fragments. The authoritative board removal
        # and key access remain immediate; no delayed puzzle rewards/tasks.
        for y in (-.3,.3):
            BoardFragment(parent=self.parent,shader=None,model='cube',
                          position=self.world_position+Vec3(0,y*self.scale_y,0),
                          scale=tuple(self.world_scale), rotation=self.world_rotation,
                          color=color.rgb32(105,77,49),collider=None)

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


class BoardFragment(Entity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.elapsed = 0.0
        self.start = Vec3(self.position)

    def update(self):
        self.elapsed += max(0,time.dt)
        self.y = self.start.y - 1.5*self.elapsed*self.elapsed
        self.rotation_z = 30*self.elapsed
        if self.elapsed >= .4:
            destroy(self)
