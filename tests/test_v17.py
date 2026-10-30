"""Independent main/floating time views, manual browsing and pitch-centered sizing."""
import os,sys,unittest,copy
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication,QAbstractSlider,QStyleOptionSlider,QStyle
from PySide6.QtTest import QTest
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.piano_roll import PianoRoll, KEY_W
from lingfeng.music.model import Project, Note, Chord, PPQ, demo_project
from tests.test_v14 import Synth

APP=QApplication.instance() or QApplication([])

class PitchAnchorTests(unittest.TestCase):
    def test_centered_note_stays_centered_in_both_roles_and_ruler_sizes(self):
        for role in ('melody','harmony'):
            r=PianoRoll(Project(),role=role);r.resize(1000,650);r.show();APP.processEvents()
            try:
                for detailed in (False,True):
                    r.set_panel('ruler',detailed);APP.processEvents();r.center_pitch(60)
                    for height in (35,10,48,22,32)*8:
                        r.set_row_height(height)
                        center=r.ruler_height+(r.viewport().height()-r.ruler_height)/2
                        self.assertLessEqual(abs(r.y_at(60)+height/2-center),.5)
            finally:r.close();r.deleteLater();APP.processEvents()
    def test_fractional_row_anchor_survives_full_and_compact_zoom(self):
        p=Project();p.notes=[Note(0,480,pitch) for pitch in range(30,100,2)]
        r=PianoRoll(p,role='harmony');r.resize(900,500);r.show();APP.processEvents()
        try:
            for compact in (False,True):
                r.set_compact(compact);r.verticalScrollBar().setValue(319);middle=(r.viewport().height()-r.ruler_height)/2
                anchor=(r.verticalScrollBar().value()+middle)/r.row_height
                r.set_row_height(40);self.assertLessEqual(abs((r.verticalScrollBar().value()+middle)/r.row_height-anchor),.02)
        finally:r.close();r.deleteLater();APP.processEvents()

