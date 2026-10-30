"""Meter-safe chord editing, linked note selection and shared window controls."""
import copy,os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from popscore.model import Project,Chord,Note,Measure,Context,PPQ,PATTERNS
from popscore.meter import regions,losses,moved_chord
from popscore.rhythm import analyze,supports,PATTERN_METERS,regenerate
from popscore.operations import resize_chord,repartition_chord
from popscore.chordops import roman_label,chord_details,move_chords,change_chords,can_merge_chords
from popscore.app import MainWindow
from popscore.controls import IconButton
from popscore.dialogs import ChordDialog

APP=QApplication.instance() or QApplication([])
def mixed():
    p=Project();p.measures=[Measure(4,4),Measure(3,4),Measure(4,4)];p.contexts=[Context(0,p.end)];return p
def events(notes):return sorted((n.start,n.duration,n.pitch,n.velocity) for n in notes)

class MeterTests(unittest.TestCase):
    def test_regions_use_full_signature_not_equal_duration(self):
        p=Project();p.measures=[Measure(2,4),Measure(4,8),Measure(4,8),Measure(2,4)]
        self.assertEqual(regions(p),[(0,1920,(2,4)),(1920,5760,(4,8)),(5760,7680,(2,4))])

    def test_resize_and_move_cannot_cross_source_region(self):
        p=mixed();c=Chord(3840,1920,pattern='up');p.put_chord(c);c=p.chords[0]
        result=resize_chord(c,0,p.end,project=p);self.assertEqual((result.start,result.end),(3840,6720))
        for target in (0,6720,8000):self.assertIsNone(moved_chord(p,c,target))
        self.assertEqual(moved_chord(p,c,3839).start,3840)
        result=moved_chord(p,c,5760);self.assertEqual((result.start,result.end),(5760,6720));self.assertEqual(analyze(result,p).pattern,'up')
        p.chords=[c];move_chords(p,{c.id},-960);self.assertEqual((p.chords[0].start,p.chords[0].end),(3840,4800));p.chords=[c]
        repartition_chord(p,c.id,0,p.end);self.assertEqual((p.chords[0].start,p.chords[0].end),(3840,6720));p.validate()

    def test_custom_move_crops_preserving_per_note_attributes(self):
        p=mixed();c=Chord(3840,1920,custom_rhythm=True,notes=[Note(0,1920,60,111,flat=True)])
        moved=moved_chord(p,c,6240)
        self.assertEqual(events(moved.render_notes()),[(6240,480,60,111)]);self.assertTrue(moved.notes[0].flat)
        self.assertIsNone(analyze(moved,p));self.assertTrue(moved.custom_rhythm)

    def test_growing_bar_inserts_silence_without_stretching_chords(self):
        p=Project();p.chords=[Chord(0,7680,notes=[Note(0,7680,k,83) for k in (48,52,55)])]
        p.notes=[Note(3500,600,72,109),Note(4200,240,74)]
        p.change_meter(0,5,4)
        self.assertEqual(events(p.notes),[(3500,340,72,109),(4800,260,72,109),(5160,240,74,92)])
        self.assertEqual([(c.start,c.end) for c in p.chords],[(0,3840),(4800,8640)])
        self.assertFalse(any(n.start<4800 and n.end>3840 for n in p.harmony_notes()));p.validate()

    def test_shortening_requires_permission_then_crops_and_shifts(self):
        p=Project();p.notes=[Note(2700,800,60),Note(3000,200,64),Note(4000,120,65)]
        p.chords=[Chord(0,7680,notes=[Note(0,7680,k,80) for k in (48,52,55)])]
        original=p.to_dict();self.assertEqual(losses(p,[0],3,4),(2,3,0))
        with self.assertRaises(ValueError):p.change_meter(0,3,4)
        self.assertEqual(p.to_dict(),original)
        p.change_meter(0,3,4,True)
        self.assertEqual(events(p.notes),[(2700,180,60,92),(3040,120,65,92)])
        self.assertEqual([(c.start,c.end) for c in p.chords],[(0,2880),(2880,6720)])
        self.assertTrue(all(analyze(c,p).pattern=='block' for c in p.chords));p.validate()

    def test_equal_length_meter_change_preserves_midi_and_reidentifies(self):
        p=Project();p.set_markers([0,1,2,3,4,5,6,7],48,'Ionian',2,4)
        c=Chord(0,3840,pattern='quarters');p.put_chord(c);before=events(p.harmony_notes())
        p.change_meter(0,4,8)
        self.assertEqual(events(p.harmony_notes()),before);self.assertEqual(len(p.chords),2)
        self.assertIsNone(analyze(p.chords[0],p));self.assertEqual(analyze(p.chords[1],p).pattern,'quarters');p.validate()

    def test_broadcast_uses_final_meter_map_without_transient_splits(self):
        p=Project();p.measures=[Measure(2,4) for _ in range(8)];p.contexts=[Context(0,p.end)]
        p.chords=[Chord(0,7680,notes=[Note(0,7680,k) for k in (48,52,55)])]
        before=events(p.harmony_notes());p.set_markers(range(8),48,'Ionian',4,8)
        self.assertEqual(len(p.chords),1);self.assertEqual(events(p.harmony_notes()),before);p.validate()

    def test_pattern_map_and_menu_commands_refuse_unsupported_meter(self):
        self.assertEqual(set(PATTERN_METERS),set(PATTERNS))
        p=mixed();c=Chord(3840,2880);p.put_chord(c)
        self.assertTrue(supports('up',p,c.start));self.assertFalse(supports('bass_chord',p,c.start))
        before=p.to_dict()
        with self.assertRaises(ValueError):change_chords(p,{c.id},'pattern:bass_chord')
        self.assertEqual(before,p.to_dict())

    def test_insert_pattern_and_move_at_final_region_are_cropped_on_grid(self):
        p=mixed();p.put_chord(Chord(960,6000,pattern='up'))
        c=p.chords[0];self.assertEqual(c.end,3840);self.assertEqual(analyze(c,p).pattern,'up')
        self.assertEqual(c.notes[0].pitch,c.pitches[2])
        c=Chord(7680,2000,custom_rhythm=True,notes=[Note(0,2000,60,101)]);p.chords=[c]
        move_chords(p,{c.id},2400);self.assertEqual((p.chords[0].start,p.chords[0].end),(10080,p.end));p.validate()

    def test_cross_key_labels_and_multiline_details(self):
        p=Project();p.set_context([[3840,p.end]],tonic=50,mode='Dorian');c=Chord(0,7680)
        self.assertEqual(roman_label(p,c),'I → ♭VII')
        details=chord_details(p,c)
        for token in ('C3','D3','Ionian','Dorian','1 = C','♭7 = C','实际低音'):self.assertIn(token,details)
        c.bass=4;self.assertIn('/3 →',roman_label(p,c));self.assertIn('C/E',details if False else c.name)

    def test_random_meter_edits_preserve_valid_timeline(self):
        import random
        rng=random.Random(27);p=Project()
        p.notes=[Note(i*240,120,60+i%5) for i in range(100)]
        p.chords=[Chord(i*3840,3840,pattern='up') for i in range(8)]
        for _ in range(40):
            i=rng.randrange(8);n,d=rng.choice([(3,4),(4,4),(6,8),(2,4),(4,8),(5,4)])
            p.change_meter(i,n,d,True);p.validate()
            self.assertTrue(all(any(a<=c.start<c.end<=b for a,b,m in regions(p)) for c in p.chords))


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.save=patch.object(MainWindow,'save_preferences');self.save.start()
        p=mixed();p.chords=[Chord(0,3840,notes=[Note(960,2880,60,event_id="held")]),Chord(3840,2880,notes=[Note(0,2880,60,event_id="held")])]
        self.w=MainWindow(p);self.w.change_language('zh',False);self.w.show();self.w.resize(1200,900)
        self.w.timer.stop();self.w.autosave.stop()
        for b in self.w.mute_buttons.values():b.setChecked(True)
        self.w.open_harmony();QTest.qWait(25)
        self.r=self.w.harmony_window.roll;self.r.center_pitch(60);self.r.tool='smart';APP.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.save.stop()
    def point(self,tick):return QPoint(round(self.r.x_at(tick)),round(self.r.y_at(60)+self.r.row_height/2))

    def test_click_marquee_and_context_select_entire_visible_long_note(self):
        r=self.r;ids={n.id for n in r.notes};before=self.w.project.to_dict()
        for tick in (1500,4200):
            r.selected_ids.clear();QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,pos=self.point(tick));self.assertEqual(r.selected_ids,ids)
        QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ControlModifier,self.point(2000));self.assertFalse(r.selected_ids)
        menu=r.note_menu(self.point(1500));self.assertEqual(r.selected_ids,ids);menu.deleteLater()
        r.selected_ids.clear();start=self.point(1500)+QPoint(0,-r.row_height)
        QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(r.viewport(),self.point(2000));QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=self.point(2000))
        self.assertEqual(r.selected_ids,ids);self.assertEqual(self.w.project.to_dict(),before)

    def test_long_note_outer_resize_keeps_inner_boundary(self):
        r=self.r;pos=self.point(6600);hit=r.note_hit(QPointF(pos));right=QPoint(round(hit[0].right()-1),pos.y())
        QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=right);QTest.mouseMove(r.viewport(),self.point(4800));QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=self.point(4800))
        self.assertEqual(events(self.w.project.harmony_notes()),[(960,3840,60,92)])
        self.assertEqual(len(r.selected_ids),1)

    def test_chord_lane_hover_and_pattern_availability(self):
        lane=self.r.lane;c=self.w.project.chords[1];c.recognized=True;self.w.refresh();APP.processEvents()
        point=QPoint(round(lane.x_at(c.start+100)),25);QTest.mouseMove(lane,point);self.assertIn('和弦音',lane.toolTip())
        menu=lane.context_menu(point);items={a.text():a for a in menu.pattern_menu.actions()}
        self.assertFalse(items['低音 + 和弦'].isEnabled());self.assertTrue(items['上行琶音'].isEnabled())
        dialog=ChordDialog(c,self.w.project);self.assertFalse(dialog.pattern.model().item(dialog.pattern.findData('bass_chord')).isEnabled());dialog.deleteLater()

    def test_all_title_buttons_use_same_painter_and_restore_state(self):
        w=self.w;w.harmony_window.setFloating(True);APP.processEvents()
        for b in w.title_bar.window_buttons+w.harmony_window.title_bar.buttons+[w.harmony_window.title_bar.dock]:self.assertIsInstance(b,IconButton);self.assertEqual(b.text(),'')
        w.title_bar.maximize();APP.processEvents();self.assertEqual(w.title_bar.window_buttons[1].kind,'restore')
        w.title_bar.maximize();APP.processEvents();self.assertEqual(w.title_bar.window_buttons[1].kind,'maximize')
        w.harmony_window.title_bar.maximize();APP.processEvents();self.assertEqual(w.harmony_window.title_bar.maximize_button.kind,'restore')

    def test_confirmation_cancel_and_accept_are_atomic_and_undoable(self):
        w=self.w;w.project=mixed();w.project.notes=[Note(2700,800,60)];w.refresh();before=w.project.to_dict()
        with patch('popscore.app.QMessageBox.question',return_value=QMessageBox.StandardButton.No) as question:
            self.assertFalse(w.confirm_meter_trim([0],3,4));self.assertTrue(question.called)
        self.assertEqual(before,w.project.to_dict())
        with patch('popscore.app.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):
            self.assertTrue(w.confirm_meter_trim([0],3,4))
            self.assertTrue(w.mutate('meter',lambda p:p.change_meter(0,3,4,True)))
        self.assertEqual(w.project.notes[0].end,2880);w.undo();self.assertEqual(w.project.to_dict(),before)

    def test_bar_dialog_and_propagation_use_confirmation_before_mutation(self):
        from PySide6.QtWidgets import QDialog
        w=self.w;w.project=Project();w.project.notes=[Note(3000,480,60)];w.refresh();before=w.project.to_dict()
        with patch('popscore.app.MarkerDialog') as factory:
            factory.return_value.exec.return_value=QDialog.DialogCode.Accepted
            factory.return_value.value.return_value=dict(tonic=48,mode='Ionian',numerator=3,denominator=4)
            with patch('popscore.app.QMessageBox.question',return_value=QMessageBox.StandardButton.No):w.edit_context([[0,3840]])
            self.assertEqual(before,w.project.to_dict())
            with patch('popscore.app.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):w.edit_context([[0,3840]])
        self.assertEqual(w.project.measures[0].ticks,2880);self.assertFalse(w.project.notes);w.undo();self.assertEqual(before,w.project.to_dict())
        w.project=mixed();w.project.notes=[Note(10080,240,60)];w.refresh();before=w.project.to_dict()
        with patch('popscore.app.QMessageBox.question',return_value=QMessageBox.StandardButton.No):w.propagate_marker(1,'meter')
        self.assertEqual(before,w.project.to_dict())
        with patch('popscore.app.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):w.propagate_marker(1,'meter')
        self.assertFalse(w.project.notes);self.assertEqual(w.project.measures[2].ticks,2880);w.project.validate()

if __name__=='__main__':unittest.main()
