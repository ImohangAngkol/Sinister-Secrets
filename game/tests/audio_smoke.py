"""Actual main.py with the system audio backend; verifies playback, not listening."""
import json
from pathlib import Path
import runpy
import tempfile
import time as wall
from direct.showbase.ShowBase import ShowBase
from panda3d.core import loadPrcFileData

loadPrcFileData('', 'model-cache-dir\n')


def verify(app):
    from ursina import application, camera, mouse, scene, time
    from game.game_manager import GameManager
    from game.settings import Preferences
    from game.systems.save_manager import SaveManager
    manager=next(e for e in scene.entities if isinstance(e,GameManager))
    directory=tempfile.TemporaryDirectory()
    manager.preferences=Preferences(path=None)
    manager.save_manager=SaveManager(directory.name)
    manager.main_menu.refresh_saves()
    manager.automatic_checkpoints=False
    manager.window_events.ignore('window-event')
    manager.set_focus(True)
    application.calculate_dt=False
    mouse.enabled=False
    def frames(count=1):
        for _ in range(count):
            time.dt=time.dt_unscaled=1/60
            app.taskMgr.step()
            wall.sleep(.02)
    try:
        manager.start_game();frames(2)
        audio=manager.scene_manager.audio
        player=manager.scene_manager.player
        manager.scene_manager.ghost.enabled=False
        audio.stop_all();audio.play('ambience',loop=True,gain=.65,cooldown=0)
        frames(2)
        sound=audio.sounds['ambience'][0]
        report=dict(sound_description=str(sound),status=sound.status(),playing_status=sound.PLAYING)
        if sound.status()!=sound.PLAYING:
            report['result']='AUDIO_BACKEND_UNAVAILABLE: silent fallback remains playable'
        else:
            position=sound.get_time()
            manager.pause_game();frames(2)
            assert sound.status()!=sound.PLAYING
            manager.resume_game();frames(2)
            assert sound.status()==sound.PLAYING
            assert sound.get_time()>=position
            assert len([n for n,(_,_,loop) in audio.playing.items() if loop])==1
            audio.configure(dict(master_volume=0))
            assert sound.get_volume()==0
            audio.configure(dict(master_volume=.7))
            assert sound.get_volume()>0
            for name in ('door','step','fuse','lockbox','crowbar','pickup','battery','select','creak','knock','presence','search','inspect'):
                assert audio.play(name,cooldown=0,gain=.3)
                frames(1)
                assert audio.sounds[name][0].status()==sound.PLAYING, name
                audio.stop(name)
            player.stats.battery=50
            manager.begin_jumpscare();frames(2)
            assert 'capture' in audio.playing
            manager.set_focus(False);frames(2)
            assert audio.paused and 'capture' not in audio.playing
            manager.set_focus(True);manager.input('r');frames(2)
            assert audio.closed and not audio.playing
            current=manager.scene_manager.audio
            manager.return_to_menu()
            assert current.closed and not current.playing
            report['result']='NATIVE_AUDIO_PLAYBACK_OK'
        Path(__file__).with_name('render_m8_audio_profile.json').write_text(json.dumps(report,indent=2))
        print(report,flush=True)
    finally:
        manager.return_to_menu();app.destroy();directory.cleanup()


if __name__=='__main__':
    ShowBase.run=verify
    runpy.run_path(str(Path(__file__).resolve().parents[2]/'main.py'),run_name='__main__')
