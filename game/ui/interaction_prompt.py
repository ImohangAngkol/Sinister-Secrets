from ursina import Text, camera


class InteractionPrompt(Text):
    def __init__(self):
        super().__init__(
            parent=camera.ui,
            text="",
            origin=(0, 0),
            y=-0.34,
            scale=1.1,
        )

    def show(self, text: str):
        self.text = text

    def clear(self):
        self.text = ""
