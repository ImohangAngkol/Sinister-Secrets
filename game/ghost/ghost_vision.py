import math

from ursina import Vec3, distance_xz
from game.world.environment import world_raycast as raycast

from game.settings import (GHOST_FOV, GHOST_VISION_DISTANCE, GHOST_DARK_VISIBILITY,
                           GHOST_CROUCH_VISIBILITY)


def visibility_factor(player):
    lit = player.flashlight_on and player.flashlight_light.color.r > 0
    return (1 if lit else GHOST_DARK_VISIBILITY) * (GHOST_CROUCH_VISIBILITY if player.crouching else 1)


def has_line_of_sight(ghost, player):
    if player.hidden:
        return False
    eye = ghost.world_position + Vec3(0, 1.55, 0)
    target = player.world_position + Vec3(0, player.height * 0.6, 0)
    direction = target - eye
    length = direction.length()
    if length <= 0.001:
        return True
    hit = raycast(eye, direction / length, distance=length + 0.1, ignore=[ghost])
    return hit.hit and hit.entity == player


def can_see_player(ghost, player):
    if player.hidden or distance_xz(ghost.world_position, player.world_position) > GHOST_VISION_DISTANCE * visibility_factor(player):
        return False
    # FOV is horizontal; using the vertical eye offset hid nearby players.
    delta = player.world_position - ghost.world_position
    direction = Vec3(delta.x, 0, delta.z)
    if direction.length() > 0.001:
        minimum_dot = math.cos(math.radians(GHOST_FOV / 2))
        if ghost.forward.normalized().dot(direction.normalized()) < minimum_dot:
            return False
    return has_line_of_sight(ghost, player)
