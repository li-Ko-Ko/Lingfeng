"""FluidSynth isolation and MIDI behavior; optional real-bank integration."""
import ctypes as C
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from lingfeng.audio.sf2 import Sf2Voice,load_library

ROOT=Path(__file__).resolve().parents[1]


class FakeFluid:
    """Only the headless renderer API exists; no OS audio/MIDI driver is used."""
    def __init__(self):self.calls=[];self.fail_load=False;self.freed=[]
    def new_fluid_settings(self):return 1
    def new_fluid_synth(self,settings):return 2
    def delete_fluid_settings(self,settings):self.freed.append(('settings',settings))
    def delete_fluid_synth(self,synth):self.freed.append(('synth',synth))
    def fluid_settings_setnum(self,*args):self.calls.append(('setting',*args));return 0
    fluid_settings_setint=fluid_settings_setnum
    def fluid_synth_sfload(self,*args):return -1 if self.fail_load else 3
    def fluid_synth_program_select(self,*args):self.calls.append(('program',*args));return 0
    def fluid_synth_get_channel_preset(self,*args):return 4
    def fluid_synth_get_internal_bufsize(self,*args):return 64
    def fluid_synth_cc(self,*args):self.calls.append(('cc',*args));return 0
    def fluid_synth_noteon(self,*args):self.calls.append(('on',*args));return 0
    def fluid_synth_noteoff(self,*args):self.calls.append(('off',*args));return 0
    def fluid_synth_pitch_bend(self,*args):self.calls.append(('bend',*args));return 0
    def fluid_synth_all_sounds_off(self,*args):self.calls.append(('stop',*args));return 0
    def fluid_synth_write_float(self,handle,count,left,loff,lincr,right,roff,rincr):
        self.calls.append(('render',count))
        output=C.cast(left,C.POINTER(C.c_float))
        for i in range(count*2):output[i]=1
        return 0


class Sf2BackendTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'tmp').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'tone.sf2').write_bytes(b'RIFF\x04\0\0\0sfbk')
        self.api=FakeFluid();self.info=dict(path=str(self.root),voices=256)
        self.item=dict(sf2='tone.sf2',model=4,bank=0,gain=.5)

    def voice(self):
        voice=Sf2Voice(self.api,self.info,self.item,44100,256);self.addCleanup(voice.close);return voice

    def test_midi_sustain_velocity_zero_and_pitch_bend_use_one_internal_channel(self):
        voice=self.voice();voice.send(0x93,60,90);voice.send(0x93,60,0)
        voice.send(0xb7,64,127);voice.send(0xe5,0,127)
        self.assertIn(('on',2,0,60,90),self.api.calls)
        self.assertIn(('off',2,0,60),self.api.calls)
        self.assertIn(('cc',2,0,64,127),self.api.calls)
        self.assertIn(('bend',2,0,16256),self.api.calls)

    def test_volume_expression_and_pan_apply_once_after_rendering(self):
        voice=self.voice();voice.send(0xb0,7,127);voice.send(0xb0,11,127)
        self.assertTrue(np.allclose(voice.render(3),.5))
        voice.send(0xb0,10,0);data=voice.render(3)
        self.assertTrue(np.allclose(data[:,0],.5));self.assertFalse(np.any(data[:,1]))
        voice.send(0xb0,11,0);self.assertFalse(np.any(voice.render(3)))
        self.assertEqual(voice.render(0).shape,(0,2))

    def test_immediate_stop_discards_pre_rendered_internal_block(self):
        voice=self.voice();voice.render(3);voice.send(0xb0,120,0)
        self.assertEqual(self.api.calls[-2:],[('stop',2,0),('render',61)])
        self.assertEqual(voice.rendered,0)

    def test_failed_soundfont_load_releases_synth_and_settings(self):
        self.api.fail_load=True
        with self.assertRaises(ValueError):self.voice()
        self.assertEqual(self.api.freed,[('synth',2),('settings',1)])

    def test_assets_must_be_in_pack_and_have_a_soundfont_header(self):
        for path in ('../outside.sf2','C:/outside.sf2'):
            self.item['sf2']=path
            with self.assertRaises(ValueError):self.voice()
        self.item['sf2']='tone.sf2';(self.root/'tone.sf2').write_bytes(b'not soundfont')
        with self.assertRaises(ValueError):self.voice()
        self.assertFalse(self.api.calls)

    def test_dependency_tampering_and_unlisted_dlls_are_rejected_before_load(self):
        binary=self.root/'bin/main.dll';binary.parent.mkdir();binary.write_bytes(b'fixture')
        info=dict(path=str(self.root),library='bin/main.dll',library_hashes={'bin/main.dll':hashlib.sha256(binary.read_bytes()).hexdigest()})
        with patch('lingfeng.audio.sf2.C.CDLL',side_effect=AssertionError('must not execute native code')):
            binary.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum'):load_library(binary,info)
            binary.write_bytes(b'fixture');(binary.parent/'unlisted.dll').write_bytes(b'other')
            with self.assertRaisesRegex(ValueError,'Unverified'):load_library(binary,info)


@unittest.skipUnless((ROOT/'synths/keyboard-gm/synth.json').is_file(),'Optional FluidR3 pack is not installed')
class ActualFluidR3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=ROOT/'synths/keyboard-gm';cls.info=json.loads((cls.root/'synth.json').read_text('utf-8'))
        cls.info['path']=str(cls.root.resolve());cls.api=load_library(cls.root/cls.info['library'],cls.info)

    def voice(self,program=0):
        item=next(i for i in self.info['presets'] if i['program']==program)
        voice=Sf2Voice(self.api,self.info,item,44100,256,offline=True);self.addCleanup(voice.close);return voice

    def test_all_128_gm_programs_select_and_produce_finite_nonzero_pcm(self):
        for program in range(128):
            with self.subTest(program=program):
                # FluidR3's acoustic contrabass retains its natural bass range.
                voice=self.voice(program);voice.send(0x90,48 if program==43 else 60,100);data=voice.render(8192)
                self.assertTrue(np.isfinite(data).all());self.assertGreater(float(np.max(np.abs(data))),1e-6)
                voice.close()

    def test_partial_internal_blocks_stop_immediately_and_render_consistently(self):
        a=self.voice();b=self.voice()
        for voice in (a,b):voice.send(0x90,60,100)
        expected=a.render(5000);parts=np.concatenate([b.render(n) for n in (1,3,257,1000,3739)])
        self.assertTrue(np.array_equal(expected,parts))
        b.send(0xb0,120,0);self.assertFalse(np.any(b.render(1000)))

    def test_sustain_and_expression_are_supported_by_real_renderer(self):
        voice=self.voice(4);voice.send(0xb0,64,127);voice.send(0x90,60,100);voice.render(4410)
        voice.send(0x80,60);self.assertGreater(float(np.max(abs(voice.render(4410)))),1e-5)
        voice.send(0xb0,11,0);self.assertFalse(np.any(voice.render(100)))


if __name__=='__main__':unittest.main()
