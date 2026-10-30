"""Tonic-independent progressions, MIDI ownership, calibrated synth models."""
import copy,os,unittest
from unittest.mock import MagicMock,patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from PySide6.QtWidgets import QApplication,QWidget
from popscore.audio import MidiRouter,Transport
from popscore.model import Project,Chord,Context
from popscore.progressions import (capture,apply,resolve,selection_root_query,search_recipe,
    CaptureProgressionDialog,ProgressionEntryDialog,ProgressionManagerDialog,ProgressionDialog)
from popscore.sounddialog import SoundSettingsDialog
from popscore.synthesis import SynthEngine
from popscore import soundbanks as banks
from scripts.release_policy import bundle_synths
APP=QApplication.instance() or QApplication([])

def score():
    p=Project();p.chords=[Chord(i*3840,3840,root,quality) for i,(root,quality) in enumerate([(55,'m'),(48,''),(53,'')])]
    return p

class TonicTests(unittest.TestCase):
    def test_user_example_preserves_music_and_library_has_no_tonic(self):
        p=score();before=copy.deepcopy(p.to_dict());ids={c.id for c in p.chords}
        self.assertEqual(capture(p,ids),'v I IV');self.assertEqual(capture(p,ids,5),'ii V I')
        d=CaptureProgressionDialog(p,ids)
        try:
            self.assertEqual([d.tonic.itemData(i) for i in range(12)],list(range(12)))
            self.assertEqual([d.tonic.itemText(i).split(' · ')[0] for i in range(12)],'1 #1 2 #2 3 4 #4 5 #5 6 #6 7'.split())
            d.tonic.setCurrentIndex(5);self.assertEqual(d.value(),dict(name='ii – V – I',sequence='ii V I'))
            d.name.setText('Cadence');d.auto_name=False;d.tonic.setCurrentIndex(0);self.assertEqual(d.value()['name'],'Cadence')
            d.reject();self.assertEqual(p.to_dict(),before)
        finally:d.close()
        e=ProgressionEntryDialog(dict(sequence='ii V I'))
        try:self.assertFalse(hasattr(e,'tonic'));self.assertEqual(set(e.value()),{'name','sequence'})
        finally:e.close()
    def test_anchor_is_first_selected_chord_context_not_root_or_playhead(self):
        p=score();p.contexts=[Context(0,3840,48,'Ionian'),Context(3840,p.end,53,'Ionian')]
        ids={p.chords[1].id,p.chords[2].id};d=CaptureProgressionDialog(p,ids)
        try:
            self.assertEqual(d.tonic.currentData(),5)
            self.assertEqual([d.tonic.itemData(i) for i in range(12)],[5,6,7,8,9,10,11,0,1,2,3,4])
            self.assertEqual(d.value()['sequence'],'V I')
        finally:d.close()
    def test_application_uses_one_tonic_across_key_changes_and_retains_bounds(self):
        p=score();p.contexts=[Context(0,3840,48,'Ionian'),Context(3840,p.end,50,'Dorian')]
        before=[(c.id,c.start,c.duration) for c in p.chords];contexts=copy.deepcopy(p.contexts)
        ids=apply(p,p.chords[0].id,'ii V I',False,tonic=5)
        self.assertEqual([c.root%12 for c in p.chords],[7,0,5]);self.assertEqual([c.quality for c in p.chords],['m','',''])
        self.assertEqual([(c.id,c.start,c.duration) for c in p.chords],before);self.assertEqual(p.contexts,contexts)
        self.assertEqual(capture(p,set(ids),5),'ii V I');p.validate()
    def test_application_preview_and_value_share_tonic(self):
        p=score();d=ProgressionDialog(p,p.chords[0].id,[dict(name='Cadence',sequence='ii V I')])
        try:
            self.assertEqual(d.resolved.text(),'Dm – G – C');d.tonic.setCurrentIndex(5)
            self.assertEqual(d.resolved.text(),'Gm – C – F');self.assertEqual(d.value()['tonic'],5)
            apply(p,p.chords[0].id,**d.value());self.assertEqual([c.root%12 for c in p.chords],[7,0,5])
        finally:d.close()
    def test_search_rebases_selected_chords_but_never_edits_recipes(self):
        p=score();ids={c.id for c in p.chords};values=[dict(name='C',sequence='v I IV'),dict(name='F',sequence='ii V I')]
        d=ProgressionManagerDialog(values,query=selection_root_query(p,ids),query_factory=lambda t:selection_root_query(p,ids,t))
        try:
            self.assertEqual(d.table.item(0,0).text(),'C');d.tonic.setCurrentIndex(5)
            self.assertEqual(d.search.text(),'II – V – I');self.assertEqual(d.table.rowCount(),1)
            self.assertEqual(d.table.item(0,0).text(),'F');self.assertEqual(d.table.item(0,2).text(),'Gm – C – F')
            self.assertCountEqual(d.value(),values)
            d.manual_query();d.search.setText('Gm C F');self.assertEqual(d.table.item(0,0).text(),'F')
            d.tonic.setCurrentIndex(0);self.assertEqual(d.table.item(0,0).text(),'C')
            d.search.setText('ii V I');d.tonic.setCurrentIndex(7);self.assertEqual(d.table.item(0,0).text(),'F')
        finally:d.close()
    def test_letter_query_preserves_accidentals_and_roman_is_relative(self):
        self.assertEqual(search_recipe('Gm C F',5),'II V I')
        self.assertEqual(search_recipe('Bb F C',0),'bVII IV I')
        self.assertEqual(search_recipe('ii V I',5),'ii V I')
        with self.assertRaises(ValueError):search_recipe('nonsense',0)
    def test_all_tonics_roundtrip_inversions_and_qualities(self):
        p=score();p.chords=[Chord(0,3840,55,'mM7',10)]
        for tonic in range(12):
            result=resolve(capture(p,{p.chords[0].id},tonic),tonic)
            self.assertEqual((result.root%12,result.quality,result.bass),(7,'mM7',10))

