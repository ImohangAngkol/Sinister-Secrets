"""Geometry builder for the fixed, data-authored haunted house."""
from ursina import Entity, Mesh, Vec3, color
from game.systems.asset_manager import assets

from game.items.battery import BatteryPickup
from game.items.flashlight import FlashlightPickup
from game.items.key import KeyPickup
from game.items.item import InventoryPickup
from game.levels.haunted_house import load_level, room_connections, wall_segments
from game.world.exit_door import ExitDoor
from game.world.locked_door import LockedDoor
from game.world.room import Room
from game.world.waypoint import Waypoint
from game.world.puzzles import PuzzleProp


class House(Entity):
    def __init__(self, on_escape):
        super().__init__()
        self.set_shader_auto()
        self.level = load_level()
        data = self.level.house
        self.room_graph = room_connections(data)
        self.rooms = {room["id"]: Room(room, parent=self) for room in data["rooms"]}
        self.hiding_spots = tuple(prop.hiding_spot for room in self.rooms.values()
                                  for prop in room.props if hasattr(prop, "hiding_spot"))
        self.player_spawn = Vec3(*self.level.spawns["player"]["position"])
        self.ghost_spawn = Vec3(*self.level.spawns["ghost"]["position"])
        self.walls = []
        self.door_frames = []
        self.pickups = {}
        height, thickness = data["wall_height"], data["wall_thickness"]
        for axis, line, low, high in wall_segments(data):
            center, length = (low + high) / 2, high - low
            position = (line, height / 2, center) if axis == "x" else (center, height / 2, line)
            scale = (thickness, height, length) if axis == "x" else (length, height, thickness)
            self.walls.append(self._wall(position, scale))
        for definition in data["extra_walls"]:
            self.walls.append(self._wall(definition["position"], definition["scale"]))
        for opening in (*data["connections"], data["exit_opening"]):
            self._door_frame(opening)
        x0, z0, x1, z1 = data["bounds"]
        self.ceiling = Entity(parent=self, model="cube", shader=None, collider="box",
                              position=((x0 + x1) / 2, height + 0.1, (z0 + z1) / 2),
                              scale=(x1 - x0, 0.2, z1 - z0), color=color.rgb32(73, 75, 80))
        # A short landing keeps the exit crossing grounded before the win callback.
        Entity(parent=self, model="cube", shader=None, collider="box",
               position=(0, -0.15, 19.5), scale=(4, 0.3, 3), color=color.rgb32(60, 63, 66))
        self._build_navigation()
        self._place_items(on_escape)
        self.puzzles = {definition["id"]: PuzzleProp(definition, parent=self)
                        for definition in data["progression"]["props"]}
        self.assets = assets
        self._presentation_quality = None
        self._build_presentation()
        self.apply_presentation({'texture_quality':'standard','decorative_detail':'standard'})

    def _build_presentation(self):
        from game.systems.horror_manager import descendants
        self.decorations = Entity(parent=self, shader=None)
        vertices, triangles, uvs, normals = [], [], [], []
        # Bake all skirting into one non-colliding mesh, inside wall footprints.
        corners = [(-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),
                   (1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1)]
        faces = [(0,4,6,2),(5,1,3,7),(1,0,2,3),(4,5,7,6),(2,6,7,3),(1,5,4,0)]
        face_normals = [(0,0,-1),(0,0,1),(-1,0,0),(1,0,0),(0,1,0),(0,-1,0)]
        for wall in self.walls:
            center = Vec3(wall.position);center.y = .105
            size = Vec3(wall.scale);size.y = .21
            size.x += .035;size.z += .035
            for face, normal in zip(faces,face_normals):
                base=len(vertices)
                for index, uv in zip(face,((0,0),(1,0),(1,1),(0,1))):
                    c=corners[index]
                    vertices.append(tuple(center+Vec3(c[0]*size.x/2,c[1]*size.y/2,c[2]*size.z/2)))
                    uvs.append(uv);normals.append(normal)
                triangles.extend([(base,base+2,base+1),(base,base+3,base+2)])
        trim=Entity(parent=self.decorations,shader=None,
                    model=Mesh(vertices=vertices,triangles=triangles,uvs=uvs,normals=normals),
                    color=color.rgb32(67,58,49),collider=None)
        trim.material_name='wood'
        for wall in self.walls:
            wall.material_name='wallpaper'
            wall.material_scale=(max(wall.scale_x,wall.scale_z)/2,wall.scale_y/2)
        self.ceiling.material_name='plaster'
        self.ceiling.material_scale=(8,8)
        for frame in self.door_frames:
            frame.material_name='wood'
        for name in self.level.doors:
            door=getattr(self,name)
            door.material_name='wood'
            door.material_scale=(1,2)
            # Non-colliding metal handle attached to the existing animated leaf.
            Entity(parent=door,shader=None,model='cube',position=(.83,.52,-.58),
                   scale=(.10,.025,.18),color=color.rgb32(112,103,78),collider=None)
        for prop in self.puzzles.values():
            prop.material_name='wood' if prop.puzzle_id=='boards' else 'metal'
        self._build_story_details()
        self.material_surfaces=[entity for entity in descendants(self) if hasattr(entity,'material_name')]

    def _build_story_details(self):
        # One baked mesh, within existing furniture/wall footprints. No
        # collision, update callbacks, lights, or new navigation obstacles.
        frame = [((-3.5,.72,-17),(1,.06,.56),(79,61,45)),
                 ((-3.5,.76,-17),(.85,.025,.42),(126,119,101))]
        # An abstract family portrait is procedural geometry, not a bitmap.
        for x,height in ((-3.75,.12),(-3.5,.12),(-3.28,.08)):
            frame.append(((x,.78,-17),(.10,.015,height),(58,61,59)))
        for i in range(5):
            frame.append(((15.43,1.05+i*.09,-5.52),(.018,.025,.33),(43,36,31)))
        frame.append(((8.7,.755,8.55),(.28,.012,.07),(115,64,66)))  # Elsie's ribbon
        frame.append(((8.8,.73,-8.45),(.22,.04,.13),(71,63,51)))  # packed case
        details = Entity(parent=self.decorations,shader=None,collider=None,
                         model=self.assets.box_mesh('story_details',frame))
        details.material_name='wood'
        # Keep photograph faces and ribbon colours independent of inherited
        # entity tint; standard lighting still illuminates vertex colours.

    def apply_presentation(self, values):
        quality=values['texture_quality']
        self.decorations.enabled=values['decorative_detail']=='standard'
        if quality == self._presentation_quality:
            return
        for entity in self.material_surfaces:
            if not entity.is_empty():
                entity.texture=self.assets.texture(entity.material_name,quality)
                entity.texture_scale=getattr(entity,'material_scale',(1,1))
        self._presentation_quality=quality

    def _wall(self, position, scale):
        return Entity(parent=self, model="cube", shader=None, collider="box",
                      position=position, scale=scale, color=color.rgb32(110, 112, 119))

    def _door_frame(self, opening):
        axis, line, center, width = (opening[key] for key in ("axis", "line", "at", "width"))
        for offset in (-width / 2 - 0.06, width / 2 + 0.06):
            position = (line, 1.6, center + offset) if axis == "x" else (center + offset, 1.6, line)
            scale = (0.38, 3.2, 0.18) if axis == "x" else (0.18, 3.2, 0.38)
            # Exterior trim overlaps the door edge to seal collider seams.
            # Interior frames share existing walls and need no extra collider.
            self.door_frames.append(Entity(parent=self, model="cube", shader=None,
                                           position=position, scale=scale,
                                           collider="box" if "id" not in opening else None,
                                           color=color.rgb32(77, 65, 57)))
        position = (line, 3.06, center) if axis == "x" else (center, 3.06, line)
        scale = (0.38, 0.28, width) if axis == "x" else (width, 0.28, 0.38)
        self.door_frames.append(Entity(parent=self, model="cube", shader=None,
                                       position=position, scale=scale, color=color.rgb32(77, 65, 57)))

    def _build_navigation(self):
        # Preserve Panda3D Entity.nodes; level IDs live in nav_nodes.
        self.waypoints = {node: Waypoint(node, Vec3(*position))
                          for node, position in self.level.navigation["nodes"].items()}
        self.nav_nodes = {node: waypoint.position for node, waypoint in self.waypoints.items()}
        self.graph = {node: [] for node in self.nav_nodes}
        for a, b in self.level.navigation["edges"]:
            self.graph[a].append(b)
            self.graph[b].append(a)
        self.patrol_targets = tuple(self.level.navigation["patrol_targets"])

    def _place_items(self, on_escape):
        for spawn in self.level.spawns["pickups"]:
            kind = spawn["item"]
            args = {"parent": self, "position": spawn["position"]}
            if kind == "flashlight":
                item = FlashlightPickup(**args)
            elif kind == "battery":
                item = BatteryPickup(amount=self.level.items[kind]["restore"], **args)
            elif self.level.items[kind]["type"] == "key":
                item = KeyPickup(key_id=kind, key_name="Exit Key", **args)
            else:
                item = InventoryPickup(kind, self.level.items[kind], **args)
            item.spawn_id = spawn["id"]
            item.enabled = not spawn.get("requires")
            self.pickups[spawn["id"]] = item
        exit_data, basement_data = self.level.doors["exit_door"], self.level.doors["basement_door"]

        def door_args(definition):
            return {key: definition[key] for key in
                    ("position", "scale", "rotation_y", "required_key", "locked_message")}

        self.exit_door = ExitDoor(parent=self, on_escape=on_escape, **door_args(exit_data))
        self.basement_door = LockedDoor(parent=self, **door_args(basement_data))
        self.basement_door.interaction_text = "[E] Basement entrance (sealed)"

    def room_at(self, position):
        return next((room for room in self.rooms.values() if room.contains(position)), None)
