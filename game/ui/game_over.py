from game.ui.main_menu import MenuScreen


class EndScreen(MenuScreen):
    def __init__(self, manager=None):
        options = [] if manager is None else [
            ("Restart Game", manager.restart_game), ("Main Menu", manager.return_to_menu),
            ("Retry from Checkpoint", manager.retry_checkpoint)]
        super().__init__("", options, row_y=-.04)
        self.manager = manager

    def configure_checkpoint(self, available):
        if self.manager is None:
            return
        # Reuse existing rows; the third row is constructed once by the manager.
        self.disabled_rows = set() if available else {2}
        self.rows[2][1].text = 'Retry from Checkpoint' if available else 'Retry (no checkpoint)'
        self.refresh_selection()

    def show(self, title: str, subtitle: str):
        self.enabled = True
        self.selected = 0
        self.title_text.text = title
        self.subtitle_text.text = subtitle
        self.refresh_selection()
