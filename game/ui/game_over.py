from ursina import Entity, Text, camera, color


class EndScreen(Entity):
    def __init__(self):
        super().__init__(
            parent=camera.ui,
            enabled=False,
        )

        self.background = Entity(
            parent=self,
            model="quad",
            color=color.rgba(
                0,
                0,
                0,
                220,
            ),
            scale=2,
        )

        self.title_text = Text(
            parent=self,
            text="",
            origin=(0, 0),
            y=0.07,
            scale=2.2,
        )

        self.subtitle_text = Text(
            parent=self,
            text="",
            origin=(0, 0),
            y=-0.11,
            scale=1.0,
        )

    def show(
        self,
        title: str,
        subtitle: str,
    ):
        self.enabled = True
        self.title_text.text = title
        self.subtitle_text.text = subtitle
