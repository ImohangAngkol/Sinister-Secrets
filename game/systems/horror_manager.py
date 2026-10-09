"""Seeded, bounded disturbances. No gameplay colliders, tasks, or extra lights."""
import math
import random
from collections import deque
from dataclasses import dataclass

from ursina import Entity, Text, Vec3, Vec4, application, camera, color, destroy
from ursina.shaders import unlit_shader
from game import settings
from game.ghost.ghost_states import GhostState
from game.world.environment import world_raycast


@dataclass(frozen=True)
class EventDefinition:
    name: str
    category: str
    seconds: float
    rooms: tuple = ()
    minimum_tension: float = 0


EVENTS = (
    EventDefinition("room_dimming", "lighting", 5),
    EventDefinition("power_dip", "lighting", 4),
    EventDefinition("hallway_dim", "lighting", 6, ("main_hall",)),
    EventDefinition("fill_failure", "lighting", 4, minimum_tension=.25),
    EventDefinition("prop_shift", "environment", 4),
    EventDefinition("prop_vibration", "environment", 3),
    EventDefinition("cabinet_creak", "environment", 5, ("living",)),
    EventDefinition("distant_close", "environment", 3, ("living",)),
    EventDefinition("apparition", "apparition", 6, minimum_tension=.25),
    EventDefinition("shadow_pass", "apparition", 4, minimum_tension=.20),
)


class TensionDirector:
    def __init__(self):
        self.tension = 0.0
        self.exploration_seconds = 0.0
        self.last_chase = -1000.0
        self.last_hiding = -1000.0
        self.quiet_until = 0.0
        self._was_chasing = False
        self._was_hidden = False

    def update(self, dt, clock, player, ghost, since_event):
        self.exploration_seconds += dt
        chasing = ghost.ai.state == GhostState.CHASE
        if chasing:
            self.last_chase = clock
        if self._was_chasing and not chasing:
            self.quiet_until = max(self.quiet_until, clock + settings.HORROR_POST_CHASE_QUIET_SECONDS)
        if player.hidden:
            self.last_hiding = clock
        if self._was_hidden and not player.hidden:
            self.quiet_until = max(self.quiet_until, clock + 8)
        self._was_chasing, self._was_hidden = chasing, player.hidden
        progression = player.progression
        progress = sum((progression.power_restored, progression.safe_unlocked, progression.boards_removed)) / 3
        proximity = max(0, 1 - (ghost.world_position-player.world_position).length()/12)
        recent_chase = max(0, 1-(clock-self.last_chase)/30)
        recent_hiding = max(0, 1-(clock-self.last_hiding)/20)
        target = (.08 + min(.22,self.exploration_seconds/600) + .20*progress + .22*proximity
                  + .20*recent_chase + .08*recent_hiding + .10*min(1,since_event/90))
        self.tension += (min(1,target)-self.tension)*(1-math.exp(-dt/5))


def destroy_temporary(root):
    """Ursina 8.3 children before parents, without delayed destroy callbacks."""
    for child in reversed(root.children):
        destroy_temporary(child)
    destroy(root)


def descendants(root):
    for child in root.children:
        yield child
        yield from descendants(child)


