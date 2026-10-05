from ursina import Text, camera, color


class InventoryUI(Text):

    def __init__(self):

        super().__init__(
            parent=camera.ui,

            text=(
                "Flashlight: NOT FOUND\n"
                "Keys: 0"
            ),

            x=-0.86,
            y=0.46,

            origin=(-0.5, 0.5),

            scale=1.05,

            color=color.white,
        )

    def refresh(
        self,
        player,
    ):

        if player.has_flashlight:

            flashlight_text = (
                f"Flashlight: "
                f"{int(player.stats.battery)}%"
            )

        else:

            flashlight_text = (
                "Flashlight: NOT FOUND"
            )

        self.text = (
            f"{flashlight_text}\n"
            f"Keys: "
            f"{player.inventory.key_count()}"
        )