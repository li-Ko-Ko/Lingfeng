"""Shared timeline gestures, pan, footers, and cropped-pattern score semantics."""
import copy,os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from lingfeng.ui.main_window import MainWindow
from lingfeng.music.model import Project, Note, Chord, PPQ
from lingfeng.engraving.notation import is_chord_tone, fragments_for_bar
from lingfeng.ui.piano_roll import KEY_W

APP=QApplication.instance() or QApplication([])
LEFT=Qt.MouseButton.LeftButton;RIGHT=Qt.MouseButton.RightButton;MIDDLE=Qt.MouseButton.MiddleButton
SHIFT=Qt.KeyboardModifier.ShiftModifier;CTRL=Qt.KeyboardModifier.ControlModifier


class GestureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prefs=patch.object(MainWindow,'save_preferences');cls.prefs.start()
        cls.w=MainWindow(Project());cls.w.change_language('zh',False);cls.w.show();cls.w.timer.stop();cls.w.autosave.stop()
    @classmethod
    def tearDownClass(cls):
        cls.w.dirty=False;cls.w.close();cls.w.deleteLater();APP.processEvents();cls.prefs.stop()
    def setUp(self):
        w=self.w
        if QApplication.activePopupWidget():QApplication.activePopupWidget().close()
        w.switch_workspace('compose')
        w.melody_window.setFloating(False);w.harmony_window.setFloating(False)
        p=Project();p.notes=[Note(0,960,60),Note(960,960,60),Note(2400,480,64)]
        p.chords=[Chord(0,1920),Chord(1920,1920,50,'m')]
        w.replace_project(p);w.resize(1100,860);w.show_information=True
        for key in ('melody','chords','timeline','volume'):w.visibility_actions[key].setChecked(True)
        w.visibility_actions['harmony'].setChecked(False);w.roll.zoom=120;w.roll.row_height=22;w.roll.tool='smart';w.roll.compact=False
        w.roll.update_ranges();w.roll.timeViewChanged.emit();w.roll.horizontalScrollBar().setValue(0);w.roll.center_pitch(62);w.roll.selected_ids.clear()
        w.seek(0);w.mount_panels();APP.processEvents();w.roll.grab();w.chord_lane.grab()
    def point(self,tick,y=None):
        return QPoint(round(self.w.timeline.x_at(tick)),self.w.timeline.roll.bar_ruler_height+15 if y is None else y)
    def drag(self,widget,start,end,button=LEFT,mod=Qt.KeyboardModifier.NoModifier):
        QTest.mousePress(widget,button,mod,start);QTest.mouseMove(widget,end);QTest.mouseRelease(widget,button,mod,end);APP.processEvents()
    def note_point(self,tick,pitch=60):
        r=self.w.roll;return QPoint(round(r.x_at(tick)),round(r.y_at(pitch)+r.row_height/2))

    def test_lower_click_seeks_without_bar_selection_or_loop(self):
        w=self.w;selected=copy.deepcopy(w.roll.selection)
        QTest.mouseClick(w.timeline,LEFT,pos=self.point(1920))
        self.assertEqual(w.play_anchor,1920);self.assertEqual(w.roll.selection,selected);self.assertIsNone(w.loop_range);self.assertFalse(w.transport.playing)

    def test_upper_selects_whole_bars_and_never_seeks(self):
        w=self.w;w.seek(480);self.drag(w.timeline,self.point(100,12),self.point(4300,12))
        self.assertEqual(w.roll.selection,[[0,7680]]);self.assertEqual(w.play_anchor,480);self.assertIsNone(w.loop_range)
        QTest.mouseClick(w.timeline,LEFT,CTRL,self.point(100,12));self.assertEqual(w.roll.selection,[[3840,7680]])

    def test_lower_drag_sets_shared_loop_without_moving_position(self):
        w=self.w;w.seek(480);bars=copy.deepcopy(w.roll.selection)
        self.drag(w.timeline,self.point(960),self.point(2500))
        self.assertEqual(w.loop_range,(960,2640));self.assertTrue(w.loop.isChecked());self.assertEqual(w.play_anchor,480)
        self.assertEqual(w.roll.selection,bars)
        for r in (w.main_roll,w.roll,w.harmony_window.roll):self.assertEqual(r.loop_range,(960,2640))

    def test_other_selections_preserve_loop_and_cancel_does_not_restore(self):
        w=self.w;w.set_loop_range((960,2880));QTest.mouseClick(w.timeline,LEFT,pos=self.point(4000,12))
        self.assertEqual(w.loop_range,(960,2880));self.assertTrue(w.loop.isChecked())
        self.drag(w.roll.viewport(),self.note_point(100,66),self.note_point(2800,59))
        self.assertEqual(w.loop_range,(960,2880));QTest.mouseClick(w.chord_lane,LEFT,pos=QPoint(round(w.chord_lane.x_at(2400)),25))
        self.assertEqual(w.loop_range,(960,2880));w.loop.setChecked(False)
        for r in (w.main_roll,w.roll,w.harmony_window.roll):self.assertIsNone(r.loop_range)
        w.loop.setChecked(True);self.assertIsNone(w.loop_range);self.assertFalse(w.loop_active())

    def test_loop_edges_resize_and_shift_extends_but_control_click_only_seeks(self):
        w=self.w;w.set_loop_range((960,2880));w.seek(480)
        self.drag(w.timeline,self.point(960),self.point(480));self.assertEqual(w.loop_range,(480,2880));self.assertEqual(w.play_anchor,480)
        self.drag(w.timeline,self.point(2880),self.point(3840));self.assertEqual(w.loop_range,(480,3840))
        QTest.mouseClick(w.timeline,LEFT,SHIFT,self.point(4300));self.assertEqual(w.loop_range[1],4320)
        bounds=w.loop_range;QTest.mouseClick(w.timeline,LEFT,CTRL,self.point(1200));self.assertEqual(w.loop_range,bounds);self.assertEqual(w.play_anchor,1200)

    def test_lower_right_drag_does_nothing(self):
        w=self.w;before=(copy.deepcopy(w.roll.selection),w.play_anchor)
        self.drag(w.timeline,self.point(960),self.point(2400),RIGHT)
        self.assertEqual((w.roll.selection,w.play_anchor),before);self.assertIsNone(w.loop_range);self.assertIsNone(w.timeline.gesture.menu)

    def test_upper_right_marquee_selects_then_opens_only_bar_menu(self):
        w=self.w;self.drag(w.timeline,self.point(500,12),self.point(4500,12),RIGHT)
        self.assertEqual(w.roll.selection,[[0,3840],[3840,7680]]);menu=w.timeline.gesture.menu;self.assertIsNotNone(menu)
        self.assertTrue(any('拍号' in a.text() for a in menu.actions()));self.assertFalse(any('音符' in a.text() for a in menu.actions()));menu.close()

    def test_timeline_edge_scroll_extends_upper_and_lower_without_seeking(self):
        w=self.w;t=w.timeline;r=t.roll
        for y in (12,r.bar_ruler_height+15):
            r.horizontalScrollBar().setValue(0);start=self.point(480,y);end=QPoint(t.width()-2,y)
            QTest.mousePress(t,LEFT,pos=start);QTest.mouseMove(t,end)
            with patch.object(QApplication,'mouseButtons',return_value=LEFT):
                for _ in range(10):t.gesture.scroll_edge()
            self.assertGreater(r.horizontalScrollBar().value(),0);self.assertFalse(w.follow_playhead.isChecked());self.assertEqual(w.play_anchor,0)
            QTest.mouseRelease(t,LEFT,pos=end)

    def test_middle_pan_roll_moves_both_axes_without_music_or_selection_change(self):
        w=self.w;r=w.roll;r.horizontalScrollBar().setValue(200);v=r.verticalScrollBar().value();before=w.project.to_dict();r.selected_ids={r.notes[0].id}
        self.drag(r.viewport(),QPoint(400,160),QPoint(320,130),MIDDLE)
        self.assertEqual(r.horizontalScrollBar().value(),280);self.assertEqual(r.verticalScrollBar().value(),v+30)
        self.assertEqual(r.selected_ids,{r.notes[0].id});self.assertEqual(w.project.to_dict(),before);self.assertEqual(w.play_anchor,0);self.assertFalse(w.follow_playhead.isChecked())

    def test_middle_pan_chord_lane_only_moves_horizontal(self):
        w=self.w;r=w.chord_lane.editor;r.horizontalScrollBar().setValue(200);v=r.verticalScrollBar().value();before=w.project.to_dict()
        self.drag(w.chord_lane,QPoint(400,30),QPoint(320,10),MIDDLE)
        self.assertEqual(r.horizontalScrollBar().value(),280);self.assertEqual(r.verticalScrollBar().value(),v);self.assertEqual(w.project.to_dict(),before)

    def test_adjacent_note_gap_seeks_but_note_body_draw_click_deletes(self):
        w=self.w;r=w.roll;heard=[];r.audition.connect(heard.append)
        for tool in ('smart','draw'):
            w.seek(0);r.tool=tool;before=w.project.to_dict();pos=self.note_point(960)
            self.assertIsNone(r.note_hit(pos));QTest.mouseClick(r.viewport(),LEFT,pos=pos)
            self.assertEqual(w.play_anchor,960);self.assertEqual(w.project.to_dict(),before)
        self.assertFalse(heard);QTest.mouseClick(r.viewport(),LEFT,pos=self.note_point(1200));self.assertEqual(len(w.project.notes),2);self.assertFalse(heard)

    def test_gap_press_stays_arrow_then_drag_selects_without_seeking(self):
        w=self.w;r=w.roll;start=self.note_point(960);end=self.note_point(2800,64)
        QTest.mouseMove(r.viewport(),start);QTest.mousePress(r.viewport(),LEFT,pos=start)
        self.assertEqual(r.viewport().cursor().shape(),Qt.CursorShape.ArrowCursor);self.assertIsNone(r.marquee)
        QTest.mouseMove(r.viewport(),end);self.assertEqual(r.viewport().cursor().shape(),Qt.CursorShape.CrossCursor)
        QTest.mouseRelease(r.viewport(),LEFT,pos=end);self.assertEqual(w.play_anchor,0);self.assertTrue(r.selected_ids)

    def test_right_note_marquee_in_smart_is_non_destructive_and_has_menu(self):
        w=self.w;r=w.roll;r.tool='smart';before=w.project.to_dict();heard=[];r.audition.connect(heard.append)
        self.drag(r.viewport(),self.note_point(50,66),self.note_point(2850,59),RIGHT)
        self.assertEqual(r.selected_ids,{n.id for n in r.notes});self.assertEqual(w.project.to_dict(),before);self.assertFalse(heard)
        self.assertTrue(any('音符' in a.text() for a in r.active_menu.actions()));r.active_menu.close();self.assertIsNone(r.marquee)

    def test_right_chord_marquee_selects_and_has_no_residual_rectangle(self):
        w=self.w;lane=w.chord_lane;before=w.project.to_dict()
        self.drag(lane,QPoint(round(lane.x_at(50)),10),QPoint(round(lane.x_at(3700)),50),RIGHT)
        self.assertEqual(lane.editor.selected_chords,{c.id for c in w.project.chords});self.assertEqual(w.project.to_dict(),before);self.assertIsNone(lane.marquee);lane.active_menu.close()

    def test_floating_rolls_use_the_same_split_ruler_and_local_pan(self):
        w=self.w;w.open_harmony();w.melody_window.setFloating(True);w.harmony_window.setFloating(True);APP.processEvents()
        for r in (w.roll,w.harmony_window.roll):
            w.loop.setChecked(False)
            r.horizontalScrollBar().setValue(0);w.set_timeline_sync(False,r)
            start=QPoint(round(r.x_at(960)),r.bar_ruler_height+15);end=QPoint(round(r.x_at(2400)),r.bar_ruler_height+15)
            self.drag(r.viewport(),start,end);self.assertEqual(w.loop_range,(960,2640));self.assertEqual(w.play_anchor,0)
            QTest.mouseClick(r.viewport(),LEFT,pos=QPoint(round(r.x_at(2880)),r.bar_ruler_height+15));self.assertEqual(w.play_anchor,2880);w.seek(0)
        before=w.main_roll.horizontalScrollBar().value();self.drag(w.roll.viewport(),QPoint(450,180),QPoint(350,150),MIDDLE)
        self.assertEqual(w.main_roll.horizontalScrollBar().value(),before);self.assertGreater(w.roll.horizontalScrollBar().value(),0)

    def test_shared_footer_stays_one_row_and_is_visible_in_score_and_floats(self):
        w=self.w;w.resize(700,860);w.status_message('测试提示 '*100);APP.processEvents()
        for footer in w.shared_footers():
            self.assertLessEqual(len(footer.hint.message),80);self.assertIn('测试',footer.hint.message)
        self.assertTrue(w.audio_footer.isVisible());self.assertLessEqual(w.audio_footer.height(),42)
        w.switch_workspace('score');APP.processEvents();self.assertTrue(w.audio_footer.isVisible())
        w.edit_toggle.setChecked(True);w.toggle_editor();w.toggle_score_panel_floating('melody');APP.processEvents();self.assertTrue(w.melody_volume.isVisible())
        w.melody_volume.sliders['chords'].setValue(51)
        self.assertEqual(w.project.volumes['chords'],51)
        for footer in w.shared_footers():self.assertEqual(footer.sliders['chords'].value(),51)
        w.change_information(False)
        for footer in w.shared_footers():self.assertEqual(footer.hint.message,'')
        w.change_information(True)
        for footer in w.shared_footers():self.assertTrue(footer.hint.message)
        w.toggle_score_panel_floating('melody')


