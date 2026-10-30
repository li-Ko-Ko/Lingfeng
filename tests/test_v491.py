"""MIDI-onset rhythm and lossless, range-scoped lyric autofill/editing."""
import copy,os,tempfile,unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord
from popscore.lyrics import melody_onsets,apply_range,plan_range,range_source,events,sections,delete_range
from popscore.midi import event_list

APP=QApplication.instance() or QApplication([])

def song():
    p=Project();p.notes=[Note(b*3840+t,480,60+i) for b in range(4) for i,t in enumerate((0,480,960))]
    apply_range(p,'甲/s/x{乙} | 丙 & 丁',0,2)
    apply_range(p,'戊己庚',2,1)
    apply_range(p,'one two three',0,1,1)
    return p

def assignments(p,verse=0):
    return [(e['tick'],e['text'],e.get('kind','note'),e.get('skip',False)) for e in events(p) if e.get('verse',0)==verse]

class RhythmTests(unittest.TestCase):
    def test_unique_starts_inside_sustains_and_across_bars_ignore_harmony(self):
        p=Project();p.notes=[Note(0,9600,60),Note(0,480,64),Note(240,60,67),Note(240,120,72),Note(3810,960,69),Note(4000,240,71),Note(5480,240,73)]
        p.chords=[Chord(960,960)]
        self.assertEqual(melody_onsets(p),[0,240,3810,4000,5480])
        self.assertEqual(melody_onsets(p,3840,7680),[4000,5480])
        plan=plan_range(p,'一二三四五',0,2)
        self.assertFalse(plan.issues);self.assertEqual([e['tick'] for e in plan.events],melody_onsets(p))
        w=MainWindow(p);w.timer.stop();w.autosave.stop()
        try:
            w.lyric_panel.count.setValue(2);w.lyric_panel.template()
            self.assertEqual(w.lyric_panel.text.toPlainText(),'&&&\n&&')
            self.assertEqual([w.lyric_panel.rhythm.topLevelItem(i).text(3) for i in range(2)],['0/3','0/2'])
        finally:w.dirty=False;w.close();w.deleteLater();APP.processEvents()

    def test_mixed_meter_and_boundary_onsets_have_one_owner(self):
        p=Project();p.change_meter(0,3,4);boundary=p.starts[1]
        p.notes=[Note(0,boundary+960,60),Note(boundary-1,60,65),Note(boundary,120,67),Note(boundary,60,72)]
        self.assertEqual(melody_onsets(p,0,boundary),[0,boundary-1]);self.assertEqual(melody_onsets(p,boundary,p.starts[2]),[boundary])

class RangeDataTests(unittest.TestCase):
    def test_autofill_roundtrip_preserves_missing_slots_skip_and_rap(self):
        p=song();before=p.to_dict();text,valid=range_source(p,0,3)
        self.assertTrue(valid);self.assertEqual(text,'甲/s/x{乙}\n丙&丁\n戊己庚');self.assertEqual(p.to_dict(),before)
        plan=plan_range(p,text,0,3,replace=True)
        self.assertFalse(plan.issues)
        self.assertEqual([(e['tick'],e['text']) for e in plan.events if e['kind']!='pending'],[(e['tick'],e['text']) for e in events(p) if e['verse']==0])

    def test_range_update_preserves_outside_events_stanzas_and_midi(self):
        p=song();before=[e for e in events(p) if e['tick']>=3840 or e['verse']==1];midi=event_list(p)
        apply_range(p,'新/s/x{词}',0,1,section_id=sections(p)[0]['id'],replace=True)
        self.assertEqual([e for e in events(p) if e['tick']>=3840 or e['verse']==1],before);self.assertEqual(event_list(p),midi)
        for s in sections(p):
            first=p.measure_at(s['start']);count=p.measure_at(s['end']-1)-first+1
            self.assertFalse(plan_range(p,s['text'],first,count,s['verse'],s['id']).issues)
        with tempfile.TemporaryDirectory(dir='tmp') as directory:
            path=Path(directory)/'range.lfs';p.save(path);q=Project.load(path)
        self.assertEqual(assignments(q),assignments(p))

    def test_delete_middle_range_leaves_both_section_tails(self):
        p=song();apply_range(p,'一二三 | 四五六 | 七八九 | 十甲乙',0,4,replace=True)
        original=events(p);delete_range(p,1,2)
        self.assertEqual(events(p),[e for e in original if e['verse']!=0 or not 3840<=e['tick']<11520])
        self.assertTrue(range_source(p,0,4)[1]);p.validate()

    def test_legacy_note_lyrics_and_dotted_timed_rap_can_load(self):
        p=Project();p.notes=[Note(0,1920,60,lyric='旧'),Note(480,240,62,lyric='词')]
        self.assertEqual(range_source(p,0,1),('旧词',True))
        p.notes.append(Note(960,240,64,lyric='_'));self.assertEqual(range_source(p,0,1),('旧词/s',True))
        q=Project();apply_range(q,'我/64.爱/64你/64',0,1)
        self.assertEqual(range_source(q,0,1),('我/64.爱/64你/64',True))

