"""Headless FluidSynth backend for optional, self-contained SF2 packs.

The application creates no FluidSynth audio or MIDI driver. Its existing WASAPI
worker and offline exporter both consume the same interleaved float renderer.
"""
import ctypes as C
import hashlib
import os
from pathlib import Path

import numpy as np

from lingfeng.audio.sfz import relative_file


def configure_library(api):
    pointer=C.c_void_p; integer=C.c_int; string=C.c_char_p
    signatures={
        'new_fluid_settings':([],pointer),
        'delete_fluid_settings':([pointer],None),
        'fluid_settings_setnum':([pointer,string,C.c_double],integer),
        'fluid_settings_setint':([pointer,string,integer],integer),
        'new_fluid_synth':([pointer],pointer),
        'delete_fluid_synth':([pointer],None),
        'fluid_synth_sfload':([pointer,string,integer],integer),
        'fluid_synth_program_select':([pointer,integer,integer,integer,integer],integer),
        'fluid_synth_noteon':([pointer,integer,integer,integer],integer),
        'fluid_synth_noteoff':([pointer,integer,integer],integer),
        'fluid_synth_cc':([pointer,integer,integer,integer],integer),
        'fluid_synth_pitch_bend':([pointer,integer,integer],integer),
        'fluid_synth_all_sounds_off':([pointer,integer],integer),
        'fluid_synth_write_float':([pointer,integer,pointer,integer,integer,pointer,integer,integer],integer),
        'fluid_synth_get_channel_preset':([pointer,integer],pointer),
        'fluid_synth_get_internal_bufsize':([pointer],integer),
        'fluid_version_str':([],string),
    }
    for name,(arguments,result) in signatures.items():
        function=getattr(api,name);function.argtypes=arguments;function.restype=result
    return api


def load_library(path,info):
    """Verify every packaged runtime DLL before the Windows loader sees it."""
    path=Path(path).resolve();root=Path(info['path']).resolve()
    hashes=info.get('library_hashes',{})
    if not hashes or info['library'] not in hashes:
        raise ValueError('SF2 runtime dependency hashes are missing')
    dependencies=[]
    for name,expected in hashes.items():
        file=(root/relative_file(name)).resolve()
        if not file.is_relative_to(root) or file.suffix.lower()!='.dll' or not file.is_file():
            raise ValueError('Missing or unsafe SF2 runtime dependency: '+name)
        if hashlib.sha256(file.read_bytes()).hexdigest()!=expected:
            raise ValueError('SF2 runtime dependency checksum mismatch: '+name)
        dependencies.append(file)
    # An unlisted sibling DLL must not be picked up through native resolution.
    if any(p.resolve() not in dependencies for p in path.parent.glob('*.dll')):
        raise ValueError('Unverified DLL in the SF2 runtime directory')
    cookie=os.add_dll_directory(str(path.parent)) if hasattr(os,'add_dll_directory') else None
    try:
        options={'winmode':0x1100} if os.name=='nt' else {}
        # Dependencies stay loaded for the same lifetime as their main library.
        handles=[C.CDLL(str(p),**options) for p in dependencies if p!=path]
        api=configure_library(C.CDLL(str(path),**options))
        api._lingfeng_dependency_handles=handles
        api._lingfeng_dll_directory=cookie
        return api
    except Exception:
        if cookie:cookie.close()
        raise


