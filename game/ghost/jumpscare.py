"""One staged camera-space encounter after the AI validates a catch."""
import math
from ursina import Entity, Vec3, camera, color, destroy, scene
from ursina.shaders import unlit_shader
from game import settings
from game.ghost.ghost_visual import GhostVisual
from game.systems.horror_manager import destroy_temporary


class Jumpscare:
    def __init__(self, on_caught=None):
        self.on_caught = on_caught
        self.triggered = False
        self.active = False
        self.elapsed = 0.0
        self.proxy = self.overlay = None

    def trigger(self):
        if self.triggered:
            return False
        self.triggered = True
        if self.on_caught:
            self.on_caught()
        return True

    def begin(self, on_finished):
        self.active = True
        self.elapsed = 0
        self.duration = max(.1,settings.JUMPSCARE_SECONDS)
        self.intensity = max(0,min(1,getattr(self, 'preference_intensity', settings.JUMPSCARE_INTENSITY)))
        self.on_finished = on_finished
        self.saved_position = Vec3(camera.world_position)
        self.saved_rotation = Vec3(camera.world_rotation)
        self.saved_fov = camera.fov
        camera.world_parent = scene
        # Presentation-only humanoid; the real catch position and hitbox stay fixed.
        self.proxy = Entity(parent=camera, shader=unlit_shader,
                            position=(0,-1.45,2.4), collider=None)
        self.visual = GhostVisual(parent=self.proxy, cinematic=True, rotation_y=180)
        if getattr(self,'audio',None):
            self.audio.play('capture', gain=self.intensity, cooldown=2)
        self.overlay = Entity(parent=camera.ui,model='quad',scale=(camera.aspect_ratio,1),
                              z=-.2,color=color.rgba(0,0,0,0))

    @property
    def phase(self):
        fraction = self.elapsed/self.duration if self.active else 1
        return 'seize' if fraction < .2 else 'approach' if fraction < .7 else 'fade'

    def update(self, dt):
        if not self.active:
            return
        self.elapsed = min(self.duration,self.elapsed+max(0,dt))
        fraction = self.elapsed/self.duration
        approach = max(0,min(1,(fraction-.2)/.5))
        approach = approach*approach*(3-2*approach)
        self.visual.advance(dt,state='capture')
        self.proxy.z = 2.4-1.1*self.intensity*approach
        shake = settings.JUMPSCARE_SHAKE_DEGREES*self.intensity
        if getattr(self, 'preference_reduced_shake', settings.JUMPSCARE_REDUCED_SHAKE):
            shake *= .15
        camera.world_rotation = self.saved_rotation + Vec3(
            math.sin(self.elapsed*13)*shake,math.sin(self.elapsed*9)*shake*.5,0)
        self.overlay.scale = (camera.aspect_ratio,1)
        darkness = self.intensity*.65*max(0,(fraction-.65)/.35)
        self.overlay.color = color.rgba(0,0,0,darkness)
        if self.elapsed >= self.duration-1e-9:
            callback = self.on_finished
            self.cancel()
            callback()

    def cancel(self):
        if self.proxy is not None and not self.proxy.is_empty():
            destroy_temporary(self.proxy)
        if self.overlay is not None and not self.overlay.is_empty():
            destroy(self.overlay)
        if self.active:
            camera.world_position = self.saved_position
            camera.world_rotation = self.saved_rotation
            camera.fov = self.saved_fov
        self.proxy = self.overlay = None
        self.visual = None
        if getattr(self,'audio',None):
            self.audio.stop('capture')
        self.active = False
