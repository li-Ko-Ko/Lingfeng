"""Chord-track recognition can include a second roll without rewriting accompaniment."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lingfeng.music.chord_operations import change_chords, contextual_chord_name
from lingfeng.music.model import Chord, Note, Project
from lingfeng.music.recognition import set_marker, set_recognition_disabled
from lingfeng.platform import chord_preferences
from lingfeng.platform.preferences import load_preferences


def song():
    return Project(chords=[Chord(0, 1920), Chord(1920, 1920), Chord(3840, 3840)],
                   notes=[Note(0, 960, 66)], instrument_notes=[Note(1440, 2400, 71)])


class InstrumentRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(chord_preferences.load_preferences, chord_preferences.settings_dict(include_recognition=True))
        chord_preferences.load_preferences({})

    def test_range_overlap_and_pitch_colors_follow_current_preference(self):
        project = song()
        before = project.to_dict()
        midi = project.harmony_notes()
        self.assertEqual([c.name for c in project.chords], ['C', 'C', 'C'])
        chord_preferences.set_include_instrument_in_recognition(True)
        project.rescan_instrument_recognition()
        self.assertEqual([c.name for c in project.chords], ['Cmaj7', 'Cmaj7', 'C'])
        self.assertEqual(project.chords[0].roman(48), 'Imaj7')
        self.assertEqual(contextual_chord_name(project, project.chords[0]), 'Cmaj7')
        self.assertIn(11, project.chords[1].highlight_pcs)
        self.assertNotIn(6, project.chords[1].highlight_pcs)
        self.assertEqual(project.to_dict(), before)
        self.assertEqual(project.harmony_notes(), midi)
        chord_preferences.set_include_instrument_in_recognition(False)
        project.rescan_instrument_recognition()
        self.assertEqual([c.name for c in project.chords], ['C', 'C', 'C'])

    def test_local_override_roundtrip_and_manual_mark_precedence(self):
        project = song()
        first, second, _ = project.chords
        change_chords(project, {first.id, second.id}, 'recognition_source:1')
        self.assertEqual([first.name, second.name], ['Cmaj7', 'Cmaj7'])
        project = Project.from_dict(project.to_dict())
        first, second, _ = project.chords
        self.assertIs(first.include_instrument_in_recognition, True)
        chord_preferences.set_include_instrument_in_recognition(True)
        change_chords(project, {first.id}, 'recognition_source:0')
        self.assertEqual([first.name, second.name], ['C', 'Cmaj7'])
        change_chords(project, {first.id}, 'recognition_source:default')
        self.assertEqual(first.name, 'Cmaj7')
        set_marker(first, 50, 'm')
        self.assertEqual(first.name, 'Dm')
        set_recognition_disabled(first, False, project)
        self.assertEqual(first.name, 'Cmaj7')
        self.assertIsNone(first.include_instrument_in_recognition)

    def test_instrument_only_analysis_and_changes_do_not_create_harmony_notes(self):
        project = Project(chords=[Chord(0, 3840, notes=[], recognized=False)])
        chord_preferences.set_include_instrument_in_recognition(True)
        before = project.to_dict()
        project.instrument_notes = [Note(0, 960, p) for p in (60, 64, 67)]
        project.rescan_changed_harmony(before)
        self.assertEqual(project.chords[0].name, 'C')
        self.assertEqual(project.harmony_notes(), [])
        before = project.to_dict()
        project.instrument_notes.clear()
        project.rescan_changed_harmony(before)
        self.assertEqual(project.chords[0].name, 'N.C.')

    def test_window_checkbox_and_marquee_override_undo(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication
        from lingfeng.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'tmp') as tmp:
            folder = Path(tmp)
            with patch.dict(os.environ, {'LINGFENG_USER_DATA': str(folder / 'data'),
                                         'LINGFENG_SYNTH_CACHE': str(folder / 'cache.json')}):
                window = MainWindow(song())
                window.timer.stop()
                window.autosave.stop()
                try:
                    self.assertFalse(window.instrument_recognition_action.isChecked())
                    window.instrument_recognition_action.trigger()
                    self.assertEqual(window.project.chords[0].name, 'Cmaj7')
                    self.assertIs(load_preferences(folder / 'data')['include_instrument_in_recognition'], True)
                    self.assertFalse(window.undo_history)
                    lane = window.chord_lane
                    first, second = window.project.chords[:2]
                    lane.editor.selected_chords = {first.id, second.id}
                    menu = lane.context_menu(QPoint(round(lane.x_at(100)), 18), preserve=True)
                    actions = {action.data(): action for action in menu.recognition_source_menu.actions()}
                    self.assertTrue(actions['default'].isChecked())
                    actions['0'].trigger()
                    self.assertEqual([c.name for c in window.project.chords[:2]], ['C', 'C'])
                    window.undo()
                    self.assertEqual([c.name for c in window.project.chords[:2]], ['Cmaj7', 'Cmaj7'])
                    menu.close()
                finally:
                    window.dirty = False
                    window.close()
                    app.processEvents()
