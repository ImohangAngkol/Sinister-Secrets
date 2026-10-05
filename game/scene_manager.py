from game.ghost.ghost import Ghost
from game.player.player import HorrorPlayer
from game.world.house import House


class SceneManager:
    def __init__(self, hud, on_escape, on_caught):
        self.hud = hud

        # =========================
        # HOUSE
        # =========================

        self.house = House(
            on_escape=on_escape
        )

        # =========================
        # PLAYER
        # =========================

        self.player = HorrorPlayer(
            hud=hud,
            position=self.house.player_spawn,
        )

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
        )

    def stop_gameplay(self):
        self.player.cleanup()

        self.player.enabled = False
        self.ghost.enabled = False