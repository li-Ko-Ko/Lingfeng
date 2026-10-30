"""Regression coverage for anchored zoom, independent layout and bar propagation."""
import os,copy,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent,QImage,QPainter
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.editor import PianoRoll,KEY_W
from popscore.model import Project,Note,PPQ
from popscore.notation import ScoreLayout
from popscore.i18n import set_language
from tests.test_v14 import Synth

APP=QApplication.instance() or QApplication([])

class ZoomTests(unittest.TestCase):
    def setUp(self):
        self.roll=PianoRoll(Project());self.roll.resize(900,600);self.roll.show();APP.processEvents()
    def tearDown(self):self.roll.close();self.roll.deleteLater();APP.processEvents()
    def anchor(self,x):return (x-KEY_W+self.roll.horizontalScrollBar().value())/self.roll.zoom*PPQ
    def test_wheel_keeps_pointer_time_and_vertical_pitch(self):
        r=self.roll;r.horizontalScrollBar().setValue(900);r.verticalScrollBar().setValue(300);x=KEY_W+230;tick=self.anchor(x);pitch=r.pitch_at(200)
        for delta in (120,120,-120):
            event=QWheelEvent(QPointF(x,200),QPointF(x,200),QPoint(),QPoint(0,delta),Qt.MouseButton.NoButton,Qt.KeyboardModifier.ControlModifier,Qt.ScrollPhase.NoScrollPhase,False)
            APP.sendEvent(r.viewport(),event);self.assertLessEqual(abs(r.x_at(tick)-x),1);self.assertEqual(r.pitch_at(200),pitch)
    def test_center_zoom_and_left_boundary(self):
        r=self.roll;r.horizontalScrollBar().setValue(700);x=KEY_W+(r.viewport().width()-KEY_W)/2;tick=self.anchor(x)
        r.zoom_at(1.2);self.assertLessEqual(abs(r.x_at(tick)-x),.6)
        r.horizontalScrollBar().setValue(3);r.zoom_at(.5,x);self.assertEqual(r.horizontalScrollBar().value(),0);self.assertEqual(r.x_at(0),KEY_W)
    def test_end_anchor_and_64th_editable_at_maximum(self):
        r=self.roll;x=KEY_W+200;r.horizontalScrollBar().setValue(round(r.project.end/PPQ*r.zoom-200));tick=self.anchor(x)
        r.zoom_at(.8,x);self.assertLessEqual(abs(r.x_at(tick)-x),.6)
        r.zoom_at(10000,x);self.assertEqual(r.zoom,2048);self.assertEqual(r.x_at(60)-r.x_at(0),128)
        self.assertAlmostEqual(r.x_at(40)-r.x_at(0),2048/24)
        r.zoom_at(.00001,x);self.assertEqual(r.zoom,32)

class MarkerTests(unittest.TestCase):
    def test_key_overwrites_later_keys_preserving_meters_and_notes(self):
        p=Project();p.set_markers([1],53,'Dorian',6,8);p.set_markers([4],55,'Aeolian',3,4);p.notes=[Note(0,240,60),Note(p.starts[6],120,65)]
        notes=copy.deepcopy(p.notes);meters=[(m.numerator,m.denominator) for m in p.measures];first=p.marker_value(0)
        p.propagate_marker(1,'key');self.assertEqual(p.notes,notes);self.assertEqual(meters,[(m.numerator,m.denominator) for m in p.measures]);self.assertEqual(p.marker_value(0),first)
        self.assertTrue(all(p.marker_value(i)[2:]==(53,'Dorian') for i in range(1,len(p.measures))))
    def test_meter_copies_denominator_retains_key_and_note_bar_offsets(self):
        p=Project();p.set_markers([1],53,'Dorian',6,8);p.set_markers([4],55,'Aeolian',3,4);p.notes=[Note(p.starts[6]+240,120,65)]
        keys=[p.marker_value(i)[2:] for i in range(len(p.measures))]
        p.propagate_marker(1,'meter');self.assertEqual(keys,[p.marker_value(i)[2:] for i in range(len(p.measures))]);self.assertEqual(p.notes[0].start,p.starts[6]+240)
        self.assertTrue(all((m.numerator,m.denominator)==(6,8) for m in p.measures[1:]));self.assertEqual(p.marker_value(0)[:2],(4,4))
    def test_last_bar_is_noop_and_invalid_input_rejected(self):
        p=Project();before=p.to_dict();p.propagate_marker(len(p.measures)-1,'key');self.assertEqual(p.to_dict(),before)
        with self.assertRaises(ValueError):p.propagate_marker(-1,'meter')
        with self.assertRaises(ValueError):p.propagate_marker(0,'unknown')

