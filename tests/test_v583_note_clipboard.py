import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QMenu, QMessageBox

from lingfeng.music.model import Chord, Context, Note, Project
from lingfeng.platform import chord_preferences
from lingfeng.platform.i18n import tr
from lingfeng.ui.main_window import MainWindow


class NoteClipboardTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        project = Project(notes=[Note(0, 480, 60, 73)], instrument_notes=[Note(0, 360, 71, 80)],
                          chords=[Chord(0, 3840, notes=[Note(0, 720, 48, 85)])])
        self.window = MainWindow(project)
        self.window.timer.stop()
        self.window.autosave.stop()

    def tearDown(self):
        self.window.dirty = False
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def action(self, roll, label, tick=1920):
        menu = QMenu(roll)
        roll.selection_menu(menu, tick)
        self.addCleanup(menu.deleteLater)
        return next(a for a in menu.actions() if a.text().split('\t')[0] == tr(label))

    def test_context_cut_and_paste_select_the_new_note_in_each_roll(self):
        window = self.window
        for role in ('vocal', 'instrument', 'harmony'):
            with self.subTest(role=role):
                if role == 'harmony':
                    roll = window.harmony_window.roll
                else:
                    window.switch_melody_track(int(role == 'instrument'))
                    roll = window.roll
                original = roll.notes[0]
                roll.selected_ids = {original.id}
                before = len(window.undo_history)
                cut = self.action(roll, '剪切所选音符')
                self.assertTrue(cut.isEnabled())
                self.assertEqual(cut.property('shortcutCommand'), 'cut_selection')
                cut.trigger()
                self.assertEqual(roll.selected_ids, set())
                self.assertEqual(roll.notes, [])
                self.assertEqual(window.clipboard_kind, 'cut_notes')
                self.assertFalse(self.action(roll, '剪切所选音符').isEnabled())
                paste = self.action(roll, '在此粘贴音符')
                self.assertTrue(paste.isEnabled())
                paste.trigger()
                self.assertEqual(len(roll.notes), 1)
                pasted = roll.notes[0]
                self.assertEqual((pasted.start, pasted.duration, pasted.pitch, pasted.velocity),
                                 (1920, original.duration, original.pitch, original.velocity))
                self.assertNotEqual(pasted.id, original.id)
                self.assertEqual(roll.selected_ids, {pasted.id})
                self.assertEqual(roll.selected_note, pasted.id)
                self.assertEqual(len(window.undo_history), before+2)
        self.assertEqual([n.pitch for n in window.project.notes], [60])
        self.assertEqual([n.pitch for n in window.project.instrument_notes], [71])

    def test_copy_between_melody_tabs_targets_current_track(self):
        window = self.window
        roll = window.roll
        original = roll.notes[0]
        roll.selected_ids = {original.id}
        self.action(roll, '复制所选音符').trigger()
        window.switch_melody_track(1)
        self.action(roll, '在此粘贴音符').trigger()
        self.assertEqual(window.project.notes, [original])
        inserted = window.project.instrument_notes[-1]
        self.assertEqual((inserted.start, inserted.pitch), (1920, original.pitch))
        self.assertEqual(roll.selected_ids, {inserted.id})
        window.switch_melody_track(0)
        self.assertEqual(roll.selected_ids, {original.id})

    def test_copied_notes_use_the_destination_roll_default_velocity(self):
        self.addCleanup(chord_preferences.load_preferences,
                        chord_preferences.settings_dict(include_recognition=True))
        chord_preferences.set_preferences({'default_velocities': {'melody': 64, 'instrument': 75, 'harmony': 96}})
        window = self.window
        roll = window.roll
        original = roll.notes[0]
        roll.selected_ids = {original.id}
        self.action(roll, '复制所选音符').trigger()
        self.action(roll, '在此粘贴音符', tick=960).trigger()
        self.assertEqual(window.project.notes[-1].velocity, 64)
        window.switch_melody_track(1)
        self.action(roll, '在此粘贴音符').trigger()
        self.assertEqual(window.project.instrument_notes[-1].velocity, 75)
        harmony = window.harmony_window.roll
        with patch.object(window, 'active_roll', return_value=harmony), \
                patch.object(harmony, 'position_tick', return_value=1920):
            window.paste_selection()
        self.assertEqual(harmony.notes[-1].velocity, 96)
        self.assertEqual(window.project.notes[0], original)
        self.assertEqual(window.note_clipboard.notes[0].velocity, original.velocity)

    def test_paste_selects_all_surviving_transformed_fragments(self):
        project = Project(notes=[Note(0, 960, 60), Note(480, 240, 62)],
                          contexts=[Context(0, 480), Context(480, 960, 50), Context(960, 30720)])
        window = self.window
        window.replace_project(project)
        roll = window.roll
        roll.selected_ids = {n.id for n in roll.notes}
        window.note_command(roll, 'copy:retrograde')
        window.note_command(roll, 'paste', 1920)
        pasted = [n for n in roll.notes if n.start >= 1920]
        self.assertEqual([(n.start, n.duration, n.pitch) for n in pasted],
                         [(1920, 240, 60), (2160, 240, 60), (2400, 480, 60)])
        self.assertEqual(roll.selected_ids, {n.id for n in pasted})

    def test_failed_cut_and_boundary_paste_preserve_clipboard_and_history(self):
        window = self.window
        roll = window.roll
        roll.selected_ids = {roll.notes[0].id}
        window.note_command(roll, 'copy:direct')
        clipboard = window.note_clipboard
        with patch.object(window, 'edit_notes', return_value=False):
            self.action(roll, '剪切所选音符').trigger()
        self.assertIs(window.note_clipboard, clipboard)
        before = window.project.to_dict()
        with patch.object(QMessageBox, 'warning') as warning:
            window.note_command(roll, 'paste', window.project.end)
        warning.assert_not_called()
        self.assertEqual(window.project.to_dict(), before)
        self.assertFalse(window.undo_history)
        self.assertEqual(roll.selected_ids, {roll.notes[0].id})


if __name__ == '__main__':
    unittest.main()
