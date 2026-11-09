"""Chord number shortcuts use each selected region's own key and mode."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from lingfeng.music.chord_operations import change_chords
from lingfeng.music.model import Chord, Context, MODES, Project
from lingfeng.platform import chord_preferences
from lingfeng.platform.preferences import load_preferences
from lingfeng.ui.chord_settings_dialog import ChordDegreeShortcutsDialog
from lingfeng.ui.main_window import MainWindow


APP = QApplication.instance() or QApplication([])


class ChordDegreeShortcutTests(unittest.TestCase):
    def test_all_modes_and_degrees_form_complete_chords_in_short_regions(self):
        for mode, scale in MODES.items():
            for degree in range(1, 8):
                for size in (3, 4):
                    with self.subTest(mode=mode, degree=degree, size=size):
                        # A short arpeggio cannot play the full replacement voicing.
                        old = Chord(0, 300, 48, pattern='up')
                        p = Project(chords=[old])
                        p.contexts = [Context(0, p.end, 62, mode)]
                        change_chords(p, {old.id}, f'degree_chord:{degree}:{size}')
                        c = p.chords[0]
                        expected = {(62 + scale[(degree - 1 + i * 2) % 7]) % 12 for i in range(size)}
                        self.assertEqual(c.pcs, expected)
                        self.assertEqual((c.id, c.start, c.end, c.bass), (old.id, old.start, old.end, None))
                        p.validate()

    def test_multiselection_uses_local_key_and_saves_individual_shortcut_sizes(self):
        self.addCleanup(chord_preferences.set_degree_chord_sizes, chord_preferences.degree_chord_sizes())
        folder = Path(self.enterContext(TemporaryDirectory(dir='tmp')))
        self.enterContext(patch('lingfeng.ui.main_window.user_data_dir', return_value=folder))
        first = Chord(0, 3840, 48, pattern='quarters', velocity=85)
        second = Chord(3840, 3840, notes=[], recognized=False)
        p = Project(chords=[first, second])
        p.contexts = [Context(0, 3000), Context(3000, p.end, 53, 'Aeolian')]
        p.fill_chord_gaps()
        w = MainWindow(p)
        w.timer.stop(); w.autosave.stop()

        def close():
            w.dirty = False
            w.close()
            w.deleteLater()
            APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            APP.processEvents()

        self.addCleanup(close)
        w.show(); w.activateWindow(); APP.processEvents()
        lane = w.chord_lane
        ids = {first.id, second.id}
        before = w.project.to_dict()
        lane.setFocus()
        w.chord_selection(ids, lane.editor, lane)
        QTest.keyClick(lane, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w.project.to_dict(), before)
        QTest.keyClick(lane, Qt.Key.Key_2)
        self.assertEqual([c.name for c in w.project.chords[:2]], ['Dm', 'Gdim'])
        self.assertEqual(lane.editor.selected_chords, ids)
        self.assertEqual(len(w.undo_history), 1)
        w.undo()
        self.assertEqual(w.project.to_dict(), before)

        dialog = ChordDegreeShortcutsDialog(w)
        dialog.fields[1].setCurrentIndex(dialog.fields[1].findData(4))
        with patch.object(dialog, 'exec', return_value=QDialog.DialogCode.Accepted), patch(
                'lingfeng.ui.chord_settings_dialog.ChordDegreeShortcutsDialog', return_value=dialog):
            w.chord_degree_shortcuts()
        saved = load_preferences(folder)
        self.assertEqual(saved['degree_chord_sizes'], [3, 4, 3, 3, 3, 3, 3])
        chord_preferences.set_degree_chord_sizes(None)
        chord_preferences.load_preferences(saved)
        self.assertEqual(ChordDegreeShortcutsDialog(w).value(), (3, 4, 3, 3, 3, 3, 3))

        lane.setFocus()
        QTest.keyClick(lane, Qt.Key.Key_2, Qt.KeyboardModifier.KeypadModifier)
        self.assertEqual([c.name for c in w.project.chords[:2]], ['Dm7', 'Gm7b5'])
        self.assertEqual(w.project.chords[0].pattern, 'quarters')
        self.assertEqual(w.project.chords[0].velocity, 85)
        self.assertEqual(w.project.chords[2].id, p.chords[2].id)
