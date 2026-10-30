"""A manually browsed score follows measures, without taking over a drag."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QEvent,QPoint,QRectF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QStyle,QStyleOptionSlider
from popscore.app import MainWindow
from popscore.model import Project,Measure,Context,Note,PPQ
from popscore.presentation import add_compression
from popscore.scoreview import ScoreView

APP=QApplication.instance() or QApplication([])


def song():
    p=Project(measures=[Measure() for _ in range(40)],contexts=[Context(0,40*3840)])
    p.notes=[Note(i*3840,480,60+i%5) for i in range(40)]
    return p


class ScoreGeometryTests(unittest.TestCase):
    def setUp(self):
        self.view=ScoreView(song());self.view.resize(820,520);self.view.show();QTest.qWait(10)
    def tearDown(self):
        self.view.close();self.view.deleteLater();APP.processEvents()

    def test_partially_visible_bar_survives_when_cursor_line_is_offscreen(self):
        v=self.view;tick=PPQ;v.set_zoom(2);v.locate_tick(tick);APP.processEvents()
        rect=v.bar_rect(0);v.horizontalScrollBar().setValue(round(rect.right()-rect.width()*.25))
        self.assertTrue(v.bar_visible(tick));self.assertFalse(v.tick_visible(tick))
        v.horizontalScrollBar().setValue(round(rect.right()+2))
        self.assertFalse(v.bar_visible(tick))

    def test_vertical_measure_intersection_uses_actual_scaled_viewport(self):
        v=self.view;tick=4*3840+PPQ
        for style in ('traditional','spatial','compact'):
            p=song();p.notation['style']=style;v.canvas.rebuild(p)
            for scale in (.5,1,2):
                with self.subTest(style=style,scale=scale):
                    v.set_zoom(scale);v.locate_tick(tick);APP.processEvents()
                    rect=v.bar_rect(4)
                    v.verticalScrollBar().setValue(round(rect.bottom()-4))
                    self.assertTrue(v.bar_visible(tick))
                    v.verticalScrollBar().setValue(round(rect.bottom()+2))
                    self.assertFalse(v.bar_visible(tick))

    def test_repeat_uses_visible_source_measure_on_later_playthrough(self):
        p=song()
        for i in range(8):p.notes[i].pitch=60
        add_compression(p,list(range(8)),'repeat')
        self.view.canvas.rebuild(p);self.view.locate_bar(0);APP.processEvents()
        self.assertEqual(self.view.bar_rect(0),self.view.bar_rect(4))
        self.assertEqual(self.view.bar_visible(PPQ),self.view.bar_visible(4*3840+PPQ))
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
        self.assertFalse(self.view.bar_visible(4*3840+PPQ))

    def test_invalid_tick_or_deferred_layout_has_no_visible_measure(self):
        v=self.view
        self.assertFalse(v.bar_visible(-1));self.assertFalse(v.bar_visible(v.canvas.project.end))
        v.canvas.clear_layout();self.assertFalse(v.bar_visible(0))


class ScoreNavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='tmp');self.addCleanup(self.temp.cleanup)
        prefs=patch('popscore.app.user_data_dir',return_value=Path(self.temp.name));prefs.start();self.addCleanup(prefs.stop)
        save=patch.object(MainWindow,'save_preferences');save.start();self.addCleanup(save.stop)
        self.errors=[];hook=patch.object(sys,'excepthook',lambda typ,value,tb:self.errors.append(str(value)));hook.start();self.addCleanup(hook.stop)
        self.w=MainWindow(song());self.w.change_language('zh',False);self.w.timer.stop();self.w.autosave.stop()
        self.w.resize(1240,900);self.w.show();self.w.switch_workspace('score');self.w.show_score_panel('harmony');self.settle()
        self.v=self.w.score_view;self.cursor(PPQ);self.v.locate_tick(self.w.playhead);self.settle()

    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater()
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents();self.assertEqual(self.errors,[])
    def settle(self):
        APP.processEvents();QTest.qWait(5);APP.processEvents()
    def cursor(self,tick):
        self.w.playhead=tick;self.w.show_cursor(tick)
    def thumb(self,bar):
        option=QStyleOptionSlider();bar.initStyleOption(option)
        return bar.style().subControlRect(QStyle.ComplexControl.CC_ScrollBar,option,QStyle.SubControl.SC_ScrollBarSlider,bar).center()

    def test_partial_bar_navigation_does_not_recenter_after_releasing_slider(self):
        w,v=self.w,self.v;v.set_zoom(2);v.locate_tick(w.playhead);self.settle()
        rect=v.bar_rect(0);bar=v.horizontalScrollBar();w.follow_playhead.setChecked(True)
        bar.setSliderDown(True);bar.setSliderPosition(round(rect.right()-rect.width()*.25))
        self.assertFalse(v.tick_visible(w.playhead));self.assertTrue(v.bar_visible(w.playhead))
        self.assertTrue(w.follow_playhead.isChecked());before=bar.value()
        w.follow_views(w.playhead);self.assertEqual(bar.value(),before)
        bar.setSliderDown(False);w.follow_views(w.playhead)
        self.assertTrue(w.follow_playhead.isChecked());self.assertEqual(bar.value(),before)

    def test_score_navigation_cancels_even_with_playhead_in_active_roll(self):
        w,v=self.w,self.v;h=w.harmony_window.roll
        h.horizontalScrollBar().setValue(0);self.assertTrue(h.tick_visible(w.playhead))
        w.follow_playhead.setChecked(True);bar=v.verticalScrollBar()
        bar.setSliderDown(True);bar.setSliderPosition(bar.maximum());bar.setSliderDown(False)
        self.assertFalse(v.bar_visible(w.playhead));self.assertFalse(w.follow_playhead.isChecked())
        before=bar.value();w.follow_views(w.playhead);self.assertEqual(bar.value(),before)

    def test_real_scrollbar_press_prevents_timer_from_stealing_held_thumb(self):
        w,v=self.w,self.v;bar=v.verticalScrollBar();point=self.thumb(bar)
        w.follow_playhead.setChecked(True)
        QTest.mousePress(bar,Qt.MouseButton.LeftButton,pos=point)
        try:
            self.assertTrue(bar.isSliderDown());self.assertTrue(v.manual_navigation_active)
            before=bar.value();future=25*3840+PPQ
            self.assertFalse(v.bar_visible(future));w.follow_views(future)
            self.assertEqual(bar.value(),before)
        finally:QTest.mouseRelease(bar,Qt.MouseButton.LeftButton,pos=point)
        self.assertFalse(v.manual_navigation_active)

    def test_real_scrollbar_drag_preserves_small_move_and_cancels_far_move(self):
        w,v=self.w,self.v;bar=v.verticalScrollBar();point=self.thumb(bar)
        w.follow_playhead.setChecked(True);QTest.mousePress(bar,Qt.MouseButton.LeftButton,pos=point)
        try:
            QTest.mouseMove(bar,point+QPoint(0,1));self.settle()
            self.assertTrue(v.bar_visible(w.playhead));self.assertTrue(w.follow_playhead.isChecked())
            before=bar.value();w.follow_views(w.playhead);self.assertEqual(bar.value(),before)
            far=QPoint(point.x(),min(bar.height()-20,point.y()+100))
            QTest.mouseMove(bar,far);self.settle()
            self.assertFalse(v.bar_visible(w.playhead));self.assertFalse(w.follow_playhead.isChecked())
            before=bar.value();w.follow_views(w.playhead);self.assertEqual(bar.value(),before)
        finally:QTest.mouseRelease(bar,Qt.MouseButton.LeftButton,pos=far)

    def test_nontracking_slider_cancels_at_committed_release(self):
        w,v=self.w,self.v;bar=v.verticalScrollBar();bar.setTracking(False)
        w.follow_playhead.setChecked(True);before=bar.value()
        bar.setSliderDown(True);bar.setSliderPosition(bar.maximum())
        self.assertEqual(bar.value(),before);self.assertTrue(v.manual_navigation_active)
        w.follow_views(25*3840);self.assertEqual(bar.value(),before)
        bar.setSliderDown(False);self.settle()
        self.assertEqual(bar.value(),bar.maximum());self.assertFalse(w.follow_playhead.isChecked())
        bar.setTracking(True)

    def test_canvas_pan_temporarily_owns_camera_and_releases_it(self):
        w,v=self.w,self.v;canvas=v.canvas;point=canvas.mapFrom(v.viewport(),QPoint(250,150))
        w.follow_playhead.setChecked(True);QTest.mousePress(canvas,Qt.MouseButton.MiddleButton,pos=point)
        try:
            self.assertTrue(v.manual_navigation_active);before=v.verticalScrollBar().value()
            w.follow_views(25*3840);self.assertEqual(v.verticalScrollBar().value(),before)
        finally:QTest.mouseRelease(canvas,Qt.MouseButton.MiddleButton,pos=point)
        self.assertFalse(v.manual_navigation_active)

    def test_slider_release_checks_current_playing_measure_after_a_held_drag(self):
        w,v=self.w,self.v;bar=v.verticalScrollBar()
        for tracking in (True,False):
            with self.subTest(tracking=tracking):
                clock={'tick':PPQ};bar.setTracking(tracking);bar.setValue(0);point=self.thumb(bar)
                with patch.object(w.transport,'playing',True),patch.object(w.transport,'position',side_effect=lambda:clock['tick']):
                    w.follow_playhead.setChecked(True);QTest.mousePress(bar,Qt.MouseButton.LeftButton,pos=point)
                    try:
                        QTest.mouseMove(bar,point+QPoint(0,1));self.settle()
                        self.assertTrue(w.follow_playhead.isChecked());before=bar.value()
                        clock['tick']=25*3840;w.follow_views(clock['tick']);self.assertEqual(bar.value(),before)
                    finally:QTest.mouseRelease(bar,Qt.MouseButton.LeftButton,pos=point+QPoint(0,1))
                    self.assertFalse(w.follow_playhead.isChecked());committed=bar.value()
                    w.follow_views(clock['tick']);self.assertEqual(bar.value(),committed)
        bar.setTracking(True)

    def test_pan_release_checks_current_playing_measure_after_pointer_stops(self):
        w,v=self.w,self.v;canvas=v.canvas;point=canvas.mapFrom(v.viewport(),QPoint(250,150));clock={'tick':PPQ}
        with patch.object(w.transport,'playing',True),patch.object(w.transport,'position',side_effect=lambda:clock['tick']):
            w.follow_playhead.setChecked(True);QTest.mousePress(canvas,Qt.MouseButton.MiddleButton,pos=point)
            try:
                clock['tick']=25*3840;before=v.verticalScrollBar().value();w.follow_views(clock['tick'])
                self.assertEqual(v.verticalScrollBar().value(),before)
            finally:QTest.mouseRelease(canvas,Qt.MouseButton.MiddleButton,pos=point)
            self.assertFalse(w.follow_playhead.isChecked())
            w.follow_views(clock['tick']);self.assertEqual(v.verticalScrollBar().value(),before)


if __name__=='__main__':unittest.main()
