"""Independent creation velocities and selectable, ordered chord shortcuts."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from lingfeng.music.model import Chord, Project, QUALITIES
from lingfeng.platform import chord_preferences as preferences
from lingfeng.platform.preferences import load_preferences, save_preferences
from lingfeng.ui.chord_settings_dialog import ChordSettingsDialog, quality_formula

APP = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parents[1]


class CreationPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.before = preferences.settings_dict()
        self.addCleanup(preferences.set_preferences, self.before)
        preferences.load_preferences({})

    def test_default_velocities_validate_independently_and_ignore_last_edit(self):
        preferences.load_preferences({'default_velocities': {'melody': 47, 'harmony': 101},
                                      'chord_edit_options': {'velocity': 3}})
        self.assertEqual(preferences.default_velocity('melody'), 47)
        self.assertEqual(preferences.default_velocity('harmony'), 101)
        self.assertEqual(preferences.default_velocity('chords'), 101)
        for bad in (True, 0, 128, '80', None, float('nan')):
            preferences.load_preferences({'default_velocities': {'melody': bad, 'harmony': 60}})
            self.assertEqual(preferences.default_velocity('melody'), 92)
            self.assertEqual(preferences.default_velocity('harmony'), 60)
        preferences.load_preferences({'chord_edit_options': {'velocity': 127}})
        self.assertEqual(preferences.default_velocity('harmony'), 72)

    def test_legacy_order_migrates_without_enabling_the_extended_catalog(self):
        preferences.load_preferences({'chord_order': ['m7', 'add9', 'm7', {}, 'unknown', '7']})
        selected = preferences.quick_qualities()
        self.assertEqual(selected[:3], ['m7', 'add2', '7'])
        self.assertEqual(set(selected), set(preferences.DEFAULT_QUICK_QUALITIES))

    def test_selection_order_empty_selection_and_returned_values_are_independent(self):
        preferences.load_preferences({'quick_chord_qualities': ['7', 'm', '7', {}, 'unknown']})
        self.assertEqual(preferences.quick_qualities(), ['7', 'm'])
        copy = preferences.settings_dict()
        copy['default_velocities']['melody'] = 1
        copy['quick_chord_qualities'].append('dim')
        self.assertEqual(preferences.default_velocity('melody'), 92)
        self.assertEqual(preferences.quick_qualities(), ['7', 'm'])
        preferences.load_preferences({'quick_chord_qualities': []})
        self.assertEqual(preferences.quick_qualities(), [])

    def test_preferences_roundtrip_preserves_velocity_selection_order_and_unknown_fields(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as folder:
            preferences.set_preferences({'default_velocities': {'melody': 53, 'harmony': 107},
                                         'quick_chord_qualities': ['dim7', 'm', '7']})
            save_preferences(folder, dict(preferences.settings_dict(), future={'keep': True}))
            preferences.load_preferences({})
            saved = load_preferences(folder)
            preferences.load_preferences(saved)
            self.assertEqual(preferences.default_velocity('melody'), 53)
            self.assertEqual(preferences.default_velocity('harmony'), 107)
            self.assertEqual(preferences.quick_qualities(), ['dim7', 'm', '7'])
            self.assertEqual(saved['future'], {'keep': True})

    def test_both_rolls_use_their_default_for_draw_and_double_click_creation(self):
        from lingfeng.ui.piano_roll import PianoRoll
        preferences.set_preferences({'default_velocities': {'melody': 49, 'harmony': 103}})
        for role, expected in (('melody', 49), ('harmony', 103)):
            with self.subTest(role=role):
                roll = PianoRoll(Project(), role=role)
                self.addCleanup(roll.close)
                roll.resize(1000, 640)
                roll.show()
                APP.processEvents()
                roll.center_pitch(60)
                APP.processEvents()
                emitted = []
                roll.noteAdded.connect(emitted.append)
                roll.tool = 'draw'
                point = QPoint(round(roll.x_at(960) + 8), round(roll.y_at(60) + roll.row_height / 2))
                QTest.mouseClick(roll.viewport(), Qt.MouseButton.LeftButton, pos=point)
                roll.tool = 'smart'
                point.setX(round(roll.x_at(1920) + 8))
                QTest.mouseDClick(roll.viewport(), Qt.MouseButton.LeftButton, pos=point)
                self.assertEqual([note.velocity for note in emitted], [expected, expected])
                roll.close()


class ChordSettingsDialogTests(unittest.TestCase):
    def setUp(self):
        self.before = preferences.settings_dict()
        self.addCleanup(preferences.set_preferences, self.before)
        preferences.load_preferences({})
        self.dialog = ChordSettingsDialog()
        self.addCleanup(self.dialog.close)

    def item_for(self, code):
        return next(self.dialog.list.item(row) for row in range(self.dialog.list.count())
                    if self.dialog.list.item(row).data(Qt.ItemDataRole.UserRole) == code)

    def test_cancel_discards_quick_choices(self):
        before = preferences.settings_dict()
        self.dialog.set_all(False)
        self.item_for('m').setCheckState(Qt.CheckState.Checked)
        self.dialog.reject()
        self.assertEqual(preferences.settings_dict(), before)
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Rejected)

    def test_selection_reorder_and_confirmation_apply_only_the_dialog_result(self):
        self.dialog.set_all(False)
        self.item_for('m').setCheckState(Qt.CheckState.Checked)
        seventh = self.item_for('7')
        seventh.setCheckState(Qt.CheckState.Checked)
        self.dialog.list.setCurrentItem(seventh)
        self.dialog.move_item(-1)
        self.assertEqual(self.dialog.value()['quick_chord_qualities'], ['7', 'm'])
        self.dialog.accept()
        self.assertEqual(preferences.default_velocity('harmony'), 72)
        preferences.set_preferences(self.dialog.value())
        self.assertEqual(preferences.quick_qualities(), ['7', 'm'])
        self.assertEqual(preferences.default_velocity('melody'), 92)
        self.assertEqual(preferences.default_velocity('harmony'), 72)

    def test_full_reference_contains_each_supported_quality_and_keeps_written_degrees(self):
        self.assertEqual(self.dialog.preview.rowCount(), len(QUALITIES))
        self.assertEqual(self.dialog.list.count(), len(QUALITIES))
        self.assertEqual(quality_formula('dim7'), '1 b3 b5 bb7')
        self.assertEqual(quality_formula('maj9'), '1 3 5 7 9')
        self.assertEqual(quality_formula('add2'), '1 2 3 5')
        for row, code in enumerate(QUALITIES):
            self.assertEqual(self.dialog.preview.item(row, 0).text(), 'C' + code)
            self.assertEqual(self.dialog.preview.item(row, 2).text(), quality_formula(code))
        self.dialog.preview_root.setCurrentIndex(self.dialog.preview_root.findData(7))
        self.assertTrue(all(self.dialog.preview.item(row, 0).text().startswith('G')
                            for row in range(self.dialog.preview.rowCount())))
        self.dialog.search.setText('bb7')
        visible = [self.dialog.preview.item(row, 2).text() for row in range(self.dialog.preview.rowCount())
                   if not self.dialog.preview.isRowHidden(row)]
        self.assertTrue(visible)
        self.assertTrue(all('bb7' in formula for formula in visible))

    def test_reset_restores_quick_selection_without_changing_velocity_preferences(self):
        preferences.set_preferences({'default_velocities': {'harmony': 86}})
        self.dialog.set_all(False)
        self.assertEqual(self.dialog.value()['quick_chord_qualities'], [])
        self.dialog.reset_quick()
        self.assertEqual(self.dialog.value()['quick_chord_qualities'], list(preferences.DEFAULT_QUICK_QUALITIES))
        self.assertEqual(preferences.default_velocity('harmony'), 86)


class MainWindowCreationPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.before = preferences.settings_dict()
        self.addCleanup(preferences.set_preferences, self.before)
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        environment = patch.dict(os.environ, {'LINGFENG_USER_DATA': str(self.folder)})
        environment.start()
        self.addCleanup(environment.stop)

    def window(self):
        from lingfeng.ui.main_window import MainWindow
        window = MainWindow(Project())
        window.timer.stop()
        window.autosave.stop()
        self.addCleanup(lambda: (setattr(window, 'dirty', False), window.close()))
        return window

    def test_main_window_confirm_saves_selection_and_both_velocities_for_restart(self):
        save_preferences(self.folder, {'chord_edit_options': {'velocity': 1}})
        window = self.window()
        chosen = {'default_velocities': {'melody': 49, 'harmony': 103},
                  'quick_chord_qualities': ['maj9', '7', 'm']}
        dialog = Mock()
        dialog.exec.return_value = QDialog.DialogCode.Accepted
        dialog.value.return_value = chosen
        with patch('lingfeng.ui.chord_settings_dialog.ChordSettingsDialog', return_value=dialog):
            window.chord_preferences()
        saved = load_preferences(self.folder)
        self.assertEqual(saved['default_velocities'], chosen['default_velocities'])
        self.assertEqual(saved['quick_chord_qualities'], chosen['quick_chord_qualities'])
        window.dirty = False
        window.close()
        preferences.load_preferences({})
        reopened = self.window()
        self.assertEqual(preferences.settings_dict(), chosen)
        from lingfeng.ui.dialogs import ChordDialog
        for old_velocity in (1, 127):
            editor = ChordDialog(Chord(0, 960, velocity=old_velocity), reopened.project,
                                 defaults={'velocity': old_velocity})
            try:
                self.assertEqual(editor.velocity.value(), 103)
                editor.velocity.setValue(old_velocity)
                self.assertNotIn('velocity', editor.options())
            finally:
                editor.close()

    def test_main_window_rejected_settings_never_apply_or_save_dialog_values(self):
        window = self.window()
        before = preferences.settings_dict()
        dialog = Mock()
        dialog.exec.return_value = QDialog.DialogCode.Rejected
        dialog.value.side_effect = AssertionError('Cancelled values must not be read')
        with patch('lingfeng.ui.chord_settings_dialog.ChordSettingsDialog', return_value=dialog), \
                patch.object(window, 'save_preferences') as save:
            window.chord_preferences()
            save.assert_not_called()
        self.assertEqual(preferences.settings_dict(), before)


if __name__ == '__main__':
    unittest.main()
