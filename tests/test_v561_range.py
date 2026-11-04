"""Custom inclusive piano-key ranges are view state, never MIDI edits."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox

from lingfeng.music.model import Chord, Note, Project
from lingfeng.ui.controls import PitchRangeDialog, RollViewControls
from lingfeng.ui.piano_roll import PianoRoll

APP = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parents[1]


def music():
    p = Project()
    p.notes = [Note(0, 480, pitch, 70) for pitch in (36, 60, 84)]
    p.chords = [Chord(0, 3840, notes=[Note(0, 480, pitch, 81) for pitch in (37, 61, 85)], custom_rhythm=True)]
    return p


class PianoRangeTests(unittest.TestCase):
    def make_roll(self, role='melody'):
        roll = PianoRoll(music(), role=role)
        self.addCleanup(roll.close)
        roll.resize(900, 640)
        roll.show()
        APP.processEvents()
        return roll

    def test_both_roles_show_exact_inclusive_range_without_changing_notes_or_selection(self):
        for role in ('melody', 'harmony'):
            with self.subTest(role=role):
                roll = self.make_roll(role)
                before = roll.project.to_dict()
                roll.selected_ids = {note.id for note in roll.notes}
                selected = set(roll.selected_ids)
                roll.set_pitch_range(48, 72)
                APP.processEvents()
                roll.grab()
                self.assertEqual(roll.pitches, list(range(72, 47, -1)))
                self.assertEqual((roll.low, roll.high), (48, 72))
                self.assertEqual(roll.selected_ids, selected)
                self.assertEqual(roll.project.to_dict(), before)
                self.assertTrue(roll.hit_notes)
                self.assertTrue(all(48 <= note.pitch <= 72 for _, note in roll.hit_notes))
                roll.set_project(roll.project)
                self.assertEqual(roll.pitch_range, (48, 72))

    def test_invalid_bounds_leave_active_range_and_music_unchanged(self):
        roll = self.make_roll()
        roll.set_pitch_range(48, 72)
        before = roll.project.to_dict()
        for low, high in ((20, 72), (48, 109), (72, 48), (True, 72), (48, None)):
            with self.subTest(low=low, high=high), self.assertRaises(ValueError):
                roll.set_pitch_range(low, high)
            self.assertEqual(roll.pitch_range, (48, 72))
            self.assertEqual(roll.project.to_dict(), before)
        roll.set_pitch_range(21, 21)
        self.assertEqual(roll.pitches, [21])
        self.assertEqual(roll.verticalScrollBar().maximum(), 0)
        roll.set_pitch_range(108, 108)
        self.assertEqual(roll.pitches, [108])

    def test_existing_full_and_used_modes_clear_filter_and_remember_last_custom_range(self):
        roll = self.make_roll()
        roll.set_pitch_range(48, 72)
        roll.set_compact(True)
        self.assertIsNone(roll.pitch_range)
        self.assertEqual(roll.pitches, [84, 60, 36])
        self.assertEqual(roll.manual_pitch_range, (48, 72))
        roll.set_compact(False)
        self.assertEqual(roll.pitches, list(range(108, 20, -1)))
        self.assertEqual(roll.manual_pitch_range, (48, 72))

    def test_pointer_pitch_clamps_and_new_notes_stay_within_custom_range(self):
        for role in ('melody', 'harmony'):
            with self.subTest(role=role):
                roll = self.make_roll(role)
                roll.set_pitch_range(48, 72)
                self.assertEqual(roll.pitch_at(-10000), 72)
                self.assertEqual(roll.pitch_at(10000), 48)
                added = []
                roll.noteAdded.connect(added.append)
                roll.tool = 'draw'
                point = QPoint(round(roll.x_at(960) + 8), round(roll.y_at(60) + roll.row_height / 2))
                QTest.mouseClick(roll.viewport(), Qt.MouseButton.LeftButton, pos=point)
                self.assertEqual(len(added), 1)
                self.assertTrue(48 <= added[0].pitch <= 72)


class PitchRangeControlsTests(unittest.TestCase):
    def test_endpoints_use_standard_midi_names_and_reversed_ranges_cannot_confirm(self):
        dialog = PitchRangeDialog()
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.value(), (48, 72))
        self.assertIn('C3', dialog.low.currentText())
        self.assertIn('C5', dialog.high.currentText())
        dialog.low.setCurrentIndex(dialog.low.findData(84))
        self.assertFalse(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        dialog.accept()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        dialog.high.setCurrentIndex(dialog.high.findData(96))
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_combo_confirms_custom_range_and_reselects_it_for_editing_cancel_keeps_view(self):
        roll = PianoRoll(music())
        self.addCleanup(roll.close)
        controls = RollViewControls(roll)
        self.addCleanup(controls.close)
        self.assertEqual(controls.range.count(), 3)
        dialog = Mock()
        dialog.exec.return_value = QDialog.DialogCode.Accepted
        dialog.value.return_value = (48, 72)
        with patch('lingfeng.ui.controls.PitchRangeDialog', return_value=dialog) as factory:
            controls.range.setCurrentIndex(2)
            controls.range.activated.emit(2)
            factory.assert_called_once()
        self.assertEqual(roll.pitch_range, (48, 72))
        self.assertEqual(controls.range.currentText(), 'C3 – C5')
        before = roll.project.to_dict()
        dialog.exec.return_value = QDialog.DialogCode.Rejected
        dialog.value.side_effect = AssertionError('Cancelled endpoints must not be read')
        with patch('lingfeng.ui.controls.PitchRangeDialog', return_value=dialog) as factory:
            controls.range.activated.emit(2)
            factory.assert_called_once()
        self.assertEqual(roll.pitch_range, (48, 72))
        self.assertEqual(roll.project.to_dict(), before)
        controls.range.setCurrentIndex(0)
        self.assertIsNone(roll.pitch_range)
        dialog.exec.return_value = QDialog.DialogCode.Rejected
        with patch('lingfeng.ui.controls.PitchRangeDialog', return_value=dialog):
            controls.range.setCurrentIndex(2)
            controls.range.activated.emit(2)
        self.assertEqual(controls.range.currentIndex(), 0)


class RangeViewSynchronizationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        self.addCleanup(temporary.cleanup)
        environment = patch.dict(os.environ, {'LINGFENG_USER_DATA': temporary.name})
        environment.start()
        self.addCleanup(environment.stop)
        from lingfeng.ui.main_window import MainWindow
        self.window = MainWindow(music())
        self.window.timer.stop()
        self.window.autosave.stop()
        self.window.resize(1200, 900)
        self.window.show()
        APP.processEvents()
        self.addCleanup(lambda: (setattr(self.window, 'dirty', False), self.window.close()))

    def test_docked_rolls_share_range_and_floating_range_stays_independent_even_with_time_sync(self):
        window = self.window
        window.roll.set_pitch_range(48, 72)
        self.assertEqual(window.harmony_window.roll.pitch_range, (48, 72))
        self.assertEqual(window.roll.pitches, window.harmony_window.roll.pitches)
        self.assertEqual(window.harmony_window.view_controls.range.currentIndex(), 2)
        window.harmony_window.setFloating(True)
        QTest.qWait(40)
        window.harmony_window.sync.setChecked(True)
        window.harmony_window.roll.set_pitch_range(60, 84)
        self.assertEqual(window.roll.pitch_range, (48, 72))
        self.assertEqual(window.harmony_window.roll.pitch_range, (60, 84))
        window.harmony_window.setFloating(False)
        QTest.qWait(40)
        self.assertEqual(window.harmony_window.roll.pitch_range, (48, 72))

    def test_language_rebuild_preserves_independent_ranges_and_midi(self):
        window = self.window
        window.roll.set_pitch_range(48, 72)
        window.harmony_window.setFloating(True)
        QTest.qWait(40)
        window.harmony_window.roll.set_pitch_range(60, 84)
        before = window.project.to_dict()
        window.change_language('en', False)
        QTest.qWait(40)
        self.assertTrue(window.harmony_window.isFloating())
        self.assertEqual(window.roll.pitch_range, (48, 72))
        self.assertEqual(window.harmony_window.roll.pitch_range, (60, 84))
        self.assertEqual(window.view_controls.range.currentText(), 'C3 – C5')
        self.assertEqual(window.harmony_window.view_controls.range.currentText(), 'C4 – C6')
        self.assertEqual(window.project.to_dict(), before)


if __name__ == '__main__':
    unittest.main()
