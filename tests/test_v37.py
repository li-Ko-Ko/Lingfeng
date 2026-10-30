"""Progression library, root subsequences, naming and full public catalogue."""
import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QDialog,QDialogButtonBox
from PySide6.QtCore import QEvent
from PySide6.QtTest import QTest
from lingfeng.music.progressions import tokens, resolve, root_identity, matches_roots, make_preset, presets, load_library, preset_label, DEFAULT_PRESETS, apply; from lingfeng.ui.progression_dialogs import ProgressionEntryDialog, ProgressionManagerDialog, ProgressionDialog
from lingfeng.music.progression_catalog import HOOKTHEORY_RECIPES, CATALOG_VERSION
from lingfeng.music.model import Project, Chord, Context, PPQ
from lingfeng.ui.main_window import MainWindow
from lingfeng.platform.i18n import set_language
APP=QApplication.instance() or QApplication([])

class SearchTests(unittest.TestCase):
    def test_ordered_gaps_and_quality_independence(self):
        for seq in ('I V IV ii iii','i7 IVmaj7 V III7','I IV ii III/3'):
            self.assertTrue(matches_roots(seq,'I-IV-III'))
        for seq in ('I III IV','IV I III','I V III'):self.assertFalse(matches_roots(seq,'I-IV-III'))
    def test_accidentals_are_spelled_not_enharmonic(self):
        self.assertFalse(matches_roots('I IV #III','I-IV-III'));self.assertFalse(matches_roots('I IV bIII','I-IV-III'))
        self.assertTrue(matches_roots('I IV biii7','I-IV-bIII'));self.assertFalse(matches_roots('I IV #II','I-IV-bIII'))
        self.assertTrue(matches_roots('I IV ♭iii','i-IV-bIII'))
    def test_repeated_roots_consume_distinct_chords(self):
        self.assertFalse(matches_roots('I IV','I I'));self.assertTrue(matches_roots('I IV I','I I'))
        self.assertTrue(matches_roots('I IV',''));self.assertTrue(matches_roots('I IV','IV'))
    def test_applied_roots_ignore_bass_but_resolve_tonic(self):
        self.assertEqual(root_identity('V/vi/#5'),root_identity('III'))
        self.assertEqual(root_identity('viidim/vi'),root_identity('#V'))
        self.assertTrue(matches_roots('I V/vi/#5 vi','I III VI'))
        self.assertFalse(matches_roots('V/vi','V'))
    def test_invalid_query_is_rejected(self):
        for query in ('not a chord','VIII','I #','I/9'):
            with self.assertRaises(ValueError):matches_roots('I IV V',query)

