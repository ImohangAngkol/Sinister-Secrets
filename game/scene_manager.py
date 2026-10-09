from game.ghost.ghost import Ghost
from game.player.player import HorrorPlayer
from game.world.house import House
from game.world.environment import create_environment
from game.systems.progression import Progression
from ursina import application, camera, destroy, scene


class SceneManager:
    def __init__(self, hud, on_escape, on_caught):
        self.hud = hud

        # =========================
        # HOUSE
        # =========================

        self.house = House(
            on_escape=on_escape
        )
        self.lights = create_environment(self.house)

        # =========================
        # PLAYER
        # =========================

        self.player = HorrorPlayer(
            hud=hud,
            position=self.house.player_spawn,
            rotation_y=self.house.level.spawns["player"]["rotation_y"],
        )
        self.player.camera_pivot.rotation_x = self.house.level.spawns["player"]["camera_pitch"]
        self.player.inventory.definitions = self.house.level.items
        self.player.progression = Progression(self.house, self.player)
        self.player.progression.refresh()

        # =========================
        # GHOST
        # =========================

        self.ghost = Ghost(
            player=self.player,
            nav_nodes=self.house.nav_nodes,
            graph=self.house.graph,
            hud=hud,
            on_caught=on_caught,
            position=self.house.ghost_spawn,
            collision_root=self.house,
            patrol_targets=self.house.patrol_targets,
            hiding_spots=self.house.hiding_spots,
        )
        self.player.ghost_ai = self.ghost.ai

    def stop_gameplay(self):
        self.player.cleanup()

        self.player.enabled = False
        self.ghost.enabled = False

    def dispose(self):
        self.stop_gameplay()
        camera.world_parent = scene
        for light in (*self.lights, self.player.flashlight_light):
            application.base.render.clear_light(light.get_children()[0])
        roots = (self.house, self.ghost, self.player)
        entities = [entity for entity in scene.entities
                    if not entity.is_empty() and any(
                        entity == root or entity.has_ancestor(root) for root in roots)]
        # Children must be removed before their roots in Ursina 8.3. Keep the
        # loose cursor alive until the player's on_destroy/on_disable finishes.
        for entity in sorted(entities, key=lambda entity: entity.get_num_nodes(), reverse=True):
            destroy(entity)
        destroy(self.player.cursor)
        destroy(self.player.flashlight_light)
