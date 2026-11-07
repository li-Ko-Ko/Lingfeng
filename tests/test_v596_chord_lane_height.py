import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSplitter

from lingfeng.music.model import Chord, Project
from lingfeng.ui.piano_roll import ChordLane, PianoRoll, minimum_chord_lane_height


APP=QApplication.instance() or QApplication([])


class ChordLaneHeightTests(unittest.TestCase):
    def project(self):
        return Project(chords=[Chord(0,3840,48,'m7')])

    def shrink_by_drag(self,lane):
        grip=lane.height_grip
        start=grip.rect().center()
        end=grip.mapToGlobal(start)+QPoint(0,-80*lane.height_drag_direction())
        heights=[]
        lane.chordHeightChanged.connect(heights.append)
        QTest.mousePress(grip,Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(grip,grip.mapFromGlobal(end))
        self.assertEqual(lane.card_height(),minimum_chord_lane_height())
        self.assertEqual(heights,[])
        QTest.mouseRelease(grip,Qt.MouseButton.LeftButton,pos=grip.mapFromGlobal(end))
        APP.processEvents()
        self.assertEqual(heights,[minimum_chord_lane_height()])

    def test_embedded_height_keeps_roll_window_size_and_uses_roman_only_at_minimum(self):
        for role in ('melody','harmony'):
            with self.subTest(role=role):
                roll=PianoRoll(self.project(),role=role)
                self.addCleanup(roll.close)
                roll.resize(900,500);roll.show();APP.processEvents()
                lane=roll.lane
                before=roll.viewport().height()-roll.ruler_height
                original_height=lane.card_height()
                self.assertTrue(lane.show_card_details())
                self.shrink_by_drag(lane)
                self.assertEqual(roll.height(),500)
                self.assertEqual(roll.viewport().height()-roll.ruler_height,before+original_height-lane.card_height())
                self.assertFalse(lane.show_card_details())
                with (
                    patch('lingfeng.ui.piano_roll.roman_label',return_value='i7') as roman,
                    patch('lingfeng.ui.piano_roll.contextual_chord_name') as letter,
                    patch('lingfeng.ui.piano_roll.rhythm_label') as rhythm,
                ):
                    lane.layer_key=None
                    lane.grab()
                    roman.assert_called_once()
                    letter.assert_not_called()
                    rhythm.assert_not_called()

    def test_splitter_height_is_exchanged_only_with_adjacent_roll(self):
        splitter=QSplitter(Qt.Orientation.Vertical)
        self.addCleanup(splitter.close)
        roll=PianoRoll(self.project())
        roll.set_panel('chords',False)
        lane=ChordLane(roll);lane.update_height()
        other=PianoRoll(self.project(),role='harmony')
        splitter.addWidget(roll);splitter.addWidget(lane);splitter.addWidget(other)
        splitter.resize(900,650);splitter.show();APP.processEvents()
        sizes=splitter.sizes()
        self.shrink_by_drag(lane)
        self.assertEqual(splitter.height(),650)
        self.assertEqual(splitter.sizes()[2],sizes[2])
        self.assertEqual(sum(splitter.sizes()[:2]),sum(sizes[:2]))
        self.assertEqual(lane.card_height(),minimum_chord_lane_height())
