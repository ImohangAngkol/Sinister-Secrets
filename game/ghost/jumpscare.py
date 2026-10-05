class Jumpscare:
    """Simple prototype jumpscare controller."""

    def __init__(
        self,
        on_caught=None,
    ):
        self.on_caught = on_caught
        self.triggered = False

    def trigger(self):
        if self.triggered:
            return

        self.triggered = True

        if self.on_caught:
            self.on_caught()
