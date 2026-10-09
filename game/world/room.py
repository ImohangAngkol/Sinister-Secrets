from ursina import BoxCollider, Entity, Text, Vec3, color


class HidingSpot:
    """Interaction metadata on an existing cabinet, with collision-safe exits."""
    def __init__(self, prop, width, depth):
        self.prop = prop
        self.width, self.depth = width, depth
        self.occupant = None
        prop.hiding_spot = self
        prop.interaction_text = "[E] Hide in wardrobe"
        prop.interact = lambda player: player.enter_hiding(self)

    @property
    def view_yaw(self):
        return self.prop.world_rotation_y + 180

    @property
    def approach(self):
        return self.prop.world_position - self.prop.forward.normalized() * (self.depth / 2 + 0.8)

    def exit_candidates(self):
        front = self.approach
        right = self.prop.right.normalized()
        return (front, front + right * (self.width / 2 + 0.8), front - right * (self.width / 2 + 0.8),
                front - self.prop.forward.normalized() * 0.6)


class Room(Entity):
    """Room metadata and inexpensive geometric furniture; no imported assets."""

    def __init__(self, definition, **kwargs):
        # Even model-less containers inherit Ursina's default unlit shader.
        # Clear it so floors and furniture inherit House's generated lighting.
        super().__init__(name=definition["id"], shader=None, **kwargs)
        self.room_id = definition["id"]
        self.title = definition["name"]
        self.room_bounds = definition["bounds"]
        self.props = []
        x0, z0, x1, z1 = self.room_bounds
        Entity(parent=self, model="cube", shader=None, collider="box",
               position=((x0 + x1) / 2, -0.15, (z0 + z1) / 2),
               scale=(x1 - x0, 0.3, z1 - z0), color=color.rgb32(*definition["floor"]))
        self.sign = Text(parent=self, text=self.title.upper(), origin=(0, 0),
                         position=((x0 + x1) / 2, 2.7, z1 - 0.18),
                         scale=5, color=color.rgb32(194, 187, 169))
        for prop in definition["props"]:
            self.props.append(self._furniture(prop))

    def contains(self, position):
        x0, z0, x1, z1 = self.room_bounds
        return x0 <= position.x <= x1 and z0 <= position.z <= z1

    def _furniture(self, definition):
        kind = definition["kind"]
        defaults = {"console": (1.5, 0.7, 0.8), "bench": (2.2, 0.65, 0.8),
                    "sofa": (2.8, 1.15, 1.2), "table": (2, 0.95, 1.5),
                    "chair": (0.6, 1.15, 0.6), "cabinet": (1.2, 2, 0.7),
                    "counter": (1.2, 1, 3), "shelf": (1.1, 2.3, 2),
                    "boxes": (1.2, 1.2, 1.2), "bed": (1.9, 1.1, 3),
                    "bath": (1.6, 0.8, 3), "sink": (1, 1, 1),
                    "clock": (0.4, 2.2, 0.4), "plant": (0.8, 1.3, 0.8),
                    "steps": (1.8, 0.5, 2.1)}
        width, height, depth = definition.get("size", defaults[kind])
        prop = Entity(parent=self, name=kind, shader=None, position=definition["position"],
                      rotation_y=definition.get("rotation", 0))
        # One bounding collider per furniture assembly. Decorative legs and
        # cushions do not multiply traversal cost or create navigable traps.
        prop.collider = BoxCollider(prop, center=(0, height / 2, 0), size=(width, height, depth))
        tint = definition.get("tint", [87, 72, 60])

        def cube(position, scale, rgb=tint):
            return Entity(parent=prop, model="cube", shader=None, position=position,
                          scale=scale, color=color.rgb32(*rgb))

        if definition.get("hiding"):
            # Same footprint/collider as the old wardrobe. Hollow geometry
            # places the crouched camera inside, behind a narrow viewing slit.
            cube((-width / 2 + 0.025, height / 2, 0), (0.05, height, depth))
            cube((width / 2 - 0.025, height / 2, 0), (0.05, height, depth))
            cube((0, height / 2, depth / 2 - 0.025), (width, height, 0.05))
            cube((0, height - 0.025, 0), (width, 0.05, depth))
            for x in (-width / 4 - 0.045, width / 4 + 0.045):
                cube((x, height / 2, -depth / 2 + 0.025), (width / 2 - 0.09, height, 0.05))
            cube((0, 0.35, -depth / 2 + 0.025), (0.18, 0.7, 0.05))
            cube((0, (1.5 + height) / 2, -depth / 2 + 0.025), (0.18, height - 1.5, 0.05))
            HidingSpot(prop, width, depth)
        elif kind in ("table", "console", "bench"):
            cube((0, height - 0.07, 0), (width, 0.14, depth))
            for x in (-width / 2 + 0.1, width / 2 - 0.1):
                for z in (-depth / 2 + 0.1, depth / 2 - 0.1):
                    cube((x, (height - 0.14) / 2, z), (0.14, height - 0.14, 0.14), [47, 43, 41])
        elif kind in ("sofa", "chair"):
            cube((0, 0.35, 0), (width, 0.55, depth))
            cube((0, 0.85, depth / 2 - 0.1), (width, 0.6, 0.2))
        elif kind == "bed":
            cube((0, 0.25, 0), (width, 0.5, depth), [65, 55, 50])
            cube((0, 0.6, -0.2), (width - 0.12, 0.2, depth - 0.4))
            cube((0, 0.73, depth / 2 - 0.6), (width - 0.25, 0.18, 0.65), [137, 130, 124])
            cube((0, 0.75, depth / 2 - 0.07), (width, 0.7, 0.14), [65, 55, 50])
        elif kind == "shelf":
            cube((-width / 2 + 0.06, height / 2, 0), (0.12, height, depth))
            cube((width / 2 - 0.06, height / 2, 0), (0.12, height, depth))
            for y in (0.15, 0.8, 1.5, height - 0.08):
                cube((0, y, 0), (width, 0.12, depth))
        elif kind == "counter":
            cube((0, height / 2, 0), (width, height, depth), [62, 75, 68])
            cube((0, height + 0.04, 0), (width + 0.04, 0.08, depth), [113, 116, 111])
        elif kind in ("bath", "sink"):
            cube((0, height / 2, 0), (width, height, depth), [127, 139, 139])
            cube((0, height + 0.01, 0), (width * 0.72, 0.035, depth * 0.8), [60, 78, 82])
        elif kind == "plant":
            cube((0, 0.25, 0), (0.55, 0.5, 0.55), [91, 62, 47])
            cube((0, 0.9, 0), (width, 0.8, depth))
        elif kind == "steps":
            for step in range(3):
                cube((-width / 2 + width * (step + 0.5) / 3, height * (step + 1) / 6, 0),
                     (width / 3, height * (step + 1) / 3, depth), [67, 68, 72])
        else:
            cube((0, height / 2, 0), (width, height, depth))
            if kind == "clock":
                cube((0, height - 0.35, -depth / 2 - 0.01), (width * 0.7, 0.3, 0.025), [150, 139, 118])
            elif kind == "cabinet":
                cube((0, height / 2, -depth / 2 - 0.01), (0.04, height * 0.9, 0.025), [44, 39, 35])
        return prop
