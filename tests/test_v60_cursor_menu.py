"""Chord dividers expose only the left height grip; copy precedes cut."""
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QSplitter

from lingfeng.music.model import Chord, Note, Project
from lingfeng.platform import context_menu_preferences as preferences
from lingfeng.platform.i18n import set_language, tr
from lingfeng.ui.piano_roll import KEY_W, ChordLane, PianoRoll, minimum_chord_lane_height


APP = QApplication.instance() or QApplication([])


class ChordCursorTests(unittest.TestCase):
    def setUp(self):
        self.roll = PianoRoll(Project(chords=[Chord(0, 1920, 48)]))
        self.addCleanup(self.roll.close)

    def test_blank_margins_and_label_keep_arrow_while_cards_keep_edit_cursors(self):
        self.roll.resize(900, 500)
        self.roll.show()
        APP.processEvents()
        lane = self.roll.lane
        lane.grab()
        card = lane.card_rect(self.roll.project.chords[0])
        QTest.mouseMove(lane, card.center().toPoint())
        self.assertEqual(lane.cursor().shape(), Qt.CursorShape.OpenHandCursor)
        QTest.mouseMove(lane, QPoint(round(card.left())+1, round(card.center().y())))
        self.assertEqual(lane.cursor().shape(), Qt.CursorShape.SizeHorCursor)
        for point in (QPoint(KEY_W+20, 1), QPoint(KEY_W+20, lane.height()-1),
                      QPoint(lane.width()-10, lane.height()//2), QPoint(15, 25)):
            with self.subTest(point=point):
                QTest.mouseMove(lane, point)
                self.assertEqual(lane.cursor().shape(), Qt.CursorShape.ArrowCursor)
        self.assertEqual(lane.height_grip.cursor().shape(), Qt.CursorShape.SizeVerCursor)

    def test_scrolled_cards_cannot_hit_clipped_label_area(self):
        self.roll.resize(900, 500)
        self.roll.show()
        APP.processEvents()
        self.roll.horizontalScrollBar().setValue(100)
        lane = self.roll.lane
        lane.grab()
        self.assertIsNone(lane.chord_hit(QPointF(KEY_W-1, lane.height()/2)))

    def splitter_lane(self):
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter = splitter
        self.addCleanup(splitter.close)
        self.roll.set_panel('chords', False)
        lane = ChordLane(self.roll)
        lane.update_height()
        other = PianoRoll(self.roll.project, role='harmony')
        splitter.addWidget(self.roll)
        splitter.addWidget(lane)
        splitter.addWidget(other)
        splitter.resize(900, 700)
        splitter.show()
        APP.processEvents()
        return splitter, lane

    def test_divider_non_hot_area_keeps_arrow_and_does_not_resize(self):
        splitter, lane = self.splitter_lane()
        for index in (1, 2):
            handle = splitter.handle(index)
            with self.subTest(index=index):
                QTest.mouseMove(handle, QPoint(KEY_W+50, handle.height()//2))
                self.assertEqual(handle.cursor().shape(), Qt.CursorShape.ArrowCursor)
                sizes = splitter.sizes()
                start = QPoint(KEY_W+50, handle.height()//2)
                QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=start)
                QTest.mouseMove(handle, start+QPoint(0, 35))
                QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=start+QPoint(0, 35))
                APP.processEvents()
                self.assertEqual(splitter.sizes(), sizes)

    def test_divider_left_hot_area_adjusts_chord_height_only(self):
        splitter, lane = self.splitter_lane()
        handle = splitter.handle(1)
        start = QPoint(KEY_W//2, handle.height()//2)
        QTest.mouseMove(handle, start)
        self.assertEqual(handle.cursor().shape(), Qt.CursorShape.SizeVerCursor)
        sizes = splitter.sizes()
        heights = []
        lane.chordHeightChanged.connect(heights.append)
        target = handle.mapToGlobal(start)+QPoint(0, 90)
        QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(handle, handle.mapFromGlobal(target))
        self.assertEqual(lane.chord_height, minimum_chord_lane_height())
        self.assertEqual(heights, [])
        QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=handle.mapFromGlobal(target))
        APP.processEvents()
        self.assertEqual(heights, [minimum_chord_lane_height()])
        self.assertEqual(splitter.sizes()[2], sizes[2])
        self.assertEqual(sum(splitter.sizes()[:2]), sum(sizes[:2]))

    def test_lower_divider_left_hot_area_uses_the_lower_neighbor(self):
        splitter, lane = self.splitter_lane()
        handle = splitter.handle(2)
        start = QPoint(KEY_W//2, handle.height()//2)
        sizes = splitter.sizes()
        height = lane.chord_height
        target = handle.mapToGlobal(start)+QPoint(0, 20)
        QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=start)
        move = QMouseEvent(QEvent.Type.MouseMove, QPointF(handle.mapFromGlobal(target)),
                           QPointF(target), Qt.MouseButton.NoButton,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        APP.sendEvent(handle, move)
        QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=handle.mapFromGlobal(target))
        APP.processEvents()
        self.assertEqual(lane.chord_height, height+20)
        self.assertEqual(splitter.sizes()[0], sizes[0])
        self.assertEqual(sum(splitter.sizes()[1:]), sum(sizes[1:]))

    def test_hidden_and_remounted_lane_restores_divider_hot_area(self):
        splitter, lane = self.splitter_lane()
        lane.hide()
        APP.processEvents()
        self.assertEqual(lane.height_handles, [])
        lane.show()
        APP.processEvents()
        handle = splitter.handle(1)
        self.assertIn(handle, lane.height_handles)
        QTest.mouseMove(handle, QPoint(KEY_W+30, handle.height()//2))
        self.assertEqual(handle.cursor().shape(), Qt.CursorShape.ArrowCursor)

    def test_revealed_neighbor_gets_hot_area_without_resizing_fixed_lane(self):
        splitter, lane = self.splitter_lane()
        other = splitter.widget(2)
        other.hide()
        APP.processEvents()
        other.show()
        APP.processEvents()
        handle = splitter.handle(2)
        QTest.mouseMove(handle, QPoint(KEY_W+30, handle.height()//2))
        self.assertEqual(handle.cursor().shape(), Qt.CursorShape.ArrowCursor)
        QTest.mouseMove(handle, QPoint(KEY_W//2, handle.height()//2))
        self.assertEqual(handle.cursor().shape(), Qt.CursorShape.SizeVerCursor)

    def test_non_adjacent_divider_keeps_normal_cursor_and_resize_behavior(self):
        splitter, lane = self.splitter_lane()
        spare = PianoRoll(self.roll.project)
        splitter.addWidget(spare)
        splitter.resize(900, 1200)
        APP.processEvents()
        lane.watch_height_handles()
        handle = splitter.handle(3)
        # CursorChange must never re-enter cursor assignment in the event filter.
        handle.setCursor(Qt.CursorShape.SplitVCursor)
        start = QPoint(KEY_W+50, handle.height()//2)
        QTest.mouseMove(handle, start)
        self.assertEqual(handle.cursor().shape(), Qt.CursorShape.SplitVCursor)
        sizes = splitter.sizes()
        chord_height = lane.chord_height
        target = handle.mapToGlobal(start)+QPoint(0, 20)
        QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=start)
        move = QMouseEvent(QEvent.Type.MouseMove, QPointF(handle.mapFromGlobal(target)),
                           QPointF(target), Qt.MouseButton.NoButton,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        APP.sendEvent(handle, move)
        QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=handle.mapFromGlobal(target))
        APP.processEvents()
        self.assertNotEqual(splitter.sizes()[2:], sizes[2:])
        self.assertEqual(lane.chord_height, chord_height)


class ClipboardMenuOrderTests(unittest.TestCase):
    def setUp(self):
        set_language('zh')
        before = preferences.settings_dict()
        self.addCleanup(preferences.set_preferences, before)
        preferences.load_preferences({})
        self.roll = PianoRoll(Project(notes=[Note(0, 480, 60)]))
        self.addCleanup(self.roll.close)

    def menu(self, selected):
        self.roll.selected_ids = {self.roll.notes[0].id} if selected else set()
        menu = QMenu(self.roll)
        self.addCleanup(menu.close)
        self.roll.selection_menu(menu, 0)
        return menu

    def test_copy_above_cut_with_default_and_custom_block_order(self):
        for custom in (False, True):
            if custom:
                layout = preferences.default_layout()
                layout['note'].reverse()
                preferences.set_preferences({'context_menu_layout': layout})
            for selected in (False, True):
                with self.subTest(custom=custom, selected=selected):
                    labels = [action.text().split('\t', 1)[0] for action in self.menu(selected).actions()]
                    self.assertLess(labels.index(tr('复制所选音符')), labels.index(tr('剪切所选音符')))

    def test_copy_and_cut_keep_commands_shortcuts_and_enabled_state(self):
        commands = []
        self.roll.commandRequested.connect(lambda command, tick: commands.append((command, tick)))
        for selected in (False, True):
            menu = self.menu(selected)
            actions = {action.text().split('\t', 1)[0]: action for action in menu.actions()}
            for label, command, shortcut in (('复制所选音符', 'copy:direct', 'copy_selection'),
                                             ('剪切所选音符', 'cut', 'cut_selection')):
                action = actions[tr(label)]
                self.assertEqual(action.isEnabled(), selected)
                self.assertEqual(action.property('shortcutCommand'), shortcut)
                if selected:
                    action.trigger()
                    self.assertEqual(commands[-1], (command, 0))

    def chord_menu(self, selected):
        self.roll.project.chords = [Chord(0, 1920, 48)] if selected else []
        self.roll.selected_chords = {self.roll.project.chords[0].id} if selected else set()
        menu = self.roll.lane.context_menu(QPoint(KEY_W+12, 20))
        self.addCleanup(menu.close)
        return menu

    def test_chord_copy_above_cut_with_default_and_custom_block_order(self):
        for custom in (False, True):
            if custom:
                layout = preferences.default_layout()
                layout['chord'].reverse()
                preferences.set_preferences({'context_menu_layout': layout})
            for selected in (False, True):
                with self.subTest(custom=custom, selected=selected):
                    labels = [action.text().split('\t', 1)[0] for action in self.chord_menu(selected).actions()]
                    self.assertEqual(labels.index(tr('剪切所选和弦')), labels.index(tr('复制所选和弦'))+1)

    def test_chord_copy_and_cut_keep_commands_shortcuts_and_enabled_state(self):
        commands = []
        self.roll.chordCommand.connect(lambda command, ids: commands.append((command, ids)))
        for selected in (False, True):
            menu = self.chord_menu(selected)
            actions = {action.text().split('\t', 1)[0]: action for action in menu.actions()}
            for label, command, shortcut in (('复制所选和弦', 'copy', 'copy_selection'),
                                             ('剪切所选和弦', 'cut', 'cut_selection')):
                action = actions[tr(label)]
                self.assertEqual(action.isEnabled(), selected)
                self.assertEqual(action.property('shortcutCommand'), shortcut)
                if selected:
                    action.trigger()
                    self.assertEqual(commands[-1], (command, self.roll.selected_chords))


if __name__ == '__main__':
    unittest.main()