class LibraryTests(unittest.TestCase):
    def test_all_21_source_recipes_and_original_extras_exist(self):
        self.assertEqual(len(HOOKTHEORY_RECIPES),21);self.assertEqual(len(DEFAULT_PRESETS),26)
        self.assertEqual([len(tokens(s)) for _,s,_ in HOOKTHEORY_RECIPES],[4,5,4,4,4,4,5,4,4,4,3,3,4,3,3,3,3,3,4,3,5])
        self.assertEqual(len({x[2] for x in HOOKTHEORY_RECIPES}),21)
        for title,sequence,_ in HOOKTHEORY_RECIPES:
            self.assertIn(make_preset(sequence,title),presets(None))
            for tonic in range(12):
                for token in tokens(sequence):self.assertTrue(resolve(token,tonic).pitches)
    def test_figured_bass_converts_to_real_bass(self):
        for token,root,bass in [('I/5',0,7),('V/7',7,11),('iii/7',4,11),('I/3',0,4),('V/vi/#5',4,8),('vi7/5',9,7)]:
            for tonic in range(12):
                c=resolve(token,tonic);self.assertEqual(c.root%12,(tonic+root)%12);self.assertEqual(c.bass,(tonic+bass)%12)
        self.assertEqual(resolve('V6',0).quality,'6')
    def test_all_source_recipes_generate_without_changing_regions(self):
        for _,sequence,_ in HOOKTHEORY_RECIPES:
            p=Project();p.fill_chord_gaps();regions=[(c.id,c.start,c.duration) for c in p.chords]
            ids=apply(p,p.chords[0].id,sequence,False,'block');self.assertEqual(len(ids),len(tokens(sequence)))
            self.assertEqual(regions,[(c.id,c.start,c.duration) for c in p.chords]);p.validate()
            for c,t in zip(p.chords,tokens(sequence)):
                semantic=resolve(t,0);self.assertEqual((c.root%12,c.quality,c.bass),(semantic.root%12,semantic.quality,semantic.bass))
    def test_optional_name_and_separate_identity(self):
        self.assertEqual(make_preset('IV-iv-I')['name'],'IV – iv – I')
        self.assertEqual(preset_label(make_preset('IV-iv-I','Cadencing in style')),'Cadencing in style: IV – iv – I')
        self.assertEqual(make_preset('I IV','V VI')['sequence'],'I IV')
    def test_upgrade_preserves_custom_names_and_only_runs_once(self):
        old=[make_preset('I V vi IV'),make_preset('I V','我的段落')];before=copy.deepcopy(old)
        new=load_library(old,0);self.assertEqual(old,before);self.assertIn(old[1],new)
        self.assertIn(make_preset('I V vi IV','The most popular progression'),new)
        self.assertNotIn(old[0],new)
        edited=[e for e in new if e['name']!='Cadencing in style'];self.assertEqual(load_library(edited,CATALOG_VERSION),presets(edited))
    def test_matching_custom_sequence_does_not_lose_its_name(self):
        custom=make_preset('IV iv I','我的结尾');library=load_library([custom],0)
        self.assertIn(custom,library);self.assertIn(make_preset('IV iv I','Cadencing in style'),library)

