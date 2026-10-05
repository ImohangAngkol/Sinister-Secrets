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
        **kwargs,
    ):

        # =========================
        # GHOST ENTITY
        # =========================

        super().__init__(
            model="cube",

            color=color.rgba(
                225,
                225,
                235,
                220,
            ),

            scale=(
                0.8,
                2.0,
                0.8,
            ),

            origin_y=-0.5,

            collider="box",

            **kwargs,
        )

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
        )

    def update(self):

        self.ai.update()