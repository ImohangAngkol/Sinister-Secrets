from ursina import distance_xz

from game.settings import (
    GHOST_HEARING_BASE,
)


def can_hear_player(
    ghost,
    player,
) -> bool:
    if (
        player.stats.noise_level
        <= 0
    ):
        return False

    hearing_distance = (
        GHOST_HEARING_BASE
        + player.stats.noise_level
        * 1.15
    )

    return (
        distance_xz(
            ghost.position,
            player.position,
        )
        <= hearing_distance
    )
