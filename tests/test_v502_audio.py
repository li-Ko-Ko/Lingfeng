"""Windows MIDI controller hygiene without changing musical note content."""
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from popscore.audio import MidiRouter,Transport
from popscore.playback import PlaybackSchedule,silence_channels


class Output:
    def __init__(self,*args):
        self.events=[];self.pedal={};self.keys=set();self.voices=set();self.closed=False
    def send(self,status,a=0,b=0):
        self.events.append((status,a,b));channel=status&15;kind=status&0xf0
        if kind==0x90 and b:
            self.keys.add((channel,a));self.voices.add((channel,a))
        elif kind==0x80 or kind==0x90 and not b:
            self.keys.discard((channel,a))
            if not self.pedal.get(channel,False):self.voices.discard((channel,a))
        elif kind==0xb0:
            if a==64:
                self.pedal[channel]=b>=64
                if b<64:self.voices={n for n in self.voices if n[0]!=channel or n in self.keys}
            elif a==120:
                self.voices={n for n in self.voices if n[0]!=channel}
            elif a==123:
                self.keys={n for n in self.keys if n[0]!=channel}
                if not self.pedal.get(channel,False):self.voices={n for n in self.voices if n[0]!=channel}
            elif a==121:self.pedal[channel]=False
    def close(self):self.closed=True
    def stop(self):self.voices.clear();self.keys.clear()


class WindowsStopTests(unittest.TestCase):
    def test_old_notes_off_keeps_sustain_held_high_note_but_scoped_stop_removes_it(self):
        out=Output();out.send(0xb0,64,127);out.send(0x90,83,92);out.send(0x80,83)
        out.send(0xb0,123,0);self.assertIn((0,83),out.voices)
        silence_channels(out,(0,));self.assertNotIn((0,83),out.voices)
        self.assertEqual(out.events[-3:],[(0xb0,64,0),(0xb0,120,0),(0xb0,123,0)])

    def test_schedule_stop_clears_both_playback_channels_but_preserves_preview_and_monitor(self):
        out=Output();schedule=PlaybackSchedule(out,lambda:0)
        for ch in range(6):out.send(0xb0|ch,64,127);out.send(0x90|ch,83,92)
        schedule.stop()
        self.assertEqual(out.voices,{(ch,83) for ch in (2,3,4,5)})
        self.assertFalse(schedule.playing)

    def test_transport_preserve_auditions_does_not_silence_preview_or_monitor(self):
        t=Transport();t.synth=out=Output()
        try:
            for ch in range(6):out.send(0xb0|ch,64,127);out.send(0x90|ch,83,92)
            t.stop(preserve_auditions=True)
            self.assertEqual(out.voices,{(ch,83)for ch in (2,3,4,5)})
        finally:t.close()

    def test_full_transport_stop_clears_sustain_and_sound_on_all_owned_channels(self):
        t=Transport();t.synth=out=Output()
        try:
            for ch in range(6):out.send(0xb0|ch,64,127);out.send(0x90|ch,83,92)
            t.stop();self.assertFalse(out.voices)
            self.assertEqual({ch for ch,on in out.pedal.items() if on},set())
        finally:t.close()


class WindowsInitializationTests(unittest.TestCase):
    def create(self,settings):
        self.output_patch=patch('popscore.audio.Synth',Output);self.output_patch.start();self.addCleanup(self.output_patch.stop)
        self.devices_patch=patch('popscore.audio.midi_devices',return_value=[(0,'Windows GS')]);self.devices_patch.start();self.addCleanup(self.devices_patch.stop)
        self.default_patch=patch('popscore.audio.default_midi_device',return_value=0);self.default_patch.start();self.addCleanup(self.default_patch.stop)
        router=MidiRouter(settings);self.addCleanup(router.close);return router

    def test_windows_channels_reset_before_program_without_reverb_or_volume_rewrite(self):
        settings={role:dict(device='default',program=p)for role,p in [('melody',1),('chords',0)]}
        original=copy.deepcopy(settings);router=self.create(settings);out=router.outputs[0]
        self.assertEqual(settings,original)
        for ch in range(6):
            events=[e for e in out.events if e[0]&15==ch]
            self.assertEqual(events[:5],[(0xb0|ch,121,0),(0xb0|ch,64,0),(0xb0|ch,120,0),(0xb0|ch,123,0),(0xe0|ch,0,64)])
            self.assertEqual(events[-1],(0xc0|ch,1 if ch%2==0 else 0,0))
        self.assertFalse(any(status&0xf0==0xb0 and a in (7,91,93)for status,a,b in out.events))

    def test_default_and_named_alias_still_share_one_output(self):
        router=self.create({'melody':dict(device='default',program=1),'chords':dict(device='Windows GS',program=0)})
        self.assertEqual(len(router.outputs),1)
        self.assertTrue(all(output is router.outputs[0]for output in router.routes.values()))

    def test_panic_retains_note_numbers_program_and_volume_messages(self):
        router=self.create({role:dict(device='default',program=1)for role in ('melody','chords')});out=router.outputs[0]
        router.send(0xb0,7,72);router.send(0x90,108,92);router.send(0x80,108,0)
        self.assertEqual(out.events[-3:],[(0xb0,7,72),(0x90,108,92),(0x80,108,0)])
        silence_channels(router,(0,))
        self.assertFalse(any(status&0xf0==0xc0 for status,a,b in out.events[-3:]))


class StartupCleanupTests(unittest.TestCase):
    def test_threaded_synthesis_startup_error_is_not_replaced_by_pipe_close_race(self):
        from popscore.synthesis import NativeSynth
        from popscore.i18n import set_language,tr,LANGUAGE
        self.addCleanup(set_language,LANGUAGE);set_language('en')
        message=tr('合成音源“{0}”未安装或已更改，请复制音源文件夹后在设置中重新扫描。','synth:v502-no-such-pack')
        for _ in range(12):
            with self.assertRaises(RuntimeError)as caught:NativeSynth({0:'synth:v502-no-such-pack'},{0:0},threaded=True)
            self.assertEqual(str(caught.exception),message)


if __name__=='__main__':unittest.main()
