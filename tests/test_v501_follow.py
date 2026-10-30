"""Per-surface following across main pages, score tabs and floating rolls."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QEvent,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QAbstractSlider
from popscore.app import MainWindow
from popscore.editor import KEY_W
from popscore.model import Project,Note,Measure,Context,PPQ

APP=QApplication.instance() or QApplication([])


def song():
    p=Project(measures=[Measure() for _ in range(40)],contexts=[Context(0,40*3840)])
    p.notes=[Note(i*3840,480,60+i%5) for i in range(40)]
    return p


class FollowingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='tmp');self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.prefs=patch('popscore.app.user_data_dir',return_value=self.folder);self.prefs.start();self.addCleanup(self.prefs.stop)
        self.save=patch.object(MainWindow,'save_preferences');self.save.start();self.addCleanup(self.save.stop)
        self.errors=[];self.hook=patch.object(sys,'excepthook',lambda typ,value,tb:self.errors.append(str(value)));self.hook.start();self.addCleanup(self.hook.stop)
        self.w=MainWindow(song());self.w.change_language('zh',False)
        self.w.timer.stop();self.w.autosave.stop();self.w.resize(1240,900);self.w.show();self.settle()

    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater()
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()
        self.assertEqual(self.errors,[])

    def settle(self):
        APP.processEvents();QTest.qWait(5);APP.processEvents()

    def cursor(self,tick):
        self.w.playhead=int(tick);self.w.show_cursor(int(tick))

    def score(self,key='melody'):
        w=self.w;w.switch_workspace('score');w.show_score_panel(key);self.settle()
        return w.roll if key=='melody' else w.harmony_window.roll

    def float_score(self,key='harmony'):
        self.score(key);self.w.toggle_score_panel_floating(key);self.settle()
        return self.w.roll if key=='melody' else self.w.harmony_window.roll

    def test_compose_docked_follow_options_always_share_main_state(self):
        w=self.w;w.open_harmony();self.settle()
        self.assertFalse(w.melody_sync.isChecked());self.assertFalse(w.harmony_window.sync.isChecked())
        w.follow_playhead.setChecked(False)
        self.assertFalse(w.melody_transport.follow.isChecked());self.assertFalse(w.harmony_window.transport_controls.follow.isChecked())
        w.harmony_window.transport_controls.follow.setChecked(True)
        self.assertTrue(w.follow_playhead.isChecked());self.assertTrue(w.melody_transport.follow.isChecked())

    def test_score_docked_follow_options_share_main_without_optional_sync(self):
        self.score('harmony');w=self.w
        w.follow_playhead.setChecked(False)
        self.assertFalse(w.melody_transport.follow.isChecked());self.assertFalse(w.harmony_window.transport_controls.follow.isChecked())
        w.melody_transport.follow.setChecked(True)
        self.assertTrue(w.follow_playhead.isChecked());self.assertTrue(w.harmony_window.transport_controls.follow.isChecked())

    def test_score_main_follows_selected_harmony_and_tab_switch_catches_up(self):
        h=self.score('harmony');w=self.w;self.cursor(25*3840)
        w.follow_playhead.setChecked(True);w.follow_views(w.playhead)
        self.assertIs(w.docked_roll(),h);self.assertTrue(h.tick_visible(w.playhead))
        w.show_score_panel('melody');self.settle()
        self.assertIs(w.docked_roll(),w.roll);self.assertTrue(w.roll.tick_visible(w.playhead))
        self.assertTrue(w.score_view.tick_visible(w.playhead))

    def test_score_float_is_a_separate_view_and_has_its_own_controls(self):
        h=self.float_score('harmony');w=self.w
        self.assertIs(w.roll_pane(h),w.score_floats['harmony']);self.assertFalse(w.is_main_view(h))
        self.assertTrue(w.harmony_window.transport_controls.follow.isVisible())
        w.harmony_window.sync.setChecked(False);w.follow_playhead.setChecked(False)
        w.harmony_window.transport_controls.follow.setChecked(True)
        self.assertFalse(w.follow_playhead.isChecked())

    def test_score_melody_float_exposes_working_timeline_sync_menu(self):
        self.float_score('melody');w=self.w
        self.assertTrue(w.melody_options.isVisible())
        self.assertIn(w.melody_sync,w.melody_options.menu().actions())
        w.melody_sync.setChecked(False);w.melody_sync.trigger()
        self.assertTrue(w.melody_sync.isChecked())
        w.follow_playhead.setChecked(False);self.assertFalse(w.melody_transport.follow.isChecked())

    def test_score_independent_float_follows_while_main_stays_put(self):
        h=self.float_score('harmony');w=self.w;self.cursor(25*3840)
        w.harmony_window.sync.setChecked(False);w.follow_playhead.setChecked(False)
        w.harmony_window.transport_controls.follow.setChecked(True)
        before=(w.main_roll.horizontalScrollBar().value(),w.score_view.verticalScrollBar().value())
        w.follow_views(w.playhead)
        self.assertTrue(h.tick_visible(w.playhead))
        self.assertEqual(before,(w.main_roll.horizontalScrollBar().value(),w.score_view.verticalScrollBar().value()))

    def test_score_float_sync_links_scroll_and_follow_both_directions(self):
        h=self.float_score('harmony');w=self.w;w.harmony_window.sync.setChecked(True)
        w.follow_playhead.setChecked(False);self.assertFalse(w.harmony_window.transport_controls.follow.isChecked())
        w.harmony_window.transport_controls.follow.setChecked(True);self.assertTrue(w.follow_playhead.isChecked())
        h.horizontalScrollBar().setValue(400);self.assertEqual(w.main_roll.horizontalScrollBar().value(),400)
        w.main_roll.horizontalScrollBar().setValue(600);self.assertEqual(h.horizontalScrollBar().value(),600)

    def test_narrow_synced_score_float_follows_with_main_scroll_still_equal(self):
        h=self.float_score('harmony');w=self.w;pane=w.score_floats['harmony']
        pane.resize(620,650);self.settle();w.harmony_window.sync.setChecked(True)
        w.main_roll.horizontalScrollBar().setValue(0);self.cursor(10*PPQ)
        self.assertTrue(w.roll.tick_visible(w.playhead));self.assertFalse(h.tick_visible(w.playhead))
        w.follow_playhead.setChecked(True);w.follow_views(w.playhead)
        self.assertTrue(h.tick_visible(w.playhead))
        self.assertEqual(h.horizontalScrollBar().value(),w.main_roll.horizontalScrollBar().value())
        self.assertEqual(h.zoom,w.main_roll.zoom)

    def test_synced_score_float_follows_with_lyrics_selected_on_main(self):
        h=self.float_score('harmony');w=self.w;w.show_score_panel('lyrics');self.settle()
        w.harmony_window.sync.setChecked(True);self.cursor(25*3840)
        w.follow_playhead.setChecked(True);w.follow_views(w.playhead)
        self.assertTrue(h.tick_visible(w.playhead))
        self.assertEqual(h.horizontalScrollBar().value(),w.main_roll.horizontalScrollBar().value())

    def test_narrow_synced_compose_float_keeps_scroll_equal_during_follow(self):
        w=self.w;w.melody_window.setFloating(True);w.melody_window.resize(620,650);self.settle()
        w.melody_sync.setChecked(True);self.cursor(10*PPQ)
        w.main_roll.horizontalScrollBar().setValue(0);w.follow_playhead.setChecked(True)
        self.assertTrue(w.main_roll.tick_visible(w.playhead));self.assertFalse(w.roll.tick_visible(w.playhead))
        w.follow_views(w.playhead)
        self.assertTrue(w.roll.tick_visible(w.playhead))
        self.assertEqual(w.roll.horizontalScrollBar().value(),w.main_roll.horizontalScrollBar().value())

    def test_shared_scrollbar_small_move_keeps_follow_and_does_not_snap_back(self):
        w=self.w;self.cursor(3*PPQ);w.follow_playhead.setChecked(True)
        w.shared_scroll.triggerAction(QAbstractSlider.SliderAction.SliderSingleStepAdd);self.settle()
        moved=w.shared_scroll.value();self.assertGreater(moved,0)
        self.assertTrue(w.follow_playhead.isChecked())
        w.follow_views(w.playhead);self.assertEqual(w.shared_scroll.value(),moved)

    def test_cursor_near_right_edge_is_visible_and_not_recentered(self):
        w=self.w;r=w.roll;r.horizontalScrollBar().setValue(100)
        tick=round((r.viewport().width()-20-KEY_W+100)/r.zoom*PPQ)
        self.cursor(tick);w.follow_playhead.setChecked(True);before=r.horizontalScrollBar().value()
        self.assertTrue(r.tick_visible(tick));w.follow_views(tick)
        self.assertEqual(r.horizontalScrollBar().value(),before)

    def test_zoom_buttons_keep_follow_until_the_cursor_moves_outside_grid(self):
        w=self.w;r=w.roll
        for zoom in (w.view_controls.zoom,w.zoom):
            with self.subTest(api=zoom.__qualname__):
                r.zoom=78;r.update_ranges();r.horizontalScrollBar().setValue(0);r.timeViewChanged.emit()
                self.cursor(5*PPQ);w.follow_playhead.setChecked(True)
                zoom(12);self.assertTrue(r.tick_visible(w.playhead));self.assertTrue(w.follow_playhead.isChecked())
                zoom(72);self.assertFalse(r.tick_visible(w.playhead));self.assertFalse(w.follow_playhead.isChecked())

    def test_navigator_small_move_keeps_follow_and_far_move_cancels(self):
        w=self.w;r=w.roll;self.cursor(3*PPQ);w.follow_playhead.setChecked(True)
        center=(12+(r.viewport().width()-KEY_W)/2)/r.zoom*PPQ
        x=KEY_W+center/w.project.end*(w.navigator.width()-KEY_W)
        w.navigator.browse_to(x);self.settle()
        self.assertTrue(r.tick_visible(w.playhead));self.assertTrue(w.follow_playhead.isChecked())
        moved=r.horizontalScrollBar().value();w.follow_views(w.playhead);self.assertEqual(r.horizontalScrollBar().value(),moved)
        w.navigator.browse_to(w.navigator.width()*.9);self.settle()
        self.assertFalse(r.tick_visible(w.playhead));self.assertFalse(w.follow_playhead.isChecked())

    def test_middle_pan_keeps_follow_until_cursor_leaves_view(self):
        w=self.w;r=w.roll;self.cursor(3*PPQ);w.follow_playhead.setChecked(True)
        view=r.viewport();point=QPoint(300,max(r.ruler_height+10,view.height()//2))
        QTest.mousePress(view,Qt.MouseButton.MiddleButton,pos=point)
        QTest.mouseMove(view,point-QPoint(15,0));QTest.mouseRelease(view,Qt.MouseButton.MiddleButton,pos=point-QPoint(15,0));self.settle()
        self.assertTrue(w.follow_playhead.isChecked());self.assertTrue(r.tick_visible(w.playhead))
        QTest.mousePress(view,Qt.MouseButton.MiddleButton,pos=point)
        QTest.mouseMove(view,point-QPoint(650,0));QTest.mouseRelease(view,Qt.MouseButton.MiddleButton,pos=point-QPoint(650,0));self.settle()
        self.assertFalse(r.tick_visible(w.playhead));self.assertFalse(w.follow_playhead.isChecked())

    def test_score_roll_navigation_cancels_even_if_score_still_shows_cursor(self):
        h=self.score('harmony');w=self.w;self.cursor(PPQ)
        w.score_view.locate_tick(w.playhead);self.assertTrue(w.score_view.tick_visible(w.playhead))
        h.horizontalScrollBar().setValue(3000);w.follow_playhead.setChecked(True)
        w.cancel_follow(h);self.settle()
        self.assertFalse(h.tick_visible(w.playhead));self.assertFalse(w.follow_playhead.isChecked())

    def test_score_navigation_cancels_even_if_active_roll_still_shows_cursor(self):
        h=self.score('harmony');w=self.w;self.cursor(PPQ)
        h.horizontalScrollBar().setValue(0);w.score_view.verticalScrollBar().setValue(w.score_view.verticalScrollBar().maximum())
        self.assertTrue(h.tick_visible(w.playhead));self.assertFalse(w.score_view.bar_visible(w.playhead))
        w.follow_playhead.setChecked(True);w.cancel_follow(w.score_view);self.settle()
        self.assertFalse(w.follow_playhead.isChecked())

    def test_hidden_score_tab_cannot_keep_main_follow_after_all_visible_targets_leave(self):
        self.score('lyrics');w=self.w;self.cursor(PPQ)
        # The hidden melody tab still contains the tick, but does not contribute
        # to what this main page is actually showing.
        w.roll.horizontalScrollBar().setValue(0);self.assertTrue(w.roll.tick_visible(w.playhead))
        w.score_view.verticalScrollBar().setValue(w.score_view.verticalScrollBar().maximum())
        self.assertFalse(w.score_view.tick_visible(w.playhead))
        w.follow_playhead.setChecked(True);w.cancel_follow(w.score_view);self.settle()
        self.assertFalse(w.follow_playhead.isChecked())

    def test_score_wheel_cancels_when_playing_bar_leaves_its_viewport(self):
        h=self.score('harmony');w=self.w;view=w.score_view;self.cursor(PPQ)
        def wheel(delta):
            point=QPointF(120,120);global_point=QPointF(view.viewport().mapToGlobal(point.toPoint()))
            event=QWheelEvent(point,global_point,QPoint(),QPoint(0,delta),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
            APP.sendEvent(view.viewport(),event);self.settle()
        w.follow_playhead.setChecked(True);wheel(-120)
        self.assertTrue(view.bar_visible(w.playhead));self.assertTrue(w.follow_playhead.isChecked())
        wheel(-12000);wheel(-12000)
        self.assertFalse(view.bar_visible(w.playhead));self.assertTrue(h.tick_visible(w.playhead))
        self.assertFalse(w.follow_playhead.isChecked())
        view.verticalScrollBar().setValue(0);h.horizontalScrollBar().setValue(3000)
        self.assertTrue(view.bar_visible(w.playhead));w.follow_playhead.setChecked(True);wheel(-12000);wheel(-12000)
        self.assertFalse(view.bar_visible(w.playhead));self.assertFalse(h.tick_visible(w.playhead))
        self.assertFalse(w.follow_playhead.isChecked())

    def test_score_middle_pan_with_lyrics_tab_uses_only_visible_score_cursor(self):
        self.score('lyrics');w=self.w;view=w.score_view;canvas=view.canvas;self.cursor(PPQ)
        w.follow_playhead.setChecked(True)
        def pan(pixels):
            point=canvas.mapFrom(view.viewport(),QPoint(300,180))
            QTest.mousePress(canvas,Qt.MouseButton.MiddleButton,pos=point)
            QTest.mouseMove(canvas,point-QPoint(0,pixels))
            QTest.mouseRelease(canvas,Qt.MouseButton.MiddleButton,pos=point-QPoint(0,pixels));self.settle()
        pan(12);self.assertTrue(view.tick_visible(w.playhead));self.assertTrue(w.follow_playhead.isChecked())
        pan(800);self.assertFalse(view.tick_visible(w.playhead));self.assertFalse(w.follow_playhead.isChecked())

    def test_unsynced_score_float_cancellation_does_not_change_main_follow(self):
        h=self.float_score('harmony');w=self.w;self.cursor(PPQ)
        w.harmony_window.sync.setChecked(False);w.follow_playhead.setChecked(True)
        w.harmony_window.transport_controls.follow.setChecked(True);h.horizontalScrollBar().setValue(4000)
        w.cancel_follow(h);self.settle()
        self.assertFalse(w.harmony_window.transport_controls.follow.isChecked());self.assertTrue(w.follow_playhead.isChecked())

    def test_roll_visibility_uses_grid_not_keyboard_or_right_edge(self):
        r=self.w.roll;r.horizontalScrollBar().setValue(100)
        left=100/r.zoom*PPQ
        self.assertTrue(r.tick_visible(left));self.assertFalse(r.tick_visible(left-1))
        right=(100+r.viewport().width()-KEY_W)/r.zoom*PPQ
        self.assertFalse(r.tick_visible(right));self.assertTrue(r.tick_visible(right-1))


    def test_manual_navigation_uses_running_clock_instead_of_old_painted_tick(self):
        w=self.w;w.playhead=0;tick=3*PPQ
        with patch.object(w.transport,'playing',True),patch.object(w.transport,'position',return_value=tick):
            w.follow_playhead.setChecked(True)
            w.shared_scroll.triggerAction(QAbstractSlider.SliderAction.SliderSingleStepAdd)
            self.assertTrue(w.follow_playhead.isChecked())
            w.shared_scroll.setSliderPosition(w.shared_scroll.maximum());w.cancel_follow(w.main_roll)
            self.assertFalse(w.follow_playhead.isChecked())

    def test_switching_from_lyrics_to_docked_roll_catches_running_playhead(self):
        w=self.w;self.score('lyrics');tick=25*3840;w.follow_playhead.setChecked(True)
        with patch.object(w.transport,'playing',True),patch.object(w.transport,'position',return_value=tick):
            w.show_score_panel('harmony');self.settle()
            self.assertTrue(w.harmony_window.roll.tick_visible(tick))
            self.assertTrue(w.score_view.tick_visible(tick))


if __name__=='__main__':unittest.main()
