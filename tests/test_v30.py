"""Keyboard viewport navigation, stable marquee scrolling and batch patterns."""
import copy,os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLineEdit
from popscore.app import MainWindow
from popscore.model import Project,Chord,Note,Measure,Context,PPQ
from popscore.chordops import change_chords,can_apply_pattern
from popscore.rhythm import analyze
from popscore.keybindings import load_bindings

APP=QApplication.instance() or QApplication([])

class PatternTests(unittest.TestCase):
    def test_same_meter_separated_regions_change_patterns_atomically(self):
        p=Project();p.measures=[Measure(),Measure(3,4),Measure()];p.contexts=[Context(0,p.end)]
        p.chords=[Chord(0,1920,bass=4,velocity=110,custom_rhythm=True),Chord(6720,1920,50,'m',velocity=65)]
        before=copy.deepcopy(p.chords);change_chords(p,{c.id for c in p.chords},'pattern:up');p.validate()
        for old,c in zip(before,p.chords):
            self.assertEqual((c.id,c.start,c.duration,c.root,c.quality,c.bass,c.velocity),(old.id,old.start,old.duration,old.root,old.quality,old.bass,old.velocity))
            self.assertFalse(c.custom_rhythm);self.assertEqual(analyze(c,p).pattern,'up')
            self.assertTrue(all(n.velocity==c.velocity for n in c.notes))

    def test_mixed_unknown_and_unsupported_patterns_rejected_without_changes(self):
        p=Project();p.measures=[Measure(3,4),Measure(6,8),Measure(3,4)];p.contexts=[Context(0,p.end)]
        p.chords=[Chord(0,960),Chord(2880,960)]
        for code in ('block','up'):
            before=p.to_dict();self.assertFalse(can_apply_pattern(p,p.chords,code))
            with self.assertRaises(ValueError):change_chords(p,{c.id for c in p.chords},'pattern:'+code)
            self.assertEqual(before,p.to_dict())
        p.chords[1].start=5760;self.assertFalse(can_apply_pattern(p,p.chords,'offbeat'))
        p.chords[1].recognized=False;self.assertFalse(can_apply_pattern(p,p.chords,'block'))

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.save=patch.object(MainWindow,'save_preferences');self.save.start()
        p=Project();p.chords=[Chord(0,480),Chord(1920,960,50,'m')]
        self.w=MainWindow(p);self.w.change_language('zh',False);self.w.show();self.w.resize(1000,850);self.w.timer.stop();self.w.autosave.stop()
        self.w.keybindings=load_bindings({})
        for b in self.w.mute_buttons.values():b.setChecked(True)
        APP.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.save.stop()
    def focus(self,widget):widget.window().activateWindow();widget.setFocus();APP.processEvents()

    def test_arrows_browse_main_chord_lane_without_editing_or_seeking(self):
        w=self.w;lane=w.chord_lane;r=lane.editor;lane.selection_event({w.project.chords[0].id});r.edit_target='chords';self.focus(lane)
        before=w.project.to_dict();head=w.playhead;scroll=r.horizontalScrollBar().value()
        QTest.keyClick(lane,Qt.Key.Key_Right);self.assertGreater(r.horizontalScrollBar().value(),scroll)
        self.assertEqual(r.horizontalScrollBar().value(),w.shared_scroll.value());self.assertFalse(w.follow_playhead.isChecked())
        QTest.keyClick(lane,Qt.Key.Key_Left);self.assertEqual(r.horizontalScrollBar().value(),scroll)
        self.assertEqual(w.project.to_dict(),before);self.assertEqual(w.playhead,head)

    def test_arrows_browse_independent_window_and_ad_still_follows_moved_chords(self):
        w=self.w;w.open_harmony();w.harmony_window.setFloating(True);w.harmony_window.sync.setChecked(False);APP.processEvents()
        r=w.harmony_window.roll;r.zoom=600;r.update_ranges();r.timeViewChanged.emit();r.lane.selection_event({w.project.chords[0].id});r.edit_target='chords';self.focus(r.lane)
        main=w.main_roll.horizontalScrollBar().value();start=w.project.chords[0].start
        QTest.keyClick(r.lane,Qt.Key.Key_Right);self.assertGreater(r.horizontalScrollBar().value(),0);self.assertEqual(w.main_roll.horizontalScrollBar().value(),main);self.assertEqual(w.project.chords[0].start,start)
        for _ in range(10):QTest.keyClick(r.lane,Qt.Key.Key_D)
        self.assertGreater(r.horizontalScrollBar().value(),100);self.assertEqual(w.main_roll.horizontalScrollBar().value(),main)
        self.assertFalse(w.harmony_window.transport_controls.follow.isChecked())

    def test_shift_three_grid_only_and_docked_sync(self):
        w=self.w;w.open_harmony();self.focus(w.chord_lane);duration=w.length.currentData();grid=w.grid.currentData()
        QTest.keyClick(w.chord_lane,Qt.Key.Key_3,Qt.KeyboardModifier.ShiftModifier)
        self.assertTrue(w.grid.triplet);self.assertTrue(w.harmony_window.grid.triplet);self.assertEqual(w.roll.grid,grid*2//3)
        self.assertEqual(w.harmony_window.roll.grid,w.roll.grid);self.assertEqual(w.length.currentData(),duration)
        QTest.keyClick(w.chord_lane,Qt.Key.Key_NumberSign,Qt.KeyboardModifier.ShiftModifier);self.assertFalse(w.grid.triplet)
        field=QLineEdit(w);field.show();self.focus(field);QTest.keyClick(field,Qt.Key.Key_3,Qt.KeyboardModifier.ShiftModifier);self.assertFalse(w.grid.triplet)

    def test_floating_grid_shortcut_and_custom_binding(self):
        w=self.w;w.open_harmony();w.harmony_window.setFloating(True);w.harmony_window.sync.setChecked(False);APP.processEvents();r=w.harmony_window.roll;self.focus(r.lane)
        QTest.keyClick(r.lane,Qt.Key.Key_3,Qt.KeyboardModifier.ShiftModifier);self.assertTrue(w.harmony_window.grid.triplet);self.assertFalse(w.grid.triplet)
        w.keybindings=load_bindings({'grid_triplet':'Alt+3'})
        QTest.keyClick(r.lane,Qt.Key.Key_3,Qt.KeyboardModifier.ShiftModifier);self.assertTrue(w.harmony_window.grid.triplet)
        QTest.keyClick(r.lane,Qt.Key.Key_3,Qt.KeyboardModifier.AltModifier);self.assertFalse(w.harmony_window.grid.triplet)

    def test_blank_chord_marquee_repaints_immediately_after_release(self):
        w=self.w;w.project.chords=[];w.refresh();lane=w.chord_lane;self.focus(lane);APP.processEvents()
        start=QPoint(180,25);end=QPoint(240,45);QTest.mouseMove(lane,start);APP.processEvents();before=lane.grab().toImage()
        QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(lane,end);APP.processEvents()
        self.assertIsNotNone(lane.marquee);self.assertNotEqual(lane.grab().toImage(),before)
        QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=end);APP.processEvents()
        self.assertIsNone(lane.marquee);self.assertEqual(lane.grab().toImage(),before);self.assertFalse(lane.edge_timer.isActive())

    def test_chord_marquee_scroll_keeps_offscreen_selection_and_anchor(self):
        w=self.w;lane=w.chord_lane;r=lane.editor;r.zoom=500;r.update_ranges();r.timeViewChanged.emit();APP.processEvents()
        before=w.project.to_dict();start=QPoint(70,lane.card_height()-1);edge=QPoint(lane.width()-2,15)
        QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(lane,edge)
        anchor=lane.marquee_anchor;self.assertTrue(lane.edge_timer.isActive())
        for _ in range(50):lane.scroll_drag_edge()
        self.assertGreater(r.horizontalScrollBar().value(),300);self.assertEqual(lane.marquee_anchor,anchor)
        self.assertEqual(r.selected_chords,{c.id for c in w.project.chords});self.assertFalse(w.follow_playhead.isChecked())
        QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=edge);self.assertFalse(lane.edge_timer.isActive());self.assertIsNone(lane.marquee)
        self.assertEqual(w.project.to_dict(),before)

    def test_piano_marquee_scrolls_in_two_axes_and_preserves_selection(self):
        w=self.w;r=w.roll;r.zoom=400;r.update_ranges();r.timeViewChanged.emit();r.center_pitch(60)
        high=r.pitch_at(r.ruler_height+35);low=r.pitch_at(r.viewport().height()-25)-5
        w.project.notes=[Note(240,120,high),Note(2400,240,low)];w.refresh();APP.processEvents();before=w.project.to_dict()
        start=QPoint(70,r.ruler_height+4);edge=QPoint(r.viewport().width()-2,r.viewport().height()-2)
        QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(r.viewport(),edge);anchor=r.drag[1];h=r.horizontalScrollBar().value();v=r.verticalScrollBar().value()
        for _ in range(45):r.scroll_drag_edge()
        self.assertGreater(r.horizontalScrollBar().value(),h);self.assertGreater(r.verticalScrollBar().value(),v)
        self.assertEqual(r.drag[1],anchor);self.assertEqual(r.selected_ids,{n.id for n in w.project.notes})
        QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=edge);self.assertIsNone(r.marquee);self.assertFalse(r.edge_timer.isActive());self.assertEqual(w.project.to_dict(),before)

    def test_escape_cancels_both_marquee_timers(self):
        w=self.w
        for widget,editor in ((w.chord_lane,w.chord_lane),(w.roll.viewport(),w.roll)):
            start=QPoint(80,w.chord_lane.card_height()-1 if widget is w.chord_lane else w.roll.ruler_height+3);edge=QPoint(widget.width()-2,20 if widget is w.chord_lane else widget.height()-2)
            QTest.mousePress(widget,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(widget,edge);QTest.keyClick(editor,Qt.Key.Key_Escape)
            self.assertIsNone(editor.marquee);self.assertFalse(editor.edge_timer.isActive());QTest.mouseRelease(widget,Qt.MouseButton.LeftButton,pos=edge)

    def test_batch_pattern_menu_rebuilds_all_and_undo_restores(self):
        w=self.w;lane=w.chord_lane;ids={c.id for c in w.project.chords};lane.selection_event(ids);self.focus(lane);before=w.project.to_dict()
        menu=lane.context_menu(QPoint(80,25));a=next(a for a in menu.pattern_menu.actions() if a.text()=='上行琶音');self.assertTrue(a.isEnabled());a.trigger()
        self.assertTrue(all(c.pattern=='up' and not c.recognized and analyze(c,w.project) is None for c in w.project.chords if c.id in ids));self.assertTrue(all(c.render_notes() for c in w.project.chords if c.id in ids));w.undo();self.assertEqual(w.project.to_dict(),before)
        w.project.change_meter(0,3,4,True);w.project.chords.append(Chord(w.project.starts[1],960));w.refresh();lane.selection_event({c.id for c in w.project.chords})
        menu=lane.context_menu(QPoint(80,25));self.assertFalse(next(a for a in menu.pattern_menu.actions() if a.text()=='上行琶音').isEnabled())

if __name__=='__main__':unittest.main()