class LayoutTests(unittest.TestCase):
    def test_pitch_spacing_does_not_change_digits_rests_or_rap_size(self):
        from popscore.lyrics import apply_section
        p=Project();p.notes=[Note(0,240,60),Note(960,240,64),Note(1920,240,67)];apply_section(p,'我/64.爱/64你/64',3840)
        for style in ('spatial','compact'):
            p.notation['style']=style;sizes=[];heights=[]
            for gap in (4,8,15,32):
                p.notation['row_gap']=gap;layout=ScoreLayout(p);image=QImage(900,1273,QImage.Format.Format_RGB32);painter=QPainter(image);layout.draw(painter,0);painter.end()
                sizes.append(set(size for _,size in layout.glyph_sizes));heights.append(layout.systems[0].height)
            self.assertTrue(all(s==sizes[0] for s in sizes));self.assertEqual(heights,sorted(set(heights)))
            p.notation['font_size']=1;smaller=ScoreLayout(p);p.notation['font_size']=18;larger=ScoreLayout(p);self.assertGreater(larger.glyph_scale,smaller.glyph_scale)
            self.assertLessEqual(larger.glyph_scale*15,larger.max_font_size)
    def test_help_has_no_unbundled_local_references_or_retired_rules(self):
        from popscore.helpview import TOPICS
        text=' '.join(str(t) for t in TOPICS)+Path('README.md').read_text('utf-8')+Path('docs/REFERENCES.md').read_text('utf-8')
        for token in ('1_01_PS2','台湾谱（','编辑音乐时会停播','谱面高度控制'):self.assertNotIn(token,text)

