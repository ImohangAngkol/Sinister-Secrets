import math
from ursina import mouse
from game.settings import (PLAYER_HEIGHT, PLAYER_CROUCH_HEIGHT,
                           PLAYER_CAMERA_HEIGHT_RESPONSE, HIDING_LOOK_YAW,
                           HIDING_LOOK_PITCH)


class CameraController:
    """Smooth stance height and restrict the view inside a hiding spot."""

    def __init__(self, player):
        self.player = player

    def update(self, dt):
        player = self.player
        if player.hidden:
            centre = player.hiding_spot.view_yaw
            player.rotation_y = max(centre - HIDING_LOOK_YAW, min(centre + HIDING_LOOK_YAW,
                player.rotation_y + mouse.velocity.x * player.mouse_sensitivity.y))
            player.camera_pivot.rotation_x = max(-HIDING_LOOK_PITCH, min(HIDING_LOOK_PITCH,
                player.camera_pivot.rotation_x - mouse.velocity.y * player.mouse_sensitivity.x))
            return
        target = PLAYER_CROUCH_HEIGHT if player.crouching else PLAYER_HEIGHT
        player.camera_pivot.y += (target - player.camera_pivot.y) * (1 - math.exp(-PLAYER_CAMERA_HEIGHT_RESPONSE * dt))
        if abs(player.camera_pivot.y - target) < 0.001:
            player.camera_pivot.y = target
        # Head rays and the physical body follow the actual camera while lowering.
        player.set_body_height(max(target, player.camera_pivot.y))
