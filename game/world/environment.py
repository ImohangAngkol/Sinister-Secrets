from ursina import AmbientLight, DirectionalLight, Vec3, color, scene, window
from ursina.hit_info import HitInfo
from panda3d.core import CollisionHandlerQueue, CollisionNode, CollisionRay, CollisionTraverser, Fog

from game.settings import (HOUSE_AMBIENT_COLOR, HOUSE_FILL_COLOR, HOUSE_FOG_COLOR,
                           HOUSE_FOG_DENSITY, HOUSE_SIGN_COLOR)


_world_ray = None


def world_raycast(origin, direction=(0, 0, 1), distance=9999,
                  traverse_target=scene, ignore=None, debug=False, **kwargs):
    """World-space rays without Ursina 8.3's accumulated look_at rotations.

    Its shared ray Entity can point in the wrong direction after successive
    opposite casts. Set the Panda ray direction explicitly instead.
    """
    global _world_ray
    if _world_ray is None:
        solid = CollisionRay()
        node = CollisionNode("prototype_world_ray")
        node.set_into_collide_mask(0)
        node.add_solid(solid)
        path = scene.attach_new_node(node)
        queue = CollisionHandlerQueue()
        traverser = CollisionTraverser()
        traverser.add_collider(path, queue)
        _world_ray = solid, queue, traverser
    solid, queue, traverser = _world_ray
    origin = Vec3(*origin)
    direction = Vec3(*direction)
    if direction.length() < 0.001:
        return HitInfo(hit=False, distance=distance)
    solid.set_origin(origin)
    solid.set_direction(direction.normalized())
    queue.clear_entries()
    traverser.traverse(traverse_target)
    queue.sort_entries()
    for entry in queue.get_entries():
        entity = entry.get_into_node_path().parent.get_python_tag("Entity")
        if entity not in scene.collidables or entity in (ignore or []):
            continue
        point = Vec3(entry.get_surface_point(scene))
        length = (point - origin).length()
        if length > distance:
            continue
        return HitInfo(hit=True, entity=entity, entities=[entity], distance=length,
                       world_point=point, point=Vec3(entry.get_surface_point(entity)),
                       world_normal=Vec3(entry.get_surface_normal(scene)),
                       normal=Vec3(entry.get_surface_normal(entity)))
    return HitInfo(hit=False, distance=distance)


def create_environment(parent):
    # Replace Ursina's unconfigured default linear fog. In 8.3 its numeric
    # fog_density setter does not configure exponential fog at all. Explicit
    # Panda3D exponential fog works with the existing generated world shader.
    scene.clear_fog()
    fog = Fog("house_distance_fog")
    fog.set_color(*HOUSE_FOG_COLOR)
    fog.set_exp_density(HOUSE_FOG_DENSITY)
    scene.set_fog(fog)
    ambient = AmbientLight(
        parent=parent,
        color=color.rgb(*HOUSE_AMBIENT_COLOR),
    )
    fill = DirectionalLight(parent=parent, shadows=False)
    fill.color = color.rgb(*HOUSE_FILL_COLOR)
    fill.look_at(Vec3(1, -2, -1))
    window.color = color.rgb(*HOUSE_FOG_COLOR)
    # World Text uses an unlit SDF shader. Keep it faint rather than turning
    # labels into bright signs in otherwise dark rooms. UI is a separate scene.
    for room in parent.rooms.values():
        room.sign.color = color.rgb32(*HOUSE_SIGN_COLOR)
    return ambient, fill
