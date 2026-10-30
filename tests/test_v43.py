"""Synth pack installation/cache, native DSP, routing and export regression."""
import json,os,shutil,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from PySide6.QtWidgets import QApplication
from popscore import soundbanks as banks
from popscore.model import Project,Note
from popscore.synthesis import SynthEngine,RATE,BLOCK
from popscore.sounddialog import SoundSettingsDialog
from popscore.exporting import offline_pcm
APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parent.parent
BANKS=banks.default_root()
CORE='synth:stk-essentials';EXTRA='synth:stk-colors'

class PackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.base=Path(self.tmp.name)
        self.root=patch.object(banks,'default_root',return_value=self.base/'synths');self.cache=patch.object(banks,'cache_path',return_value=self.base/'index.json')
        self.root.start();self.cache.start();banks._state=None
    def tearDown(self):
        self.root.stop();self.cache.stop();banks._state=None;self.tmp.cleanup()
    def install(self):
        target=self.base/'synths/stk-essentials';shutil.copytree(BANKS/'stk-essentials',target);return target
    def test_empty_core_remains_editable(self):
        self.assertEqual(banks.installed_packs(),[]);self.assertEqual(Project().audio['melody']['device'],'default')
        p=Project.from_dict(dict(Project().to_dict(),audio={'melody':dict(device=CORE,program=1),'chords':dict(device=EXTRA,program=73)}));p.validate()
        self.assertEqual(p.audio['chords']['device'],EXTRA)
    def test_copy_requires_scan_then_cache_survives_restart(self):
        banks.registry();self.install();self.assertFalse(banks.installed_packs());banks.rescan()
        self.assertEqual(len(banks.available_programs()),15);banks._state=None
        with patch.object(banks,'rescan',side_effect=AssertionError('Do not rescan at startup')):self.assertEqual(len(banks.installed_packs()),1)
    def test_remove_and_reinstall_same_id(self):
        target=self.install();banks.rescan();p=Project();dest=self.base/'moved';target.rename(dest)
        self.assertFalse(banks.installed_packs());p.validate();banks.rescan([str(dest)])
        self.assertEqual(banks.pack(CORE)['path'],str(dest.resolve()));self.assertEqual(p.audio['melody']['device'],CORE)
    def test_corrupt_pack_does_not_hide_good_pack(self):
        self.install();bad=self.base/'synths/broken';bad.mkdir();(bad/'synth.json').write_text('{','utf-8')
        state=banks.rescan();self.assertEqual(len(state['packs']),1);self.assertEqual(len(state['errors']),1)
    def test_duplicate_is_reported(self):
        target=self.install();shutil.copytree(target,self.base/'synths/duplicate');state=banks.rescan()
        self.assertEqual(len(state['packs']),1);self.assertIn('Duplicate',state['errors'][0])
    def test_traversal_checksum_and_invalid_preset_rejected(self):
        target=self.install();manifest=target/'synth.json';data=json.loads(manifest.read_text('utf-8'))
        for changes in [dict(library='../outside.dll'),dict(sha256='0'*64),dict(presets=[dict(data['presets'][0],gain=float('nan'))])]:
            manifest.write_text(json.dumps(dict(data,**changes)),'utf-8');self.assertFalse(banks.rescan()['packs'])
    def test_corrupt_index_recovers_from_directory(self):
        self.install();(self.base/'index.json').write_text('null','utf-8');self.assertEqual(len(banks.registry()['packs']),1)
    def test_defaults_persist_without_overwriting_explicit_project(self):
        self.install();banks.rescan();saved={'melody':dict(device=CORE,program=24),'chords':dict(device=CORE,program=33)}
        banks.save_defaults(saved);banks._state=None;self.assertEqual(Project().audio,saved)
        data=Project().to_dict();data['audio']['melody']['program']=1;self.assertEqual(Project.from_dict(data).audio['melody']['program'],1)
    def test_legacy_migration_keeps_program_and_missing_reference(self):
        data=Project().to_dict();data['audio']['melody']=dict(device='samples',program=40);p=Project.from_dict(data)
        self.assertEqual(p.audio['melody'],dict(device=CORE,program=40));self.assertEqual(data['audio']['melody']['device'],'samples')
    def test_dialog_scan_restores_new_pack_and_empty_disables_accept(self):
        with patch('popscore.audio.midi_devices',return_value=[]):
            d=SoundSettingsDialog(Project().audio)
            try:
                self.assertFalse(d.preview_buttons['melody'].isEnabled());self.install();d.scan()
                self.assertTrue(d.preview_buttons['melody'].isEnabled());self.assertEqual(d.fields['melody'][0].currentData(),CORE)
                self.assertEqual(d.fields['melody'][1].count(),15)
            finally:d.reject()

class SynthesisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):banks.rescan([str(BANKS)])
    def engine(self,program=1,device=CORE):
        e=SynthEngine(device);e.send(0xc0,program);self.addCleanup(e.close);return e
    def test_all_presets_audible_and_stoppable(self):
        for pack in banks.installed_packs():
            for p in pack['presets']:
                with self.subTest(pack=pack['id'],program=p['program']):
                    e=self.engine(p['program'],'synth:'+pack['id']);e.send(0x90,60,90);out=e.render(8192)
                    self.assertTrue(np.isfinite(out).all());self.assertGreater(float(abs(out).max()),.0001)
                    self.assertLess(np.mean(abs(out)>=.999),.001);e.stop();self.assertFalse(e.render(512).any());e.close()
    def test_edge_pitches(self):
        for program in (1,5,24,25,33,40,43):
            e=self.engine(program)
            for pitch in (21,48,60,84,108):
                e.stop();e.send(0x90,pitch,80);out=e.render(16384)
                self.assertTrue(np.isfinite(out).all());self.assertGreater(abs(out).max(),.00001,(program,pitch))
    def test_volume_noteoff_and_sustain(self):
        e=self.engine();e.send(0x90,60,100);e.send(0xb0,7,0);self.assertFalse(e.render(512).any())
        e.send(0xb0,7,100);e.send(0xb0,64,127);e.send(0x80,60);self.assertGreater(abs(e.render(8192)).max(),.001)
        e.send(0xb0,64,0);e.render(8192);self.assertFalse(e.render(512).any())
    def test_channels_and_program_change_preserve_volume(self):
        e=self.engine();e.send(0xc1,40);e.send(0x91,60,80);e.send(0xb0,7,0);e.send(0x80,60)
        self.assertGreater(abs(e.render(4096)).max(),.001);e.send(0xb1,120);e.send(0xc0,5);e.send(0x90,60,100);self.assertFalse(e.render(256).any())
    def test_delayed_event_and_block_splitting_are_exact(self):
        a=self.engine();b=self.engine();a.send(0x90,60,90,delay=37);data=a.render(333)
        expected=np.concatenate([b.render(37),self._after_note(b,296)])
        np.testing.assert_allclose(data,expected,atol=1e-7)
        self.assertFalse(data[:37].any())
    def _after_note(self,e,count):e.send(0x90,60,90);return e.render(count)
    def test_invalid_program_does_not_replace_existing_channel(self):
        e=self.engine()
        with self.assertRaises(ValueError):e.send(0xc0,127)
        self.assertEqual(e.programs[0],1)
    def test_export_matches_live_engine_with_sub_block_noteoff(self):
        p=Project();p.audio={'melody':dict(device=CORE,program=1),'chords':dict(device=CORE,program=0)};p.notes=[Note(0,137,60,90)]
        pcm=np.frombuffer(b''.join(offline_pcm(p,'melody',0,200,threading.Event(),lambda n:None)),dtype='<i2').reshape(-1,2)
        e=self.engine();e.send(0xb0,7,p.volumes['melody']);e.send(0x90,60,90);off=round(137*60/p.bpm/960*RATE)
        e.send(0x80,60,0,delay=off);expected=(e.render(8192)*32767).astype('<i2')
        np.testing.assert_array_equal(pcm[:8192],expected)
    def test_export_preserves_chosen_pack_and_rejects_windows(self):
        p=Project();p.notes=[Note(0,240,60)];p.audio['melody']=dict(device=EXTRA,program=73)
        self.assertIn('stk-colors',banks.credits_text(p,'melody',0,240,'offline'));self.assertTrue(b''.join(offline_pcm(p,'melody',0,240,threading.Event(),lambda n:None)))
        p.audio['melody']['device']='default'
        with self.assertRaises(ValueError):next(offline_pcm(p,'melody',0,240,threading.Event(),lambda n:None))
    def test_router_one_native_stream_mixed_packs_and_windows(self):
        from popscore.audio import MidiRouter
        settings={'melody':dict(device=CORE,program=1),'chords':dict(device=EXTRA,program=73)}
        with patch('popscore.audio.midi_devices',return_value=[(0,'GS')]),patch('popscore.synthesis.NativeSynth') as native,patch('popscore.audio.Synth') as win:
            r=MidiRouter(settings);self.assertEqual(native.call_count,1);r.close();native.return_value.close.assert_called_once()
            settings['chords']['device']='GS';r=MidiRouter(settings);r.send(0x91,60,90);win.return_value.send.assert_any_call(0x91,60,90);r.close()
    def test_many_simultaneous_notes_and_release_remain_bounded(self):
        e=self.engine(40)
        for n in range(36,84):e.send(0x90,n,100)
        data=e.render(8192);self.assertTrue(np.isfinite(data).all());self.assertLessEqual(float(abs(data).max()),.950001);e.send(0xb0,123);e.render(8192);self.assertFalse(e.render(512).any())
    def test_limiter_stays_linear_at_normal_levels_and_split_invariant(self):
        a=self.engine();b=self.engine()
        for ch in range(6):
            a.send(0xc0|ch,1);b.send(0xc0|ch,1)
            for pitch in (48,52,55,60,64,67,72,76):a.send(0x90|ch,pitch,100);b.send(0x90|ch,pitch,100)
        whole=a.render(4096);split=np.concatenate([b.render(137),b.render(3959)])
        np.testing.assert_allclose(whole,split,atol=1e-7);self.assertLessEqual(float(abs(whole).max()),.950001)
    def test_output_releases_only_initialized_frames(self):
        from popscore.exporting import _com_apartment
        from popscore.synthesis import write_output
        with _com_apartment():
            from soundcard.mediafoundation import _ffi
            class Player:
                def __init__(self):self.allocated=[];self.released=[];self.buffer=_ffi.new('float[]',8192)
                def _render_available_frames(self):return 4096
                def _render_buffer(self,n):self.allocated.append(n);return [_ffi.cast('BYTE*',self.buffer)]
                def _render_release(self,n):self.released.append(n)
            player=Player();data=np.full((256,2),.25,np.float32);write_output(player,data)
            self.assertEqual(player.allocated,[256]);self.assertEqual(player.released,[256]);self.assertAlmostEqual(player.buffer[511],.25);self.assertEqual(player.buffer[512],0)

if __name__=='__main__':unittest.main()
