from ursina import Entity, Vec3, color, time
from game.ghost.ghost_visual import GhostVisual

from game.ghost.ghost_ai import GhostAI
from game.ghost.jumpscare import Jumpscare


class Ghost(Entity):

    def __init__(
        self,
        player,
        nav_nodes,
        graph,
        hud,
        on_caught,
        collision_root=None,
        patrol_targets=None,
        hiding_spots=(),
        **kwargs,
    ):

        # =========================
        # GHOST ENTITY
        # =========================

        super().__init__(
            model="cube",

            shader=None,
            color=color.rgb32(160, 205, 210),

            scale=(
                0.8,
                2.0,
                0.8,
            ),

            origin_y=-0.5,

            collider="box",

            **kwargs,
        )
        self.set_shader_auto()
        # Keep the original collider and scale; visual joints use world metres.
        self.model = None
        self.visual = GhostVisual(parent=self, scale=(1.25,.5,1.25))
        self.audio = None
        self._was_inspecting = False

        # =========================
        # JUMPSCARE
        # =========================

        self.jumpscare = Jumpscare(
            on_caught=on_caught
        )

        # =========================
        # GHOST AI
        # =========================

        self.ai = GhostAI(
            ghost=self,
            player=player,
            nav_nodes=nav_nodes,
            graph=graph,
            hud=hud,
            jumpscare=self.jumpscare,
            collision_root=collision_root,
            patrol_targets=patrol_targets,
            hiding_spots=hiding_spots,
        )

    def update(self):

        before = Vec3(self.world_position)
        self.ai.update()
        after = self.world_position
        travel = ((after.x-before.x)**2+(after.z-before.z)**2)**.5
        inspecting = self.ai.inspection_target is not None
        self.visual.advance(time.dt, displacement=travel, state=self.ai.state, inspection=inspecting)
        if inspecting and not self._was_inspecting and self.audio:
            self.audio.play('inspect', gain=.4, cooldown=10)
        self._was_inspecting = inspecting