class DialogTests(unittest.TestCase):
    def setUp(self):set_language('zh');self.dialogs=[]
    def tearDown(self):
        for d in self.dialogs:d.close();d.deleteLater()
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()
    def keep(self,d):self.dialogs.append(d);return d
    def test_entry_field_order_auto_name_and_optional_custom_name(self):
        d=self.keep(ProgressionEntryDialog());d.show();APP.processEvents()
        self.assertLess(d.sequence.mapTo(d,d.sequence.rect().topLeft()).y(),d.name.mapTo(d,d.name.rect().topLeft()).y())
        d.sequence.setText('IV-iv-I');self.assertEqual(d.name.text(),'IV – iv – I')
        d.name.selectAll();QTest.keyClicks(d.name,'Cadencing in style');d.sequence.setText('IV-iv-I-V')
        self.assertEqual(d.value()['name'],'Cadencing in style')
        d.name.clear();self.assertEqual(d.value()['name'],'IV – iv – I – V')
    def test_entry_rejects_invalid_and_empty_sequences(self):
        d=self.keep(ProgressionEntryDialog());ok=d.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.assertFalse(ok.isEnabled());d.sequence.setText('I-INVALID');self.assertFalse(ok.isEnabled())
        d.accept();self.assertNotEqual(d.result(),QDialog.DialogCode.Accepted)
        d.sequence.setText('I V/vi/#5');self.assertTrue(ok.isEnabled())
    def test_manager_filter_modes_counts_empty_and_invalid(self):
        values=[make_preset('I V IV ii iii','one'),make_preset('I IV #III','two'),make_preset('IV iv I','Cadencing in style')]
        d=self.keep(ProgressionManagerDialog(values));d.search.setText('I-IV-III');self.assertEqual(d.table.rowCount(),1);self.assertEqual(d.table.item(0,0).text(),'one')
        d.search.setText('VII VII');self.assertEqual(d.table.rowCount(),0);self.assertFalse(d.edit_button.isEnabled())
        d.search.setText('oops');self.assertEqual(d.table.rowCount(),0);self.assertTrue(d.info.text())
        d.search_mode.setCurrentIndex(1);d.search.setText('CADENCING');self.assertEqual(d.table.rowCount(),1)
        d.search.clear();self.assertEqual(d.table.rowCount(),3)
    def test_manager_filtered_edit_delete_and_cancel_are_local(self):
        values=[make_preset('I IV V','one'),make_preset('ii V I','two')];before=copy.deepcopy(values)
        d=self.keep(ProgressionManagerDialog(values));d.search_mode.setCurrentIndex(1);d.search.setText('two');index=d.current_index()
        d.store_entry(make_preset('IV iv I','changed'),index);self.assertIn(make_preset('IV iv I','changed'),d.value())
        d.search.setText('changed');d.remove_entry();self.assertEqual(d.table.rowCount(),0)
        d.search.clear();self.assertFalse(d.remove_button.isEnabled());d.reject();self.assertEqual(values,before)
    def test_add_and_edit_buttons_share_entry_dialog(self):
        d=self.keep(ProgressionManagerDialog([make_preset('I V')]))
        new=make_preset('IV iv I','custom')
        with patch.object(ProgressionEntryDialog,'exec',return_value=QDialog.DialogCode.Accepted),patch.object(ProgressionEntryDialog,'value',return_value=new):d.add_button.click()
        self.assertIn(new,d.value());self.assertEqual(d.table.item(d.table.currentRow(),0).text(),'custom')
        changed=make_preset('IV V I','edited')
        with patch.object(ProgressionEntryDialog,'exec',return_value=QDialog.DialogCode.Accepted),patch.object(ProgressionEntryDialog,'value',return_value=changed):d.edit_button.click()
        self.assertIn(changed,d.value());self.assertNotIn(new,d.value())
    def test_apply_shows_name_roman_and_letters_on_separate_rows(self):
        p=Project();p.chords=[Chord(0,3840)];entry=make_preset('IV iv I','Cadencing in style')
        d=self.keep(ProgressionDialog(p,p.chords[0].id,[entry]));d.show();APP.processEvents()
        self.assertEqual(d.preset.currentText(),'Cadencing in style: IV – iv – I');self.assertEqual(d.roman.text(),'IV – iv – I');self.assertEqual(d.resolved.text(),'F – Fm – C')
        self.assertLess(d.preset.y(),d.roman.y());self.assertLess(d.roman.y(),d.resolved.y())
        p.contexts=[Context(0,p.end,53,'Ionian')];d.tonic.setCurrentIndex(d.tonic.findData(5));d.refresh();self.assertEqual(d.resolved.text(),'Bb – Bbm – F')
    def test_capture_uses_optional_name_form_and_retains_cancel(self):
        with patch.object(MainWindow,'save_preferences'):
            w=MainWindow(Project());w.timer.stop();w.autosave.stop();w.project.chords=[Chord(0,960,53),Chord(960,960,53,'m'),Chord(1920,960,48)]
            ids={c.id for c in w.project.chords};before=copy.deepcopy(w.progression_presets)
            with patch.object(ProgressionEntryDialog,'exec',return_value=QDialog.DialogCode.Rejected):w.capture_progression(ids)
            self.assertEqual(w.progression_presets,before)
            entry=make_preset('IV iv I','My cadence')
            with patch.object(ProgressionEntryDialog,'exec',return_value=QDialog.DialogCode.Accepted),patch.object(ProgressionEntryDialog,'value',return_value=entry):w.capture_progression(ids)
            self.assertIn(entry,w.progression_presets);w.dirty=False;w.close();w.deleteLater()
    def test_catalog_version_and_edits_persist_across_restart(self):
        with tempfile.TemporaryDirectory(dir='tmp') as folder,patch('lingfeng.ui.main_window.user_data_dir',return_value=Path(folder)):
            w=MainWindow(Project());w.timer.stop();w.autosave.stop();w.progression_presets=[make_preset('I IV','Kept')];w.save_preferences();w.dirty=False;w.close()
            data=json.loads((Path(folder)/'preferences.json').read_text('utf-8'));self.assertEqual(data['progression_catalog_version'],CATALOG_VERSION)
            other=MainWindow(Project());self.assertEqual(other.progression_presets,w.progression_presets);other.dirty=False;other.close();other.deleteLater();w.deleteLater()

if __name__=='__main__':unittest.main()
