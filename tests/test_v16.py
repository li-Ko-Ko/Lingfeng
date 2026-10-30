"""Continuous transport, browsing-only navigation and explicit seek surfaces."""
import os,copy,time,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent,QContextMenuEvent
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from lingfeng.music.model import Project, Note, Chord, PPQ
from lingfeng.ui.main_window import MainWindow
from lingfeng.audio.transport import Transport
from lingfeng.ui.piano_roll import KEY_W
from lingfeng.platform.i18n import set_language
from tests.test_v14 import Synth

APP=QApplication.instance() or QApplication([])

def until(predicate,timeout=1.5):
    limit=time.perf_counter()+timeout
    while not predicate() and time.perf_counter()<limit:time.sleep(.003)
    return predicate()

class LoopTests(unittest.TestCase):
    def setUp(self):
        self.p=Project();self.p.bpm=300;self.p.notes=[Note(0,2880,60,85),Note(1200,240,67,79)]
        self.t=Transport();self.t.synth=Synth()
    def tearDown(self):self.t.close();APP.processEvents()
    def test_disable_loop_keeps_clock_sustain_and_plays_events_beyond_end(self):
        p,t=self.p,self.t;t.play(p,0,960,True);self.assertTrue(until(lambda:(0x90,60,85) in t.synth.events));time.sleep(.025)
        worker=t.thread;clock=t.start_time;tick=t.position();t.synth.events.clear();t.set_loop(p,False,0,960)
        self.assertTrue(until(lambda:t.position()>1450));self.assertIs(t.thread,worker);self.assertEqual(t.start_time,clock);self.assertGreater(t.position(),tick)
        self.assertEqual(t.end_tick,p.end);self.assertFalse(t.loop);self.assertIn((0x90,67,79),t.synth.events)
        self.assertFalse(any(e[0]==0xB0 or e[:2] in ((0x80,60),(0x90,60)) for e in t.synth.events));self.assertTrue(worker.is_alive())
    def test_disable_after_wrap_continues_from_current_iteration(self):
        p,t=self.p,self.t;t.play(p,480,960,True,loop_start=480)
        self.assertTrue(until(lambda:t.synth.events.count((0x90,60,85))>=2));clock=t.start_time;worker=t.thread
        t.set_loop(p,False,480,960);self.assertTrue(until(lambda:t.position()>1200));self.assertEqual(t.start_time,clock);self.assertIs(t.thread,worker)
    def test_edit_and_tempo_revision_cannot_restore_cancelled_loop(self):
        p,t=self.p,self.t;t.play(p,0,960,True);t.set_loop(p,False,0,960)
        p.bpm=250;p.notes.append(Note(1800,240,69,90));p.insert_measure(len(p.measures));t.revise(p)
        self.assertTrue(until(lambda:t.end_tick==p.end and t.seconds_per_tick==60/250/PPQ));self.assertFalse(t.loop)
        self.assertTrue(until(lambda:(0x90,69,90) in t.synth.events));self.assertGreater(t.position(),960)
    def test_enable_and_cancel_loop_without_restarting(self):
        p,t=self.p,self.t;t.play(p);worker=t.thread;t.set_loop(p,True,0,480)
        self.assertTrue(until(lambda:t.synth.events.count((0x90,60,85))>=2));self.assertIs(t.thread,worker);self.assertTrue(t.loop)
        t.set_loop(p,False);self.assertTrue(until(lambda:t.position()>800));self.assertIs(t.thread,worker)
    def test_enable_after_selection_does_not_jump_back(self):
        p,t=self.p,self.t;t.play(p,1920);worker=t.thread;t.set_loop(p,True,0,960);time.sleep(.02)
        self.assertFalse(t.loop);self.assertGreaterEqual(t.position(),1920);self.assertIs(t.thread,worker)

