"""Editor IPC backpressure, loading cancellation and cached sample safety."""
import ctypes as C
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from lingfeng.audio.playback import ProcessRouter
from lingfeng.audio import sfz
from lingfeng.audio.synthesis import BLOCK, RATE, _synthesis_worker
from tests.test_v50_audio import FileRouter

ROOT=Path(__file__).resolve().parents[1]


class SlowLoadingRouter:
    def __init__(self,settings):
        Path(settings['started']).write_text(str(os.getpid()),'utf-8')
        time.sleep(30)


class LoadingTests(unittest.TestCase):
    def test_precancelled_load_never_starts_a_process(self):
        cancel=threading.Event();cancel.set()
        with patch('lingfeng.audio.playback.multiprocessing.get_context') as context:
            with self.assertRaisesRegex(RuntimeError,'已取消|cancelled|canceled'):
                ProcessRouter({},cancel=cancel)
            context.assert_not_called()

    def test_cancel_during_loading_closes_own_child_promptly(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            path=Path(directory)/'started';cancel=threading.Event()
            def cancel_started():
                limit=time.monotonic()+5
                while not path.exists() and time.monotonic()<limit:time.sleep(.01)
                cancel.set()
            watcher=threading.Thread(target=cancel_started);watcher.start()
            started=time.monotonic()
            with self.assertRaisesRegex(RuntimeError,'已取消|cancelled|canceled'):
                ProcessRouter({'started':str(path)},SlowLoadingRouter,cancel=cancel)
            watcher.join(1)
            self.assertLess(time.monotonic()-started,6)
            self.assertTrue(path.exists())

    def test_transport_opener_is_optional_and_used_once(self):
        from lingfeng.audio.transport import Transport
        transport=Transport();opener=MagicMock();transport.router_opener=opener
        try:
            transport.open();transport.open()
            opener.assert_called_once_with(transport.settings)
        finally:transport.close()


class CommandTests(unittest.TestCase):
    def test_blocked_pipe_does_not_block_edits_or_reorder_midi_barriers(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            log=Path(directory)/'events';router=ProcessRouter({'log':str(log)},FileRouter)
            gate=threading.Event();entered=threading.Event();send=router.connection.send
            def delayed(packet):
                if packet[0]=='revise' and not entered.is_set():
                    entered.set();gate.wait(3)
                return send(packet)
            router.connection.send=delayed
            try:
                router.revise_schedule([],1,100,False,0);self.assertTrue(entered.wait(1))
                events=[(10,1,0,60,90)]
                started=time.monotonic()
                for end in range(100,300):router.revise_schedule(events,1,end,False,0)
                router.send(0x92,67,90)
                for end in range(300,500):router.revise_schedule(events,1,end,False,0)
                router.send(0x82,67,0)
                self.assertLess(time.monotonic()-started,.25)
                events.clear()
                with router.lock:
                    pending=list(router.outbound)
                    self.assertEqual([p[0] for p in pending],['revise','midi_batch','revise','midi_batch'])
                    self.assertEqual(pending[0][2][0],((10,1,0,60,90),))
                    self.assertEqual(pending[2][2][2],499)
                gate.set();router.send(0xc2,0)
                midi=[json.loads(line)[1:] for line in log.read_text('utf-8').splitlines()]
                self.assertEqual(midi[-3:],[[0x92,67,90],[0x82,67,0],[0xc2,0,0]])
            finally:gate.set();router.close()

    def test_native_event_storm_yields_to_audio_refill(self):
        class Connection:
            def __init__(self):self.packets=[('midi',(0x90,60,90),'en') for _ in range(256)]
            def poll(self,*args):return bool(self.packets)
            def recv(self):return self.packets.pop(0)
            def send(self,*args):pass
            def close(self):pass
        class Engine:
            def __init__(self,**kwargs):self.events=0
            def send(self,*args):
                self.events+=1;limit=time.perf_counter()+.001
                while time.perf_counter()<limit:pass
            def render(self,count):return np.zeros((count,2),np.float32)
            def close(self):pass
        connection=Connection();engine=Engine();counts=[];player=MagicMock()
        player.buffersize=4096;player.currentpadding=0;player.deviceperiod=(.01,.003)
        def write(player,data):
            counts.append((engine.events, len(data)));connection.packets=[('close',(),'en')]
        with (patch('lingfeng.audio.synthesis.SynthEngine', return_value=engine),
              patch('soundcard.default_speaker') as speaker,
              patch('lingfeng.audio.synthesis.pack', return_value={'engine': 'sfz'}),
              patch('lingfeng.audio.synthesis.write_output', side_effect=write)):
            speaker.return_value.player.return_value.__enter__.return_value=player
            _synthesis_worker(connection,{0:'synth:piano-small'}, {},'en')
            speaker.return_value.player.assert_called_once_with(samplerate=RATE,channels=2,blocksize=round(RATE*.06))
        self.assertEqual(len(counts), 1)
        event_count, frame_count = counts[0]
        self.assertLess(event_count, 10)
        self.assertEqual(frame_count, BLOCK)


class AssetCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'tone.wav').write_bytes(b'test')
        (self.root/'part.sfz').write_text('<region> sample=tone.wav\n<region> sample=tone.wav','utf-8')
        (self.root/'main.sfz').write_text('#include "part.sfz"','utf-8')

    def test_cached_validation_reuses_resolution_but_rechecks_changed_include(self):
        sfz.validate_assets(self.root,'main.sfz')
        with patch.object(sfz,'_asset',wraps=sfz._asset) as asset:
            sfz.validate_assets(self.root,'main.sfz')
            self.assertEqual(asset.call_count,1) # Top mapping containment is always checked.
        (self.root/'part.sfz').write_text('<region> sample=../outside.wav','utf-8')
        with self.assertRaises(ValueError):sfz.validate_assets(self.root,'main.sfz')

    def test_cached_validation_rejects_removed_sample(self):
        sfz.validate_assets(self.root,'main.sfz');(self.root/'tone.wav').unlink()
        with self.assertRaises(ValueError):sfz.validate_assets(self.root,'main.sfz')

    def test_sfizz_reuses_buffers_and_never_starts_unplayed_samplers(self):
        api=MagicMock();api.sfizz_create_synth.return_value=1;api.sfizz_load_file.return_value=True;api.sfizz_get_num_regions.return_value=1
        info={'path':str(self.root),'voices':256};item={'sfz':'main.sfz','gain':1}
        def render(handle,outputs,channels,count):
            for channel in range(2):np.ctypeslib.as_array(outputs[channel],shape=(count,))[:]=.1
        api.sfizz_render_block.side_effect=render
        voice=sfz.SfzVoice(api,info,item,44100,256)
        try:
            self.assertFalse(voice.render(256).any());api.sfizz_render_block.assert_not_called()
            pointers=voice.outputs;voice.send(0x90,60,90)
            first=voice.render(128);voice.render(256)
            self.assertIs(voice.outputs,pointers);self.assertGreater(float(first.max()),0)
            voice.send(0xb0,120,0);api.sfizz_render_block.reset_mock()
            self.assertFalse(voice.render(256).any());api.sfizz_render_block.assert_not_called()
        finally:voice.close()


if __name__=='__main__':unittest.main()
