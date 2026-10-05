from ursina import Entity, Ursina, window
from ursina.shaders import lit_with_shadows_shader

from game.game_manager import GameManager
from game.settings import WINDOW_TITLE


app = Ursina(
    title=WINDOW_TITLE,
    borderless=False,
)

window.title = WINDOW_TITLE

# Let walls/floor/props react to our lights.
Entity.default_shader = lit_with_shadows_shader

GameManager()

app.run()
