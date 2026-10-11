"""Asset and audio regressions use real WAV data and an explicit fake backend."""
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
import wave
from game.systems.asset_manager import AssetManager, ROOT, MATERIALS
from game.systems.audio_manager import AudioManager
from game.assets.generate_audio import DURATIONS, RATE, samples
from game.settings import Preferences, validate_preferences


class FakeSound:
    BAD = 0
    PLAYING = 2
    def __init__(self):
        self.plays = self.stops = 0
        self.volume = self.position = 0
        self.loop = False
        self.current_status = 1
    def set_volume(self, value): self.volume = value
    def set_loop(self, value): self.loop = value
    def set_time(self, value): self.position = value
    def get_time(self): return self.position
    def play(self):
        self.plays += 1
        self.current_status = self.PLAYING
    def stop(self):
        self.stops += 1
        self.current_status = 0
    def status(self): return self.current_status


class PresentationTests(unittest.TestCase):
    def audio(self):
        self.loaded = []
        def loader(path):
            sound = FakeSound()
            self.loaded.append((path,sound))
            return sound
        audio = AudioManager(AssetManager(), loader)
        audio.set_paused(False)
        return audio

    def test_manifest_records_all_original_assets_and_generators(self):
        assets=AssetManager()
        self.assertEqual(len(assets.manifest),25)
        for name,entry in assets.manifest.items():
            self.assertEqual(entry['license'],'LicenseRef-ProjectOriginal')
            self.assertTrue(entry['origin'])
            self.assertTrue((ROOT.parents[1]/entry['generator'].split(':')[0]).is_file())
            if entry['path']:
                self.assertIsNotNone(assets.path(name,entry['kind']))
        self.assertTrue((ROOT/'LICENSE.txt').is_file())

    def test_audio_files_are_small_valid_deterministic_pcm_and_not_silent(self):
        assets=AssetManager()
        before=random.getstate()
        total=0
        for name,duration in DURATIONS.items():
            path=assets.path(name,'audio');total+=path.stat().st_size
            with wave.open(str(path),'rb') as stream:
                self.assertEqual((stream.getnchannels(),stream.getsampwidth(),stream.getframerate()),(1,2,RATE))
                self.assertAlmostEqual(stream.getnframes()/RATE,duration,places=4)
                self.assertEqual(stream.readframes(stream.getnframes()),samples(name).tobytes())
            self.assertGreater(max(map(abs,samples(name))),100)
        self.assertLess(total,1024*1024)
        self.assertEqual(before,random.getstate())

    def test_invalid_missing_and_escaping_paths_fall_back_without_crashing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            entries={'escape':dict(kind='audio',path='../outside.wav'),
                     'missing':dict(kind='audio',path='missing.wav'),
                     'bad':dict(kind='audio',path='bad.wav')}
            (root/'manifest.json').write_text(json.dumps(dict(version=1,assets=entries)))
            (root/'bad.wav').write_bytes(b'invalid audio')
            assets=AssetManager(root)
            for name in entries:
                self.assertIsNone(assets.path(name,'audio'))
                self.assertIsNone(assets.path(name,'audio'))
            self.assertEqual(len(assets.warned),3)
            self.assertIsNone(assets.model('missing',fallback=None))

    def test_material_cache_is_partitioned_by_quality_and_has_safe_fallback(self):
        assets=AssetManager()
        with patch('game.systems.asset_manager.procedural_texture',side_effect=lambda *args:object()) as build:
            self.assertIs(assets.texture('wood'),assets.texture('wood'))
            self.assertIsNot(assets.texture('wood','low'),assets.texture('wood'))
            self.assertEqual(build.call_count,2)
        with patch('game.systems.asset_manager.procedural_texture',side_effect=[ValueError(),object()]):
            self.assertIsNotNone(assets.texture('invalid'))

    def test_sound_cache_loop_deduplication_and_cooldowns(self):
        audio=self.audio()
        self.assertTrue(audio.play('ambience',loop=True))
        for _ in range(60):audio.update(1/60)
        self.assertEqual(len(self.loaded),1)
        self.assertNotIn('\\', self.loaded[0][0])
        self.assertEqual(self.loaded[0][1].plays,1)
        self.assertTrue(audio.play('door'))
        self.assertFalse(audio.play('door'))
        audio.update(.3)
        self.assertTrue(audio.play('door'))
        self.assertEqual(len(self.loaded),2)

    def test_audio_pause_resume_preserves_one_loop_and_stops_one_shots(self):
        audio=self.audio()
        audio.play('ambience',loop=True);audio.play('door')
        loop=audio.sounds['ambience'][0];loop.position=2.25
        audio.set_paused(True)
        clock=audio.clock
        for _ in range(10):audio.update(1)
        self.assertEqual(audio.clock,clock)
        self.assertEqual(loop.volume,0)
        self.assertFalse(audio.play('door'))
        self.assertNotIn('door',audio.playing)
        audio.set_paused(False);audio.set_paused(False)
        self.assertEqual(loop.position,2.25)
        self.assertEqual(loop.plays,2)
        audio.update(.1)
        self.assertEqual(loop.plays,2)

    def test_master_and_category_volume_updates_and_distance_attenuation(self):
        audio=self.audio();audio.listener=(0,0,0)
        audio.configure(dict(master_volume=.5,ambience_volume=.2,sfx_volume=.8))
        audio.play('ambience',loop=True);audio.play('door',position=(5,0,0))
        self.assertAlmostEqual(audio.sounds['ambience'][0].volume,.1)
        self.assertAlmostEqual(audio.sounds['door'][0].volume,.2)
        audio.configure(dict(master_volume=0))
        self.assertEqual(audio.sounds['ambience'][0].volume,0)
        self.assertEqual(audio.sounds['door'][0].volume,0)

    def test_footsteps_use_displacement_not_keys_at_four_frame_rates(self):
        for fps in (4,30,60,120):
            for sprint,crouch,speed,stride in ((False,False,4,1.5),(True,False,7,2),(False,True,2,1.5)):
                audio=self.audio()
                for _ in range(fps):
                    audio.update(1/fps,gameplay=False)
                    self.assertFalse(audio.footsteps(0,sprinting=True))
                self.assertFalse(audio.sounds)
                for _ in range(fps*3):
                    audio.update(1/fps,gameplay=False)
                    audio.footsteps(speed/fps,sprinting=sprint,crouching=crouch)
                self.assertAlmostEqual(audio.distance,(speed*3)%stride,places=5)
                self.assertGreater(audio.sounds['step'][0].plays,0)

    def test_ghost_cues_quiet_period_and_dispose_do_not_leak_loops(self):
        audio=self.audio()
        for _ in range(20):audio.update(.1,state='CHASE',tension=.8)
        self.assertEqual(audio.sounds['presence'][0].plays,1)
        self.assertIn('tension',audio.playing)
        audio.update(.1,state='PATROL',quiet=True)
        self.assertNotIn('ambience',audio.playing)
        self.assertNotIn('tension',audio.playing)
        refs=[s for s,_ in audio.sounds.values()]
        audio.close();audio.close()
        self.assertFalse(audio.play('door'))
        self.assertFalse(audio.sounds)
        self.assertTrue(all(s.status()==0 for s in refs))

    def test_missing_backend_is_cached_silent_and_unknown_names_are_bounded(self):
        with patch.object(AssetManager,'warn'):
            loader=lambda path:None
            audio=AudioManager(loader=loader);audio.set_paused(False)
            self.assertFalse(audio.play('door'))
            self.assertFalse(audio.play('door'))
            for i in range(50):self.assertFalse(audio.play('unknown'+str(i)))
            self.assertEqual(set(audio.sounds),{'door'})

    def test_old_preferences_get_presentation_defaults_and_volumes_persist(self):
        values=validate_preferences({'brightness':1.25,'reduced_shake':True})
        self.assertEqual(values['texture_quality'],'standard')
        self.assertEqual(values['camera_bob'],.25)
        with tempfile.TemporaryDirectory() as folder:
            prefs=Preferences(Path(folder)/'prefs.json')
            prefs.save(dict(values,master_volume=.25,sfx_volume=0,ambience_volume=.5,texture_quality='low',camera_bob=0))
            self.assertEqual(Preferences(prefs.path).values,prefs.values)
        for key in ('master_volume','sfx_volume','ambience_volume','camera_bob'):
            for bad in (True,-.1,1.1,float('nan'),'0'):
                with self.assertRaises(ValueError):validate_preferences({key:bad})
