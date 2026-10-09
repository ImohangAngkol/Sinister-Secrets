"""Perception-driven five-state AI; navigation remains collision aware."""
import random
from ursina import Vec3, distance_xz, time
from game.ghost.ghost_hearing import can_hear_player, heard_noise
from game.ghost.ghost_navigation import GhostNavigation, nearest_node
from game.ghost.ghost_states import GhostState
from game.ghost.ghost_vision import can_see_player, has_line_of_sight, visibility_factor
from game.world.environment import world_raycast
from game.settings import (
    GHOST_CATCH_DISTANCE, GHOST_CHASE_SPEED, GHOST_INVESTIGATE_SPEED,
    GHOST_LOST_SIGHT_SECONDS, GHOST_PATROL_SPEED, GHOST_SEARCH_SECONDS,
    GHOST_ACTIVE_SEARCH_SECONDS, GHOST_SEARCH_SPEED, GHOST_DETECTION_SECONDS,
    GHOST_DETECTION_DECAY, GHOST_VISION_DISTANCE, GHOST_MEMORY_SECONDS,
    GHOST_UNCERTAINTY_GROWTH, GHOST_SEARCH_RADIUS, GHOST_NOISE_COOLDOWN,
    GHOST_INSPECTION_SECONDS,
)


class GhostAI:
    def __init__(self, ghost, player, nav_nodes, graph, hud, jumpscare,
                 collision_root=None, patrol_targets=None, hiding_spots=()):
        self.ghost, self.player = ghost, player
        self.nav_nodes, self.graph = nav_nodes, graph
        self.patrol_targets = patrol_targets
        self.hiding_spots = hiding_spots
        self.hud, self.jumpscare = hud, jumpscare
        self.state = GhostState.PATROL
        self.speed_multiplier = 1.0
        self.detection_multiplier = 1.0
        self.navigation = GhostNavigation(ghost, nav_nodes, graph, collision_root, player)
        self.last_known_player_node = None
        self.last_known_player_position = None
        self.memory_age = 0.0
        self.memory_uncertainty = 0.0
        self.detection = 0.0
        self.last_noise_sequence = 0
        self.noise_cooldown = 0.0
        self.repath_time = self.recovery_time = 0.0
        self.lost_sight_time = self.search_time = 0.0
        self.search_nodes = []
        self.search_spots = []
        self.searched_nodes = set()
        self.suspected_hiding_spot = None
        self.inspection_target = None
        self.inspection_time = 0.0
        self._choose_random_patrol_target()
        self._refresh_debug()

    def update(self):
        # Bound sensing/timer transitions at slow FPS, retaining all elapsed time.
        dt = time.dt
        remaining = max(dt, 0)
        try:
            while remaining > 1e-9 and self.state != GhostState.JUMPSCARE:
                time.dt = min(remaining, 1 / 30)
                self._update_step()
                remaining -= time.dt
        finally:
            time.dt = dt

    def _remember(self, position, uncertainty):
        self.last_known_player_position = Vec3(position)
        self.last_known_player_node = nearest_node(position, self.nav_nodes)
        self.memory_age = 0
        self.memory_uncertainty = uncertainty

    def _update_step(self):
        dt = time.dt
        self.repath_time = max(0, self.repath_time - dt)
        self.recovery_time = max(0, self.recovery_time - dt)
        self.noise_cooldown = max(0, self.noise_cooldown - dt)
        if self.last_known_player_position is not None:
            self.memory_age += dt
            self.memory_uncertainty += GHOST_UNCERTAINTY_GROWTH * dt
            if self.memory_age >= GHOST_MEMORY_SECONDS:
                self.last_known_player_position = self.last_known_player_node = None
        sees = self.recovery_time <= 0 and can_see_player(self.ghost, self.player)

        if (self.state == GhostState.CHASE and not self.player.hidden
                and distance_xz(self.ghost.world_position, self.player.world_position) <= GHOST_CATCH_DISTANCE
                and has_line_of_sight(self.ghost, self.player)):
            self._catch_player()
            return

        if sees:
            self._remember(self.player.world_position, 0.3)
            self.lost_sight_time = 0
            proximity = 1 - min(1, distance_xz(self.ghost.world_position, self.player.world_position) / GHOST_VISION_DISTANCE)
            self.detection = min(1, self.detection + dt * visibility_factor(self.player)
                                 * self.detection_multiplier * (0.45 + 0.55 * proximity) / GHOST_DETECTION_SECONDS)
            if self.detection >= 1 and self.state != GhostState.CHASE:
                self.navigation.clear()
                self.inspection_target = self.suspected_hiding_spot = None
                self._set_state(GhostState.CHASE)
            elif self.state != GhostState.CHASE:
                # Examine a visible silhouette before pursuing, rather than
                # turning away with the patrol path every frame.
                self.ghost.look_at_2d(self.player.world_position, "y")
                return
        else:
            self.detection = max(0, self.detection - GHOST_DETECTION_DECAY * dt)
            if self.state == GhostState.CHASE:
                self.lost_sight_time += dt
                if self.lost_sight_time >= GHOST_LOST_SIGHT_SECONDS or self.last_known_player_position is None:
                    self._start_search()

        event = heard_noise(self.ghost, self.player, self.last_noise_sequence)
        if event is not None:
            self.last_noise_sequence = event.sequence  # Each pulse can be used once.
            if (not sees and self.recovery_time <= 0 and self.noise_cooldown <= 0
                    and self.state != GhostState.CHASE and self.inspection_target is None
                    and self.suspected_hiding_spot is None and can_hear_player(self.ghost, self.player)):
                self._remember(Vec3(*event.position), 1.8)
                self.noise_cooldown = GHOST_NOISE_COOLDOWN
                # A sound inside a cabinet is approached from outside its solid
                # collider. Only that audible source creates this suspicion.
                self.suspected_hiding_spot = next((spot for spot in self.hiding_spots
                    if distance_xz(spot.prop.world_position, self.last_known_player_position) < 0.7), None)
                target = (self.suspected_hiding_spot.approach if self.suspected_hiding_spot
                          else self.last_known_player_position)
                if self.navigation.set_path_to_position(target):
                    self._set_state(GhostState.INVESTIGATE)
                else:
                    self._recover_without_route()

        self._run_state(sees)
        if self.state != GhostState.JUMPSCARE and self.navigation.stuck_time >= 0.5:
            if not self.navigation.replan():
                if self.state == GhostState.SEARCH and self.recovery_time <= 0:
                    self.navigation.clear()
                    self.inspection_target = None
                    self._select_search_target()
                else:
                    self._recover_without_route()

    def witness_hiding(self, spot):
        # Called BEFORE entry changes position/visibility. No global knowledge of
        # occupancy is used when choosing an inspection target.
        if self.recovery_time > 0 or not can_see_player(self.ghost, self.player):
            return False
        self._remember(spot.approach, 0.3)
        self.suspected_hiding_spot = spot
        if self.inspection_target is spot:
            # Re-entering a watched wardrobe must not restart an active check.
            return True
        self.inspection_target = None
        self.detection = 0
        if self.navigation.set_path_to_position(spot.approach):
            self._set_state(GhostState.INVESTIGATE)
        else:
            self._recover_without_route()
        return True

    def _run_state(self, sees_player):
        if self.state == GhostState.PATROL:
            self.navigation.follow_path(GHOST_PATROL_SPEED * self.speed_multiplier)
            if self.navigation.path_finished():
                self._choose_random_patrol_target()
        elif self.state == GhostState.INVESTIGATE:
            if self.navigation.blocked and self.navigation.path_finished():
                self._recover_without_route()
                return
            self.navigation.follow_path(GHOST_INVESTIGATE_SPEED * self.speed_multiplier)
            if self.navigation.path_finished():
                self._start_search()
        elif self.state == GhostState.CHASE:
            target = self.player.world_position if sees_player else self.last_known_player_position
            if target is None:
                self._start_search()
                return
            if sees_player and self.navigation.segment_clear(self.ghost.world_position, target):
                self.navigation.clear()
                self._move_directly_toward_player()
            else:
                if self.navigation.path_finished() or (sees_player and self.repath_time <= 0):
                    if not self.navigation.set_path_to_position(target):
                        self._recover_without_route()
                        return
                    self.repath_time = 0.3
                self.navigation.follow_path(GHOST_CHASE_SPEED * self.speed_multiplier)
                if not sees_player and self.navigation.path_finished():
                    self._start_search()
        elif self.state == GhostState.SEARCH:
            self.search_time -= time.dt
            if self.search_time <= 1e-8:
                self.navigation.clear()
                self.inspection_target = self.suspected_hiding_spot = None
                self.last_known_player_position = self.last_known_player_node = None
                self._set_state(GhostState.PATROL)
                self._choose_random_patrol_target()
                return
            if self.recovery_time > 0:
                self.ghost.rotation_y += 55 * time.dt
                return
            if self.inspection_target is not None:
                self._inspect_hiding_spot()
            else:
                self.navigation.follow_path(GHOST_SEARCH_SPEED * self.speed_multiplier)
                if self.navigation.path_finished():
                    self._select_search_target()

    def _start_search(self):
        self.navigation.clear()
        self._set_state(GhostState.SEARCH)
        self.search_time = GHOST_ACTIVE_SEARCH_SECONDS
        centre = self.last_known_player_position
        if centre is None:
            centre = Vec3(self.ghost.world_position)
        radius = GHOST_SEARCH_RADIUS + min(self.memory_uncertainty, 5)
        self.search_nodes = sorted(
            (node for node, pos in self.nav_nodes.items() if distance_xz(pos, centre) <= radius),
            key=lambda node: distance_xz(self.nav_nodes[node], centre))
        self.search_spots = sorted(
            (spot for spot in self.hiding_spots if distance_xz(spot.approach, centre) <= radius),
            key=lambda spot: distance_xz(spot.approach, centre))
        if self.suspected_hiding_spot:
            self.search_spots = [self.suspected_hiding_spot] + [
                spot for spot in self.search_spots if spot != self.suspected_hiding_spot]
        self.searched_nodes.clear()
        self.inspection_target = None
        self._select_search_target()

    def _select_search_target(self):
        self.navigation.clear()
        while self.search_spots:
            spot = self.search_spots.pop(0)
            if self.navigation.set_path_to_position(spot.approach):
                self.inspection_target = spot
                self.inspection_time = 0
                return
        while self.search_nodes:
            node = self.search_nodes.pop(0)
            if self.navigation.set_path_to_node(node):
                self.searched_nodes.add(node)
                return
        self.ghost.rotation_y += 55 * time.dt

    def _inspection_clear(self, spot):
        if distance_xz(self.ghost.world_position, spot.approach) > 1.3:
            return False
        start = self.ghost.world_position + Vec3(0, 1, 0)
        target = spot.prop.world_position - spot.prop.forward.normalized() * spot.depth / 2 + Vec3(0, 1, 0)
        delta = target - start
        return not world_raycast(start, delta.normalized(), distance=delta.length(),
                                 ignore=[self.ghost, self.player, spot.prop]).hit

    def _inspect_hiding_spot(self):
        spot = self.inspection_target
        self.navigation.follow_path(GHOST_SEARCH_SPEED * self.speed_multiplier)
        if not self.navigation.path_finished():
            return
        if not self._inspection_clear(spot):
            self.inspection_target = None
            self._select_search_target()
            return
        self.ghost.look_at_2d(spot.prop.world_position, "y")
        if self.inspection_time == 0 and spot.occupant == self.player:
            self.hud.show_message("The ghost is checking this wardrobe. E to leave!", seconds=2)
        self.inspection_time += time.dt
        if self.inspection_time >= GHOST_INSPECTION_SECONDS:
            if spot.occupant == self.player and self.player.hidden:
                self._catch_player()
                return
            if self.suspected_hiding_spot == spot:
                self.suspected_hiding_spot = None
            self.inspection_target = None
            self._select_search_target()

    def _move_directly_toward_player(self):
        self.navigation.move_toward(self.player.world_position, GHOST_CHASE_SPEED * self.speed_multiplier)
        self.navigation.target_position = Vec3(self.player.world_position)

    def _choose_random_patrol_target(self):
        start_node = nearest_node(self.ghost.world_position, self.nav_nodes)
        available = [node for node in (self.patrol_targets or self.nav_nodes)
                     if node in self.nav_nodes and node != start_node]
        if not available:
            available = [node for node in self.nav_nodes if node != start_node]
        random.shuffle(available)
        for node in available:
            if self.navigation.set_path_to_node(node):
                return
        self._recover_without_route()

    def _recover_without_route(self):
        self.navigation.clear()
        self.inspection_target = self.suspected_hiding_spot = None
        self.search_nodes, self.search_spots = [], []
        self._set_state(GhostState.SEARCH)
        self.search_time = self.recovery_time = self.repath_time = GHOST_SEARCH_SECONDS

    def _set_state(self, new_state):
        if self.state == new_state:
            return
        self.state = new_state
        self._refresh_debug()
        if new_state != GhostState.CHASE:
            self.lost_sight_time = 0

    def _refresh_debug(self):
        self.hud.set_ghost_state(self.state.name)

    def _catch_player(self):
        self._set_state(GhostState.JUMPSCARE)
        self.jumpscare.trigger()
