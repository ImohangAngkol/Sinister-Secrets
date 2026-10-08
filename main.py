from ursina import Ursina, window

from game.game_manager import GameManager
from game.settings import WINDOW_TITLE


app = Ursina(
    title=WINDOW_TITLE,
    borderless=False,
    fullscreen=False,
    editor_ui_enabled=False,
)

window.title = WINDOW_TITLE

GameManager()

app.run()
