"""Native main.py presentation/performance fixtures; not human playtesting."""
import ctypes
import json
import math
import random
from pathlib import Path
import runpy
import statistics
import sys
import tempfile
import time as wall
from direct.showbase.ShowBase import ShowBase
from panda3d.core import Filename, LightAttrib, SceneGraphAnalyzer, TexturePool, WindowProperties, loadPrcFileData

loadPrcFileData('', 'model-cache-dir\n')
if '--silent' in sys.argv:
    loadPrcFileData('', 'audio-library-name null')


def verify(app):
    from ursina import Vec3, application, camera, held_keys, mouse, scene, time
    from game.game_manager import GameManager
    from game.settings import Preferences
    from game.systems.save_manager import SaveManager
    from game.ghost.ghost_states import GhostState
    label=sys.argv[sys.argv.index('--label')+1] if '--label' in sys.argv else 'after'
    random.seed(8008)  # scoped fixture: repeatable patrol choices for before/after
    manager=next(e for e in scene.entities if isinstance(e,GameManager))
    manager.cinematics_enabled=False  # Comparable M8 timings isolate gameplay.
    manager.story_events_enabled=False  # The power_dip fixture is unchanged.
    folder=tempfile.TemporaryDirectory()
    manager.save_manager=SaveManager(folder.name)
    manager.preferences=Preferences(path=None)
    if '--low' in sys.argv:
        manager.preferences.values.update(texture_quality='low',decorative_detail='low',shadow_quality='off',camera_bob=0)
    manager.automatic_checkpoints=False
    manager.main_menu.refresh_saves()
    manager.apply_live_preferences()
    manager.set_focus(True)
    manager.window_events.ignore('window-event')
    mouse.enabled=False
    application.calculate_dt=False
    def frames(count=1):
        for _ in range(count):
            if app.win.get_properties().get_minimized() or not app.win.is_active():
                properties=WindowProperties();properties.set_minimized(False);properties.set_foreground(True)
                app.win.request_properties(properties)
                app.win.set_active(True)
            time.dt=time.dt_unscaled=1/60
            app.taskMgr.step()
            app.graphicsEngine.render_frame()
    def capture(name):
        target=Path(__file__).with_name(f'render_m8_{label}_{name}.png')
        assert app.win.save_screenshot(Filename.from_os_specific(str(target.resolve())))
    def pose(position,target):
        camera.world_parent=scene
        camera.position=Vec3(*position)
        camera.rotation=Vec3(0,0,0)
        direction=Vec3(*target)-camera.position
        camera.rotation=Vec3(math.degrees(math.atan2(-direction.y, math.hypot(direction.x,direction.z))),
                             math.degrees(math.atan2(direction.x,direction.z)),0)
    def memory():
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('peak_ws','ws','peak_paged','paged','peak_nonpaged','nonpaged','private','peak_private','private_usage')]
        counters=Counters();counters.cb=ctypes.sizeof(counters)
        process=ctypes.windll.kernel32.GetCurrentProcess;process.restype=wintypes.HANDLE
        query=ctypes.windll.psapi.GetProcessMemoryInfo
        query.argtypes=(wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD)
        assert query(process(),ctypes.byref(counters),counters.cb)
        return dict(private_bytes=counters.private_usage,working_set_bytes=counters.ws)
    def counts():
        graph=SceneGraphAnalyzer();graph.add_node(scene.node())
        textures=TexturePool.find_all_textures()
        house=manager.scene_manager.house
        audio=getattr(manager.scene_manager,'audio',None)
        return dict(entities=sum(not e.is_empty() for e in scene.entities),colliders=len(scene.collidables),
                    house_colliders=sum(e.has_ancestor(house) or e==house for e in scene.collidables),
                    cached_audio_clips=len(getattr(audio,'sounds',{})),
                    window_active=app.win.is_active(),window_minimized=app.win.get_properties().get_minimized(),
                    lights=app.render.get_state().get_attrib(LightAttrib).get_num_on_lights(),
                    geoms=graph.get_num_geoms(),vertices=graph.get_num_vertices(),
                    pooled_texture_ram_bytes=sum(tex.get_ram_image_size() for tex in textures),**memory())
    def timed(name,count=120):
        values=[]
        for _ in range(count):
            before=wall.perf_counter();frames();values.append((wall.perf_counter()-before)*1000)
        result=dict(median_ms=statistics.median(values),p95_ms=sorted(values)[math.ceil(.95*len(values))-1],
                    maximum_ms=max(values),**counts())
        print(name,result,flush=True)
        return result
    report={}
    try:
        frames(20)
        app.input('enter',is_raw=True)
        if manager.state=='confirm_new':app.input('enter',is_raw=True)
        frames(15)
        p,h,g=manager.scene_manager.player,manager.scene_manager.house,manager.scene_manager.ghost
        p.obtain_flashlight();p.toggle_flashlight()
        p.position,p.rotation_y=Vec3(0,0,-7),0
        p.camera_pivot.rotation_x=0;camera.rotation=Vec3(0,0,0)
        g.position=Vec3(*h.ghost_spawn)
        frames(20)
        report['exploration']=timed('exploration')
        p.position,p.rotation_y=Vec3(0,0,-10),0
        p.stats.stamina=100;p.stats.sprint_exhausted=False
        g.position=Vec3(0,0,-15);g.rotation_y=0
        g.ai.navigation.clear()
        g.ai.grace_time=g.ai.recovery_time=g.ai.repath_time=g.ai.lost_sight_time=0
        g.ai.inspection_target=g.ai.suspected_hiding_spot=None
        g.ai._set_state(GhostState.CHASE);g.ai.detection=1
        g.ai._refresh_debug()
        g.ai._remember(p.position,.3)
        chase_start=Vec3(g.position)
        held_keys['w']=held_keys['shift']=1
        report['chase']=timed('chase')
        held_keys.clear()
        assert manager.state=='playing'
        assert g.ai.state==GhostState.CHASE, g.ai.state
        assert (g.position-chase_start).length()>1
        report['chase']['final_ai_state']=g.ai.state.name
        live_update=g.update
        g.update=lambda:None
        pose((g.x,1.8,g.z+3),(g.x,1.1,g.z))
        p._set_flashlight_light(True);frames(2);capture('ghost_chase')
        camera.parent=p.camera_pivot;camera.position=Vec3(0,0,0);camera.rotation=Vec3(0,0,0)
        p.position=Vec3(0,0,-7);p.rotation_y=0
        g.position=Vec3(*h.ghost_spawn);g.ai.state=GhostState.PATROL;g.ai.detection=0
        g.ai.navigation.clear();g.ai._choose_random_patrol_target();g.enabled=True;g.update=live_update
        horror=manager.scene_manager.horror
        horror.next_allowed=0;horror.director.tension=.7
        assert horror.start_event('power_dip')
        report['paranormal']=timed('paranormal')
        horror.cancel_active()
        if '--event-profile' in sys.argv:
            from game.systems.horror_manager import EVENTS
            event_reports={}
            g.enabled=False
            for event in EVENTS:
                room='main_hall' if event.name=='hallway_dim' else 'living'
                p.position=Vec3(*h.level.navigation['nodes'][room])
                p.rotation_y=0;p.camera_pivot.rotation_x=0;camera.rotation=Vec3(0,0,0)
                # Apparitions disappear in the beam by design, so only these
                # two cases turn it off. Other events keep default illumination.
                p.flashlight_on=event.category!='apparition'
                p._set_flashlight_light(p.flashlight_on)
                horror.next_allowed=0;horror.director.quiet_until=0;horror.director.tension=.7
                assert horror.start_event(event.name),event.name
                event_reports[event.name]=timed(event.name,90)
                event_reports[event.name]['flashlight_on']=p.flashlight_on
                horror.cancel_active()
            report['events']=event_reports
            g.enabled=True;p.position=Vec3(0,0,-7);p.flashlight_on=True;p._set_flashlight_light(True)
        manager.begin_jumpscare();frames(15)
        report['jumpscare']=timed('jumpscare',70)
        capture('jumpscare')
        frames(40)
        assert manager.state=='dead'
        app.input('r',is_raw=True);frames(2)
        p,h,g=manager.scene_manager.player,manager.scene_manager.house,manager.scene_manager.ghost
        g.enabled=False;p.enabled=False
        p.obtain_flashlight()
        manager.hud.set_prompt('')
        if manager.hud.message_sequence:
            manager.hud.message_sequence.kill()
        manager.hud.message.enabled=False
        def beam(enabled):
            p.flashlight_on=enabled
            p._set_flashlight_light(enabled)
            p.hud.refresh_inventory(p)
        for name in ('foyer','main_hall','bedroom','kitchen','living'):
            view=h.level.house['views'][name]
            pose(view['position'],view['target'])
            beam(False);frames(3);capture(name+'_off')
            beam(True);frames(3);capture(name+'_on')
        g.enabled=True;g.update=lambda:None
        g.position=Vec3(0,0,-2);g.rotation_y=180
        pose((0,1.8,-5),(0,1.1,-2));p._set_flashlight_light(True);frames(3);capture('ghost_model')
        pose((-3.2,1.8,8.5),(-3.2,1,9.64));p._set_flashlight_light(True);frames(3);capture('puzzle')
        manager.pause_game();manager.open_settings()
        manager.settings_menu.selected=9;manager.settings_menu.refresh_selection();frames(2);capture('graphics_settings')
        if len(manager.settings_menu.rows)>13:
            manager.settings_menu.selected=15;manager.settings_menu.refresh_selection();frames(2);capture('audio_settings')
        from PIL import Image, ImageStat
        pixel_comparison={}
        for name in ('foyer','main_hall','bedroom','kitchen','living'):
            means=[]
            for mode in ('off','on'):
                with Image.open(Path(__file__).with_name(f'render_m8_{label}_{name}_{mode}.png')) as shot:
                    means.append(sum(ImageStat.Stat(shot.convert('RGB').crop((600,300,900,650))).mean)/3)
            assert means[1]>means[0]+1, (name,means)
            pixel_comparison[name]={'off':means[0],'on':means[1]}
        report['beam_pixels']=pixel_comparison
        report.update(gpu=app.win.get_gsg().get_driver_renderer(),label=label,
                      limitations='Native scripted scenarios, real movement/AI during exploration/chase; extra render_frame included. Geom count is not measured GPU draw calls. Pooled RAM image bytes exclude procedural textures unless reported separately; not VRAM.')
        audio=getattr(manager.scene_manager,'audio',None)
        if audio:
            report['cached_audio_clips']=len(audio.sounds)
        assets=getattr(h,'assets',None)
        if assets:report['asset_metrics']=assets.metrics()
        Path(__file__).with_name(f'render_m8_{label}_profile.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('PRESENTATION_WINDOW_OK',label,flush=True)
    finally:
        manager.return_to_menu()
        app.destroy();folder.cleanup()

if __name__=='__main__':
    if '--baseline' in sys.argv:
        # Read committed game code into memory. No checkout/reset/worktree or
        # writes to source; the authored JSON was not changed in this milestone.
        import importlib.abc
        import importlib.util
        import subprocess
        root=Path(__file__).resolve().parents[2]
        source_commit=sys.argv[sys.argv.index('--source-commit')+1] if '--source-commit' in sys.argv else 'a1ce83a'
        class CommittedSource(importlib.abc.MetaPathFinder, importlib.abc.Loader):
            def find_spec(self, fullname, path=None, target=None):
                if not fullname.startswith('game.') or fullname.startswith('game.tests'):
                    return None
                relative=fullname.replace('.','/')
                package=(root/relative/'__init__.py').is_file()
                relative += '/__init__.py' if package else '.py'
                if not (root/relative).is_file():
                    return None
                result=subprocess.run(['git','show',source_commit+':'+relative],cwd=root,capture_output=True)
                if result.returncode:
                    raise ImportError('Baseline module missing: '+relative)
                spec=importlib.util.spec_from_loader(fullname,self,is_package=package)
                spec.loader_state=(relative,result.stdout.decode('utf-8-sig'))
                return spec
            def create_module(self, spec):
                return None
            def exec_module(self, module):
                relative,source=module.__spec__.loader_state
                module.__file__=str(root/relative)
                if module.__spec__.submodule_search_locations is not None:
                    module.__path__=[str((root/relative).parent)]
                exec(compile(source,module.__file__,'exec'),module.__dict__)
        sys.meta_path.insert(0,CommittedSource())
    ShowBase.run=verify
    runpy.run_path(str(Path(__file__).resolve().parents[2]/'main.py'),run_name='__main__')
