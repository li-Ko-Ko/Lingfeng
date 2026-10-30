"""Cross-key labels, bass actions, bar insertion and conservative edit scrolling."""
import copy,os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog
from popscore.model import Project,Chord,Note,Context,Measure,QUALITIES,PPQ
from popscore.chordops import change_chords,replace_bass,invert_chord
from popscore.dialogs import MarkerDialog
from popscore.editor import PianoRoll,KEY_W
from popscore.app import MainWindow

APP=QApplication.instance() or QApplication([])

class MusicTests(unittest.TestCase):
    def test_twelve_basses_preserve_upper_voices_and_per_note_edits(self):
        for pc in range(12):
            p=Project();c=Chord(0,3840,quality='9',custom_rhythm=True);c.materialize()
            for i,n in enumerate(c.notes):n.velocity=70+i;n.flat=True
            upper=copy.deepcopy([n for n in c.notes if n.pitch!=min(x.pitch for x in c.notes)])
            p.chords=[c];change_chords(p,{c.id},'bass:'+str(pc));p.validate()
            self.assertEqual(min(n.pitch for n in c.notes)%12,pc)
            self.assertEqual([n for n in c.notes if n.pitch!=min(x.pitch for x in c.notes)],upper)
            self.assertEqual(c.bass,None if pc==0 else pc);self.assertTrue(c.custom_rhythm)
            self.assertEqual(c.quality,'9');self.assertEqual(c.root,48)

    def test_ninth_inversions_are_repeatable_bass_replacements(self):
        c=Chord(0,3840,quality='9')
        for i,pc in enumerate((0,4,7,10,2)):
            invert_chord(c,i);self.assertEqual(min(c.pitches)%12,pc)
            before=copy.deepcopy(c);invert_chord(c,i);self.assertEqual(c,before)
        c.quality='m'
        with self.assertRaises(ValueError):invert_chord(c,3)
        with self.assertRaises(ValueError):replace_bass(c,12)

    def test_bulk_insert_cuts_once_keeps_later_music_and_markers(self):
        p=Project();p.notes=[Note(3000,2000,64),Note(5000,240,67)]
        p.chords=[Chord(0,7680)];p.set_context([[3840,p.end]],tonic=50,mode='Dorian')
        before=p.end;p.insert_measures(1,3,numerator=3,denominator=4,tonic=53,mode='Aeolian')
        self.assertEqual(len(p.measures),11);self.assertEqual(p.end,before+8640)
        self.assertEqual([(n.start,n.duration,n.pitch) for n in p.notes],[(3000,840,64),(12480,1160,64),(13640,240,67)])
        self.assertFalse(any(n.start<12480 and n.end>3840 for n in p.harmony_notes()))
        self.assertEqual((p.context_at(4000).tonic,p.context_at(12480).tonic),(53,50));p.validate()
        before=p.to_dict()
        for count in (0,-1,1000):
            with self.assertRaises(ValueError):p.insert_measures(0,count)
            self.assertEqual(before,p.to_dict())

