import random

from ursina import (
    BoxCollider,
    SpotLight,
    Vec3,
    camera,
    color,
    held_keys,
    mouse,
    scene,
    time,
)

from ursina.prefabs.first_person_controller import (
    FirstPersonController,
)
from ursina.prefabs import first_person_controller
from game.world.environment import world_raycast

# Keep Ursina's controller and replace its version-specific ray orientation bug.
first_person_controller.raycast = world_raycast

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
        self._flicker_active = False
        self._flicker_dark = False
        self._flicker_remaining = 0.0

        # Make sure the ghost's vision ray can hit the player.
        self.collider = BoxCollider(
            self,
            center=Vec3(0, 0.9, 0),
            size=Vec3(0.65, 1.8, 0.65),
        )

        self.flashlight_light = SpotLight(
            parent=scene,
            color=color.rgb(0, 0, 0),
        )
        lens = self.flashlight_light._light.get_lens()
        lens.set_fov(52)
        lens.set_near_far(0.1, 24)
        self.flashlight_light._light.set_attenuation(Vec3(1, 0, 0.015))
        self.flashlight_light._light.set_shadow_caster(True, 512, 512)
        self.cursor.color = color.white

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

        elif moving:
            self.speed = PLAYER_SPEED

        else:
            self.speed = PLAYER_SPEED

        # Ursina's controller uses short rays. Substeps prevent sprinting through
        # thin walls during a slow frame; apply mouse movement only once.
        frame_dt = time.dt
        velocity = mouse.velocity
        remaining = max(frame_dt, 0)
        horizontal_distance = 0.0
        try:
            while remaining > 1e-9:
                # Keep the maximum sprint step below the controller ray's
                # clearance margin, including diagonal movement and corners.
                time.dt = min(remaining, 1 / 240)
                before = self.world_position
                super().update()
                after = self.world_position
                horizontal_distance += ((after.x - before.x) ** 2
                                        + (after.z - before.z) ** 2) ** 0.5
                remaining -= time.dt
                mouse.velocity = Vec3(0, 0, 0)
        finally:
            time.dt = frame_dt
            mouse.velocity = velocity

        actual_speed = horizontal_distance / frame_dt if frame_dt > 0 else 0
        self.stats.noise_level = (8 if sprinting else 3) * min(actual_speed / self.speed, 1)
        if actual_speed < 0.01:
            self.stats.noise_level = 0

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
        self._flicker_active = False

        self._set_flashlight_light(self.flashlight_on)
        self.hud.refresh_inventory(self)

    def add_battery(self, amount: float):
        if self.stats.battery >= MAX_BATTERY:
            self.hud.show_message("Flashlight battery is already full. Leave this battery for later.")
            return False
        if amount <= 0:
            return False
        self.stats.battery = min(
            MAX_BATTERY,
            self.stats.battery + amount,
        )

        self.hud.show_message(
            f"Battery restored to "
            f"{int(self.stats.battery)}%."
        )

        self.hud.refresh_inventory(self)
        return True

    def _update_flashlight(self):
        frame_dt = max(time.dt, 0)
        if (
            self.flashlight_on
            and self.stats.battery > 0
        ):
            self.stats.battery = max(
                0,
                self.stats.battery
                - FLASHLIGHT_DRAIN_PER_SECOND
                * frame_dt,
            )

            self.flashlight_light.world_position = (
                camera.world_position
            )

            self.flashlight_light.world_rotation = camera.world_rotation

            # Alternating intervals measured in seconds, carrying overshoot
            # across frames. RNG calls depend on elapsed time, not FPS.
            if 0 < self.stats.battery < LOW_BATTERY_THRESHOLD:
                if not self._flicker_active:
                    self._flicker_active = True
                    self._flicker_dark = False
                    self._flicker_remaining = random.uniform(0.35, 0.9)
                    low_dt = min(frame_dt, (LOW_BATTERY_THRESHOLD - self.stats.battery)
                                 / FLASHLIGHT_DRAIN_PER_SECOND)
                else:
                    low_dt = frame_dt
                self._flicker_remaining -= low_dt
                while self._flicker_remaining <= 1e-9:
                    self._flicker_dark = not self._flicker_dark
                    self._flicker_remaining += (random.uniform(0.06, 0.12)
                                               if self._flicker_dark
                                               else random.uniform(0.35, 0.9))
                self._set_flashlight_light(not self._flicker_dark)
            else:
                self._flicker_active = False
                self._set_flashlight_light(True)

            if self.stats.battery <= 0:
                self.flashlight_on = False
                self._set_flashlight_light(False)

                self.hud.show_message(
                    "The flashlight battery died."
                )

        else:
            self.flashlight_on = False
            self._flicker_active = False
            self._set_flashlight_light(False)

        self.hud.refresh_inventory(self)

    def cleanup(self):
        self.flashlight_on = False
        self._set_flashlight_light(False)
        self.cursor.enabled = False

    def _set_flashlight_light(self, enabled):
        # Stashing a Light Entity does not clear Panda's registered light.
        # Keep registration stable and switch its contribution to zero instead.
        self.flashlight_light.world_position = camera.world_position
        self.flashlight_light.world_rotation = camera.world_rotation
        self.flashlight_light.color = (
            color.rgb(0.95, 0.90, 0.78) if enabled else color.rgb(0, 0, 0)
        )
