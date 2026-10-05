import os
import sys

from ursina import Entity, application, mouse

from game.scene_manager import SceneManager
from game.ui.game_over import EndScreen
from game.ui.hud import HUD


class GameManager(Entity):
    def __init__(self):
        super().__init__()

        self.state = "playing"

        self.hud = HUD()
        self.end_screen = EndScreen()

        self.scene_manager = SceneManager(
            hud=self.hud,
            on_escape=self.win_game,
            on_caught=self.game_over,
        )

        self.hud.show_message(
            "Find the flashlight, locate the exit key, and escape.",
            seconds=4,
        )

    def input(self, key):
        if key == "escape":
            application.quit()

        if key == "r" and self.state != "playing":
            os.execl(
                sys.executable,
                sys.executable,
                *sys.argv,
            )

    def game_over(self):
        if self.state != "playing":
            return

        self.state = "dead"
        self.scene_manager.stop_gameplay()
        mouse.locked = False
        self.hud.set_prompt("")

        self.end_screen.show(
            "CAUGHT!",
            "The ghost found you.\nPress R to restart.",
        )

    def win_game(self):
        if self.state != "playing":
            return

        self.state = "escaped"
        self.scene_manager.stop_gameplay()
        mouse.locked = False
        self.hud.set_prompt("")

        self.end_screen.show(
            "YOU ESCAPED",
            "Sinister Secrets prototype complete.\nPress R to restart.",
        )