class Sf2Voice:
    def __init__(self,api,info,item,rate,block,offline=False):
        self.api=api;self.settings=None;self.handle=None;self.gain=item['gain']
        self.volume=100;self.expression=127;self.pan=64;self.rendered=0;self.quantum=64
        root=Path(info['path']).resolve()
        soundfont=(root/relative_file(item['sf2'])).resolve()
        if not soundfont.is_relative_to(root) or not soundfont.is_file():
            raise ValueError('Missing or unsafe SF2 soundfont')
        with soundfont.open('rb') as stream:header=stream.read(12)
        if header[:4]!=b'RIFF' or header[8:12]!=b'sfbk':
            raise ValueError('Expected an SF2 soundfont')
        try:
            self.settings=api.new_fluid_settings()
            if not self.settings:raise RuntimeError('Cannot create FluidSynth settings')
            self.check(api.fluid_settings_setnum(self.settings,b'synth.sample-rate',rate))
            self.check(api.fluid_settings_setnum(self.settings,b'synth.gain',0.6))
            for key,value in ((b'synth.polyphony',info.get('voices',256)),
                              (b'synth.reverb.active',0),(b'synth.chorus.active',0),
                              (b'synth.cpu-cores',1),(b'synth.threadsafe-api',0)):
                self.check(api.fluid_settings_setint(self.settings,key,value))
            self.handle=api.new_fluid_synth(self.settings)
            if not self.handle:raise RuntimeError('Cannot create FluidSynth synthesizer')
            self.quantum=api.fluid_synth_get_internal_bufsize(self.handle)
            identifier=api.fluid_synth_sfload(self.handle,str(soundfont).encode('utf-8'),0)
            if identifier<0:raise ValueError('Cannot load SF2 soundfont: '+item['sf2'])
            self.check(api.fluid_synth_program_select(self.handle,0,identifier,item.get('bank',0),item['model']))
            if not api.fluid_synth_get_channel_preset(self.handle,0):
                raise ValueError('SF2 bank does not contain the selected program')
            # Consistent host-side volume/pan/expression avoids applying MIDI's
            # squared volume curve in addition to Lingfeng's existing controls.
            self.check(api.fluid_synth_cc(self.handle,0,7,127))
            self.check(api.fluid_synth_cc(self.handle,0,11,127))
            self.check(api.fluid_synth_cc(self.handle,0,10,64))
            for cc,value in item.get('controls',{}).items():self.send(0xb0,int(cc),round(value))
        except Exception:
            self.close();raise

    @staticmethod
    def check(result):
        if result!=0:raise RuntimeError('FluidSynth operation failed')

    def send(self,status,a=0,b=0):
        kind=status&0xf0
        if kind==0x90 and b:self.check(self.api.fluid_synth_noteon(self.handle,0,a,b))
        elif kind in (0x80,0x90):self.api.fluid_synth_noteoff(self.handle,0,a)
        elif kind==0xe0:self.check(self.api.fluid_synth_pitch_bend(self.handle,0,a+(b<<7)))
        elif kind==0xb0:
            if a==7:self.volume=b
            elif a==11:self.expression=b
            elif a==10:self.pan=b
            elif a==120:
                self.check(self.api.fluid_synth_all_sounds_off(self.handle,0))
                # write_float caches the remainder of its internal DSP block.
                # Discard that already-rendered audio on immediate stop.
                pending=(-self.rendered)%self.quantum
                if pending:
                    discarded=np.empty((pending,2),np.float32)
                    pointer=discarded.ctypes.data_as(C.c_void_p)
                    self.check(self.api.fluid_synth_write_float(self.handle,pending,pointer,0,2,pointer,1,2))
                self.rendered=0
            else:self.check(self.api.fluid_synth_cc(self.handle,0,a,b))

    def render(self,count):
        result=np.empty((count,2),np.float32)
        if not count:return result
        pointer=result.ctypes.data_as(C.c_void_p)
        self.check(self.api.fluid_synth_write_float(self.handle,count,pointer,0,2,pointer,1,2))
        self.rendered=(self.rendered+count)%self.quantum
        result*=self.gain*(self.volume/127)*(self.expression/127)
        if self.pan<64:result[:,1]*=self.pan/64
        elif self.pan>64:result[:,0]*=(127-self.pan)/63
        return result

    def close(self):
        if self.handle:self.api.delete_fluid_synth(self.handle);self.handle=None
        if self.settings:self.api.delete_fluid_settings(self.settings);self.settings=None

    def __del__(self):self.close()
