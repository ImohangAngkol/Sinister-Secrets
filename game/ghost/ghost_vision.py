import math

from ursina import Vec3, distance_xz
from game.world.environment import world_raycast as raycast

from game.settings import GHOST_FOV, GHOST_VISION_DISTANCE


def has_line_of_sight(ghost, player):
    eye = ghost.world_position + Vec3(0, 1.55, 0)
    target = player.world_position + Vec3(0, 1.0, 0)
    direction = target - eye
    length = direction.length()
    if length <= 0.001:
        return True
    hit = raycast(eye, direction / length, distance=length + 0.1, ignore=[ghost])
    return hit.hit and hit.entity == player


def can_see_player(ghost, player):
    if distance_xz(ghost.world_position, player.world_position) > GHOST_VISION_DISTANCE:
        return False
    # FOV is horizontal; using the vertical eye offset hid nearby players.
    delta = player.world_position - ghost.world_position
    direction = Vec3(delta.x, 0, delta.z)
    if direction.length() > 0.001:
        minimum_dot = math.cos(math.radians(GHOST_FOV / 2))
        if ghost.forward.normalized().dot(direction.normalized()) < minimum_dot:
            return False
    return has_line_of_sight(ghost, player)