class EngravingTests(unittest.TestCase):
    def test_recognized_cropped_bass_pattern_circles_only_performed_tones(self):
        p=Project();p.chords=[Chord(0,960,58,notes=[Note(0,864,46)],pattern='bass_chord')];before=p.to_dict()
        self.assertFalse(is_chord_tone(p,62,0));self.assertFalse(is_chord_tone(p,65,320));self.assertFalse(is_chord_tone(p,60,640));self.assertTrue(is_chord_tone(p,58,0));self.assertEqual(p.to_dict(),before)
        p.chords[0].recognized=False;self.assertFalse(is_chord_tone(p,62,0));self.assertTrue(is_chord_tone(p,58,0))
    def test_optional_project_bar20_triplets_and_following_tones(self):
        from pathlib import Path
        location=os.environ.get('LINGFENG_DIAGNOSTIC_PROJECT')
        if not location:self.skipTest('Set LINGFENG_DIAGNOSTIC_PROJECT for an optional local diagnostic')
        source=Path(location)
        if not source.exists():self.skipTest('Local diagnostic project is not distributed')
        data=source.read_bytes();p=Project.load(source);a=p.starts[19];pieces=[f for f in fragments_for_bar(p,19) if f.note]
        self.assertEqual([is_chord_tone(p,f.pitch,f.start) for f in pieces], [bool(p.chord_at(f.start) and f.pitch%12 in {n.pitch%12 for n in p.chord_at(f.start).render_notes()}) for f in pieces])
        self.assertEqual(source.read_bytes(),data)


if __name__=='__main__':unittest.main()
