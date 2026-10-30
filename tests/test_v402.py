"""Default last-duration tracking and dominant seventh flat-five integration."""
import copy,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.controls import DurationSelector
from popscore.model import Project,Chord,Note,Context,Measure,PPQ,QUALITIES,PATTERNS
from popscore.chordops import chord_details,change_chords,quality_items,set_quality_order
from popscore.progressions import resolve,capture,apply
from popscore.recognition import recognize
from popscore.rhythm import analyze
from popscore.dialogs import ChordDialog,NoteDialog
from popscore.i18n import set_language
APP=QApplication.instance() or QApplication([])

class QualityTests(unittest.TestCase):
    def tearDown(self):set_language('zh');set_quality_order([])
    def test_components_names_and_spelling(self):
        from pychord import Chord as PyChord
        self.assertEqual(PyChord('C7b5').components(visible=False),[0,4,6,10])
        c=Chord(0,3840,48,'7b5');self.assertEqual(c.pitches,[36,48,52,54,58])
        self.assertEqual(c.name,'C7b5');self.assertEqual(c.roman(48),'I7b5')
        hint=chord_details(Project(),c,compact=True)
        for tone in ('1: C','3: E','b5: Gb','b7: Bb'):self.assertIn(tone,hint)
        self.assertNotEqual(c.pcs,Chord(0,3840,48,'m7b5').pcs)
    def test_all_roots_and_inversions_recognize_preferred_symbol(self):
        for root in range(12):
            for bass in (None,0,4,6,10):
                c=Chord(0,3840,48+root,'7b5',None if bass is None else (root+bass)%12)
                found=recognize(c.pitches,preferred=(root,'7b5'))[0]
                self.assertEqual((found.root,found.quality),(root,'7b5'))
    def test_progression_capture_and_application_roundtrip(self):
        for tonic in range(12):
            p=Project();p.contexts=[Context(0,p.end,48+tonic)]
            c=resolve('V7b5/b2',tonic);c.duration=3840;p.chords=[c]
            recipe=capture(p,{c.id});restored=resolve(recipe,tonic)
            self.assertEqual((restored.root,restored.quality,restored.bass),(c.root,c.quality,c.bass))
            apply(p,c.id,recipe,keep_rhythm=False);self.assertEqual(p.chords[0].pcs,c.pcs);p.validate()
        self.assertEqual(resolve('V7♭5',0).quality,'7b5')
    def test_all_patterns_regenerate_and_keep_altered_fifth(self):
        for pattern in PATTERNS:
            p=Project();c=Chord(0,3840,48,'7b5',pattern=pattern);p.put_chord(c);c=p.chords[0]
            # The existing Alberti preset uses only bass and the outer upper tone.
            expected={0,10} if pattern=='alberti' else {0,4,6,10}
            self.assertEqual({n.pitch%12 for n in c.render_notes()},expected,pattern)
            self.assertEqual(analyze(c,p).pattern,pattern)
            if pattern.startswith('alternating_'):
                self.assertEqual([n.pitch for n in c.render_notes() if n.pitch<48],[36,42,36,42])
    def test_quality_menu_dialog_order_and_file_roundtrip(self):
        set_quality_order(['7','m7b5']);self.assertIn('7b5',dict(quality_items()))
        p=Project();c=Chord(0,3840);p.chords=[c];change_chords(p,{c.id},'quality:7b5')
        d=ChordDialog(p.chords[0],p)
        try:self.assertEqual(d.quality.currentData(),'7b5');self.assertEqual(d.value().pcs,{0,4,6,10})
        finally:d.deleteLater()
        set_language('en');self.assertIn('Dominant seventh flat five',dict(quality_items())['7b5'])
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            file=Path(folder)/'flat-five.lfs';p.save(file);q=Project.load(file)
            self.assertEqual(q.to_dict(),p.to_dict())
            from popscore.midi import export_midi
            from popscore.midi_import import read_midi
            midi=Path(folder)/'flat-five.mid';export_midi(p,midi)
            data=read_midi(midi);notes=data.notes_for(range(len(data.tracks)));self.assertEqual({n.pitch%12 for n in notes},{0,4,6,10})

class DurationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='tmp');self.paths=patch('popscore.app.user_data_dir',return_value=Path(self.temp.name));self.paths.start()
        self.w=MainWindow(Project());self.w.timer.stop();self.w.autosave.stop();self.w.show();self.r=self.w.roll
        self.r.center_pitch(60);APP.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.paths.stop();self.temp.cleanup()
    def point(self,tick,pitch=60):return QPoint(round(self.r.x_at(tick)),round(self.r.y_at(pitch)+self.r.row_height/2))
    def test_default_stays_previous_while_fallback_follows_grid(self):
        for control,r in ((self.w.length,self.r),(self.w.harmony_window.length,self.w.harmony_window.roll)):
            self.assertEqual(control.currentData(),-1);self.assertEqual(r.duration,-1);self.assertIsNone(r.previous_duration)
            r.grid=160;self.assertEqual(r.note_duration(0),160);r.grid=60;self.assertEqual(r.note_duration(0),60)
            self.assertEqual(control.currentData(),-1);self.assertIsNone(r.previous_duration)
        self.w.project.measures[0]=Measure(3,4);self.w.refresh();self.r.grid_bars=1
        self.assertEqual(self.r.note_duration(0),2880)
    def test_smart_creation_remembers_fallback_then_ignores_grid_changes(self):
        QTest.mouseDClick(self.r.viewport(),Qt.MouseButton.LeftButton,pos=self.point(120));APP.processEvents()
        self.assertEqual([n.duration for n in self.w.project.notes],[240])
        self.w.grid.setCurrentIndex(self.w.grid.findData(480))
        QTest.mouseDClick(self.r.viewport(),Qt.MouseButton.LeftButton,pos=self.point(1200,64));APP.processEvents()
        self.assertEqual([n.duration for n in self.w.project.notes],[240,240]);self.assertEqual(self.w.length.currentData(),-1)
    def test_draw_and_resize_update_next_duration(self):
        r=self.r;r.tool='draw'
        QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=self.point(120))
        QTest.mouseMove(r.viewport(),self.point(960));QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=self.point(960))
        self.assertEqual(self.w.project.notes[0].duration,960);self.assertEqual(r.note_duration(2000),960)
        r.tool='smart';n=self.w.project.notes[0];edge=QPoint(round(r.x_at(n.end)-3),self.point(0).y())
        QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=edge)
        QTest.mouseMove(r.viewport(),self.point(1440));QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=self.point(1440))
        self.assertEqual(self.w.project.notes[0].duration,1440);self.assertEqual(r.note_duration(2000),1440)
    def test_select_existing_note_and_follow_subsequent_edits_and_undo(self):
        n=Note(0,720,60);self.w.project.notes=[n];self.w.refresh()
        QTest.mouseClick(self.r.viewport(),Qt.MouseButton.LeftButton,pos=self.point(300));self.assertEqual(self.r.note_duration(2000),720)
        self.w.mutate('duration',lambda p:setattr(p.notes[0],'duration',1200))
        self.assertEqual(self.r.note_duration(2000),1200);self.w.undo();self.assertEqual(self.r.note_duration(2000),720)
    def test_property_edit_and_split_use_updated_duration(self):
        n=Note(0,960,60);self.w.add_note(n)
        def accept(d):d.duration.setCurrentIndex(d.duration.findData(480));return QDialog.DialogCode.Accepted
        with patch.object(NoteDialog,'exec',accept):self.w.edit_note(n.id)
        self.assertEqual(self.r.note_duration(2000),480)
        self.r.selected_ids={n.id};self.w.note_command(self.r,'split');self.assertEqual(self.r.note_duration(2000),240)
    def test_fixed_and_grid_modes_remain_explicit_and_switch_back_tracks(self):
        self.w.add_note(Note(0,777,60));self.w.length.setCurrentIndex(self.w.length.findData(960))
        self.assertEqual(self.r.note_duration(2000),960);self.w.length.setCurrentIndex(self.w.length.findData(0))
        self.assertEqual(self.r.note_duration(2000),240);self.w.length.setCurrentIndex(self.w.length.findData(-1))
        self.assertEqual(self.r.note_duration(2000),777)
    def test_floating_harmony_tracks_independently_across_language_rebuild(self):
        w=self.w;w.harmony_window.setFloating(True);w.harmony_window.show();h=w.harmony_window.roll
        w.add_note(Note(0,720,60));w.edit_notes(h,[Note(0,1200,64)],[])
        w.change_language('en',False);self.assertEqual(w.roll.note_duration(2000),720);self.assertEqual(w.harmony_window.roll.note_duration(2000),1200)
        w.mutate('harmony duration',lambda p:setattr(p.chords[0].notes[0],'duration',960))
        self.assertEqual(w.harmony_window.roll.note_duration(2000),960)
    def test_new_project_resets_untraceable_history(self):
        self.w.add_note(Note(0,777,60));self.w.replace_project(Project())
        self.w.grid.setCurrentIndex(self.w.grid.findData(120));self.assertEqual(self.r.note_duration(0),120)
        self.assertIsNone(self.r.previous_duration);self.assertEqual(self.w.length.currentData(),-1)
    def test_failed_edit_does_not_replace_remembered_duration(self):
        self.w.add_note(Note(0,720,60));before=(self.r.previous_note_id,self.r.previous_duration)
        with patch('popscore.app.QMessageBox.warning'):
            self.assertFalse(self.w.edit_notes(self.r,[Note(960,0,64)],[]))
        self.assertEqual((self.r.previous_note_id,self.r.previous_duration),before)
    def test_cross_chord_continuous_note_tracks_whole_event(self):
        w=self.w;h=w.harmony_window.roll
        w.project.chords=[Chord(0,960,notes=[]),Chord(960,960,notes=[])];w.refresh()
        w.edit_notes(h,[Note(0,1440,60)],[])
        self.assertEqual(h.note_duration(2000),1440)

if __name__=='__main__':unittest.main()
