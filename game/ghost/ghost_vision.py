import math

from ursina import (
    Vec3,
    distance_xz,
    raycast,
)

from game.settings import (
    GHOST_FOV,
    GHOST_VISION_DISTANCE,
)


def can_see_player(
    ghost,
    player,
) -> bool:
    distance = distance_xz(
        ghost.position,
        player.position,
    )

    if (
        distance
        > GHOST_VISION_DISTANCE
    ):
        return False

    eye = (
        ghost.world_position
        + Vec3(
            0,
            1.55,
            0,
        )
    )

    target = (
        player.world_position
        + Vec3(
            0,
            1.0,
            0,
        )
    )

    direction = target - eye

    if direction.length() <= 0.001:
        return True

    direction = (
        direction.normalized()
    )

    minimum_dot = math.cos(
        math.radians(
            GHOST_FOV / 2
        )
    )

    if (
        ghost.forward.dot(
            direction
        )
        < minimum_dot
    ):
        return False

    # Walls block this ray.
    hit = raycast(
        origin=eye,
        direction=direction,
        distance=distance + 1,
        ignore=[ghost],
    )

    return (
        hit.hit
        and hit.entity == player
    )
