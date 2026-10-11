"""Cached project assets; deterministic original materials and safe fallbacks."""
import json
import logging
import math
from pathlib import Path
import random
import wave

ROOT = Path(__file__).resolve().parents[1] / 'assets'
MATERIALS = ('wood','wallpaper','plaster','fabric','metal','tile')
log = logging.getLogger(__name__)


def procedural_texture(name, size=128):
    """Monochrome/modestly tinted albedo only. Inherits the house lighting."""
    if name not in MATERIALS or size not in (64,128):
        raise ValueError('Unsupported procedural material or resolution')
    from panda3d.core import PNMImage, Texture as PandaTexture
    from ursina import Texture
    image=PNMImage(size,size,3)
    rng=random.Random(1729+MATERIALS.index(name))
    for y in range(size):
        v=y/size
        for x in range(size):
            u=x/size
            noise=rng.uniform(-.025,.025)
            shade=.95+noise
            if name=='wood':
                board=int(v*4)
                shade=.87+.07*math.sin((u*42+math.sin(v*18)*.5)*math.pi)+noise
                if y%(size//4)<=1 or (x+board*(size//4))%(size//2)<=1:shade=.42
                if abs(math.sin(u*27+v*9))>.999:shade-=.10
            elif name=='wallpaper':
                shade=.97+noise-.06*math.sin(u*8*math.pi)**2*math.sin(v*4*math.pi)**2
                stain=max(0,math.sin(u*2*math.pi+.4)*math.cos(v*2*math.pi)-.25)
                shade-=.16*stain
                crack=abs(u-.52-.04*math.sin(v*14))
                if crack<.006 and .12<v<.72:shade-=.20
            elif name=='plaster':
                shade=.9+noise-.10*max(0,math.sin(u*17)*math.cos(v*13))
            elif name=='fabric':
                shade=.92+noise-.055*((x%4==0)+(y%4==0))
            elif name=='metal':
                shade=.94+noise-.12*max(0,math.sin(u*19+v*31)-.7)
            elif name=='tile':
                shade=.94+noise
                if x%(size//4)<2 or y%(size//4)<2:shade=.5
            shade=max(.3,min(1,shade))
            image.set_xel(x,y,shade,shade*(.93 if name=='wood' else 1),shade*(.84 if name=='wood' else 1))
    native=PandaTexture('sinister_'+name+'_'+str(size));native.load(image)
    native.set_wrap_u(native.WM_repeat);native.set_wrap_v(native.WM_repeat)
    texture=Texture(native,filtering='mipmap')
    texture._cached_image=None
    return texture


class AssetManager:
    def __init__(self, root=ROOT):
        self.root=Path(root).resolve()
        self.cache={}
        self.warned=set()
        try:
            document=json.loads((self.root/'manifest.json').read_text(encoding='utf-8'))
            if type(document.get('version')) is not int or document['version']!=1 or not isinstance(document.get('assets'),dict):
                raise ValueError('Unsupported asset manifest')
            self.manifest=document['assets']
        except (OSError,ValueError,AttributeError):
            self.manifest={}
            self.warn('manifest','Asset manifest unavailable; procedural/primitive fallbacks remain active')

    def warn(self,key,message):
        if key not in self.warned:
            log.warning('%s',message)
            if len(self.warned)<128:self.warned.add(key)

    def path(self,name,kind):
        entry=self.manifest.get(name)
        if not isinstance(entry,dict) or entry.get('kind')!=kind or not entry.get('path'):
            return None
        try:
            relative=Path(entry['path'])
            path=(self.root/relative).resolve()
            if relative.is_absolute() or not path.is_relative_to(self.root):
                raise ValueError('Asset path escapes root')
            allowed={'audio':('.wav','.ogg'),'texture':('.png','.jpg'),'model':('.obj','.bam','.egg')}
            if path.suffix.lower() not in allowed[kind] or not path.is_file() or path.stat().st_size>8*1024*1024:
                raise ValueError('Missing, unsupported or oversized asset')
            if kind=='audio' and path.suffix.lower()=='.wav':
                with wave.open(str(path),'rb') as stream:
                    if stream.getnchannels() not in (1,2) or stream.getsampwidth()!=2 or stream.getnframes()==0:
                        raise ValueError('Unsupported PCM sound')
            return path
        except (OSError,ValueError,TypeError,KeyError,EOFError,wave.Error) as error:
            self.warn(name,f'Asset {name} unavailable: {error}')
            return None

    def texture(self,name,quality='standard'):
        key=('texture',name,quality)
        if key not in self.cache:
            from ursina import Texture
            path=self.path(name,'texture')
            try:
                self.cache[key]=Texture(path,filtering='mipmap') if path else procedural_texture(name,64 if quality=='low' else 128)
            except Exception as error:
                self.warn(name,f'Material {name} fallback: {error}')
                self.cache[key]=procedural_texture('plaster',64)
        return self.cache[key]

    def model(self,name,fallback='cube'):
        key=('model',name)
        if key not in self.cache:
            from ursina import load_model
            path=self.path(name,'model')
            try:
                if path and path.suffix.lower() in ('.egg','.bam'):
                    from panda3d.core import Filename
                    from ursina import application
                    self.cache[key]=application.base.loader.load_model(Filename.from_os_specific(str(path)))
                else:
                    self.cache[key]=load_model(path.name,folder=path.parent,use_deepcopy=True) if path else None
                if path and self.cache[key] is None:
                    self.warn(name,f'Model {name} could not be decoded; using primitive fallback')
            except Exception as error:
                self.warn(name,f'Model {name} fallback: {error}');self.cache[key]=None
        return self.cache[key] or fallback

    def metrics(self):
        textures=[value._texture for key,value in self.cache.items() if key[0]=='texture']
        return dict(cached_entries=len(self.cache),procedural_texture_ram_bytes=sum(t.get_ram_image_size() for t in textures),
                    procedural_texture_count=len(textures))

    def box_mesh(self, name, boxes):
        """Bake once; return independent nodes sharing immutable geometry."""
        key = ('geometry',name)
        if key not in self.cache:
            from ursina import Mesh, Vec3, color
            corners = [(-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),
                       (1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1)]
            faces = [(0,4,6,2),(5,1,3,7),(1,0,2,3),(4,5,7,6),(2,6,7,3),(1,5,4,0)]
            directions = [(0,0,-1),(0,0,1),(-1,0,0),(1,0,0),(0,1,0),(0,-1,0)]
            vertices, triangles, normals, uvs, colors = [], [], [], [], []
            for position,size,tint in boxes:
                for face,normal in zip(faces,directions):
                    start = len(vertices)
                    for index,uv in zip(face,((0,0),(1,0),(1,1),(0,1))):
                        c = corners[index]
                        vertices.append(tuple(Vec3(*position)+Vec3(*(c[j]*size[j]/2 for j in range(3)))))
                        normals.append(normal);uvs.append(uv);colors.append(color.rgb32(*tint))
                    triangles.extend(((start,start+2,start+1),(start,start+3,start+2)))
            self.cache[key] = Mesh(vertices=vertices,triangles=triangles,normals=normals,uvs=uvs,colors=colors)
        # Entity.model reparents a NodePath verbatim in Ursina 8.3. Sharing that
        # root would steal presentation from an outgoing staged-load scene or
        # the real ghost during capture. copy_to shares Geom/vertex buffers but
        # gives each caller its own parent, texture and color-scale state.
        from panda3d.core import NodePath
        return self.cache[key].copy_to(NodePath('asset_instance'))

    def apparition_mesh(self):
        return self.box_mesh('apparition', [
            ((0,.1,0),(.44,1.1,.045),(255,255,255)),
            ((0,.8,0),(.25,.32,.045),(255,255,255)),
            ((-.28,.05,0),(.10,.85,.045),(255,255,255)),
            ((.28,.05,0),(.10,.85,.045),(255,255,255)),
            ((0,-.54,0),(.30,.45,.045),(255,255,255))])


assets=AssetManager()
