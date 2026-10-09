from game.ui.main_menu import MenuScreen


class EndScreen(MenuScreen):
    def __init__(self, manager=None):
        options = [] if manager is None else [
            ("Restart Game", manager.restart_game), ("Main Menu", manager.return_to_menu)]
        super().__init__("", options, row_y=-.04)

    def show(self, title: str, subtitle: str):
        self.enabled = True
        self.selected = 0
        self.title_text.text = title
        self.subtitle_text.text = subtitle
        self.refresh_selection()
