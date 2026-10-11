"""One-time authored beats, coordinated with the existing paranormal director."""
import math
import textwrap
from ursina import Entity, Vec3, Vec4, application, camera, color
from game.ghost.ghost_states import GhostState
from game.systems.narrative import STORY, event_ready
from game.systems.horror_manager import destroy_temporary
from game.systems.asset_manager import assets
from game.world.environment import world_raycast


class StoryDirector:
    cooldown_seconds = 12

    def __init__(self, scene_manager):
        self.scene = scene_manager
        self.clock = self.next_allowed = 0
        self.active = None
        self.enabled = True
        self._visibility_clock = -1000
        self._visible_positions = []

    def positions(self, event):
        if event['id']=='final_warning':
            position = self.scene.house.nav_nodes['exit_approach']
            delta = position+Vec3(0,1,0)-camera.world_position
            if (2.5 <= delta.length() <= 14 and camera.forward.dot(delta.normalized())>.5
                    and not world_raycast(camera.world_position,delta,distance=delta.length(),
                                          traverse_target=self.scene.house).hit):
                return [('exit_approach',position)]
        return self.scene.horror.apparition_position()

    def protected(self):
        sm = self.scene
        return (application.paused or not sm.player.enabled or sm.player.hud.panel.active
                or sm.player.hidden or sm.ghost.ai.state in (GhostState.CHASE,GhostState.JUMPSCARE)
                or sm.ghost.ai.detection >= .2 or sm.ghost.ai.grace_time > 0
                or (sm.player.world_position-sm.ghost.world_position).length() < 3
                or sm.horror.clock < sm.horror.director.quiet_until or sm.house.exit_door.opening)

    def eligible(self):
        if not self.enabled or self.protected() or self.active or self.clock < self.next_allowed-1e-8:
            return []
        sm = self.scene
        p = sm.player
        flags = {name:getattr(p.progression,name) for name in ('power_restored','safe_unlocked','boards_removed')}
        near_boards = (p.position-sm.house.puzzles['boards'].world_position).length() < 3
        near_exit = sm.house.room_at(p.position) == sm.house.rooms['exit_area']
        eligible = [event for event in STORY['events'] if event['id'] not in sm.narrative.completed_events
                and event_ready(event['id'],p.inventory.quantities,flags,near_boards,near_exit)]
        if any(event['id']=='the_watcher' for event in eligible) and sm.horror.frequency>0:
            if self.clock-self._visibility_clock >= .2:
                self._visible_positions = sm.horror.apparition_position()
                self._visibility_clock = self.clock
            eligible = [e for e in eligible if e['id']!='the_watcher' or self._visible_positions]
        return eligible

    def start_event(self, event_id):
        event = next((e for e in self.eligible() if e['id']==event_id),None)
        if event is None:
            return False
        sm = self.scene
        positions = self.positions(event) if event['kind'] in ('apparition','warning') and sm.horror.frequency>0 else []
        if event_id=='the_watcher' and sm.horror.frequency>0 and not positions:
            return False  # Wait for a doorway the player can actually see.
        sm.horror.cancel_active()
        active = self.active = dict(event=event, elapsed=0., temporary=[], colors=[], transforms=[], cue_token=None)
        # Commit before showing anything. Interrupted beats never surprise twice.
        sm.narrative.completed_events.add(event_id)
        sm.player.hud.show_message(textwrap.fill(event['caption'],width=int(65/sm.player.hud.text_scale)),seconds=event['seconds'])
        if sm.horror.frequency > 0:
            if sm.audio.play(event['cue'],gain=.22,cooldown=8):
                active['cue_token'] = sm.audio.last[event['cue']]
            if event['kind'] == 'power':
                active['colors'] = [(light,Vec4(light.color)) for light in sm.lights]
            if event['kind'] in ('apparition','warning'):
                if positions:
                    # Prefer the clear centre of the view over a distant side
                    # doorway partly hidden by a landmark or door frame.
                    position = max(positions,key=lambda item: camera.forward.dot(
                        (item[1]+Vec3(0,1,0)-camera.world_position).normalized()))[1]
                    silhouette = Entity(parent=sm.house,model=assets.apparition_mesh(),
                                        shader=sm.horror.apparition_shader, collider=None,
                                        position=position+Vec3(0,.85,0), color=color.rgb32(36,39,43),double_sided=True)
                    silhouette.look_at_2d(sm.player.world_position,'y')
                    active['temporary'].append(silhouette)
            if event['kind']=='warning':
                cabinet = next(prop for prop in sm.house.rooms['living'].props if prop.name=='cabinet')
                leaf = Entity(parent=cabinet,model='cube',shader=None,collider=None,origin_x=-.5,
                              position=(-.5,.85,-.36),scale=(1,1.6,.045),color=color.rgb32(72,57,45),
                              texture=assets.texture('wood',sm.house._presentation_quality))
                active['temporary'].append(leaf)
                active['transforms'].append((leaf,Vec3(leaf.position),Vec3(leaf.rotation)))
            if event['kind']=='shift':
                room = sm.house.rooms['dining']
                visuals = [child for prop in room.props if prop.name=='chair' for child in prop.children if child.model]
                if visuals:
                    visual = visuals[0]
                    active['transforms'] = [(visual,Vec3(visual.position),Vec3(visual.rotation))]
        return True

    def update(self, dt):
        if not self.enabled or application.paused:
            return
        self.clock += max(0,dt)
        if self.active:
            if self.protected():
                self.cancel_active()
                return
            active = self.active
            if any((entity.world_position-camera.world_position).length()<2.5 for entity in active['temporary']
                   if entity.parent==self.scene.house):
                self.cancel_active()
                return
            event = active['event']
            active['elapsed'] = min(event['seconds'],active['elapsed']+max(0,dt))
            envelope = math.sin(math.pi*active['elapsed']/event['seconds'])**2
            for light, original in active['colors']:
                # One smooth dim, no strobing; beam and colliders stay intact.
                light.color = color.rgba(original.x*(1-.22*envelope),original.y*(1-.22*envelope),
                                         original.z*(1-.22*envelope),original.w)
            for visual,position,rotation in active['transforms']:
                if not self.scene.player.presentation.reduced:
                    visual.rotation_y = rotation.y + 5*envelope
            if active['elapsed'] >= event['seconds']-1e-8:
                self.cancel_active()
        else:
            eligible = self.eligible()
            if eligible:
                self.start_event(eligible[0]['id'])

    def cancel_active(self):
        if not self.active:
            return
        active,self.active = self.active,None
        for light,original in active['colors']:
            light.color = original
        for visual,position,rotation in active['transforms']:
            if not visual.is_empty():
                visual.position,visual.rotation = position,rotation
        for entity in active['temporary']:
            if not entity.is_empty():
                destroy_temporary(entity)
        cue = active['event']['cue']
        if active['cue_token'] is not None and self.scene.audio.last.get(cue)==active['cue_token']:
            self.scene.audio.stop(cue)
        self.next_allowed = self.clock+self.cooldown_seconds
        self.scene.horror.director.quiet_until = max(self.scene.horror.director.quiet_until,
                                                     self.scene.horror.clock+8)
