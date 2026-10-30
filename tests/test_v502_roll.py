"""Roll browsing must not be pulled back to the left by a visible score."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint,QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QAbstractSlider
from lingfeng.ui.main_window import MainWindow
from lingfeng.music.model import PPQ
from lingfeng.ui.piano_roll import KEY_W
from tests.test_v501_follow import song

APP=QApplication.instance() or QApplication([])


class RollBrowseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='tmp');self.addCleanup(self.temp.cleanup)
        self.paths=patch('lingfeng.ui.main_window.user_data_dir',return_value=Path(self.temp.name));self.paths.start();self.addCleanup(self.paths.stop)
        self.saving=patch.object(MainWindow,'save_preferences');self.saving.start();self.addCleanup(self.saving.stop)
        self.errors=[];self.hook=patch.object(sys,'excepthook',lambda kind,value,tb:self.errors.append(str(value)));self.hook.start();self.addCleanup(self.hook.stop)
        self.w=MainWindow(song());self.w.change_language('zh',False);self.w.timer.stop();self.w.autosave.stop()
        self.w.resize(1240,900);self.w.show();APP.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()
        self.assertEqual(self.errors,[])
    def score(self,key='harmony'):
        w=self.w;w.switch_workspace('score');w.show_score_panel(key);APP.processEvents()
        w.playhead=3*PPQ;w.show_cursor(w.playhead);w.score_view.locate_tick(w.playhead)
        return w.roll if key=='melody' else w.harmony_window.roll
    def right_of_cursor(self,roll):
        return round(self.w.playhead/PPQ*roll.zoom)+40

    def test_score_docked_roll_browsing_cancels_even_while_score_shows_cursor(self):
        for key in ('melody','harmony'):
            with self.subTest(roll=key):
                r=self.score(key);w=self.w;w.follow_playhead.setChecked(True)
                self.assertTrue(w.score_view.tick_visible(w.playhead))
                r.horizontalScrollBar().setValue(self.right_of_cursor(r));r.navigationRequested.emit()
                before=r.horizontalScrollBar().value();self.assertLess(r.x_at(w.playhead),KEY_W)
                self.assertFalse(w.follow_playhead.isChecked())
                self.assertFalse(w.melody_transport.follow.isChecked());self.assertFalse(w.harmony_window.transport_controls.follow.isChecked())
                w.follow_views(w.playhead);self.assertEqual(r.horizontalScrollBar().value(),before)

    def test_small_score_roll_navigation_keeps_manual_offset_without_snap(self):
        r=self.score();w=self.w;r.horizontalScrollBar().setValue(15);w.follow_playhead.setChecked(True);r.navigationRequested.emit()
        self.assertTrue(w.follow_playhead.isChecked());self.assertTrue(r.tick_visible(w.playhead))
        w.follow_views(w.playhead);self.assertEqual(r.horizontalScrollBar().value(),15)

    def test_actual_roll_scrollbar_drag_does_not_snap_cursor_to_left(self):
        r=self.score();w=self.w;bar=r.horizontalScrollBar();w.follow_playhead.setChecked(True)
        bar.setSliderDown(True)
        try:bar.setSliderPosition(self.right_of_cursor(r))
        finally:bar.setSliderDown(False)
        self.assertFalse(w.follow_playhead.isChecked());before=bar.value()
        for _ in range(3):w.follow_views(w.playhead);APP.processEvents()
        self.assertEqual(bar.value(),before);self.assertLess(r.x_at(w.playhead),KEY_W)

    def test_middle_pan_in_score_roll_leaves_cursor_offscreen_without_pullback(self):
        r=self.score();w=self.w;w.follow_playhead.setChecked(True)
        viewport=r.viewport();point=QPoint(500,max(r.ruler_height+10,viewport.height()//2))
        QTest.mousePress(viewport,Qt.MouseButton.MiddleButton,pos=point)
        QTest.mouseMove(viewport,point-QPoint(450,0));QTest.mouseRelease(viewport,Qt.MouseButton.MiddleButton,pos=point-QPoint(450,0))
        self.assertFalse(r.tick_visible(w.playhead));self.assertFalse(w.follow_playhead.isChecked())
        before=r.horizontalScrollBar().value();w.follow_views(w.playhead)
        self.assertEqual(r.horizontalScrollBar().value(),before)

    def test_running_clock_is_used_when_score_cursor_paint_is_one_frame_old(self):
        r=self.score();w=self.w;w.playhead=0;tick=3*PPQ
        with patch.object(w.transport,'playing',True),patch.object(w.transport,'position',return_value=tick):
            r.horizontalScrollBar().setValue(round(tick/PPQ*r.zoom)+40);w.follow_playhead.setChecked(True);r.navigationRequested.emit()
            self.assertFalse(w.follow_playhead.isChecked());before=r.horizontalScrollBar().value()
            w.follow_views(tick);self.assertEqual(r.horizontalScrollBar().value(),before)

    def test_score_and_compose_cancel_at_the_same_roll_boundary(self):
        w=self.w;states=[]
        for workspace in ('compose','score'):
            w.switch_workspace(workspace)
            if workspace=='score':w.show_score_panel('melody')
            APP.processEvents();r=w.roll;w.playhead=3*PPQ;w.show_cursor(w.playhead)
            w.follow_playhead.setChecked(True);r.horizontalScrollBar().setValue(self.right_of_cursor(r));r.navigationRequested.emit()
            states.append((w.follow_playhead.isChecked(),r.tick_visible(w.playhead)))
        self.assertEqual(states,[(False,False),(False,False)])

    def test_unsynced_score_float_browse_keeps_main_follow(self):
        r=self.score();w=self.w;w.toggle_score_panel_floating('harmony');APP.processEvents();w.harmony_window.sync.setChecked(False)
        w.follow_playhead.setChecked(True);w.harmony_window.transport_controls.follow.setChecked(True)
        r.horizontalScrollBar().setValue(self.right_of_cursor(r));r.navigationRequested.emit()
        self.assertTrue(w.follow_playhead.isChecked());self.assertFalse(w.harmony_window.transport_controls.follow.isChecked())
        before=r.horizontalScrollBar().value();w.follow_views(w.playhead);self.assertEqual(r.horizontalScrollBar().value(),before)

    def test_synced_score_float_browse_cancels_shared_follow(self):
        r=self.score();w=self.w;w.toggle_score_panel_floating('harmony');APP.processEvents();w.harmony_window.sync.setChecked(True)
        w.follow_playhead.setChecked(True);r.horizontalScrollBar().setValue(self.right_of_cursor(r));r.navigationRequested.emit()
        self.assertFalse(w.follow_playhead.isChecked());self.assertFalse(w.harmony_window.transport_controls.follow.isChecked())
        before=r.horizontalScrollBar().value();w.follow_views(w.playhead);self.assertEqual(r.horizontalScrollBar().value(),before)


if __name__=='__main__':unittest.main()