class RollTests(unittest.TestCase):
    def setUp(self):
        self.p=Project();self.r=PianoRoll(self.p)
        for panel in ('chords','velocity','navigator'):self.r.set_panel(panel,False)
        self.r.resize(760,400);self.r.show();APP.processEvents();self.r.center_pitch(60)
    def tearDown(self):
        self.r.close();self.r.deleteLater();APP.processEvents()
    def select(self,notes):
        self.p.notes=notes;self.r.set_project(self.p);self.r.selected_ids={n.id for n in notes}
    def test_cross_key_label_uses_time_order_and_exact_end_boundary(self):
        self.p.contexts=[Context(0,3840,48),Context(3840,7680,56,'Aeolian'),Context(7680,self.p.end,58,'Dorian')]
        self.assertEqual(self.r.note_degree_label(60,0,9600),'1 (3, 2)')
        self.assertEqual(self.r.note_degree_label(60,0,3840),'1')
        self.assertEqual(self.r.note_degree_label(60,3840,9600),'3 (2)')
        self.p.contexts=[Context(0,3840),Context(3840,self.p.end)]
        self.assertEqual(self.r.note_degree_label(60,0,9600),'1')

    def test_vertical_follow_waits_for_last_visible_note_both_directions(self):
        r=self.r;self.select([Note(0,PPQ,60),Note(0,PPQ,48)]);r.center_pitch(60)
        before=r.verticalScrollBar().value();r.ensure_selection_visible(dy=-1);self.assertEqual(r.verticalScrollBar().value(),before)
        for n in self.p.notes:n.pitch-=14
        r.ensure_selection_visible(dy=-1)
        self.assertGreater(r.verticalScrollBar().value(),before)
        self.assertLessEqual(r.y_at(46)+r.row_height,r.viewport().height())
        before=r.verticalScrollBar().value();r.ensure_selection_visible(dy=-1);self.assertEqual(r.verticalScrollBar().value(),before)
        for n in self.p.notes:n.pitch+=35
        r.ensure_selection_visible(dy=1);self.assertGreaterEqual(r.y_at(69),r.ruler_height)

    def test_horizontal_follow_short_note_and_one_meter_beat(self):
        r=self.r;self.select([Note(0,4*PPQ,60),Note(5*PPQ,PPQ//4,64)])
        before=r.horizontalScrollBar().value();r.ensure_selection_visible(dx=1);self.assertEqual(before,r.horizontalScrollBar().value())
        for n in self.p.notes:n.start+=9*PPQ
        r.ensure_selection_visible(dx=1)
        self.assertAlmostEqual(r.x_at(9*PPQ)+r.zoom,r.viewport().width(),delta=1)
        r.horizontalScrollBar().setValue(1000)
        r.ensure_selection_visible(dx=-1)
        last=self.p.notes[-1];self.assertGreaterEqual(r.x_at(last.end)-last.duration/PPQ*r.zoom,KEY_W-1)
        r.horizontalScrollBar().setValue(0);self.p.measures[0]=Measure(4,8);self.p.contexts=[Context(0,self.p.end)]
        self.select([Note(PPQ,4*PPQ,60)]);r.zoom=600;r.update_ranges();r.ensure_selection_visible(dx=1)
        self.assertAlmostEqual(r.x_at(PPQ)+300,r.viewport().width(),delta=1)

    def test_drag_edges_scroll_slowly_and_release_stops(self):
        r=self.r;self.select([Note(PPQ,PPQ,60)])
        pos=QPoint(round(r.x_at(1440)),round(r.y_at(60)+r.row_height/2))
        edge=QPoint(r.viewport().width()-2,r.viewport().height()-2)
        QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=pos);QTest.mouseMove(r.viewport(),edge)
        self.assertTrue(r.edge_timer.isActive());before=(r.horizontalScrollBar().value(),r.verticalScrollBar().value())
        r.scroll_drag_edge()
        self.assertTrue(0<r.horizontalScrollBar().value()-before[0]<=12)
        self.assertTrue(0<r.verticalScrollBar().value()-before[1]<=8)
        self.assertTrue(r.previews)
        QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=edge)
        self.assertFalse(r.edge_timer.isActive());before=r.horizontalScrollBar().value();QTest.qWait(65)
        self.assertEqual(before,r.horizontalScrollBar().value())

    def test_hover_and_unmoved_press_never_scroll_escape_cancels_drag(self):
        r=self.r;self.select([Note(0,PPQ,60)])
        edge=QPoint(r.viewport().width()-2,r.viewport().height()-2);before=r.horizontalScrollBar().value()
        QTest.mouseMove(r.viewport(),edge);QTest.qWait(40);self.assertEqual(before,r.horizontalScrollBar().value())
        pos=QPoint(round(r.x_at(480)),round(r.y_at(60)+r.row_height/2))
        QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=pos);self.assertFalse(r.edge_timer.isActive())
        QTest.mouseMove(r.viewport(),edge);QTest.keyClick(r,Qt.Key.Key_Escape);self.assertFalse(r.edge_timer.isActive());self.assertIsNone(r.drag)
        QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=edge)

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.save=patch.object(MainWindow,'save_preferences');self.save.start()
        self.w=MainWindow(Project());self.w.change_language('zh',False);self.w.show();self.w.resize(1200,900)
        self.w.timer.stop();self.w.autosave.stop()
        for b in self.w.mute_buttons.values():b.setChecked(True)
        APP.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.save.stop()
    def test_hide_buttons_match_view_checkboxes_and_can_restore(self):
        w=self.w;w.melody_hide.activated.emit();self.assertFalse(w.visibility_actions['melody'].isChecked());self.assertTrue(w.melody_window.isHidden())
        w.visibility_actions['melody'].setChecked(True);self.assertTrue(w.melody_window.isVisible())
        w.open_harmony();w.harmony_window.hide_button.activated.emit();self.assertFalse(w.visibility_actions['harmony'].isChecked())
        self.assertTrue(w.visibility_actions['chords'].isChecked());w.open_harmony();self.assertTrue(w.harmony_window.isVisible())

    def test_bass_and_inversion_menu_availability_and_undo(self):
        w=self.w
        for quality in ('','7','9','5'):
            c=Chord(0,3840,quality=quality);w.project.chords=[c];w.refresh();APP.processEvents()
            menu=w.chord_lane.context_menu(QPoint(round(w.chord_lane.x_at(240)),20))
            self.assertEqual(len(menu.bass_menu.actions()),12);self.assertEqual(len(menu.inversion_menu.actions()),5)
            self.assertEqual(sum(a.isEnabled() for a in menu.inversion_menu.actions()),len(QUALITIES[quality]))
            self.assertFalse(any(a.isCheckable() for a in menu.bass_menu.actions()+menu.inversion_menu.actions()))
            menu.bass_menu.actions()[1].trigger();self.assertEqual(w.project.chords[0].bass,1);w.undo();self.assertIsNone(w.project.chords[0].bass)
            menu.deleteLater()
        c.recognized=False;w.project.chords=[c];w.refresh();menu=w.chord_lane.context_menu(QPoint(round(w.chord_lane.x_at(240)),20))
        self.assertFalse(menu.bass_menu.isEnabled());self.assertFalse(menu.inversion_menu.isEnabled());menu.deleteLater()

    def test_batch_insert_dialog_is_one_undo_and_selects_inserted_bars(self):
        w=self.w;before=w.project.to_dict()
        def accept(dialog):dialog.count.setValue(4);return QDialog.DialogCode.Accepted
        with patch.object(MarkerDialog,'exec',accept):w.insert_measure(1)
        self.assertEqual(len(w.project.measures),12);self.assertEqual(w.roll.selection,[[3840,19200]])
        w.undo();self.assertEqual(w.project.to_dict(),before);w.redo();self.assertEqual(len(w.project.measures),12)

    def test_keyboard_and_context_move_scroll_same_roll_without_seeking(self):
        w=self.w;r=w.roll;w.project.notes=[Note(0,PPQ,60),Note(0,PPQ,48)];w.refresh();r.selected_ids={n.id for n in r.notes};r.center_pitch(60);r.setFocus();APP.processEvents()
        head=w.playhead;before=r.verticalScrollBar().value();w.note_command(r,'chromatic:-24')
        self.assertGreater(r.verticalScrollBar().value(),before);self.assertLessEqual(r.y_at(36)+r.row_height,r.viewport().height());self.assertEqual(w.playhead,head)
        w.melody_window.setFloating(True);APP.processEvents();r.zoom=600;r.update_ranges();r.setFocus();r.grid=960
        for _ in range(4):w.editor_key_command('right')
        self.assertGreater(r.horizontalScrollBar().value(),0);self.assertEqual(w.playhead,head)

if __name__=='__main__':unittest.main()