class OwnershipTests(unittest.TestCase):
    def test_mapper_and_named_output_share_one_handle_in_either_order(self):
        for first,second in [('default','GS'),('GS','default')]:
            with patch('popscore.audio.midi_devices',return_value=[(2,'GS')]),patch('popscore.audio.default_midi_device',return_value=2),patch('popscore.audio.Synth') as synth:
                r=MidiRouter(dict(melody=dict(device=first,program=1),chords=dict(device=second,program=25)))
                synth.assert_called_once_with(2);self.assertIs(r.routes[0],r.routes[1]);r.close();r.close()
                synth.return_value.close.assert_called_once()
    def test_close_detaches_transport_and_reopens_same_settings(self):
        t=Transport();old=MagicMock();t.synth=old;t.close();t.close();old.close.assert_called_once();self.assertIsNone(t.synth)
        with patch('popscore.audio.ProcessRouter') as router:
            t.configure(copy.deepcopy(t.settings));t.open();router.assert_called_once_with(t.settings);t.close()
    def test_preview_releases_retained_main_handle_and_cancel_releases_preview(self):
        parent=QWidget();parent.transport=Transport();parent.transport.synth=MagicMock();old=parent.transport.synth
        settings={k:dict(device='default',program=1) for k in ('melody','chords')}
        with patch('popscore.audio.midi_devices',return_value=[(0,'GS')]):d=SoundSettingsDialog(settings,parent)
        with patch('popscore.audio.MidiRouter') as router:
            d.preview('melody');old.close.assert_called_once();self.assertIsNone(parent.transport.synth)
            d.reject();router.return_value.close.assert_called_once();self.assertIsNone(d.preview_router)
        parent.close()
    def test_partial_router_open_failure_closes_native_and_midi(self):
        with patch('popscore.audio.midi_devices',return_value=[]),patch('popscore.synthesis.NativeSynth') as native:
            with self.assertRaises(RuntimeError):MidiRouter(dict(melody=dict(device='synth:stk-essentials',program=1),chords=dict(device='missing',program=1)))
            native.return_value.close.assert_called_once()
    def test_failed_backend_is_released_and_program_failure_keeps_old_settings(self):
        t=Transport();old=copy.deepcopy(t.settings);device=MagicMock();device.send.side_effect=RuntimeError('lost device');t.synth=device
        changed=copy.deepcopy(old);changed['melody']['program']=24
        with self.assertRaises(RuntimeError):t.configure(changed)
        self.assertIsNone(t.synth);device.close.assert_called_once();self.assertEqual(t.settings,old)

class SoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):banks.rescan()
    def test_37_presets_include_six_additional_models_and_tone_settings(self):
        packs=[banks.pack('synth:'+i) for i in ('stk-essentials','stk-colors','stk-acoustic')]
        self.assertEqual(sum(len(p['presets']) for p in packs),37)
        self.assertTrue(set(range(12,18)).issubset({p['model'] for pack in packs for p in pack['presets']}))
        self.assertTrue(all(200<=p['cutoff_hz']<=16000 for pack in packs for p in pack['presets']))
    def test_sitar_retriggered_chromatic_sequence_has_no_feedback_burst(self):
        e=SynthEngine('synth:stk-acoustic');e.send(0xc0,104)
        try:
            for key in range(21,109):
                for velocity in ((1,40,90,127) if key in (21,36,60,84,108) else (90,)):
                    e.stop();e.send(0x90,key,velocity);data=e.channels[0].render(16384)
                    self.assertTrue(np.isfinite(data).all());self.assertLess(abs(data).max(),.3,(key,velocity))
                    e.send(0x80,key);e.render(8192);self.assertFalse(e.render(512).any())
        finally:e.close()
    def test_soft_brass_high_notes_are_audible_without_loud_excitation(self):
        e=SynthEngine('synth:stk-colors');e.send(0xc0,56)
        try:
            for key in (21,60,95,108):
                e.stop();e.send(0x90,key,1);data=e.render(16384)
                self.assertGreater(abs(data).max(),1e-7,key);self.assertLess(abs(data).max(),.02)
        finally:e.close()
    def test_pack_size_policy_uses_same_units_and_threshold(self):
        self.assertTrue(bundle_synths(1000,500));self.assertTrue(bundle_synths(1000,1000))
        self.assertFalse(bundle_synths(1000,1001));self.assertFalse(bundle_synths(0,0))
    def test_windows_names_have_unique_labels_and_correct_program_ids(self):
        from popscore.gm_instruments import NAMES,label
        self.assertEqual(len(NAMES),128);self.assertEqual(len({cn for cn,en in NAMES}),128)
        self.assertEqual(NAMES[74][1],'Recorder');self.assertEqual(NAMES[1][0],'明亮钢琴')
        self.assertTrue(label(127).startswith('128 · '))

if __name__=='__main__':unittest.main()
