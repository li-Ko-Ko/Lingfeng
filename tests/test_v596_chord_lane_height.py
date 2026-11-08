import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSplitter

from lingfeng.music.model import Chord, Project
from lingfeng.ui.piano_roll import KEY_W, ChordLane, PianoRoll, minimum_chord_lane_height


APP=QApplication.instance() or QApplication([])


class ChordLaneHeightTests(unittest.TestCase):
    def project(self):
        return Project(chords=[Chord(0,3840,48,'m7')])

    def assert_height_grip_edge(self,lane,at_bottom):
        grip=lane.height_grip
        active_y=lane.height()-1 if at_bottom else 0
        inactive_y=0 if at_bottom else lane.height()-1
        self.assertIs(lane.childAt(KEY_W//2,active_y),grip)
        self.assertEqual(grip.cursor().shape(),Qt.CursorShape.SizeVerCursor)
        for point in (QPoint(KEY_W//2,inactive_y),QPoint(KEY_W+20,active_y)):
            hovered=lane.childAt(point) or lane
            self.assertIsNot(hovered,grip)
            QTest.mouseMove(hovered,hovered.mapFrom(lane,point))
            self.assertEqual(hovered.cursor().shape(),Qt.CursorShape.ArrowCursor)

    def shrink_by_drag(self,lane,at_bottom):
        grip=lane.height_grip
        start=grip.rect().center()
        end=grip.mapToGlobal(start)+QPoint(0,-80 if at_bottom else 80)
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
                at_bottom=role=='harmony'
                self.assertTrue(lane.show_card_details())
                self.assert_height_grip_edge(lane,at_bottom)
                self.shrink_by_drag(lane,at_bottom)
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
                lane.set_velocity_visible(True);APP.processEvents()
                self.assert_height_grip_edge(lane,at_bottom)

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
        original_height=lane.card_height()
        self.assert_height_grip_edge(lane,False)
        self.shrink_by_drag(lane,False)
        self.assertEqual(splitter.height(),650)
        self.assertEqual(splitter.sizes()[2],sizes[2])
        self.assertEqual(sum(splitter.sizes()[:2]),sum(sizes[:2]))
        self.assertEqual(lane.card_height(),minimum_chord_lane_height())

        lane.set_chord_height(original_height)
        roll.hide();APP.processEvents()
        sizes=splitter.sizes()
        self.assert_height_grip_edge(lane,True)
        self.shrink_by_drag(lane,True)
        self.assertEqual(splitter.sizes()[2]-sizes[2],original_height-lane.card_height())
        roll.show();APP.processEvents()
        self.assert_height_grip_edge(lane,False)