class RangePanelTests(unittest.TestCase):
    def setUp(self):
        self.w=MainWindow(song());self.w.timer.stop();self.w.autosave.stop();self.w.show();self.w.switch_workspace('score');self.panel=self.w.lyric_panel
    def tearDown(self):self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents()

    def test_spin_range_and_stanza_autofill_without_mutation(self):
        panel=self.panel;before=self.w.project.to_dict();panel.count.setValue(1)
        self.assertEqual(panel.text.toPlainText(),'甲/s/x{乙}');self.assertTrue(panel.check());self.assertFalse(panel.dirty)
        panel.start.setValue(3);self.assertEqual(panel.text.toPlainText(),'戊己庚')
        panel.start.setValue(1);panel.verse.setValue(2);self.assertEqual(panel.text.toPlainText(),'one two three')
        panel.start.setValue(4);self.assertEqual(panel.text.toPlainText(),'');self.assertEqual(self.w.project.to_dict(),before)

    def test_score_selection_loads_multiple_sections_and_same_range_reselection(self):
        w=self.w;self.panel.start.setValue(len(w.project.measures));w.score_view.canvas.selected_bars={0,1,2};self.panel.use_selection()
        self.assertEqual((self.panel.start.value(),self.panel.count.value()),(1,3));self.assertIn('戊己庚',self.panel.text.toPlainText())
        self.panel.text.setPlainText('草稿');self.panel.use_selection();self.assertNotIn('草稿',self.panel.text.toPlainText());self.assertFalse(self.panel.dirty)
        w.show_score_panel('lyrics');w.toggle_score_panel_floating('lyrics');self.panel.start.setValue(3)
        self.assertTrue(self.panel.text.toPlainText().startswith('戊己庚'))

    def test_range_delete_stays_enabled_after_refreshing_a_cross_section_draft(self):
        p=self.panel;self.w.score_view.canvas.selected_bars={0,1,2};p.use_selection()
        p.text.setPlainText('草稿');p.refresh()
        self.assertTrue(p.dirty);self.assertTrue(p.remove.isEnabled());self.assertEqual(p.text.toPlainText(),'草稿')

    def test_orphan_autofill_is_visible_without_silently_rebinding(self):
        p=self.panel;self.w.project.notes=[n for n in self.w.project.notes if n.start!=0];before=self.w.project.to_dict()
        p.count.setValue(1)
        self.assertIn('甲',p.text.toPlainText());self.assertFalse(p.autofill_valid);self.assertFalse(p.check())
        p.commit();self.assertEqual(self.w.project.to_dict(),before)

    def test_confirm_after_autofill_updates_instead_of_duplicate_error_and_undo(self):
        p=self.panel;w=self.w;p.count.setValue(1);before=w.project.to_dict()
        p.text.setPlainText('改/s/x{词}');self.assertTrue(p.check());p.commit()
        self.assertEqual([e['text'] for e in events(w.project) if e['verse']==0 and e['tick']<3840],['改','','词'])
        self.assertEqual([e['text'] for e in events(w.project) if e['verse']==0 and 3840<=e['tick']<7680],['丙','丁'])
        w.undo();self.assertEqual(w.project.to_dict(),before);self.assertEqual(p.text.toPlainText(),'甲/s/x{乙}')
        w.redo();self.assertEqual(p.text.toPlainText(),'改/s/x{词}')
        p.delete();self.assertFalse(any(e['verse']==0 and e['tick']<3840 for e in events(w.project)));self.assertTrue(any(e['text']=='丙' for e in events(w.project)))

    def test_draft_and_range_mode_survive_language_switch(self):
        p=self.panel;p.count.setValue(1);p.text.setPlainText('草稿')
        self.w.change_language('en',False);p=self.w.lyric_panel
        self.assertTrue(p.range_edit);self.assertTrue(p.dirty);self.assertEqual(p.text.toPlainText(),'草稿');self.assertTrue(p.check())
        self.w.change_language('zh',False)

if __name__=='__main__':unittest.main()
