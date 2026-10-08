from ursina import Entity, Vec3, color

from game.items.battery import BatteryPickup
from game.items.flashlight import FlashlightPickup
from game.items.key import KeyPickup
from game.settings import EXIT_KEY_ID
from game.world.exit_door import ExitDoor


class House(Entity):

    def __init__(self, on_escape):
        super().__init__()
        # Panda's generated shader supports ambient, directional and spot lights.
        self.set_shader_auto()

        # =====================================
        # SPAWN LOCATIONS
        # =====================================

        self.player_spawn = Vec3(
            -10,
            1,
            -10,
        )

        self.ghost_spawn = Vec3(
            10,
            0,
            10,
        )

        self._build_house()

        self._build_navigation()

        self._place_items(
            on_escape
        )

    # =========================================
    # WALL CREATOR
    # =========================================

    def _wall(
        self,
        position,
        scale,
    ):

        return Entity(
            parent=self,

            model="cube",

            position=position,

            scale=scale,

            shader=None,
            color=color.rgb32(
                125,
                129,
                138,
            ),

            collider="box",
        )

    # =========================================
    # BUILD HOUSE
    # =========================================

    def _build_house(self):

        # =====================================
        # FLOOR
        # =====================================

        Entity(
            parent=self,

            model="cube",

            position=(
                0,
                -0.15,
                0,
            ),

            scale=(
                30,
                0.3,
                30,
            ),

            shader=None,
            color=color.rgb32(
                60,
                63,
                69,
            ),

            collider="box",
        )

        # IMPORTANT:
        #
        # No ceiling yet.
        #
        # This makes debugging the prototype
        # much easier.

        # =====================================
        # OUTSIDE WALLS
        # =====================================

        self._wall(
            (-15, 1.5, 0),
            (0.4, 3, 30),
        )

        self._wall(
            (15, 1.5, 0),
            (0.4, 3, 30),
        )

        self._wall(
            (0, 1.5, -15),
            (30, 3, 0.4),
        )

        # =====================================
        # NORTH WALL
        # =====================================
        #
        # Gap near the right side is
        # where our exit door goes.

        self._wall(
            (-3.25, 1.5, 15),
            (23.5, 3, 0.4),
        )

        self._wall(
            (13.25, 1.5, 15),
            (3.5, 3, 0.4),
        )

        # =====================================
        # INTERIOR WALLS
        # =====================================

        # SOUTH VERTICAL WALL

        self._wall(
            (0, 1.5, -9),
            (0.4, 3, 12),
        )

        # NORTH VERTICAL WALL

        self._wall(
            (0, 1.5, 9),
            (0.4, 3, 12),
        )

        # WEST HORIZONTAL WALL

        self._wall(
            (-9, 1.5, 0),
            (12, 3, 0.4),
        )

        # EAST HORIZONTAL WALL

        self._wall(
            (9, 1.5, 0),
            (12, 3, 0.4),
        )

        # =====================================
        # DEBUG LANDMARKS
        # =====================================

        # These are temporary cubes so you
        # can understand where you are.

        Entity(
            parent=self,
            model="cube",
            position=(-12, 0.5, -12),
            scale=(1, 1, 1),
            color=color.red,
            shader=None,
            collider="box",
        )

        Entity(
            parent=self,
            model="cube",
            position=(12, 0.5, 12),
            scale=(1, 1, 1),
            color=color.green,
            shader=None,
            collider="box",
        )

    # =========================================
    # GHOST NAVIGATION
    # =========================================

    def _build_navigation(self):

        # DO NOT rename this to self.nodes.
        #
        # Panda3D already uses the name
        # "nodes".

        self.nav_nodes = {

            0: Vec3(
                -10,
                0,
                -10,
            ),

            1: Vec3(
                -4,
                0,
                -4,
            ),

            2: Vec3(
                0,
                0,
                0,
            ),

            3: Vec3(
                4,
                0,
                -4,
            ),

            4: Vec3(
                10,
                0,
                -10,
            ),

            5: Vec3(
                4,
                0,
                4,
            ),

            6: Vec3(
                10,
                0,
                10,
            ),

            7: Vec3(
                10,
                0,
                13,
            ),

            8: Vec3(
                -4,
                0,
                4,
            ),

            9: Vec3(
                -10,
                0,
                10,
            ),
        }

        # =====================================
        # CONNECTION GRAPH
        # =====================================

        self.graph = {

            0: [1],

            1: [
                0,
                2,
            ],

            2: [
                1,
                3,
                5,
                8,
            ],

            3: [
                2,
                4,
            ],

            4: [
                3,
            ],

            5: [
                2,
                6,
            ],

            6: [
                5,
                7,
            ],

            7: [
                6,
            ],

            8: [
                2,
                9,
            ],

            9: [
                8,
            ],
        }

    # =========================================
    # ITEMS
    # =========================================

    def _place_items(
        self,
        on_escape,
    ):

        # =====================================
        # FLASHLIGHT
        # =====================================
        #
        # BRIGHT WHITE rectangular object
        # close to spawn.

        FlashlightPickup(
            parent=self,

            position=(
                -8,
                0.5,
                -10,
            ),
        )

        # =====================================
        # BATTERY
        # =====================================
        #
        # BLUE object.

        BatteryPickup(
            parent=self,

            position=(
                -10,
                0.5,
                9,
            ),

            amount=35,
        )

        # =====================================
        # EXIT KEY
        # =====================================
        #
        # YELLOW object.

        KeyPickup(
            parent=self,

            position=(
                10,
                0.5,
                -9,
            ),

            key_id=EXIT_KEY_ID,

            key_name="Exit Key",
        )

        # =====================================
        # EXIT DOOR
        # =====================================

        self.exit_door = ExitDoor(
            parent=self,

            position=(
                8.5,
                0,
                14.75,
            ),

            scale=(
                3.0,
                3.0,
                0.35,
            ),

            required_key=EXIT_KEY_ID,

            locked_message=(
                "The exit is locked. "
                "Find the exit key."
            ),

            on_escape=on_escape,
        )
