from dataclasses import dataclass
from ursina import Vec3, distance_xz
from game.world.environment import world_raycast

from game.settings import (
    GHOST_HEARING_BASE,
    GHOST_SOUND_OCCLUSION,
    NOISE_EVENT_LIFETIME,
)


@dataclass(frozen=True)
class NoiseEvent:
    sequence: int
    position: tuple
    strength: float
    created_at: float
    kind: str


def heard_noise(ghost, player, after_sequence=0):
    """Hear immutable, recent sources; never read the player's current position."""
    for event in reversed(player.stats.noise_events):
        if event.sequence <= after_sequence:
            break
        if player.stats.elapsed_time - event.created_at > NOISE_EVENT_LIFETIME:
            continue
        source = Vec3(*event.position)
        radius = GHOST_HEARING_BASE + event.strength * 1.15
        origin = ghost.world_position + Vec3(0, 1.2, 0)
        delta = source + Vec3(0, 0.6, 0) - origin
        if delta.length() > 0.001:
            obstruction = world_raycast(origin, delta.normalized(), distance=delta.length(),
                                        ignore=[ghost, player])
            if obstruction.hit:
                radius *= GHOST_SOUND_OCCLUSION
        if distance_xz(ghost.world_position, source) <= radius:
            return event
    return None


def can_hear_player(
    ghost,
    player,
) -> bool:
    return heard_noise(ghost, player) is not None
