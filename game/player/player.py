import random
from panda3d.core import CollisionBox

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
    FLASHLIGHT_ATTENUATION,
    FLASHLIGHT_COLOR,
    FLASHLIGHT_EXPONENT,
    FLASHLIGHT_FOV,
    FLASHLIGHT_RANGE,
    FLASHLIGHT_SHADOWS,
    FLASHLIGHT_SHADOW_RESOLUTION,
    LOW_BATTERY_THRESHOLD,
    MAX_BATTERY,
    PLAYER_HEIGHT,
    PLAYER_SPEED,
    PLAYER_SPRINT_SPEED,
    PLAYER_CROUCH_HEIGHT,
    PLAYER_CROUCH_SPEED,
    PLAYER_CROUCH_NOISE,
    WALK_NOISE_STRIDE,
    SPRINT_NOISE_STRIDE,
    CROUCH_NOISE_STRIDE,
    HIDING_SAFE_SECONDS,
    HIDING_NOISE_INTERVAL,
    HIDING_NOISE_LEVEL,
    HIDING_REENTRY_DELAY,
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
        self.progression = None
        self.stats = PlayerStats()
        self.crouching = False
        self.sprinting = False
        self.hiding_spot = None
        self.ghost_ai = None
        self._noise_distance = 0.0
        self._hide_elapsed = 0.0
        self._next_hide_noise = HIDING_SAFE_SECONDS
        self._hide_cooldown = 0.0
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
        lens.set_fov(FLASHLIGHT_FOV)
        lens.set_near_far(0.1, FLASHLIGHT_RANGE)
        self.flashlight_light._light.set_attenuation(Vec3(*FLASHLIGHT_ATTENUATION))
        self.flashlight_light._light.set_exponent(FLASHLIGHT_EXPONENT)
        self.flashlight_light._light.set_max_distance(FLASHLIGHT_RANGE)
        self.flashlight_light._light.set_shadow_caster(
            FLASHLIGHT_SHADOWS, FLASHLIGHT_SHADOW_RESOLUTION, FLASHLIGHT_SHADOW_RESOLUTION)
        self.cursor.color = color.white

        self.hud.refresh_inventory(self)

    def update(self):
        # Ursina's controller uses short rays. Substeps prevent sprinting through
        # thin walls during a slow frame; apply mouse movement only once.
        frame_dt = time.dt
        velocity = mouse.velocity
        remaining = max(frame_dt, 0)
        noise_integral = 0.0
        self._hide_cooldown = max(0, self._hide_cooldown - max(frame_dt, 0))
        if self.hud.panel.active and not self.hidden:
            self.stats.advance(max(frame_dt, 0))
            self.stats.noise_level = 0
            self.sprinting = False
            self._update_flashlight()
            self.hud.set_prompt("")
            return
        if self.hidden:
            if self.hud.panel.active:
                mouse.velocity = Vec3(0, 0, 0)
            self.camera_controller.update(max(frame_dt, 0))
            mouse.velocity = velocity
            self.stats.advance(frame_dt)
            self.stats.noise_level = 0
            self.sprinting = False
            self._hide_elapsed += max(frame_dt, 0)
            while self._hide_elapsed >= self._next_hide_noise:
                self.stats.emit_noise(self.world_position, HIDING_NOISE_LEVEL, "breathing")
                self._next_hide_noise += HIDING_NOISE_INTERVAL
            self._update_flashlight()
            update_interaction_prompt(self)
            return
        try:
            while remaining > 1e-9:
                # Keep the maximum sprint step below the controller ray's
                # clearance margin, including diagonal movement and corners.
                time.dt = min(remaining, 1 / 240)
                wants_crouch = any(held_keys[key] for key in ("control", "left control", "right control"))
                self.crouching = bool(wants_crouch or (self.crouching and not self.can_stand()))
                self.camera_controller.update(time.dt)
                wants_sprint = (held_keys["shift"] or held_keys["left shift"]) and not self.crouching
                self.sprinting = bool(wants_sprint and self.stats.stamina > 0 and not self.stats.sprint_exhausted)
                self.speed = (PLAYER_CROUCH_SPEED if self.crouching else
                              PLAYER_SPRINT_SPEED if self.sprinting else PLAYER_SPEED)
                before = self.world_position
                step_speed = self.speed
                if self.crouching or self.camera_pivot.y < PLAYER_HEIGHT - 0.001:
                    direction = (self.forward * (held_keys["w"] - held_keys["s"])
                                 + self.right * (held_keys["d"] - held_keys["a"])).normalized()
                    destination = before + direction * self.speed * time.dt
                    # The controller's two horizontal rays can straddle a thin
                    # low ceiling. Check the full headroom while changing stance.
                    if not self.can_stand(destination, self.height):
                        self.speed = 0
                try:
                    super().update()
                finally:
                    self.speed = step_speed
                after = self.world_position
                travel = ((after.x - before.x) ** 2 + (after.z - before.z) ** 2) ** 0.5
                moving_seconds = min(time.dt, travel / self.speed)
                self.stats.advance(time.dt, moving_seconds if self.sprinting else 0)
                strength = PLAYER_CROUCH_NOISE if self.crouching else 8 if self.sprinting else 3
                noise_integral += strength * moving_seconds
                self._noise_distance += travel
                stride = (CROUCH_NOISE_STRIDE if self.crouching else
                          SPRINT_NOISE_STRIDE if self.sprinting else WALK_NOISE_STRIDE)
                while self._noise_distance >= stride:
                    self.stats.emit_noise(after, strength)
                    self._noise_distance -= stride
                remaining -= time.dt
                mouse.velocity = Vec3(0, 0, 0)
        finally:
            time.dt = frame_dt
            mouse.velocity = velocity

        self.stats.noise_level = noise_integral / frame_dt if frame_dt > 0 else 0
        if self.stats.noise_level < 0.01:
            self.stats.noise_level = 0
        self._update_flashlight()
        update_interaction_prompt(self)

    @property
    def hidden(self):
        return self.hiding_spot is not None

    def set_body_height(self, height):
        if abs(self.height - height) < 0.0001:
            return
        self.height = height
        collider = self.collider
        collider.center, collider.size = Vec3(0, height / 2, 0), Vec3(0.65, height, 0.65)
        collider.shape = CollisionBox(collider.center, 0.325, height / 2, 0.325)
        collider.node_path.node().clear_solids()
        collider.node_path.node().add_solid(collider.shape)

    def can_stand(self, position=None, height=PLAYER_HEIGHT):
        position = self.world_position if position is None else position
        for x, z in ((0, 0), (-0.32, -0.32), (-0.32, 0.32), (0.32, -0.32), (0.32, 0.32)):
            hit = world_raycast(position + Vec3(x, 0.05, z), Vec3(0, 1, 0),
                                distance=height, ignore=[self])
            if hit.hit:
                return False
        return True

    def can_occupy(self, position, height=PLAYER_HEIGHT):
        for x, z in ((0, 0), (-0.34, -0.34), (-0.34, 0.34), (0.34, -0.34), (0.34, 0.34)):
            hit = world_raycast(position + Vec3(x, 0.05, z), Vec3(0, 1, 0),
                                distance=height, ignore=[self])
            if hit.hit:
                return False
        for y in (0.5, height - 0.1):
            for direction in (Vec3(1, 0, 0), Vec3(-1, 0, 0), Vec3(0, 0, 1), Vec3(0, 0, -1)):
                if world_raycast(position + Vec3(0, y, 0), direction, distance=0.35, ignore=[self]).hit:
                    return False
        floor = world_raycast(position + Vec3(0, 0.5, 0), Vec3(0, -1, 0), distance=0.6, ignore=[self])
        # Panda transforms normals with Entity scale; floor tiles have Y scale .3.
        return floor.hit and floor.world_normal.normalized().y > 0.7

    def enter_hiding(self, spot):
        if self.hidden or spot.occupant is not None or self._hide_cooldown > 0:
            return False
        if (self.world_position - spot.prop.world_position).length() > 2.5:
            return False
        exit_position = next((p for p in (Vec3(self.world_position), *spot.exit_candidates())
                              if self.can_occupy(p)), None)
        if exit_position is None:
            self.hud.show_message("There is no safe space to leave this wardrobe.")
            return False
        delta = spot.prop.world_position - self.world_position
        if delta.length() > 0.001 and world_raycast(self.world_position + Vec3(0, 0.6, 0),
                delta.normalized(), distance=delta.length(), ignore=[self, spot.prop]).hit:
            return False
        if self.ghost_ai is not None:
            self.ghost_ai.witness_hiding(spot)
        self._hiding_return = (exit_position, self.rotation_y, self.camera_pivot.rotation_x, Vec3(camera.rotation))
        self.hiding_spot = spot
        spot.occupant = self
        self._hide_elapsed = 0
        self._next_hide_noise = HIDING_SAFE_SECONDS
        self.crouching = True
        self.sprinting = False
        self.world_position = spot.prop.world_position
        self.rotation_y = spot.view_yaw
        camera.rotation = Vec3(0, 0, 0)
        self.camera_pivot.rotation_x = 0
        self.camera_pivot.y = PLAYER_CROUCH_HEIGHT
        self.set_body_height(PLAYER_CROUCH_HEIGHT)
        self.stats.noise_level = 0
        self.stats.emit_noise(self.world_position, 1.5, "hiding_entry")
        self.hud.show_message("Hidden. E to leave. Staying too long makes noise.")
        self.hud.refresh_inventory(self)
        return True

    def leave_hiding(self):
        if not self.hidden:
            return False
        spot = self.hiding_spot
        position, yaw, pitch, camera_rotation = self._hiding_return
        # Validate the whole short exit sweep; never escape through an adjacent wall.
        for candidate in (position, *spot.exit_candidates()):
            if not self.can_occupy(candidate, PLAYER_CROUCH_HEIGHT):
                continue
            delta = candidate - self.world_position
            sideways = Vec3(-delta.z, 0, delta.x).normalized()
            if any(world_raycast(self.world_position + Vec3(0, 0.5, 0) + sideways * offset,
                    delta.normalized(), distance=delta.length(), ignore=[self, spot.prop]).hit
                    for offset in (-0.325, 0, 0.325)):
                continue
            self.world_position = candidate
            self.rotation_y, self.camera_pivot.rotation_x = yaw, pitch
            camera.rotation = camera_rotation
            spot.occupant = None
            self.hiding_spot = None
            self._hide_cooldown = HIDING_REENTRY_DELAY
            self.stats.emit_noise(self.world_position, 1.5, "hiding_exit")
            self.hud.show_message("Left hiding spot.")
            self.hud.refresh_inventory(self)
            return True
        self.hud.show_message("Exit obstructed. Try again when it is clear.")
        return False

    def input(self, key):
        if self.hud.panel.active:
            return
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
        self.inventory.add("flashlight")
        if self.progression:
            self.progression.refresh()

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
        self.hud.panel.close()
        if self.hidden:
            self.hiding_spot.occupant = None
            self.hiding_spot = None
        self.stats.noise_events.clear()
        self.flashlight_on = False
        self._set_flashlight_light(False)
        self.cursor.enabled = False

    def _set_flashlight_light(self, enabled):
        # Stashing a Light Entity does not clear Panda's registered light.
        # Keep registration stable and switch its contribution to zero instead.
        self.flashlight_light.world_position = camera.world_position
        self.flashlight_light.world_rotation = camera.world_rotation
        self.flashlight_light.color = (
            color.rgb(*FLASHLIGHT_COLOR) if enabled else color.rgb(0, 0, 0)
        )
