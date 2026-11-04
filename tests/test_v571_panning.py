"""Camera movement avoids musical rebuilds and retains exact pan navigation."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QEvent,QPoint,QPointF,Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Chord,Context,Measure,Note,Project
from lingfeng.ui.main_window import MainWindow

APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]
MIDDLE=Qt.MouseButton.MiddleButton
NONE=Qt.MouseButton.NoButton


def song():
    p=Project(measures=[Measure() for _ in range(32)],contexts=[Context(0,32*3840)])
    p.notes=[Note(i*240,180,48+i%24) for i in range(32*16)]
    p.chords=[Chord(i*3840,3840,pattern='quarters') for i in range(32)]
    return p


def send(widget,kind,point,button,buttons):
    APP.sendEvent(widget,QMouseEvent(kind,QPointF(point),QPointF(widget.mapToGlobal(point)),button,buttons,Qt.KeyboardModifier.NoModifier))


class CameraPanTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'tmp').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.temp.cleanup)
        environment=patch.dict(os.environ,{'LINGFENG_USER_DATA':str(Path(self.temp.name)/'user'),'LINGFENG_SYNTH_CACHE':str(Path(self.temp.name)/'index/current.json')})
        environment.start();self.addCleanup(environment.stop)
        self.w=MainWindow(song());self.w.timer.stop();self.w.autosave.stop()
        self.w.resize(1240,900);self.w.show();self.w.open_harmony();self.settle()

    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater()
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()

    def settle(self):
        APP.processEvents();QTest.qWait(5);APP.processEvents()

    def test_two_axis_pan_does_not_rebuild_music_or_pitch_ranges(self):
        w=self.w;r=w.roll;r.horizontalScrollBar().setValue(200);r.verticalScrollBar().setValue(500)
        r.selected_ids={r.notes[0].id};r.refresh();self.settle()
        before=copy.deepcopy(w.project.to_dict());selection=(copy.deepcopy(r.selection),set(r.selected_ids));history=(len(w.undo_history),len(w.redo_history),w.dirty)
        revisions=[roll.paint_revision for roll in (w.main_roll,w.roll,w.harmony_window.roll)]
        moved=[];geometry=[];r.timeViewChanged.connect(lambda:moved.append(True));r.viewChanged.connect(lambda:geometry.append(True))
        with patch.object(w.project,'harmony_notes',side_effect=AssertionError('Panning rebuilt harmony MIDI')), \
             patch.object(r,'update_ranges',side_effect=AssertionError('Panning rebuilt source range')), \
             patch.object(w.harmony_window.roll,'update_ranges',side_effect=AssertionError('Panning rebuilt linked range')), \
             patch.object(r,'expand_note_selection',side_effect=AssertionError('Panning normalized note selection')):
            start=QPoint(400,180);end=start-QPoint(85,60)
            send(r.viewport(),QEvent.Type.MouseButtonPress,start,MIDDLE,MIDDLE)
            send(r.viewport(),QEvent.Type.MouseMove,end,NONE,MIDDLE)
            send(r.viewport(),QEvent.Type.MouseButtonRelease,end,MIDDLE,NONE)
        self.assertEqual((r.horizontalScrollBar().value(),r.verticalScrollBar().value()),(285,560))
        self.assertEqual(w.main_roll.horizontalScrollBar().value(),285)
        self.assertEqual(w.harmony_window.roll.horizontalScrollBar().value(),285)
        self.assertEqual(moved,[True]);self.assertEqual(geometry,[])
        self.assertEqual([roll.paint_revision for roll in (w.main_roll,w.roll,w.harmony_window.roll)],revisions)
        self.assertEqual((r.selection,r.selected_ids),selection);self.assertEqual(w.project.to_dict(),before)
        self.assertEqual((len(w.undo_history),len(w.redo_history),w.dirty),history)

    def test_release_applies_final_position_when_the_last_move_was_not_delivered(self):
        r=self.w.roll;r.horizontalScrollBar().setValue(200);r.verticalScrollBar().setValue(500)
        start=QPoint(420,200);partial=start-QPoint(10,10);end=start-QPoint(95,75)
        send(r.viewport(),QEvent.Type.MouseButtonPress,start,MIDDLE,MIDDLE)
        send(r.viewport(),QEvent.Type.MouseMove,partial,NONE,MIDDLE)
        send(r.viewport(),QEvent.Type.MouseButtonRelease,end,MIDDLE,NONE)
        self.assertEqual((r.horizontalScrollBar().value(),r.verticalScrollBar().value()),(295,575))
        self.assertIsNone(r.pan_state)

    def test_chord_lane_pan_keeps_vertical_camera_and_uses_final_release_position(self):
        lane=self.w.chord_lane;r=lane.editor;r.horizontalScrollBar().setValue(200);r.verticalScrollBar().setValue(500)
        start=QPoint(400,25);end=start-QPoint(70,15)
        send(lane,QEvent.Type.MouseButtonPress,start,MIDDLE,MIDDLE)
        send(lane,QEvent.Type.MouseButtonRelease,end,MIDDLE,NONE)
        self.assertEqual((r.horizontalScrollBar().value(),r.verticalScrollBar().value()),(270,500))
        self.assertIsNone(lane.pan_state)

    def test_floating_independent_pan_does_not_move_main_until_sync_is_enabled(self):
        w=self.w;w.melody_window.setFloating(True);w.melody_sync.setChecked(False);self.settle()
        r=w.roll;main=w.main_roll.horizontalScrollBar().value()
        r.pan_to(600,450)
        self.assertEqual(r.horizontalScrollBar().value(),600)
        self.assertEqual(w.main_roll.horizontalScrollBar().value(),main)
        w.melody_sync.setChecked(True);r.pan_to(725,460)
        self.assertEqual(w.main_roll.horizontalScrollBar().value(),725)
        self.assertEqual(r.horizontalScrollBar().value(),725)

    def test_overview_music_cache_survives_camera_motion_and_invalidates_for_edits(self):
        w=self.w;r=w.roll;nav=w.navigator;nav.grab();renders=nav.cache_renders
        lane=w.chord_lane;lane.grab();lane_renders=lane.cache_renders
        with patch.object(nav,'segments',wraps=nav.segments) as segments:
            r.pan_to(180,500);nav.grab()
            r.pan_to(250,520);nav.grab()
            self.assertEqual(nav.cache_renders,renders);segments.assert_not_called()
            lane.grab();horizontal_renders=lane.cache_renders
            r.pan_to(250,560);lane.grab()
            self.assertEqual(lane.cache_renders,horizontal_renders)
            r.project.notes[0].pitch+=1;r.refresh();nav.grab()
            self.assertGreater(nav.cache_renders,renders);segments.assert_called_once()
        self.assertGreaterEqual(lane.cache_renders,lane_renders)

    def test_visible_grid_matches_full_grid_in_mixed_meters_and_at_endpoints(self):
        r=self.w.roll;p=r.project
        p.change_meter(2,3,8,allow_trim=True);p.change_meter(4,5,16,allow_trim=True);r.set_project(p)
        windows=[(-100,0),(0,2300),(3850,5650),(p.starts[4],p.starts[5]),(p.end-10,p.end+100),(p.end+10,p.end+500)]
        for bars in (0,1,2,4,8):
            for step in (60,160,240,960):
                r.grid_bars=bars;r.grid=step;points=r.grid_points()
                for left,right in windows:
                    with self.subTest(bars=bars,step=step,left=left,right=right):
                        self.assertEqual(list(r.visible_grid_points(left,right)),[tick for tick in points if left<=tick<=right])


if __name__=='__main__':unittest.main()
