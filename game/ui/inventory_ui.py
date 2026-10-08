from ursina import Text, camera, color


class InventoryUI(Text):

    def __init__(self):

        super().__init__(
            parent=camera.ui,

            text=(
                "Flashlight: NOT FOUND\n"
                "Keys: 0"
            ),

            x=-camera.aspect_ratio / 2 + 0.03,
            y=0.46,

            origin=(-0.5, 0.5),

            scale=1.05,

            color=color.white,
        )
        self.create_background(padding=0.025, color=color.black66)

    def refresh(
        self,
        player,
    ):

        if player.has_flashlight:

            flashlight_text = (
                f"Flashlight: "
                f"{int(player.stats.battery)}% "
                f"({'ON' if player.flashlight_on else 'OFF'})"
            )

        else:

            flashlight_text = (
                "Flashlight: NOT FOUND"
            )

        text = (
            f"{flashlight_text}\n"
            f"Keys: "
            f"{player.inventory.key_count()}"
        )
        if self.text != text:
            self.text = text
            self.create_background(padding=0.025, color=color.black66)