class InteractionTests(unittest.TestCase):
    def setUp(self):
        set_language('zh');p=Project();p.notes=[Note(0,480,60),Note(1920,480,64)];p.chords=[Chord(0,1920,48),Chord(3840,1920,53)]
        self.w=MainWindow(p);self.w.change_language('zh',False);self.w.resize(1260,920);self.w.show();self.w.timer.stop();self.w.autosave.stop();self.w.open_harmony();QTest.qWait(25)
        self.w.transport.close();self.w.transport.synth=Synth();self.w.seek(960)
        self.warnings=[];self.warning_patch=patch('lingfeng.ui.main_window.QMessageBox.warning',side_effect=lambda *args:self.warnings.append(args[1:]) or QMessageBox.StandardButton.Ok);self.warning_patch.start()
    def tearDown(self):
        self.warning_patch.stop();self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.assertFalse(self.warnings)
    def point(self,r,tick=1200,pitch=67):
        r.center_pitch(pitch);APP.processEvents()
        return QPoint(round(r.x_at(tick)+5),round(r.y_at(pitch)+r.row_height/2))
    def test_navigation_drags_only_view_in_playing_and_paused_states(self):
        w=self.w
        for playing in (False,True):
            if playing:w.toggle_play()
            worker=w.transport.thread;clock=w.transport.start_time;anchor=w.play_anchor;head=w.playhead;cursor=w.roll.cursor_tick
            w.follow_playhead.setChecked(True);nav=w.navigator
            QTest.mousePress(nav,Qt.MouseButton.LeftButton,pos=QPoint(nav.width()//3,17))
            QTest.mouseMove(nav,QPoint(nav.width()*2//3,17));QTest.mouseRelease(nav,Qt.MouseButton.LeftButton,pos=QPoint(nav.width()*2//3,17))
            self.assertGreater(w.shared_scroll.value(),0);self.assertFalse(w.follow_playhead.isChecked());self.assertEqual(w.play_anchor,anchor);self.assertEqual(w.playhead,head);self.assertEqual(w.roll.cursor_tick,cursor)
            self.assertIs(w.transport.thread,worker);self.assertEqual(w.transport.start_time,clock);self.assertEqual(w.transport.playing,playing)
            if playing:
                before=w.transport.position();time.sleep(.015);w.playback_tick();self.assertGreater(w.playhead,before);self.assertEqual(w.play_anchor,anchor)
    def test_grid_keyboard_and_chord_clicks_do_not_seek_or_restart(self):
        w=self.w;w.toggle_play();worker=w.transport.thread;clock=w.transport.start_time;anchor=w.play_anchor;head=w.playhead
        for r in (w.roll,w.harmony_window.roll):
            r.center_pitch(64);APP.processEvents();r.tool='smart'
            for pos in (self.point(r),self.point(r,2400)+QPoint(8,0),QPoint(round(r.x_at(2400))+8,r.ruler_height+44),QPoint(20,round(r.y_at(64)+10))):
                QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,pos=pos)
            QTest.mouseDClick(r.viewport(),Qt.MouseButton.LeftButton,pos=self.point(r,1200,68)+QPoint(8,0)+QPoint(8,0)+QPoint(8,0));APP.processEvents()
            r.tool='draw';QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,pos=self.point(r,1440,70)+QPoint(8,0)+QPoint(8,0)+QPoint(8,0));APP.processEvents()
            for tick in (480,2880):QTest.mouseClick(w.chord_lane,Qt.MouseButton.LeftButton,pos=QPoint(round(w.chord_lane.x_at(tick)),24))
            with patch.object(w.chord_lane,'context_menu'):
                pos=QPoint(round(w.chord_lane.x_at(2880)),20);event=QContextMenuEvent(QContextMenuEvent.Reason.Mouse,pos,w.chord_lane.mapToGlobal(pos));w.chord_lane.contextMenuEvent(event)
            self.assertEqual((w.playhead,w.play_anchor),(head,anchor));self.assertIs(w.transport.thread,worker);self.assertEqual(w.transport.start_time,clock);self.assertTrue(w.transport.playing)
    def test_only_real_ruler_in_chord_roll_controls_playhead(self):
        w=self.w;w.harmony_window.setFloating(True);QTest.qWait(25);r=w.harmony_window.roll;head=w.playhead
        # Empty structure-header space is not a time ruler.
        pos=QPoint(round(r.x_at(2880)),r.ruler_height-10);QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,pos=pos);self.assertEqual(w.playhead,head)
        QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(round(r.x_at(2880)),r.bar_ruler_height+12));self.assertEqual(w.playhead,2880);self.assertFalse(w.transport.playing)
    def test_timeline_and_score_seek_preserve_play_state(self):
        w=self.w
        for playing in (False,True):
            w.switch_workspace('compose')
            if playing:w.toggle_play()
            QTest.mouseClick(w.timeline,Qt.MouseButton.LeftButton,pos=QPoint(round(w.timeline.x_at(1920)),w.timeline.roll.bar_ruler_height+12));self.assertEqual(w.play_anchor,1920);self.assertEqual(w.transport.playing,playing)
            w.switch_workspace('score');w.open_score_roll('melody',0);QTest.qWait(20);r=w.roll
            QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(round(r.x_at(2400)),r.bar_ruler_height+12));self.assertEqual(w.play_anchor,2400);self.assertEqual(w.transport.playing,playing)
            head=w.playhead;QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,pos=self.point(r,2880)+QPoint(8,0));self.assertEqual(w.playhead,head)
            canvas=w.score_view.canvas;canvas.grab();pg,rect,_=canvas.layout.hit_bars[0];x,y=canvas.page_origin(pg);pos=QPoint(round(x+rect.center().x()*canvas.scale),round(y+(rect.top()+10)*canvas.scale));target=canvas.timeline_at(pos)[1]
            QTest.mouseClick(canvas,Qt.MouseButton.LeftButton,pos=pos);self.assertEqual(w.play_anchor,target);self.assertEqual(w.transport.playing,playing)
    def test_main_timeline_double_click_plays_and_body_double_click_does_not(self):
        w=self.w;w.roll.tool='smart';w.roll.center_pitch(66);QTest.mouseDClick(w.roll.viewport(),Qt.MouseButton.LeftButton,pos=self.point(w.roll,1440,66));self.assertFalse(w.transport.playing)
        QTest.mouseDClick(w.timeline,Qt.MouseButton.LeftButton,pos=QPoint(round(w.timeline.x_at(2880)),w.timeline.roll.bar_ruler_height+12));self.assertTrue(w.transport.playing);self.assertEqual(w.play_anchor,2880)
    def test_timeline_wheel_anchors_and_syncs_both_rolls(self):
        w=self.w
        for floating in (False,True):
            w.melody_window.setFloating(floating);w.set_timeline_sync(True,w.roll if floating else w.harmony_window.roll);QTest.qWait(25);r=w.timeline.roll;r.horizontalScrollBar().setValue(600)
            x=350;local=x-w.timeline.offset();tick=(local-KEY_W+r.horizontalScrollBar().value())/r.zoom*PPQ;zoom=r.zoom;head=w.playhead
            event=QWheelEvent(QPointF(x,16),QPointF(x,16),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.ControlModifier,Qt.ScrollPhase.NoScrollPhase,False)
            APP.sendEvent(w.timeline,event);self.assertAlmostEqual(r.zoom,zoom*1.2);self.assertLessEqual(abs(w.timeline.x_at(tick)-x),1)
            self.assertEqual(w.roll.zoom,w.harmony_window.roll.zoom);self.assertEqual(w.roll.horizontalScrollBar().value(),w.harmony_window.roll.horizontalScrollBar().value());self.assertEqual(w.playhead,head)
    def test_loop_checkbox_cancels_live_schedule_without_moving_anchor(self):
        w=self.w;w.project.bpm=300;w.set_loop_range((0,960));w.seek(0);w.toggle_play();worker=w.transport.thread;anchor=w.play_anchor
        w.loop.setChecked(False);self.assertTrue(until(lambda:w.transport.position()>1100));self.assertIs(w.transport.thread,worker);self.assertEqual(w.play_anchor,anchor);self.assertTrue(w.transport.playing)
    def test_language_rebuild_does_not_reconfigure_active_loop(self):
        w=self.w;w.set_loop_range((3840,7680));w.seek(3840);w.toggle_play();bounds=w.transport.requested_bounds;worker=w.transport.thread
        w.change_language('en',False);self.assertEqual(w.transport.requested_bounds,bounds);self.assertIs(w.transport.thread,worker);self.assertTrue(w.loop.isChecked())
    def test_chord_root_degrees_use_start_key_and_raw_hit_near_boundary(self):
        w=self.w;p=w.project;p.set_context([[0,960]],tonic=53,mode='Dorian');p.set_context([[960,p.end]],tonic=55,mode='Aeolian');p.chords=[Chord(0,1920,53),Chord(1920,1920,55)];w.refresh();w.seek(2400)
        for r in (w.roll,w.harmony_window.roll):
            menu=r.lane.context_menu(QPoint(round(r.lane.x_at(1890)),18));actions=menu.root_menu.actions();self.assertEqual(len(actions),12)
            self.assertEqual(actions[0].text(),'1 · F');self.assertEqual(actions[7].text(),'5 · C');self.assertEqual(actions[1].text(),'#1 · F#');self.assertEqual(actions[1].data(),6)
            self.assertTrue(actions[0].isChecked());head=w.playhead;actions[1].trigger();self.assertEqual(w.project.chords[0].root%12,6);self.assertEqual(w.project.chords[1].root%12,7);self.assertEqual(w.playhead,head);w.undo()

if __name__=='__main__':unittest.main()
