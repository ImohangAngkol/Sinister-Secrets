from game.ghost.ghost import Ghost
from game.player.player import HorrorPlayer
from game.world.house import House
from game.world.environment import create_environment


class SceneManager:
    def __init__(self, hud, on_escape, on_caught):
        self.hud = hud

        # =========================
        # HOUSE
        # =========================

        self.house = House(
            on_escape=on_escape
        )
        self.lights = create_environment(self.house)

        # =========================
        # PLAYER
        # =========================

        self.player = HorrorPlayer(
            hud=hud,
            position=self.house.player_spawn,
            rotation_y=90,
        )
        self.player.camera_pivot.rotation_x = 32

        # =========================
        # GHOST
        # =========================

        self.ghost = Ghost(
            player=self.player,
            nav_nodes=self.house.nav_nodes,
            graph=self.house.graph,
            hud=hud,
            on_caught=on_caught,
            position=self.house.ghost_spawn,
            collision_root=self.house,
        )

    def stop_gameplay(self):
        self.player.cleanup()

        self.player.enabled = False
        self.ghost.enabled = False
