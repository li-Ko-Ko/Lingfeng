"""Navigator tracks, overlapping melody colors and height gestures."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Chord, Note, Project
from lingfeng.ui.piano_roll import (KEY_W, NAVIGATOR_MIN_HEIGHT,
                                    NAVIGATOR_MAX_HEIGHT, PianoRoll)
from lingfeng.ui.theme import color

APP=QApplication.instance() or QApplication([])


class NavigatorTests(unittest.TestCase):
    def roll(self,project):
        roll=PianoRoll(project);self.addCleanup(roll.close)
        roll.resize(900,500);roll.show();APP.processEvents()
        return roll

    def test_defaults_empty_tracks_and_live_automatic_height(self):
        project=Project(notes=[Note(0,480,60)],chords=[Chord(0,3840,48)])
        roll=self.roll(project);nav=roll.navigator
        one=nav.height()
        self.assertEqual({s[0] for s in nav.segments()},{0})
        project.instrument_notes.append(Note(0,480,67));roll.refresh()
        self.assertGreater(nav.height(),one)
        two=nav.height()
        nav.set_visible_tracks(['vocal','instrument','chords'])
        self.assertGreater(nav.height(),two)
        self.assertEqual({s[0] for s in nav.segments()},{0,1,2})
        project.instrument_notes.clear();roll.refresh()
        self.assertNotIn(2,{s[0] for s in nav.segments()})
        nav.set_visible_tracks([])
        self.assertEqual(nav.height(),NAVIGATOR_MIN_HEIGHT)
        self.assertEqual(nav.segments(),[])

    def test_melody_bands_overlap_and_vocal_color_wins(self):
        project=Project(notes=[Note(0,960,40),Note(1920,480,60)],
                        instrument_notes=[Note(0,960,58)])
        roll=self.roll(project);nav=roll.navigator
        bands=nav.track_bands();vocal_top,band=bands[0];instrument_top,_=bands[2]
        self.assertGreater(instrument_top,vocal_top)
        self.assertLess(instrument_top,vocal_top+band)
        segments=nav.segments()
        vocal=next(s for s in segments if s[0]==0)
        instrument=next(s for s in segments if s[0]==2)
        self.assertEqual(vocal[2],instrument[2])
        image=QImage(nav.size(),QImage.Format.Format_RGB32)
        painter=QPainter(image)
        try:nav.paint_content(painter)
        finally:painter.end()
        self.assertEqual(image.pixelColor(round((vocal[1]+vocal[3])/2),round(vocal[2])),color(nav.TRACK_COLORS[0]))

    def test_height_drag_clamps_and_does_not_browse_or_change_playhead(self):
        roll=self.roll(Project(notes=[Note(0,480,60)]));nav=roll.navigator
        grip=nav.height_grip;heights=[];nav.navigatorHeightChanged.connect(heights.append)
        original=(roll.horizontalScrollBar().value(),roll.cursor_tick,roll.anchor_tick,roll.height())
        start=grip.rect().center();global_start=grip.mapToGlobal(start)
        with patch.object(nav,'browse_to',side_effect=AssertionError('height drag must not browse')):
            QTest.mousePress(grip,Qt.MouseButton.LeftButton,pos=start)
            end=global_start+QPoint(0,-300)
            QTest.mouseMove(grip,grip.mapFromGlobal(end))
            QTest.mouseRelease(grip,Qt.MouseButton.LeftButton,pos=grip.mapFromGlobal(end))
        self.assertEqual(nav.height(),NAVIGATOR_MIN_HEIGHT)
        self.assertEqual(heights,[NAVIGATOR_MIN_HEIGHT])
        self.assertEqual(original,(roll.horizontalScrollBar().value(),roll.cursor_tick,roll.anchor_tick,roll.height()))
        nav.set_navigator_height(999);self.assertEqual(nav.height(),NAVIGATOR_MAX_HEIGHT)
        nav.set_navigator_height(None);self.assertEqual(nav.height(),nav.preferred_height())

    def test_height_hotspot_click_preserves_automatic_height(self):
        roll=self.roll(Project(notes=[Note(0,480,60)]));nav=roll.navigator
        heights=[];nav.navigatorHeightChanged.connect(heights.append)
        QTest.mouseClick(nav.height_grip,Qt.MouseButton.LeftButton,pos=nav.height_grip.rect().center())
        self.assertIsNone(nav.navigator_height)
        self.assertEqual(heights,[])

    def test_hidden_navigator_does_not_render_harmony_during_refresh(self):
        roll=self.roll(Project(chords=[Chord(0,3840,48)]));nav=roll.navigator
        nav.set_visible_tracks(['chords']);roll.set_panel('navigator',False)
        with patch.object(Project,'harmony_notes',side_effect=AssertionError('hidden overview need not generate harmony')):
            roll.refresh();roll.update_panel_layout()

    def test_track_toggle_invalidates_overview_but_panning_reuses_pixels(self):
        roll=self.roll(Project(notes=[Note(0,480,60)],instrument_notes=[Note(480,480,64)]))
        nav=roll.navigator;nav.grab();renders=nav.cache_renders
        roll.horizontalScrollBar().setValue(100);nav.grab()
        self.assertEqual(nav.cache_renders,renders)
        nav.set_navigator_height(60);nav.grab();renders=nav.cache_renders
        nav.set_visible_tracks(['instrument']);nav.grab()
        self.assertGreater(nav.cache_renders,renders)
        self.assertEqual({s[0] for s in nav.segments()},{2})


if __name__=='__main__':unittest.main()
