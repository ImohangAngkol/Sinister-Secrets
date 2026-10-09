"""One staged camera-space encounter after the AI validates a catch."""
import math
from ursina import Entity, Vec3, camera, color, destroy, scene
from ursina.shaders import unlit_shader
from game import settings


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
        self.intensity = max(0,min(1,settings.JUMPSCARE_INTENSITY))
        self.on_finished = on_finished
        self.saved_position = Vec3(camera.world_position)
        self.saved_rotation = Vec3(camera.world_rotation)
        self.saved_fov = camera.fov
        camera.world_parent = scene
        # A presentation proxy reuses the ghost's cube shape; the real ghost
        # stays at its legitimate catch location, with navigation disabled.
        self.proxy = Entity(parent=camera, model='cube', shader=unlit_shader,
                            position=(0,-.12,2.4), scale=(.65,1.25,.45), collider=None,
                            color=color.rgb32(79,118,124))
        # A wardrobe catch can place the world camera behind a cabinet face.
        # Composite this presentation mesh after world geometry so that face
        # cannot hide the encounter; real ghost geometry never moves/clips.
        self.proxy.set_bin('fixed',40)
        self.proxy.set_depth_test(False)
        self.proxy.set_depth_write(False)
        for x in (-.14,.14):
            Entity(parent=self.proxy,model='cube',shader=unlit_shader,
                   position=(x,.22,-.51),scale=(.12,.065,.025),color=color.rgb32(8,11,13))
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
        self.proxy.z = 2.4-1.1*self.intensity*approach
        shake = settings.JUMPSCARE_SHAKE_DEGREES*self.intensity
        if settings.JUMPSCARE_REDUCED_SHAKE:
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
            for child in reversed(self.proxy.children):
                destroy(child)
            destroy(self.proxy)
        if self.overlay is not None and not self.overlay.is_empty():
            destroy(self.overlay)
        if self.active:
            camera.world_position = self.saved_position
            camera.world_rotation = self.saved_rotation
            camera.fov = self.saved_fov
        self.proxy = self.overlay = None
        self.active = False
