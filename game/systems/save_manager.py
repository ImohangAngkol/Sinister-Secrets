"""Versioned local snapshots. Only JSON data crosses the persistence boundary."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
from uuid import UUID

from game.levels.haunted_house import load_level
from game import settings

log = logging.getLogger(__name__)
SAVE_VERSION = 1
SAVE_DIRECTORY = Path(__file__).resolve().parents[1] / 'data'
SLOTS = {'manual': 'manual_save.json', 'checkpoint': 'checkpoint_save.json'}
FLAGS = ('power_restored', 'safe_unlocked', 'boards_removed')


class SaveError(ValueError):
    pass


def number(value, low, high, name):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise SaveError(f'Invalid {name}')
    return value


def boolean(value, name):
    if type(value) is not bool:
        raise SaveError(f'Invalid {name}')
    return value


def validate_save(document, level=None):
    """Validate critical types and cross-field puzzle/item invariants before use."""
    level = level or load_level()
    try:
        data = deepcopy(document)
        if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != SAVE_VERSION:
            raise SaveError('Unsupported save version')
        if data['level'] != 'haunted_house_v1' or data['slot'] not in SLOTS:
            raise SaveError('Incompatible level or slot')
        if not isinstance(data['session'], str):
            raise SaveError('Invalid session ID')
        UUID(data['session'])
        stamp = datetime.fromisoformat(data['timestamp'])
        if stamp.utcoffset() is None:
            raise SaveError('Save timestamp must include timezone')
        player, world, inventory, progress = data['player'], data['world'], data['inventory'], data['progression']
        if not all(isinstance(section, dict) for section in (player, world, inventory, progress)):
            raise SaveError('Invalid save sections')
        position = player['position']
        if not isinstance(position, list) or len(position) != 3:
            raise SaveError('Invalid player position')
        x0,z0,x1,z1 = level.house['bounds']
        number(position[0], x0+.35, x1-.35, 'player X')
        number(position[1], -.05, .05, 'player floor height')
        number(position[2], z0+.35, z1-.35, 'player Z')
        number(player['yaw'], -180, 180, 'yaw')
        number(player['pitch'], -90, 90, 'pitch')
        rotation = player.setdefault('camera_rotation', [0,0,0])
        if not isinstance(rotation, list) or len(rotation) != 3:
            raise SaveError('Invalid camera rotation')
        for value in rotation:
            number(value, -180, 180, 'camera rotation')
        number(player['battery'], 0, settings.MAX_BATTERY, 'battery')
        number(player['stamina'], 0, settings.STAMINA_MAX, 'stamina')
        boolean(player['flashlight_on'], 'flashlight state')
        boolean(player.setdefault('crouching', False), 'crouching')
        boolean(player.setdefault('sprint_exhausted', player['stamina']==0), 'exhaustion')
        number(player.setdefault('regen_delay', 0), 0, settings.STAMINA_REGEN_DELAY, 'regeneration delay')
        number(player.setdefault('camera_height', 1 if player['crouching'] else settings.PLAYER_HEIGHT),
               settings.PLAYER_CROUCH_HEIGHT, settings.PLAYER_HEIGHT, 'camera height')
        if player['stamina']==0 and not player['sprint_exhausted']:
            raise SaveError('Exhausted stamina state is inconsistent')
        for flag in FLAGS:
            boolean(progress[flag], flag)
        if (progress['safe_unlocked'] and not progress['power_restored'] or
                progress['boards_removed'] and not progress['safe_unlocked']):
            raise SaveError('Puzzle dependencies are inconsistent')
        collected = world['collected']
        pickups = {p['id']:p for p in level.spawns['pickups']}
        if (not isinstance(collected, list) or not all(isinstance(item,str) for item in collected)
                or len(set(collected)) != len(collected) or not set(collected) <= pickups.keys()):
            raise SaveError('Invalid collected pickup IDs')
        available = Counter(pickups[item]['item'] for item in collected)
        for item_id, quantity in inventory.items():
            if item_id not in level.items or type(quantity) is not int or not 1 <= quantity <= 99:
                raise SaveError('Invalid inventory item or quantity')
            if level.items[item_id].get('unique') and quantity != 1:
                raise SaveError('Unique item duplicated')
        for spawn_id in collected:
            required = pickups[spawn_id].get('requires')
            if required and not progress[required]:
                raise SaveError('Collected pickup bypasses a puzzle gate')
        expected = dict(available)
        if progress['power_restored']:
            if available['fuse'] != 1:
                raise SaveError('Installed fuse was not collected')
            expected.pop('fuse', None)
        if progress['safe_unlocked']:
            expected['crowbar'] = 1
        # Batteries may be consumed. All essential items and notes are retained.
        expected['battery'] = inventory.get('battery', 0)
        if expected['battery'] > available['battery']:
            raise SaveError('Stored batteries exceed collected supply')
        expected = {k:v for k,v in expected.items() if v}
        if expected != inventory:
            raise SaveError('Inventory and persistent world state disagree')
        if player['flashlight_on'] and (not inventory.get('flashlight') or player['battery'] <= 0):
            raise SaveError('An unavailable flashlight cannot be on')
        doors = world['doors']
        if not isinstance(doors, dict) or set(doors) != set(level.doors):
            raise SaveError('Invalid door IDs')
        for door_id, opened in doors.items():
            boolean(opened, door_id)
        if doors['basement_door'] or doors['exit_door'] and not inventory.get('exit_key'):
            raise SaveError('Door bypasses a required key')
        if data['slot'] == 'checkpoint' and data.get('milestone') not in ('power','lockbox','exit_key'):
            raise SaveError('Invalid checkpoint milestone')
        if data['slot'] == 'checkpoint':
            complete = dict(power=progress['power_restored'], lockbox=progress['safe_unlocked'],
                            exit_key=bool(inventory.get('exit_key')))
            if not complete[data['milestone']]:
                raise SaveError('Checkpoint milestone has not been completed')
            foyer = level.navigation['nodes']['foyer']
            if position != foyer:
                raise SaveError('Checkpoint respawn must be the authored foyer')
        return data
    except SaveError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise SaveError('Missing or invalid critical save fields') from error


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SaveError('Duplicate JSON field')
        result[key] = value
    return result


class SaveManager:
    def __init__(self, directory=SAVE_DIRECTORY):
        self.directory = Path(directory)
        self.error = ''

    def path(self, slot):
        if slot not in SLOTS:
            raise SaveError('Unknown save slot')
        return self.directory / SLOTS[slot]

    def load(self, slot='manual'):
        path = self.path(slot)
        try:
            if not path.exists():
                self.error = f'No {slot} save exists.'
                return None
            if path.stat().st_size > 65536:
                raise SaveError('Save file exceeds size limit')
            data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_pairs,
                              parse_constant=lambda value: (_ for _ in ()).throw(SaveError('Non-finite JSON number')))
            data = validate_save(data)
            if data['slot'] != slot:
                raise SaveError('Save slot does not match file')
            self.error = ''
            return data
        except (OSError, UnicodeError, ValueError, RecursionError) as error:
            self.error = f'{slot.title()} save unavailable: {error}'
            log.warning('%s', self.error)
            return None

    def available(self):
        """Manual Continue has priority; checkpoint is a fallback, never a replacement."""
        return next(((slot, data) for slot in SLOTS if (data := self.load(slot)) is not None), None)

    def exists(self):
        return any(self.path(slot).exists() for slot in SLOTS)

    def clear_checkpoint(self):
        # New Game confirmation authorizes only this single, known local file.
        self.path('checkpoint').unlink(missing_ok=True)

    def save(self, document, slot='manual'):
        data = validate_save(document)
        if data['slot'] != slot:
            raise SaveError('Save slot does not match request')
        path = self.path(slot)
        if path.exists() and self.load(slot) is None:
            raise SaveError('Invalid existing save preserved. Back it up/remove it before saving.')
        temporary = path.with_suffix('.json.tmp')
        try:
            # Parent already exists in the project; tests supply existing temp dirs.
            with temporary.open('w', encoding='utf-8') as stream:
                json.dump(data, stream, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        self.error = ''
        return data

    @staticmethod
    def capture(scene_manager, session, slot='manual', milestone=None):
        from ursina import camera
        p, house = scene_manager.player, scene_manager.house
        # Object IDs describe collected pickups; notes/item definitions stay in level data.
        data = dict(version=SAVE_VERSION, level='haunted_house_v1', slot=slot, session=session,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    player=dict(position=list(p.position), yaw=(p.rotation_y+180)%360-180,
                                pitch=p.camera_pivot.rotation_x, camera_rotation=list(camera.rotation),
                                battery=p.stats.battery, stamina=p.stats.stamina,
                                flashlight_on=p.flashlight_on, crouching=p.crouching,
                                sprint_exhausted=p.stats.sprint_exhausted, regen_delay=p.stats.regen_delay,
                                camera_height=p.camera_pivot.y),
                    inventory=dict(p.inventory.quantities),
                    progression={flag:getattr(p.progression, flag) for flag in FLAGS},
                    world=dict(collected=sorted(name for name,entity in house.pickups.items() if entity.is_empty()),
                               doors={name:getattr(house,name).opened for name in house.level.doors}))
        if slot == 'checkpoint':
            data['milestone'] = milestone
            data['player'].update(position=list(house.nav_nodes['foyer']), yaw=0, pitch=0,
                                  camera_rotation=[0,0,0], crouching=False, camera_height=settings.PLAYER_HEIGHT)
        return validate_save(data, house.level)

    @staticmethod
    def restore(scene_manager, data):
        """Called on a staged fresh scene only; no pickup/puzzle rewards replayed."""
        from ursina import Vec3, camera, scene
        p, house = scene_manager.player, scene_manager.house
        for item, quantity in data['inventory'].items():
            if not p.inventory.add(item, quantity):
                raise SaveError('Inventory could not be restored')
        p.progression.restore(data['progression'], data['world']['collected'])
        for name, opened in data['world']['doors'].items():
            door = getattr(house, name)
            if opened:
                door.opened, door.opening = True, False
                door.opening_time = door.opening_duration
                door.rotation_y = house.level.doors[name]['rotation_y'] + 100
                door.collider = None
                door.escape_player = p
        player = data['player']
        p.position = Vec3(*player['position'])
        p.rotation_y, p.camera_pivot.rotation_x = player['yaw'], player['pitch']
        p.crouching = player['crouching']
        p.camera_pivot.y = player['camera_height']
        p.set_body_height(max(settings.PLAYER_CROUCH_HEIGHT if p.crouching else settings.PLAYER_HEIGHT,
                              p.camera_pivot.y))
        for field in ('battery','stamina','sprint_exhausted','regen_delay'):
            setattr(p.stats, field, player[field])
        p.has_flashlight = bool(p.inventory.count('flashlight'))
        p.flashlight_on = player['flashlight_on']
        camera.rotation = Vec3(*player['camera_rotation'])
        # Validate against this new world's colliders, not the outgoing scene.
        p.traverse_target = house
        if not p.can_occupy(p.position, p.height):
            raise SaveError('Saved player position is obstructed')
        p.traverse_target = scene
        ghost = scene_manager.ghost
        candidates = [name for name in house.patrol_targets
                      if (house.nav_nodes[name]-p.position).length() >= settings.LOAD_GHOST_MIN_DISTANCE]
        if not candidates:
            raise SaveError('No safe ghost restart position')
        ghost.position = max((house.nav_nodes[name] for name in candidates), key=lambda pos:(pos-p.position).length())
        ghost.ai.navigation.clear()
        ghost.ai._choose_random_patrol_target()
        ghost.ai.grace_time = settings.LOAD_GRACE_SECONDS
        scene_manager.horror.director.quiet_until = settings.HORROR_INITIAL_QUIET_SECONDS
        p._set_flashlight_light(p.flashlight_on)
        p.hud.refresh_inventory(p)
        p.progression.refresh()