class ViewTests(unittest.TestCase):
    def setUp(self):
        self.errors=[];self.hook=patch.object(sys,'excepthook',lambda typ,value,tb:self.errors.append(str(value)));self.hook.start()
        self.w=MainWindow(demo_project());self.w.change_language('zh',False);self.w.resize(1280,960);self.w.show();self.w.open_harmony();QTest.qWait(40);self.w.timer.stop();self.w.autosave.stop();self.w.transport.close();self.w.transport.synth=Synth()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.hook.stop();self.assertFalse(self.errors)
    def float_both(self):
        w=self.w;w.melody_window.setFloating(True);w.harmony_window.setFloating(True);QTest.qWait(45);return w.roll,w.harmony_window.roll
    def scroll(self,r):return r.horizontalScrollBar().value()
    def drag_thumb(self,bar):
        opt=QStyleOptionSlider();bar.initStyleOption(opt);rect=bar.style().subControlRect(QStyle.ComplexControl.CC_ScrollBar,opt,QStyle.SubControl.SC_ScrollBarSlider,bar);pos=rect.center()
        QTest.mousePress(bar,Qt.MouseButton.LeftButton,pos=pos);QTest.mouseMove(bar,pos+QPoint(45,0));QTest.mouseRelease(bar,Qt.MouseButton.LeftButton,pos=pos+QPoint(45,0));APP.processEvents()
    def test_main_and_each_floating_scrollbar_cancel_only_local_follow(self):
        w=self.w;r,h=self.float_both();w.seek(960)
        for playing in (False,True):
            if playing:w.toggle_play()
            for bar,follow in ((w.shared_scroll,w.follow_playhead),(r.horizontalScrollBar(),w.melody_transport.follow),(h.horizontalScrollBar(),w.harmony_window.transport_controls.follow)):
                checks=[w.follow_playhead,w.melody_transport.follow,w.harmony_window.transport_controls.follow]
                for check in checks:check.setChecked(True)
                worker=w.transport.thread;clock=w.transport.start_time;head=w.playhead;anchor=w.play_anchor
                self.drag_thumb(bar);self.assertFalse(follow.isChecked());self.assertTrue(all(c.isChecked() for c in checks if c is not follow))
                self.assertEqual((w.playhead,w.play_anchor),(head,anchor));self.assertIs(w.transport.thread,worker);self.assertEqual(w.transport.start_time,clock);self.assertEqual(w.transport.playing,playing)
    def test_programmatic_follow_scrolling_never_cancels_follow(self):
        w=self.w;w.follow_playhead.setChecked(True);w.shared_scroll.setValue(300);self.assertTrue(w.follow_playhead.isChecked())
        w.roll.ensure_tick(25000);self.assertTrue(w.follow_playhead.isChecked())
        w.playhead=25000;w.show_cursor(w.playhead)
        w.shared_scroll.triggerAction(QAbstractSlider.SliderAction.SliderSingleStepAdd);self.assertTrue(w.follow_playhead.isChecked())
        w.shared_scroll.triggerAction(QAbstractSlider.SliderAction.SliderToMaximum);self.assertFalse(w.follow_playhead.isChecked())
    def test_main_time_view_remains_independent_when_both_rolls_float(self):
        w=self.w;r,h=self.float_both();self.assertIs(w.timeline.roll,w.main_roll);self.assertIs(w.navigator.editor,w.main_roll);self.assertIs(w.chord_lane.editor,w.main_roll)
        w.shared_scroll.setValue(600);self.assertEqual(self.scroll(w.main_roll),600);self.assertEqual((self.scroll(r),self.scroll(h)),(0,0))
        r.horizontalScrollBar().setValue(300);h.horizontalScrollBar().setValue(900);self.assertEqual(self.scroll(w.main_roll),600)
        old=(r.zoom,h.zoom);x=350;tick=(x-KEY_W+self.scroll(w.main_roll))/w.main_roll.zoom*PPQ
        event=QWheelEvent(QPointF(x,14),QPointF(x,14),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.ControlModifier,Qt.ScrollPhase.NoScrollPhase,False)
        APP.sendEvent(w.timeline,event);self.assertEqual((r.zoom,h.zoom),old);self.assertLessEqual(abs(w.timeline.x_at(tick)-x),1)
        pos=QPoint(round(w.timeline.x_at(tick)),w.timeline.roll.bar_ruler_height+12);QTest.mouseClick(w.timeline,Qt.MouseButton.LeftButton,pos=pos);self.assertEqual(w.playhead,w.main_roll.snap_time(w.main_roll.tick_at(pos.x())))
    def test_sync_checkboxes_link_individually_to_main_and_redocking_adopts_main(self):
        w=self.w;r,h=self.float_both();w.shared_scroll.setValue(600);w.melody_sync.setChecked(True)
        self.assertFalse(w.harmony_window.sync.isChecked());self.assertEqual(self.scroll(r),600);self.assertEqual(self.scroll(h),0)
        r.zoom_at(1.5);self.assertEqual(w.main_roll.zoom,r.zoom);self.assertNotEqual(h.zoom,r.zoom)
        r.horizontalScrollBar().setValue(700);self.assertEqual(w.shared_scroll.value(),700);self.assertEqual(self.scroll(h),0)
        w.harmony_window.sync.setChecked(True);self.assertEqual(h.zoom,r.zoom);self.assertEqual(self.scroll(h),700)
        w.melody_sync.setChecked(False);w.shared_scroll.setValue(1000);self.assertEqual(self.scroll(r),700);self.assertEqual(self.scroll(h),1000)
        w.melody_window.setFloating(False);QTest.qWait(30);self.assertEqual(self.scroll(r),1000);self.assertFalse(w.melody_sync.isChecked())
        r.horizontalScrollBar().setValue(800);self.assertEqual(w.shared_scroll.value(),800);self.assertEqual(self.scroll(h),800)
    def test_follow_is_local_when_timeline_sync_is_disabled(self):
        w=self.w;r,h=self.float_both();w.melody_sync.setChecked(False);w.harmony_window.sync.setChecked(False)
        for chosen in ('main','melody','harmony'):
            r.horizontalScrollBar().setValue(0);h.horizontalScrollBar().setValue(0)
            w.shared_scroll.setValue(0);w.sync_time_views(w.main_roll);w.follow_playhead.setChecked(chosen=='main');w.melody_transport.follow.setChecked(chosen=='melody');w.harmony_window.transport_controls.follow.setChecked(chosen=='harmony')
            w.follow_views(25000);values={'main':self.scroll(w.main_roll),'melody':self.scroll(r),'harmony':self.scroll(h)}
            self.assertGreater(values[chosen],0);self.assertTrue(all(value==0 for key,value in values.items() if key!=chosen),values)
        # A vertical change is not a request to synchronize horizontal views.
        before=self.scroll(w.main_roll);h.set_row_height(32);self.assertEqual(self.scroll(w.main_roll),before)
    def test_main_follow_moves_docked_roll_but_not_floating_roll(self):
        w=self.w;w.melody_window.setFloating(True);QTest.qWait(30);w.melody_sync.setChecked(False);w.melody_transport.follow.setChecked(False);w.follow_playhead.setChecked(True)
        w.follow_views(25000);self.assertEqual(self.scroll(w.main_roll),self.scroll(w.harmony_window.roll));self.assertGreater(self.scroll(w.main_roll),0);self.assertEqual(self.scroll(w.roll),0)
    def test_independent_ruler_details_do_not_change_main_timeline(self):
        w=self.w;r,h=self.float_both();w.view_controls.panel_actions['ruler'].setChecked(False)
        self.assertEqual(r.timeline_height,52);self.assertEqual(w.timeline.height(),72)
        w.harmony_window.view_controls.panel_actions['ruler'].setChecked(False);self.assertEqual(w.timeline.height(),72)
        w.harmony_window.setFloating(False);APP.processEvents();self.assertEqual(w.timeline.height(),52)
        w.view_controls.panel_actions['ruler'].setChecked(True);self.assertEqual(w.timeline.height(),52)
    def test_linked_manual_browsing_disables_follow_for_affected_views(self):
        w=self.w;r,h=self.float_both();w.melody_sync.setChecked(True);w.harmony_window.sync.setChecked(False)
        self.drag_thumb(r.horizontalScrollBar());self.assertFalse(w.follow_playhead.isChecked());self.assertFalse(w.melody_transport.follow.isChecked());self.assertTrue(w.harmony_window.transport_controls.follow.isChecked());self.assertEqual(self.scroll(r),self.scroll(w.main_roll));self.assertEqual(self.scroll(h),0)
    def test_each_floating_transport_has_shared_play_loop_tempo_and_local_follow(self):
        w=self.w;self.float_both();m=w.melody_transport;h=w.harmony_window.transport_controls
        for controls in (m,h):
            self.assertTrue(all(c.isVisible() for c in (controls.play,controls.replay,controls.loop,controls.follow,controls.bpm)))
        m.bpm.setValue(120);self.assertEqual((w.project.bpm,w.bpm.value(),h.bpm.value()),(120,120,120));w.undo();self.assertEqual(h.bpm.value(),w.project.bpm)
        m.loop.setChecked(True);self.assertTrue(w.loop.isChecked());self.assertTrue(h.loop.isChecked());h.loop.setChecked(False);self.assertFalse(m.loop.isChecked())
        QTest.mouseClick(m.play,Qt.MouseButton.LeftButton);self.assertTrue(w.transport.playing);self.assertEqual((w.play_button.kind,m.play.kind,h.play.kind),('pause','pause','pause'))
        QTest.mouseClick(h.play,Qt.MouseButton.LeftButton);self.assertFalse(w.transport.playing);QTest.mouseClick(m.replay,Qt.MouseButton.LeftButton);self.assertFalse(w.transport.playing)
        m.follow.setChecked(False);self.assertTrue(w.follow_playhead.isChecked());self.assertTrue(h.follow.isChecked())
    def test_shared_key_height_preserves_each_roll_center_pitch(self):
        w=self.w;r=w.roll;h=w.harmony_window.roll;r.center_pitch(70);h.center_pitch(50)
        w.view_controls.height.setValue(36)
        for roll,pitch in ((r,70),(h,50)):
            self.assertEqual(roll.row_height,36);middle=roll.ruler_height+(roll.viewport().height()-roll.ruler_height)/2;self.assertLessEqual(abs(roll.y_at(pitch)+18-middle),1)
    def test_language_rebuild_preserves_all_time_views_sync_and_follow(self):
        w=self.w;r,h=self.float_both();w.shared_scroll.setValue(200);w.melody_sync.setChecked(True);w.melody_transport.follow.setChecked(False);w.harmony_window.transport_controls.follow.setChecked(True)
        h.zoom_at(1.5);h.horizontalScrollBar().setValue(700);w.harmony_window.view_controls.height.setValue(37);w.auto_follow=True;r.ensure_tick(25000);w.auto_follow=False
        expected=[(a.zoom,self.scroll(a)) for a in (w.main_roll,r,h)]
        pitches=[a.pitch_at(a.ruler_height+(a.viewport().height()-a.ruler_height)/2) for a in (r,h)]
        w.change_language('en',False);QTest.qWait(60);self.assertEqual([(a.zoom,self.scroll(a)) for a in (w.main_roll,w.roll,w.harmony_window.roll)],expected)
        self.assertTrue(w.melody_sync.isChecked());self.assertFalse(w.harmony_window.sync.isChecked());self.assertFalse(w.melody_transport.follow.isChecked());self.assertTrue(w.harmony_window.transport_controls.follow.isChecked());self.assertIs(w.timeline.roll,w.main_roll)
        self.assertEqual(w.harmony_window.roll.row_height,37);self.assertEqual(w.harmony_window.view_controls.height.value(),37)
        self.assertEqual([a.pitch_at(a.ruler_height+(a.viewport().height()-a.ruler_height)/2) for a in (w.roll,w.harmony_window.roll)],pitches)

if __name__=='__main__':unittest.main()
