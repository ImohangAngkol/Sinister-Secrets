from game.ui.main_menu import MenuScreen


class PauseMenu(MenuScreen):
    def __init__(self, manager):
        super().__init__("PAUSED", [
            ("Resume", manager.resume_game), ("Settings", manager.open_settings),
            ("Restart Game", manager.restart_game), ("Return to Main Menu", manager.return_to_menu),
            ("Quit Game", manager.quit_game)], "The house waits. Escape resumes.", row_y=.14, row_step=.085)
