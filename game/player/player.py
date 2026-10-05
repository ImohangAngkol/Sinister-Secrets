import random

from ursina import (
    BoxCollider,
    SpotLight,
    Vec3,
    camera,
    color,
    held_keys,
    scene,
    time,
)

from ursina.prefabs.first_person_controller import (
    FirstPersonController,
)

from game.items.inventory import Inventory
from game.player.camera_controller import CameraController
from game.player.interaction import (
    interact,
    update_interaction_prompt,
)
from game.player.player_stats import PlayerStats
from game.settings import (
    FLASHLIGHT_DRAIN_PER_SECOND,
    LOW_BATTERY_THRESHOLD,
    MAX_BATTERY,
    PLAYER_HEIGHT,
    PLAYER_SPEED,
    PLAYER_SPRINT_SPEED,
)


class HorrorPlayer(FirstPersonController):
    def __init__(self, hud, **kwargs):
        super().__init__(
            speed=PLAYER_SPEED,
            height=PLAYER_HEIGHT,
            gravity=1,
            jump_height=0,
            **kwargs,
        )

        self.hud = hud
        self.inventory = Inventory()
        self.stats = PlayerStats()
        self.camera_controller = CameraController(self)

        self.has_flashlight = False
        self.flashlight_on = False

        # Make sure the ghost's vision ray can hit the player.
        self.collider = BoxCollider(
            self,
            center=Vec3(0, 0.9, 0),
            size=Vec3(0.65, 1.8, 0.65),
        )

        self.flashlight_light = SpotLight(
            parent=scene,
            color=color.rgba(
                255,
                245,
                220,
                255,
            ),
        )

        self.flashlight_light.enabled = False

        # Narrow the spotlight when the underlying lens is available.
        try:
            lens = (
                self.flashlight_light
                ._light
                .get_lens()
            )

            lens.set_fov(52)
            lens.set_near_far(
                0.2,
                24,
            )

        except Exception:
            pass

        self.hud.refresh_inventory(self)

    def update(self):
        moving = any(
            held_keys[key]
            for key in (
                "w",
                "a",
                "s",
                "d",
            )
        )

        sprinting = moving and (
            held_keys["shift"]
            or held_keys["left shift"]
        )

        if sprinting:
            self.speed = PLAYER_SPRINT_SPEED
            self.stats.noise_level = 8

        elif moving:
            self.speed = PLAYER_SPEED
            self.stats.noise_level = 3

        else:
            self.speed = PLAYER_SPEED
            self.stats.noise_level = 0

        super().update()

        self.camera_controller.update()
        self._update_flashlight()
        update_interaction_prompt(self)

    def input(self, key):
        if key == "f":
            self.toggle_flashlight()
            return

        if key == "e":
            interact(self)
            return

        # Disable jumping in prototype 0.1.
        if key == "space":
            return

        super().input(key)

    def obtain_flashlight(self):
        if self.has_flashlight:
            return

        self.has_flashlight = True

        self.hud.show_message(
            "Flashlight acquired. Press F to toggle it."
        )

        self.hud.refresh_inventory(self)

    def toggle_flashlight(self):
        if not self.has_flashlight:
            self.hud.show_message(
                "You do not have a flashlight yet."
            )
            return

        if self.stats.battery <= 0:
            self.hud.show_message(
                "The flashlight has no battery."
            )
            return

        self.flashlight_on = (
            not self.flashlight_on
        )

        self.flashlight_light.enabled = (
            self.flashlight_on
        )

    def add_battery(self, amount: float):
        self.stats.battery = min(
            MAX_BATTERY,
            self.stats.battery + amount,
        )

        self.hud.show_message(
            f"Battery restored to "
            f"{int(self.stats.battery)}%."
        )

        self.hud.refresh_inventory(self)

    def _update_flashlight(self):
        if (
            self.flashlight_on
            and self.stats.battery > 0
        ):
            self.stats.battery = max(
                0,
                self.stats.battery
                - FLASHLIGHT_DRAIN_PER_SECOND
                * time.dt,
            )

            self.flashlight_light.world_position = (
                camera.world_position
            )

            self.flashlight_light.look_at(
                camera.world_position
                + camera.forward * 10
            )

            # Small flicker at low battery.
            if (
                self.stats.battery
                < LOW_BATTERY_THRESHOLD
                and random.random() < 0.08
            ):
                self.flashlight_light.enabled = False

            else:
                self.flashlight_light.enabled = True

            if self.stats.battery <= 0:
                self.flashlight_on = False
                self.flashlight_light.enabled = False

                self.hud.show_message(
                    "The flashlight battery died."
                )

        else:
            self.flashlight_light.enabled = False

        self.hud.refresh_inventory(self)

    def cleanup(self):
        self.flashlight_light.enabled = False
