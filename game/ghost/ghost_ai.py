import random

from ursina import (
    distance_xz,
    time,
)

from game.ghost.ghost_hearing import (
    can_hear_player,
)

from game.ghost.ghost_navigation import (
    GhostNavigation,
    nearest_node,
)

from game.ghost.ghost_states import (
    GhostState,
)

from game.ghost.ghost_vision import (
    can_see_player,
)

from game.settings import (
    GHOST_CATCH_DISTANCE,
    GHOST_CHASE_SPEED,
    GHOST_INVESTIGATE_SPEED,
    GHOST_LOST_SIGHT_SECONDS,
    GHOST_PATROL_SPEED,
    GHOST_SEARCH_SECONDS,
)


class GhostAI:

    def __init__(
        self,
        ghost,
        player,
        nav_nodes,
        graph,
        hud,
        jumpscare,
    ):

        # =========================
        # REFERENCES
        # =========================

        self.ghost = ghost

        self.player = player

        # IMPORTANT:
        # Do NOT call this self.nodes.
        #
        # Panda3D/Ursina already uses
        # the name "nodes".
        self.nav_nodes = nav_nodes

        self.graph = graph

        self.hud = hud

        self.jumpscare = jumpscare

        # =========================
        # AI STATE
        # =========================

        self.state = GhostState.PATROL

        # =========================
        # NAVIGATION
        # =========================

        self.navigation = GhostNavigation(
            ghost=ghost,
            nodes=nav_nodes,
            graph=graph,
        )

        # =========================
        # MEMORY
        # =========================

        self.last_known_player_node = None

        # =========================
        # TIMERS
        # =========================

        self.lost_sight_time = 0.0

        self.search_time = 0.0

        # =========================
        # START PATROLLING
        # =========================

        self._choose_random_patrol_target()

        self._refresh_debug()

    # ==========================================
    # MAIN AI LOOP
    # ==========================================

    def update(self):

        # Stop AI after jumpscare.
        if self.state == GhostState.JUMPSCARE:
            return

        # ======================================
        # GHOST SENSES
        # ======================================

        sees_player = can_see_player(
            self.ghost,
            self.player,
        )

        hears_player = can_hear_player(
            self.ghost,
            self.player,
        )

        # ======================================
        # CHECK IF GHOST CAUGHT PLAYER
        # ======================================

        player_distance = distance_xz(
            self.ghost.position,
            self.player.position,
        )

        if (
            self.state == GhostState.CHASE
            and player_distance
            <= GHOST_CATCH_DISTANCE
        ):

            self._catch_player()

            return

        # ======================================
        # GHOST SEES PLAYER
        # ======================================

        if sees_player:

            self.last_known_player_node = (
                nearest_node(
                    self.player.position,
                    self.nav_nodes,
                )
            )

            self.lost_sight_time = 0.0

            self._set_state(
                GhostState.CHASE
            )

        # ======================================
        # GHOST LOST PLAYER
        # ======================================

        elif self.state == GhostState.CHASE:

            self.lost_sight_time += time.dt

            # Travel toward the last location
            # where the player was seen.
            if (
                self.navigation.path_finished()
                and
                self.last_known_player_node
                is not None
            ):

                self.navigation.set_path_to_node(
                    self.last_known_player_node
                )

            # After a while, stop chasing
            # and start searching.
            if (
                self.lost_sight_time
                >= GHOST_LOST_SIGHT_SECONDS
            ):

                self._set_state(
                    GhostState.SEARCH
                )

                self.search_time = (
                    GHOST_SEARCH_SECONDS
                )

        # ======================================
        # GHOST HEARS PLAYER
        # ======================================

        elif (
            hears_player
            and self.state
            in (
                GhostState.PATROL,
                GhostState.SEARCH,
            )
        ):

            self.last_known_player_node = (
                nearest_node(
                    self.player.position,
                    self.nav_nodes,
                )
            )

            self.navigation.set_path_to_node(
                self.last_known_player_node
            )

            self._set_state(
                GhostState.INVESTIGATE
            )

        # ======================================
        # RUN CURRENT STATE
        # ======================================

        self._run_state(
            sees_player
        )

    # ==========================================
    # STATE BEHAVIOR
    # ==========================================

    def _run_state(
        self,
        sees_player,
    ):

        # ======================================
        # PATROL
        # ======================================

        if self.state == GhostState.PATROL:

            self.navigation.follow_path(
                GHOST_PATROL_SPEED
            )

            if self.navigation.path_finished():

                self._choose_random_patrol_target()

        # ======================================
        # INVESTIGATE
        # ======================================

        elif self.state == GhostState.INVESTIGATE:

            self.navigation.follow_path(
                GHOST_INVESTIGATE_SPEED
            )

            if self.navigation.path_finished():

                self._set_state(
                    GhostState.SEARCH
                )

                self.search_time = (
                    GHOST_SEARCH_SECONDS
                )

        # ======================================
        # CHASE
        # ======================================

        elif self.state == GhostState.CHASE:

            # If the ghost can physically
            # see the player, chase directly.
            if sees_player:

                self.navigation.clear()

                self._move_directly_toward_player()

            # Otherwise use the waypoint path.
            else:

                self.navigation.follow_path(
                    GHOST_CHASE_SPEED
                )

        # ======================================
        # SEARCH
        # ======================================

        elif self.state == GhostState.SEARCH:

            # Slowly rotate while searching.
            self.ghost.rotation_y += (
                55 * time.dt
            )

            self.search_time -= time.dt

            # Give up after search timer ends.
            if self.search_time <= 0:

                self._set_state(
                    GhostState.PATROL
                )

                self._choose_random_patrol_target()

    # ==========================================
    # DIRECT CHASE
    # ==========================================

    def _move_directly_toward_player(
        self,
    ):

        self.ghost.look_at_2d(
            self.player.position,
            "y",
        )

        self.ghost.position += (
            self.ghost.forward
            * GHOST_CHASE_SPEED
            * time.dt
        )

    # ==========================================
    # RANDOM PATROL
    # ==========================================

    def _choose_random_patrol_target(
        self,
    ):

        # Find waypoint closest to ghost.
        start_node = nearest_node(
            self.ghost.position,
            self.nav_nodes,
        )

        # Don't choose current node.
        available_nodes = [

            node_id

            for node_id
            in self.nav_nodes

            if node_id != start_node
        ]

        if not available_nodes:

            self.navigation.clear()

            return

        # Pick random destination.
        target_node = random.choice(
            available_nodes
        )

        self.navigation.set_path_to_node(
            target_node
        )

    # ==========================================
    # CHANGE STATE
    # ==========================================

    def _set_state(
        self,
        new_state,
    ):

        if self.state == new_state:
            return

        self.state = new_state

        self._refresh_debug()

        if new_state != GhostState.CHASE:

            self.lost_sight_time = 0.0

    # ==========================================
    # DEBUG UI
    # ==========================================

    def _refresh_debug(self):

        self.hud.set_ghost_state(
            self.state.name
        )

    # ==========================================
    # PLAYER CAUGHT
    # ==========================================

    def _catch_player(self):

        self._set_state(
            GhostState.JUMPSCARE
        )

        self.jumpscare.trigger()