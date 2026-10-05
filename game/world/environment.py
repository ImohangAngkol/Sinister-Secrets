from ursina import AmbientLight, color


def create_environment(parent):
    AmbientLight(
        parent=parent,
        color=color.rgba(
            45,
            45,
            55,
            255,
        ),
    )
