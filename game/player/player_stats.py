from game.settings import FLASHLIGHT_START_BATTERY


class PlayerStats:
    def __init__(self):
        self.battery = float(
            FLASHLIGHT_START_BATTERY
        )

        self.noise_level = 0.0
