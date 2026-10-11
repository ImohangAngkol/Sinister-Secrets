"""Actual main.py native story routes; scripted input, not human playtesting."""
import json
import math
from pathlib import Path
import runpy
import sys
import tempfile
import time as wall
from direct.showbase.ShowBase import ShowBase
from panda3d.core import Filename, LightAttrib, WindowProperties, loadPrcFileData

loadPrcFileData('', 'model-cache-dir\n')


def verify(app):
    from ursina import Vec3, application, camera, held_keys, mouse, scene, time
    from game.game_manager import GameManager
    from game.settings import Preferences
    from game.systems.save_manager import SaveManager
    from game.systems.narrative import DOCUMENT_IDS
    from game.ghost.ghost_navigation import astar
    from game.ghost.ghost_states import GhostState
    from game.player.interaction import get_interaction_hit
    manager = next(e for e in scene.entities if isinstance(e,GameManager))
    directory = tempfile.TemporaryDirectory()
    manager.save_manager = SaveManager(directory.name)
    manager.preferences = Preferences(path=None)
    manager.automatic_checkpoints = False
    manager.window_events.ignore('window-event')
    manager.set_focus(True)
    manager.main_menu.refresh_saves();manager.apply_live_preferences()
    application.calculate_dt=False;mouse.enabled=False
    report = {'input':'scripted keyboard and lens aim; OS pointer/Alt-Tab not tested', 'routes':{}, 'screenshots':[]}
    current='foyer'

    def frames(count=1,dt=1/30):
        for _ in range(count):
            time.dt=time.dt_unscaled=dt
            app.taskMgr.step();app.graphicsEngine.render_frame()

    def refs():
        sm=manager.scene_manager
        return sm.player,sm.house,sm.ghost

    def capture(name):
        path=Path(__file__).with_name('render_m9_'+name+'.png')
        assert app.win.save_screenshot(Filename.from_os_specific(str(path.resolve())))
        report['screenshots'].append(path.name)

    def aim(target):
        p,_,_=refs()
        direction=Vec3(target)-camera.world_position
        p.rotation_y=math.degrees(math.atan2(direction.x,direction.z))
        p.camera_pivot.rotation_x=math.degrees(math.atan2(-direction.y,math.hypot(direction.x,direction.z)))
        camera.rotation=Vec3(0,0,0)
        p._set_flashlight_light(p.flashlight_on)

    def walk_to(position):
        p,_,_=refs();target=Vec3(*position)
        for _ in range(1500):
            delta=target-p.position;delta.y=0
            if delta.length()<.11:break
            p.rotation_y=math.degrees(math.atan2(delta.x,delta.z))
            p.camera_pivot.rotation_x=0;camera.rotation=Vec3(0,0,0)
            held_keys['w']=1;frames()
            assert manager.state=='playing',manager.state
        else:raise AssertionError(('Blocked walking route',tuple(p.position),tuple(target)))
        held_keys.clear()

    def go_room(room):
        nonlocal current
        p,h,g=refs()
        walk_to(h.nav_nodes[current])
        path=astar(current,room,h.nav_nodes,h.graph)
        assert current==room or path,(current,room)
        for node in path:walk_to(h.nav_nodes[node])
        current=room

    def visit(spawn_id,capture_name=None):
        p,h,g=refs()
        entry=next(s for s in h.level.spawns['pickups'] if s['id']==spawn_id)
        go_room(entry['room']);walk_to(entry['approach'])
        entity=h.pickups[spawn_id];aim(entity.world_position);frames(1)
        assert get_interaction_hit(p).entity==entity,spawn_id
        app.input(p.bindings['interact'],is_raw=True);frames(1)
        assert entity.is_empty(),spawn_id
        if capture_name:capture(capture_name)
        if manager.hud.panel.active:app.input('escape',is_raw=True)

    def visit_prop(prop_id):
        p,h,g=refs()
        entry=next(s for s in h.level.house['progression']['props'] if s['id']==prop_id)
        go_room(entry['room']);walk_to(entry['approach'])
        entity=h.puzzles[prop_id];aim(entity.world_position);frames(1)
        assert get_interaction_hit(p).entity==entity,prop_id
        app.input(p.bindings['interact'],is_raw=True);frames(1)

    def new_game(label,skip=True):
        nonlocal current
        if manager.state!='menu':manager.return_to_menu()
        manager.main_menu.selected=0
        app.input('enter',is_raw=True)
        if manager.state=='confirm_new':app.input('enter',is_raw=True)
        frames(2)
        assert manager.state=='intro'
        if label=='A':capture('opening')
        if not skip:
            manager.set_focus(False);elapsed=manager.story_screen.elapsed;frames(3,1)
            assert manager.story_screen.elapsed==elapsed
            manager.set_focus(True);frames(1)
            frames(43,.5)
            capture('arrival')
            while manager.state=='intro':frames(1,.5)
        else:app.input('enter',is_raw=True)
        frames(1)
        assert manager.state=='playing' and manager.scene_manager.narrative.intro_seen
        p,h,g=refs();g.enabled=False;g.ai.grace_time=0
        # Freeze AI only for authored route/UI fixtures. Route D uses live catch.
        current='foyer'
        visit('foyer_flashlight');app.input('f',is_raw=True);frames(2)
        if label=='A':
            aim(Vec3(-3.5,.78,-17));frames(2);capture('foyer')
        print('NEW_STORY_ROUTE',label,flush=True)

    def evidence(capture_ui=False):
        for item_id in sorted(DOCUMENT_IDS):
            visit('story_'+item_id.removeprefix('lore_'), 'narrative_note' if capture_ui and item_id=='lore_keeper_journal' else None)
        p,h,g=refs()
        assert p.narrative.mystery_uncovered
        if capture_ui:
            app.input('tab',is_raw=True);app.input('right arrow',is_raw=True);frames(2);capture('journal')
            app.input('escape',is_raw=True)

    def power():
        visit('living_instructions');visit('storage_fuse');visit_prop('fuse_box')
        assert refs()[0].progression.power_restored

    def remaining_puzzles():
        visit('kitchen_tally');visit_prop('lockbox')
        assert manager.hud.panel.mode=='combination'
        for digit in '2417':app.input(digit,is_raw=True)
        app.input('enter',is_raw=True);frames(2)
        assert refs()[0].progression.safe_unlocked
        visit_prop('boards');visit('bedroom_exit_key')
        assert refs()[0].inventory.has_key('exit_key')

    def exit_house(ending,capture_choice=False):
        p,h,g=refs();go_room('exit_area');walk_to(h.nav_nodes['exit_approach'])
        aim(Vec3(0,1.5,17.8));app.input('e',is_raw=True);frames(26)
        assert h.exit_door.opened
        p.rotation_y=0;p.camera_pivot.rotation_x=0;camera.rotation=Vec3(0,0,0)
        for _ in range(100):
            held_keys['w']=1;frames()
            if manager.state!='playing':break
        held_keys.clear()
        if manager.state=='ending_choice':
            if capture_choice:capture('ending_choice')
            if ending=='truth':app.input('down arrow',is_raw=True)
            app.input('enter',is_raw=True)
        assert manager.state=='ending' and manager.ending==ending,(manager.state,manager.ending)
        frames(2);capture(ending+'_ending')
        app.input('enter',is_raw=True);frames(1)
        assert manager.state=='escaped'
        assert not manager.menu_audio.playing and not manager.scene_manager.audio.playing

    def resize(width,height):
        properties=WindowProperties();properties.set_size(width,height);app.win.request_properties(properties)
        for _ in range(100):
            frames(1)
            if (app.win.get_x_size(),app.win.get_y_size())==(width,height):return
            wall.sleep(.01)
        raise AssertionError('Window resize failed')

    try:
        frames(10)
        def run_routes():
            nonlocal current
            new_game('A',skip=False);power();remaining_puzzles();exit_house('escape')
            report['routes']['A']='Intro played; essential chain; no lore; Escape'
            app.input('r',is_raw=True);frames(2)
            assert manager.state=='playing' and not refs()[0].narrative.documents
            new_game('B');evidence(capture_ui=True);power();remaining_puzzles();exit_house('truth',True)
            report['routes']['B']='Eight records; essential chain; explicit Truth choice'
            new_game('C');visit('story_family_photo');visit('story_keeper_journal')
            p,h,g=refs();go_room('main_hall')
            app.input('escape',is_raw=True);assert manager.state=='paused'
            assert manager.save_game();saved=manager.save_manager.load()
            manager.return_to_menu();manager.main_menu.selected=1;manager.main_menu.refresh_selection()
            app.input('enter',is_raw=True);frames(1)
            assert manager.state=='playing' and manager.scene_manager.narrative.snapshot()==saved['narrative']
            p,h,g=refs();g.enabled=False;g.ai.grace_time=0;current='main_hall'
            # Collect only still-present evidence through the same interaction rays.
            for item_id in sorted(DOCUMENT_IDS-set(p.narrative.documents)):
                visit('story_'+item_id.removeprefix('lore_'))
            power();remaining_puzzles();exit_house('truth')
            report['routes']['C']='Manual save; menu Continue without intro; retained evidence; Truth'
            new_game('D');visit('story_family_photo');visit('story_keeper_journal');power()
            manager.automatic_checkpoints=True;go_room('main_hall');frames(2)
            checkpoint=manager.save_manager.load('checkpoint');assert checkpoint
            p,h,g=refs();g.enabled=True;g.position=p.position+Vec3(0,0,-1)
            g.ai.grace_time=g.ai.recovery_time=0;g.ai._set_state(GhostState.CHASE);g.ai._remember(p.position,.3)
            frames(60)
            assert manager.state=='dead',manager.state
            manager.end_screen.selected=2;manager.end_screen.refresh_selection();app.input('enter',is_raw=True);frames(1)
            assert manager.state=='playing' and manager.scene_manager.narrative.snapshot()==checkpoint['narrative']
            p,h,g=refs();g.enabled=False;g.ai.grace_time=0;current='foyer';manager.automatic_checkpoints=False
            for item_id in sorted(DOCUMENT_IDS-set(p.narrative.documents)):
                visit('story_'+item_id.removeprefix('lore_'))
            remaining_puzzles();exit_house('truth')
            report['routes']['D']='Power checkpoint; live ghost capture; Retry; retained evidence; Truth'
        if '--visual-only' in sys.argv:
            new_game('A')
        else:
            run_routes()
        # Stationary native effect and accessibility fixtures, with actor
        # positions deliberately staged and reported separately from routes.
        app.input('r',is_raw=True);frames(1);p,h,g=refs();g.enabled=False;g.ai.grace_time=0
        p.position=Vec3(0,0,-7);p.rotation_y=0;p.camera_pivot.rotation_x=0;camera.rotation=Vec3(0,0,0)
        p.obtain_flashlight();p.toggle_flashlight()
        visit('living_instructions');visit('storage_fuse');visit_prop('fuse_box')
        sm=manager.scene_manager;sm.story.cancel_active();sm.story.next_allowed=0;sm.horror.director.quiet_until=0
        sm.narrative.completed_events.discard('power_restoration')
        p.position=Vec3(0,0,-7);current='main_hall';p.rotation_y=0;p.camera_pivot.rotation_x=0;camera.rotation=Vec3(0,0,0)
        assert sm.story.start_event('power_restoration');frames(70);capture('power_restoration')
        sm.story.cancel_active();sm.story.next_allowed=0;sm.horror.director.quiet_until=0
        sm.house.pickups['story_keeper_journal'].interact(p);manager.hud.panel.close()
        sm.narrative.completed_events.discard('the_watcher')
        sm.story.enabled=False;frames(2);capture('apparition_clear');sm.story.enabled=True
        assert sm.story.start_event('the_watcher')
        assert sm.story.active['temporary'];frames(2);capture('apparition');sm.story.cancel_active()
        from PIL import Image, ImageChops
        root=Path(__file__).parent
        difference=ImageChops.difference(Image.open(root/'render_m9_apparition.png').convert('RGB'),
                                        Image.open(root/'render_m9_apparition_clear.png').convert('RGB'))
        pixels=difference.crop((int(app.win.get_x_size()*.4),int(app.win.get_y_size()*.35),
                                int(app.win.get_x_size()*.6),int(app.win.get_y_size()*.78))).get_flattened_data()
        changed=sum(max(rgb)>5 for rgb in pixels)
        assert changed>100,('Apparition not visibly rendered',changed)
        report['apparition_changed_world_pixels']=changed
        for factor in (1,1.25,1.5):
            manager.preferences.values['text_scale']=factor;manager.apply_live_preferences()
            for size in ((640,480),(960,720),(1280,720)):
                resize(*size);app.input('tab',is_raw=True);app.input('right arrow',is_raw=True);frames(2)
                capture(f'journal_{factor}_{size[0]}x{size[1]}');app.input('enter',is_raw=True);frames(2)
                capture(f'note_{factor}_{size[0]}x{size[1]}');app.input('escape',is_raw=True)
                manager.story_screen.begin('truth',__import__('game.systems.narrative',fromlist=['STORY']).STORY['endings']['truth'])
                manager.story_screen.enabled=True;frames(2);capture(f'cards_{factor}_{size[0]}x{size[1]}');manager.story_screen.enabled=False
        report['counts']=dict(entities=sum(not e.is_empty() for e in scene.entities),colliders=len(scene.collidables),
                              lights=app.render.get_state().get_attrib(LightAttrib).get_num_on_lights())
        profile='render_m9_visual_profile.json' if '--visual-only' in sys.argv else 'render_m9_story_profile.json'
        Path(__file__).with_name(profile).write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('STORY_NATIVE_ROUTES_OK',report['routes'],flush=True)
    finally:
        manager.return_to_menu();app.destroy();directory.cleanup()


if __name__=='__main__':
    ShowBase.run=verify
    runpy.run_path(str(Path(__file__).resolve().parents[2]/'main.py'),run_name='__main__')
