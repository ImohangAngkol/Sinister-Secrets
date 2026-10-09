from ursina import Entity, color

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
        )

    def update(self):

        self.ai.update()
