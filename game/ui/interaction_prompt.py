from ursina import Text, camera, color


class InteractionPrompt(Text):
    def __init__(self):
        super().__init__(
            parent=camera.ui,
            text="",
            origin=(0, 0),
            y=-0.34,
            scale=1.1,
            color=color.white,
        )

    def show(self, text: str):
        if self.text != text:
            self.text = text
            self.create_background(padding=0.025, color=color.black66)
        self.enabled = True

    def clear(self):
        self.text = ""
        self.enabled = False
