"""Bounded, cached Panda3D audio without audio Entities or gameplay noise events."""
import math
from game.systems.asset_manager import assets


class AudioManager:
    def __init__(self, asset_manager=assets, loader=None):
        if loader is None:
            from ursina import application
            loader = application.base.loader.load_sfx
        self.assets, self.loader = asset_manager, loader
        self.sounds, self.last, self.playing = {}, {}, {}
        self.clock = self.distance = 0.0
        self.paused, self.closed = True, False
        self.listener = None
        self.volumes = dict(master_volume=.7, ambience_volume=.35, sfx_volume=.65)
        self.state = None

    def configure(self, values):
        for key in self.volumes:
            self.volumes[key] = max(0, min(1, values.get(key, self.volumes[key])))
        self._refresh_volumes()

    def _sound(self, name):
        if name not in self.assets.manifest or self.assets.manifest[name].get('kind') != 'audio':
            self.assets.warn(name, f'Unknown audio {name}; continuing silently')
            return None, 'sfx'
        if name not in self.sounds:
            entry = self.assets.manifest[name]
            path = self.assets.path(name, 'audio')
            sound = None
            if path:
                try:
                    from panda3d.core import Filename
                    sound = self.loader(Filename.from_os_specific(str(path)).get_fullpath())
                    if sound is not None and sound.status() == sound.BAD:
                        sound = None
                except Exception as error:
                    self.assets.warn(name, f'Audio {name} unavailable: {error}')
            if sound is None:
                self.assets.warn(name, f'Audio {name} unavailable; continuing silently')
            self.sounds[name] = (sound, entry.get('channel', 'sfx'))
        return self.sounds[name]

    def _volume(self, channel, gain, position):
        attenuation = 1.0
        if position is not None and self.listener is not None:
            distance = math.sqrt(sum((a-b)**2 for a,b in zip(position, self.listener)))
            attenuation = 1 / (1 + (distance / 5)**2)
        group = 'ambience_volume' if channel == 'ambience' else 'sfx_volume'
        return self.volumes['master_volume'] * self.volumes[group] * gain * attenuation

    def _refresh_volumes(self):
        for name, (gain, position, loop) in self.playing.items():
            sound, channel = self.sounds[name]
            sound.set_volume(0 if self.paused else self._volume(channel, gain, position))

    def play(self, sound_name, *, loop=False, gain=1.0, position=None, cooldown=.2):
        if self.closed or self.paused or self.clock-self.last.get(sound_name, -1000) < cooldown:
            return False
        if loop and sound_name in self.playing:
            return False
        sound, channel = self._sound(sound_name)
        if sound is None:
            return False
        sound.stop()
        sound.set_loop(loop)
        sound.set_time(0)
        position = tuple(position) if position is not None else None
        sound.set_volume(self._volume(channel, gain, position))
        sound.play()
        self.playing[sound_name] = (gain, position, loop)
        self.last[sound_name] = self.clock
        return True

    def stop(self, name):
        if name in self.playing:
            self.sounds[name][0].stop()
            del self.playing[name]

    def stop_all(self):
        for name in list(self.playing):
            self.stop(name)
        self.distance = 0
        self.state = None

    def set_paused(self, paused):
        paused = bool(paused)
        if paused == self.paused:
            return
        self.paused = paused
        if paused:
            self.resume_times = {}
            for name, (_, _, loop) in list(self.playing.items()):
                sound = self.sounds[name][0]
                if loop:
                    self.resume_times[name] = sound.get_time()
                    sound.stop()
                else:
                    self.stop(name)
        else:
            for name, (gain, position, loop) in list(self.playing.items()):
                sound = self.sounds[name][0]
                sound.set_time(getattr(self, 'resume_times', {}).get(name, 0))
                sound.play()
        self._refresh_volumes()

    def update(self, dt, listener=None, state=None, tension=0, quiet=False, gameplay=True):
        if self.paused or self.closed:
            return
        self.clock += max(0, dt)
        self.listener = tuple(listener) if listener is not None else None
        for name, (_, _, loop) in list(self.playing.items()):
            sound = self.sounds[name][0]
            if not loop and sound.status() != sound.PLAYING:
                del self.playing[name]
        if gameplay:
            if quiet:
                self.stop('ambience')
            else:
                self.play('ambience', loop=True, gain=.65)
            name = getattr(state, 'name', str(state))
            if name != self.state:
                cue = {'SEARCH':'search', 'CHASE':'presence'}.get(name)
                if cue:
                    self.play(cue, gain=.45, cooldown=8)
                self.state = name
            if name == 'CHASE' and tension > .3 and not quiet:
                self.play('tension', loop=True, gain=.35)
            else:
                self.stop('tension')
        self._refresh_volumes()

    def footsteps(self, travel, *, sprinting=False, crouching=False):
        if self.paused or self.closed or travel <= 0:
            return False
        stride = 1.5 if crouching else 2 if sprinting else 1.5
        self.distance += travel
        if self.distance < stride-1e-9:
            return False
        self.distance = max(0,self.distance-stride*math.floor((self.distance+1e-9)/stride))
        return self.play('step', gain=.18 if crouching else .55 if sprinting else .35, cooldown=.12)

    def close(self):
        self.stop_all()
        self.sounds.clear()
        self.closed = True