class UITests(unittest.TestCase):
    def setUp(self):
        set_language('zh');self.w=MainWindow(Project());self.w.change_language('zh',False);self.w.resize(1280,960);self.w.show();self.w.autosave.stop();QTest.qWait(40)
    def tearDown(self):self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents()
    def test_shared_and_independent_chord_zoom_keep_anchor(self):
        w=self.w;w.open_harmony();r=w.harmony_window.roll;r.horizontalScrollBar().setValue(800)
        x=KEY_W+(r.viewport().width()-KEY_W)/2;tick=(x-KEY_W+r.horizontalScrollBar().value())/r.zoom*PPQ
        w.harmony_window.view_controls.zoom(12);self.assertAlmostEqual(w.roll.zoom,r.zoom);self.assertEqual(w.roll.horizontalScrollBar().value(),r.horizontalScrollBar().value());self.assertLessEqual(abs(r.x_at(tick)-x),.6)
        w.harmony_window.setFloating(True);QTest.qWait(20);old=w.roll.zoom;r.zoom_at(2);self.assertEqual(w.roll.zoom,old);self.assertNotEqual(r.zoom,old)
        w.set_timeline_sync(True,r);self.assertEqual(w.roll.zoom,r.zoom)
    def test_navigation_cancels_follow_without_changing_play_state(self):
        w=self.w;w.transport.close();w.transport.synth=Synth()
        for playing in (False,True):
            if playing:w.toggle_play()
            w.follow_playhead.setChecked(True);QTest.mouseClick(w.navigator,Qt.MouseButton.LeftButton,pos=QPoint(w.navigator.width()//3,18))
            self.assertFalse(w.follow_playhead.isChecked());self.assertEqual(w.transport.playing,playing)
            w.shared_scroll.setValue(0);w.follow_playhead.setChecked(True)
            nav=w.harmony_window.roll.navigator;nav.browse_to(nav.width()-1)
            self.assertFalse(w.follow_playhead.isChecked());self.assertEqual(w.transport.playing,playing)
    def test_single_bar_menu_propagation_and_undo_on_both_rolls(self):
        w=self.w;w.project.set_markers([0],53,'Dorian',6,8);w.refresh()
        for r in (w.roll,w.harmony_window.roll):
            r.horizontalScrollBar().setValue(0);r.selection=[w.project.starts[0:2]];menu=r.timeline_menu(QPoint(KEY_W+5,10));actions=[a for a in menu.actions() if '后续所有小节' in a.text()]
            self.assertEqual(len(actions),2);before=w.project.to_dict();actions[0].trigger();self.assertTrue(all(w.project.marker_value(i)[2:]==(53,'Dorian') for i in range(len(w.project.measures))));w.undo();self.assertEqual(w.project.to_dict(),before)
            r.selection=[[0,w.project.starts[2]]];self.assertFalse(any(a.isEnabled() for a in r.timeline_menu(QPoint(KEY_W+5,10)).actions() if '后续所有' in a.text()))
            r.selection=[w.project.starts[-2:]];r.horizontalScrollBar().setValue(round(w.project.starts[-2]/PPQ*r.zoom));last=r.timeline_menu(QPoint(KEY_W+3,10));self.assertFalse(any(a.isEnabled() for a in last.actions() if '后续所有' in a.text()))
    def test_meter_propagation_failure_is_atomic(self):
        w=self.w;w.project.change_meter(0,3,4);w.project.notes=[Note(w.project.starts[2]-240,240,60)];w.refresh();before=w.project.to_dict();history=len(w.undo_history)
        from PySide6.QtWidgets import QMessageBox
        with patch('popscore.app.QMessageBox.question',return_value=QMessageBox.StandardButton.No) as question:w.propagate_marker(0,'meter');self.assertTrue(question.called)
        self.assertEqual(w.project.to_dict(),before);self.assertEqual(len(w.undo_history),history)
    def test_reclick_toggles_bars_and_beats_shift_and_control_remain(self):
        w=self.w;w.switch_workspace('score');QTest.qWait(30);c=w.score_view.canvas
        def click(key,modifier=Qt.KeyboardModifier.NoModifier):
            pg,rect,_=next(item for item in c.selection_rects() if item[2]==key);x,y=c.page_origin(pg);pos=QPoint(round(x+rect.center().x()*c.scale),round(y+(rect.top()+10)*c.scale));QTest.mouseClick(c,Qt.MouseButton.LeftButton,modifier,pos)
        click(0);self.assertEqual(c.selected_bars,{0});click(0);self.assertFalse(c.selected_bars)
        click(2,Qt.KeyboardModifier.ShiftModifier);self.assertEqual(c.selected_bars,{0,1,2});click(1);self.assertEqual(c.selected_bars,{0,2})
        click(2,Qt.KeyboardModifier.ControlModifier);self.assertEqual(c.selected_bars,{0})
        c.set_selection_unit('beat');key=c.selection_rects()[0][2];click(key);self.assertEqual(c.selected_beats,{key});click(key);self.assertFalse(c.selected_beats)
    def test_score_top_alignment_survives_resize_and_language_switch(self):
        w=self.w;w.switch_workspace('score')
        for key in w.score_pages:w.set_score_panel_visible(key,False)
        QTest.qWait(30);self.assertFalse(hasattr(w,'score_height'))
        for width,height in ((1280,800),(680,1000)):
            w.resize(width,height);QTest.qWait(30);self.assertEqual(w.score_view.y(),0);self.assertGreaterEqual(w.score_view.height(),w.score_splitter.height()-4)
        w.change_language('en',False);self.assertFalse(hasattr(w,'score_height'));self.assertTrue(w.score_view.alignment()&Qt.AlignmentFlag.AlignTop)

    def test_pointer_leave_during_language_rebuild_is_ignored(self):
        w=self.w;pane=w.harmony_window
        try:
            w.workspace_ready=False;w.harmony_window=None;w.roll.chordHover.emit('');w.roll.chordSelection.emit(set())
        finally:w.harmony_window=pane;w.workspace_ready=True
        w.chord_hover('');self.assertEqual(w.harmony_window.roll.hovered_chord,'')

if __name__=='__main__':unittest.main()
