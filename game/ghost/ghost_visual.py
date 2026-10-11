"""Original jointed humanoid, presentation only; no collision/perception changes."""
import math
from ursina import Entity, Vec3, color
from game.systems.asset_manager import assets


class GhostVisual(Entity):
    def __init__(self,parent,cinematic=False,**kwargs):
        super().__init__(parent=parent,shader=None,**kwargs)
        self.cinematic=cinematic
        self.animation_state='idle'
        self.phase=self.clock=self.amount=0.
        self.joints={}
        cloth=color.rgb32(93,100,96)
        pale=color.rgb32(186,191,178)
        self.torso=Entity(parent=self,shader=None,y=1.05)
        def part(name,parent,position,scale,tint,model='cube'):
            joint=Entity(parent=parent,shader=None,position=position)
            Entity(parent=joint,shader=None,model=model,scale=scale,color=tint,
                   texture=assets.texture('fabric') if tint==cloth else None)
            self.joints[name]=joint
            return joint
        part('coat',self.torso,(0,.22,0),(.46,.68,.29),cloth)
        part('hem',self.torso,(0,-.25,0),(.51,.38,.31),cloth)
        part('collar',self.torso,(0,.57,-.01),(.32,.12,.29),color.rgb32(48,52,49))
        self.head=part('head',self.torso,(.025,.80,0),(.30,.44,.30),pale,'sphere')
        # Hollow sockets and a long dark mouth face the ghost's +Z forward.
        # Sockets and mouth always move together with the head. Bake their
        # original shapes/tints once, reducing three draws to one geometry.
        face = [((x,.035,.142),(.065,.065,.027),(9,12,11)) for x in (-.07,.07)]
        face.append(((0,-.105,.142),(.04,.10,.027),(27,30,28)))
        Entity(parent=self.head,model=assets.box_mesh('ghost_face',face),shader=None)
        for side in (-1,1):
            arm=Entity(parent=self.torso,shader=None,position=(side*.28,.45,0))
            Entity(parent=arm,model='cube',shader=None,y=-.35,scale=(.11,.78,.12),color=cloth,texture=assets.texture('fabric'))
            Entity(parent=arm,model='cube',shader=None,y=-.78,z=.025,scale=(.095,.22,.09),color=pale)
            leg=Entity(parent=self,shader=None,position=(side*.14,.78,0))
            Entity(parent=leg,model='cube',shader=None,y=-.34,scale=(.14,.64,.17),color=cloth,texture=assets.texture('fabric'))
            Entity(parent=leg,model='cube',shader=None,y=-.70,z=.06,scale=(.17,.13,.30),color=color.rgb32(37,39,38))
            self.joints['arm'+str(side)]=arm;self.joints['leg'+str(side)]=leg
        if cinematic:
            from ursina.shaders import unlit_shader
            self.shader=unlit_shader
            # Child Entities explicitly cleared shaders; parent inheritance
            # provides the controlled camera-space encounter coloration.
            self.set_bin('fixed',40);self.set_depth_test(False);self.set_depth_write(False)

    def advance(self,dt,displacement=0,state='idle',inspection=False):
        dt=max(0,dt)
        self.clock+=dt
        self.phase+=max(0,displacement)*math.tau/1.4
        state=getattr(state,'name',str(state)).lower()
        if inspection:state='inspection'
        elif state=='patrol':state='walk' if displacement>1e-5 else 'idle'
        self.animation_state=state
        target=1. if displacement>1e-5 and state not in ('jumpscare','capture') else 0.
        self.amount+=(target-self.amount)*(1-math.exp(-8*dt))
        stride=math.sin(self.phase)*self.amount
        amp=26 if state=='chase' else 12
        blend=1-math.exp(-8*dt)
        def turn(joint,angle):joint.rotation_x+=(angle-joint.rotation_x)*blend
        for side in (-1,1):
            turn(self.joints['leg'+str(side)],side*stride*amp)
            reach=-35 if state in ('inspection','jumpscare','capture') else -10 if state=='chase' else 0
            turn(self.joints['arm'+str(side)],reach-side*stride*amp*.65)
        self.torso.y=1.05+.008*math.sin(self.clock*1.6)+.012*math.cos(self.phase*2)*self.amount
        turn(self.torso,-8 if state=='chase' else 3 if state=='inspection' else 0)
        turn(self.head,9 if state=='inspection' else -10 if state=='capture' else 0)
        self.head.rotation_y=(math.sin(self.clock*1.2)*14 if state in ('search','investigate','inspection') else math.sin(self.clock*.7)*3)
        self.head.rotation_z=5+math.sin(self.clock*.9)*2

    def reset(self):
        self.phase=self.clock=self.amount=0.
        self.animation_state='idle'
        self.torso.position=Vec3(0,1.05,0)
        for joint in self.joints.values():joint.rotation=Vec3(0,0,0)