class HorrorManager:
    def __init__(self, house, player, ghost, lights, seed=None, frequency=None):
        self.house, self.player, self.ghost, self.lights = house, player, ghost, lights
        self.rng = random.Random(settings.HORROR_SEED if seed is None else seed)
        self.frequency = min(3,max(0, settings.HORROR_EVENT_FREQUENCY if frequency is None else frequency))
        self.director = TensionDirector()
        self.clock = 0.0
        self._accumulator = 0.0
        self.next_check = settings.HORROR_INITIAL_QUIET_SECONDS / max(self.frequency,.01)
        self.next_allowed = self.next_check
        self.last_event = 0.0
        self.active = None
        self.running = True
        self.history = deque(maxlen=64)
        self.previous_room = None
        self.room_entered = -1000.0

    def protected(self):
        player = self.player
        return (not self.running or not player.enabled or application.paused or player.hud.panel.active
                or player.hidden or self.ghost.ai.state in (GhostState.CHASE,GhostState.JUMPSCARE)
                or any((player.world_position-prop.world_position).length() < 3
                       for prop in self.house.puzzles.values() if prop.enabled)
                or self.house.exit_door.opening)

    def safe_visuals(self, room):
        # Only decorative children move. Assembly colliders, wardrobes, pickups,
        # and all support geometry near puzzle items remain untouched.
        if room.room_id not in ("living","dining","bedroom_one","bathroom","main_hall"):
            return []
        return [child for prop in room.props if not hasattr(prop,"hiding_spot")
                and prop.name != "console" and not (room.room_id=="dining" and prop.name=="cabinet")
                for child in prop.children if child.model and not child.collider and not isinstance(child,Text)]

    def apparition_position(self):
        options = []
        for name, position in sorted(self.house.nav_nodes.items()):
            target = position + Vec3(0,1,0)
            delta = target-camera.world_position
            if not 5 <= delta.length() <= 14 or camera.forward.dot(delta.normalized()) < .65:
                continue
            if not world_raycast(camera.world_position, delta, distance=delta.length(),
                                 traverse_target=self.house, ignore=[self.player,self.ghost]).hit:
                options.append((name,position))
        return options

    def eligible_events(self):
        if self.frequency <= 0 or self.protected() or not self.player.has_flashlight or self.clock < self.director.quiet_until:
            return []
        room = self.house.room_at(self.player.world_position)
        if room is None:
            return []
        visuals = self.safe_visuals(room)
        return [event for event in EVENTS
                if (not event.rooms or room.room_id in event.rooms)
                and event.minimum_tension <= self.director.tension
                and (event.category != "environment" or visuals)
                and (event.category != "apparition" or self.apparition_position())
                and (event.name != "distant_close" or self.clock-self.room_entered <= 10)]

    def update(self, dt):
        if not self.running or application.paused:
            return
        if self.protected():
            self.cancel_active()
        self._accumulator += max(0,dt)
        # Fixed director ticks make RNG decisions and envelopes FPS independent.
        while self._accumulator >= 1/30-1e-9:
            self._accumulator = max(0,self._accumulator-1/30)
            self.clock += 1/30
            room = self.house.room_at(self.player.world_position)
            room_id = room.room_id if room else None
            if room_id != self.previous_room:
                self.previous_room, self.room_entered = room_id,self.clock
            self.director.update(1/30,self.clock,self.player,self.ghost,self.clock-self.last_event)
            if self.active:
                self._advance_event(1/30)
            if self.clock >= self.next_check-1e-8:
                self.next_check += settings.HORROR_CHECK_SECONDS/max(self.frequency,.01)
                if (self.frequency > 0 and self.active is None and self.clock >= self.next_allowed
                        and self.clock >= self.director.quiet_until):
                    eligible = self.eligible_events()
                    if eligible and self.rng.random() < .18+.32*self.director.tension:
                        weights = [max(0,settings.HORROR_CATEGORY_WEIGHTS.get(e.category,0)) /
                                   sum(other.category==e.category for other in eligible) for e in eligible]
                        if sum(weights) > 0:
                            self.start_event(self.rng.choices(eligible,weights=weights,k=1)[0].name)

    def start_event(self, name):
        """Developer/test hook obeys safety and cooldowns just like scheduling."""
        if self.active or self.clock < self.next_allowed-1e-8:
            return False
        definition = next((e for e in self.eligible_events() if e.name==name),None)
        if definition is None:
            return False
        room = self.house.room_at(self.player.world_position)
        intensity = min(max(0,settings.HORROR_INTENSITY_LIMIT), .30+.60*self.director.tension)
        self.active = dict(definition=definition, elapsed=0.0, room=room, intensity=intensity,
                           colors=[], transforms=[], temporary=[])
        active = self.active
        if definition.name in ("power_dip","fill_failure"):
            active['colors'] = [(light,Vec4(light.color)) for light in self.lights]
        elif definition.category == "lighting":
            x0,z0,x1,z1 = room.room_bounds
            walls = [wall for wall in self.house.walls
                     if x0-.2 <= wall.x <= x1+.2 and z0-.2 <= wall.z <= z1+.2]
            models = [entity for entity in descendants(room) if entity.model and not isinstance(entity,Text)]
            active['colors'] = [(entity,Vec4(entity.color)) for entity in (*models,*walls)]
        elif definition.category == "environment":
            if name in ("cabinet_creak","distant_close"):
                prop = next(p for p in room.props if p.name=='cabinet' and not hasattr(p,'hiding_spot'))
                # Decorative door on an already solid furniture assembly. It
                # cannot open a route, change locks, or move its collider.
                leaf = Entity(parent=prop, model='cube', shader=None, origin_x=-.5,
                              position=(-.5,.85,-.36), scale=(1,1.6,.045), color=color.rgb32(72,57,45))
                active['temporary'].append(leaf)
                active['transforms'].append((leaf,Vec3(leaf.position),Vec3(leaf.rotation)))
            else:
                visual = self.rng.choice(self.safe_visuals(room))
                active['transforms'].append((visual,Vec3(visual.position),Vec3(visual.rotation)))
        else:
            _, position = self.rng.choice(self.apparition_position())
            silhouette = Entity(parent=self.house, model='cube', shader=unlit_shader, collider=None,
                                position=position+Vec3(0,.75,0), scale=(.6,1.3,.045),
                                color=color.rgb32(15,16,22))
            Entity(parent=silhouette,model='cube',shader=None,position=(0,.63,0),
                   scale=(.48,.27,1),color=color.rgb32(15,16,22))
            silhouette.look_at_2d(self.player.world_position,'y')
            active['temporary'].append(silhouette)
            active['transforms'].append((silhouette,Vec3(silhouette.position),Vec3(silhouette.rotation)))
        self.history.append((round(self.clock,6),name,room.room_id,round(intensity,6)))
        self.last_event = self.clock
        return True

    def _advance_event(self, dt):
        active = self.active
        active['elapsed'] = min(active['definition'].seconds,active['elapsed']+dt)
        event = active['definition']
        elapsed, duration, intensity = active['elapsed'],event.seconds,active['intensity']
        envelope = math.sin(math.pi*elapsed/duration)**2
        if event.category == 'lighting':
            if not settings.HORROR_REDUCED_FLICKER and event.name != 'fill_failure':
                envelope *= .75+.25*math.cos(2*math.pi*elapsed*.8)
            factor = 1-.55*intensity*envelope
            for entity, original in active['colors']:
                if not entity.is_empty():
                    scale = (1-envelope if event.name=='fill_failure' and entity==self.lights[1] else factor)
                    entity.color = color.rgba(original.x*scale,original.y*scale,original.z*scale,original.w)
        elif event.category == 'environment':
            for entity, position, rotation in active['transforms']:
                if event.name in ('cabinet_creak','distant_close'):
                    angle = (18*envelope if event.name=='cabinet_creak' else 18*(1-elapsed/duration))
                    entity.rotation_y = rotation.y + angle*intensity
                elif event.name == 'prop_shift':
                    entity.position = position + Vec3(.22*intensity*envelope,0,0)
                    entity.rotation_y = rotation.y + 8*intensity*envelope
                else:
                    entity.rotation_z = rotation.z + 2*intensity*envelope*math.sin(elapsed*12)
        else:
            entity, position, _ = active['transforms'][0]
            delta = entity.world_position-camera.world_position
            lit = (self.player.flashlight_on and self.player.flashlight_light.color.r>0
                   and delta.length()<settings.FLASHLIGHT_RANGE
                   and camera.forward.dot(delta.normalized())>math.cos(math.radians(settings.FLASHLIGHT_FOV/2))
                   and not world_raycast(camera.world_position,delta,distance=delta.length(),
                                         traverse_target=self.house,ignore=[self.player,self.ghost]).hit)
            if delta.length()<2.5 or lit:
                self.cancel_active()
                return
            if event.name=='shadow_pass':
                entity.position = position + entity.right*.8*intensity*envelope
        if elapsed >= duration-1e-8:
            self.cancel_active()

    def cancel_active(self):
        if self.active is None:
            return
        active, self.active = self.active, None
        for entity, original in active['colors']:
            if not entity.is_empty():
                entity.color = original
        for entity, position, rotation in active['transforms']:
            if not entity.is_empty():
                entity.position,entity.rotation = position,rotation
        for entity in active['temporary']:
            if not entity.is_empty():
                destroy_temporary(entity)
        self.next_allowed = self.clock + self.rng.uniform(*settings.HORROR_COOLDOWN_SECONDS)/max(self.frequency,.01)

    def stop(self):
        self.cancel_active()
        self.running = False
        self._accumulator = 0
