"""Small additive visual motion, independent of movement/collision and view aim."""
import math
from ursina import Entity, Vec3, camera, color
from game.systems.asset_manager import assets


class CameraPresentation:
    def __init__(self, player):
        self.player = player
        self.phase = self.amount = self.reaction = 0.0
        self.strength = .25
        self.reduced = False
        # Lives with the player, so detaching the camera during loading cannot
        # strand first-person meshes under the eternal camera.
        self.handheld = Entity(parent=player.camera_pivot, shader=None,
                               position=(.3,-.32,.52), rotation_x=8, enabled=False)
        Entity(parent=self.handheld, model='cube', shader=None, texture=assets.texture('metal'),
               scale=(.07,.08,.24), color=color.rgb32(82,88,83))
        Entity(parent=self.handheld, model='cube', shader=None, position=(0,0,.13),
               scale=(.10,.10,.055), color=color.rgb32(125,129,117))

    def configure(self, values):
        self.strength = values['camera_bob']
        self.reduced = values['reduced_shake']

    def react(self, strength=.2):
        if not self.reduced:
            self.reaction = max(self.reaction, min(.3, strength))

    def reset(self):
        self.phase = self.amount = self.reaction = 0
        if camera.parent == self.player.camera_pivot:
            camera.position = Vec3(0,0,0)

    def update(self, dt, travel):
        dt = max(0, dt)
        moving = travel > .0001 and not self.player.hidden and not self.player.hud.panel.active
        self.amount += ((1 if moving else 0)-self.amount)*(1-math.exp(-8*dt))
        self.phase += travel*math.tau/1.5
        self.reaction *= math.exp(-8*dt)
        strength = 0 if self.reduced else self.strength
        amplitude = .035*strength*self.amount*(1.35 if self.player.sprinting else .65 if self.player.crouching else 1)
        offset = Vec3(math.sin(self.phase)*amplitude*.4,
                      math.cos(self.phase*2)*amplitude + self.reaction*.012*strength,0)
        if camera.parent == self.player.camera_pivot:
            camera.position = offset
            # The actual beam follows the current view in this same frame.
            self.player.flashlight_light.world_position = camera.world_position
            self.player.flashlight_light.world_rotation = camera.world_rotation
        self.handheld.enabled = self.player.has_flashlight
        self.handheld.position = Vec3(.3,-.32,.52) + offset*.5
        self.handheld.rotation_z = math.sin(self.phase)*strength*self.amount*2
