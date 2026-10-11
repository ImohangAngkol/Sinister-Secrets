"""Rebuild small original mono PCM assets with Python's standard library."""
from array import array
import json
import math
from pathlib import Path
import random
import wave

ROOT=Path(__file__).resolve().parent
RATE=22050
DURATIONS={'ambience':6.,'tension':4.,'step':.18,'creak':.65,'knock':.35,'presence':.8,'search':.6,'inspect':.65,'capture':1.8,'door':.4,'fuse':.25,'lockbox':.3,'crowbar':.45,'pickup':.2,'battery':.3,'select':.08}


def samples(name):
    seconds=DURATIONS[name]
    rng=random.Random(1729+list(DURATIONS).index(name))
    output=array('h')
    smooth_noise=0
    for index in range(round(RATE*seconds)):
        t=index/RATE;f=t/seconds
        smooth_noise=.88*smooth_noise+.12*rng.uniform(-1,1)
        if name in ('ambience','tension'):
            # All frequencies complete integer cycles; no abrupt loop seam.
            frequency=55 if name=='ambience' else 70
            signal=.08*math.sin(2*math.pi*frequency*t)+.035*math.sin(2*math.pi*(frequency*2+.5)*t)
            signal*=.65+.25*math.cos(2*math.pi*t/seconds)
            if name=='ambience':
                signal+=.025*smooth_noise*math.sin(math.pi*f)**2
        else:
            fade=math.sin(math.pi*f)**2
            if name=='step':signal=.38*smooth_noise*math.exp(-t*20)+.13*math.sin(2*math.pi*85*t)*math.exp(-t*22)
            elif name=='capture':signal=.19*smooth_noise+.12*math.sin(2*math.pi*(100*t+35*t*t))
            elif name in ('creak','door','crowbar','inspect'):signal=.21*smooth_noise+.12*math.sin(2*math.pi*(120*t+60*t*t))
            elif name in ('presence','search'):signal=.09*math.sin(2*math.pi*90*t)+.08*smooth_noise
            elif name=='knock':signal=.3*math.sin(2*math.pi*110*t)*math.exp(-t*14)
            else:
                frequency={'fuse':260,'lockbox':190,'pickup':420,'battery':330,'select':520}[name]
                signal=.19*math.sin(2*math.pi*frequency*t)*math.exp(-t*12)+.06*smooth_noise
            signal*=fade
        output.append(round(max(-.4,min(.4,signal))*32767))
    if name in ('step','knock'):
        # Their short exponential envelope otherwise buries these transients
        # below the room tone. Normalize modestly before category/user volumes.
        peak=max(map(abs,output))
        if peak:
            output=array('h',(round(value/peak*.28*32767) for value in output))
    return output


def generate():
    entries=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))['assets']
    for name,entry in entries.items():
        if entry['kind']!='audio':continue
        path=ROOT/entry['path'];path.parent.mkdir(parents=True,exist_ok=True)
        with wave.open(str(path),'wb') as stream:
            stream.setparams((1,2,RATE,0,'NONE','not compressed'))
            stream.writeframes(samples(name).tobytes())
    print('Generated 16 original PCM sounds.')

if __name__=='__main__':generate()
