from ursina import camera, raycast

from game.settings import INTERACT_DISTANCE


def get_interaction_hit(player):
    return raycast(
        origin=camera.world_position,
        direction=camera.forward,
        distance=INTERACT_DISTANCE,
        ignore=[player],
    )


def update_interaction_prompt(player):
    hit = get_interaction_hit(player)

    if hit.hit and hasattr(hit.entity, "interact"):
        prompt = getattr(
            hit.entity,
            "interaction_text",
            "[E] Interact",
        )

        player.hud.set_prompt(prompt)

    else:
        player.hud.set_prompt("")


def interact(player):
    hit = get_interaction_hit(player)

    if hit.hit and hasattr(hit.entity, "interact"):
        hit.entity.interact(player)
