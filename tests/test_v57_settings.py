"""User-wide rhythm recognition controls, persistence and every chord surface."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from lingfeng.audio import velocity
from lingfeng.audio.midi import event_list
from lingfeng.music.model import Chord, PATTERNS, Project
from lingfeng.music.rhythm import analyze, label
from lingfeng.platform import chord_preferences, context_menu_preferences, i18n, rhythm_preferences
from lingfeng.platform.preferences import load_preferences, save_preferences
from lingfeng.ui import theme
from lingfeng.ui.dialogs import ChordDialog
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.piano_roll import PianoRoll

APP = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parents[1]


def song():
    project = Project()
    project.chords = [Chord(i * 3840, 3840, pattern='quarters') for i in range(3)]
    for chord in project.chords:
        chord.materialize()
    project.chords[1].custom_rhythm = True
    project.chords[2].recognition_disabled = True
    return project


class RecordingPainter:
    """Capture the actual card strings while drawing to a real Qt device."""
    def __init__(self, painter):
        self.painter = painter
        self.texts = []

    def __getattr__(self, name):
        return getattr(self.painter, name)

    def drawText(self, *args):
        self.texts.append(args[-1])
        return self.painter.drawText(*args)


class RhythmSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        environment = patch.dict(os.environ, {
            'LINGFENG_USER_DATA': str(self.folder / 'user-data'),
            'LINGFENG_SYNTH_CACHE': str(self.folder / 'synth-index.json'),
        })
        environment.start(); self.addCleanup(environment.stop)
        self.user_data = self.folder / 'user-data'
        self.addCleanup(rhythm_preferences.load_preferences, rhythm_preferences.settings_dict())
        self.addCleanup(chord_preferences.set_preferences, chord_preferences.settings_dict())
        self.addCleanup(context_menu_preferences.set_preferences, context_menu_preferences.settings_dict())
        self.addCleanup(velocity.set_options, velocity.options())
        self.addCleanup(i18n.set_language, i18n.LANGUAGE)
        self.addCleanup(theme.apply_theme, theme.is_dark())
        self.addCleanup(theme.set_roll_palettes, copy.deepcopy(theme.CUSTOM_PALETTES))
        self.addCleanup(theme.set_roll_coloring, copy.deepcopy(theme.ROLL_COLORING))
        self.addCleanup(theme.set_note_degrees, theme.SHOW_NOTE_DEGREES)
        self.addCleanup(theme.set_accidental_preference, theme.ACCIDENTAL_PREFERENCE)
        rhythm_preferences.load_preferences({})
        i18n.set_language('zh')
        self.windows = []
        self.addCleanup(self.close_windows)

    def close_windows(self):
        for window in self.windows:
            window.dirty = False; window.close(); window.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def window(self, project=None):
        window = MainWindow(project or song())
        window.timer.stop(); window.autosave.stop()
        self.windows.append(window)
        return window

    def menu(self, lane, chord):
        lane.editor.selected_chords = {chord.id}
        menu = lane.context_menu(QPoint(round(lane.x_at(chord.start + 100)), 18), preserve=True)
        self.addCleanup(menu.close)
        return menu

    def test_default_and_malformed_preferences_keep_existing_recognition_enabled(self):
        for values in (None, {}, {'rhythm_recognition': None}, {'rhythm_recognition': 0},
                       {'rhythm_recognition': 'false'}, {'rhythm_recognition': []}):
            with self.subTest(values=values):
                rhythm_preferences.set_enabled(False)
                rhythm_preferences.load_preferences(values)
                self.assertTrue(rhythm_preferences.enabled())
        rhythm_preferences.load_preferences({'rhythm_recognition': False})
        self.assertEqual(rhythm_preferences.settings_dict(), {'rhythm_recognition': False})

    def test_real_checkbox_saves_restart_and_language_switch_without_editing_music(self):
        save_preferences(self.user_data, {'language': 'zh', 'unknown_future_option': {'kept': True}})
        window = self.window()
        action = window.rhythm_recognition_action
        self.assertTrue(action.isCheckable()); self.assertTrue(action.isChecked())
        before = copy.deepcopy(window.project.to_dict()); midi = event_list(window.project)
        undo = list(window.undo_history); redo = list(window.redo_history); dirty = window.dirty
        action.trigger()
        self.assertFalse(rhythm_preferences.enabled()); self.assertFalse(action.isChecked())
        saved = load_preferences(self.user_data)
        self.assertIs(saved['rhythm_recognition'], False)
        self.assertEqual(saved['unknown_future_option'], {'kept': True})
        self.assertEqual(window.project.to_dict(), before)
        self.assertEqual(event_list(window.project), midi)
        self.assertEqual((window.undo_history, window.redo_history, window.dirty), (undo, redo, dirty))
        window.change_language('en')
        self.assertFalse(window.rhythm_recognition_action.isChecked())
        self.assertNotEqual(window.rhythm_recognition_action.text(), '节奏型识别')
        self.assertEqual(window.project.to_dict(), before)
        self.assertFalse(rhythm_preferences.enabled())
        reopened = self.window(Project.from_dict(before))
        self.assertFalse(reopened.rhythm_recognition_action.isChecked())
        self.assertFalse(rhythm_preferences.enabled())
        reopened.rhythm_recognition_action.trigger()
        self.assertTrue(rhythm_preferences.enabled())
        self.assertIs(load_preferences(self.user_data)['rhythm_recognition'], True)
        self.assertEqual(reopened.project.to_dict(), before)

    def test_all_chord_lanes_show_effective_off_without_changing_individual_switches(self):
        window = self.window()
        before = copy.deepcopy(window.project.to_dict())
        flags = [(c.custom_rhythm, c.recognition_disabled) for c in window.project.chords]
        window.rhythm_recognition_action.trigger()
        lanes = (window.chord_lane, window.roll.lane, window.harmony_window.top_lane)
        for lane in lanes:
            for chord in window.project.chords:
                with self.subTest(lane=lanes.index(lane), chord=chord.start):
                    menu = self.menu(lane, chord)
                    self.assertTrue(menu.custom_rhythm_action.isChecked())
                    self.assertFalse(menu.custom_rhythm_action.isEnabled())
                    self.assertTrue(menu.recognition_action.isEnabled())
                    self.assertEqual(menu.recognition_action.isChecked(), chord.recognition_disabled)
                    self.assertFalse(any(action.isChecked() for action in menu.pattern_menu.actions()
                                         if action is not menu.custom_rhythm_action))
                    self.assertEqual(label(chord, window.project), '')
        self.assertEqual(window.project.to_dict(), before)
        window.rhythm_recognition_action.trigger()
        self.assertEqual([(c.custom_rhythm, c.recognition_disabled) for c in window.project.chords], flags)
        for lane in lanes:
            plain, custom, paused = [self.menu(lane, chord) for chord in window.project.chords]
            self.assertTrue(plain.custom_rhythm_action.isEnabled())
            self.assertFalse(plain.custom_rhythm_action.isChecked())
            self.assertTrue(custom.custom_rhythm_action.isEnabled())
            self.assertTrue(custom.custom_rhythm_action.isChecked())
            self.assertFalse(paused.custom_rhythm_action.isEnabled())
            self.assertTrue(paused.custom_rhythm_action.isChecked())
        self.assertEqual(window.project.to_dict(), before)

    def test_dialog_has_no_recognized_rhythm_while_global_switch_is_off(self):
        project = song(); chord = project.chords[0]
        before = copy.deepcopy(project.to_dict())
        self.assertEqual(analyze(chord, project).pattern, 'quarters')
        rhythm_preferences.set_enabled(False)
        dialog = ChordDialog(chord, project)
        self.addCleanup(dialog.close)
        self.assertIsNone(dialog.recognized_rhythm)
        dialog.reject()
        self.assertEqual(project.to_dict(), before)
        rhythm_preferences.set_enabled(True)
        restored = ChordDialog(chord, project)
        self.addCleanup(restored.close)
        self.assertEqual(restored.recognized_rhythm.pattern, 'quarters')
        self.assertEqual(project.to_dict(), before)

    def test_legacy_compact_dialog_without_rebuild_preserves_actual_notes_when_off(self):
        rhythm_preferences.set_enabled(False)
        for edit_symbol in (False, True):
            with self.subTest(edit_symbol=edit_symbol):
                project = Project()
                chord = Chord(0, 1920, pattern='up', gate=.43, velocity=49)
                project.chords = [chord]
                self.assertIsNone(chord.notes)
                before = copy.deepcopy(chord)
                expected = copy.deepcopy(chord); expected.materialize()
                if edit_symbol:
                    from lingfeng.music.chord_operations import change_root, change_quality
                    change_root(expected, 7, project, regenerate_notes=False)
                    change_quality(expected, 'm', project, regenerate_notes=False)
                signature = lambda c: [(n.id, n.event_id, n.start, n.duration, n.pitch, n.velocity)
                                        for n in c.render_notes()]
                expected_notes = signature(expected)
                dialog = ChordDialog(chord, project)
                self.addCleanup(dialog.close)
                dialog.regenerate.setChecked(False)
                dialog.duration.setValue(6)
                dialog.gate.setValue(97); dialog.octave.setValue(2); dialog.velocity.setValue(111)
                if edit_symbol:
                    dialog.root.setCurrentIndex(dialog.root.findData(7))
                    dialog.quality.setCurrentIndex(dialog.quality.findData('m'))
                self.assertFalse(dialog.regenerate.isChecked())
                edited = dialog.value()
                self.assertIsNotNone(edited.notes)
                self.assertEqual(signature(edited), expected_notes)
                self.assertEqual((edited.duration, edited.gate, edited.octave, edited.velocity),
                                 (5760, .97, 2, 111))
                project.put_chord(edited)
                result = next(c for c in project.chords if c.id == chord.id)
                self.assertEqual(signature(result), expected_notes)
                self.assertEqual(chord, before)
                self.assertFalse(result.custom_rhythm)
                self.assertEqual(result.root % 12, 7 if edit_symbol else 0)
                self.assertEqual(result.quality, 'm' if edit_symbol else '')

    def test_floating_independent_harmony_toggle_preserves_selection_camera_and_loop(self):
        window = self.window()
        harmony = window.harmony_window
        harmony.setFloating(True); harmony.show(); APP.processEvents()
        harmony.sync.setChecked(False)
        self.assertFalse(window.rolls_linked())
        chord = window.project.chords[0]
        harmony.select_chord(chord.id, locate=False)
        self.assertIn(i18n.tr(PATTERNS['quarters']), harmony.summary.toolTip())
        roll = harmony.roll
        window.set_loop_range((960, 4800))
        roll.selection = [[100, 200]]
        roll.update_ranges()
        roll.horizontalScrollBar().setValue(270)
        roll.verticalScrollBar().setValue(500)
        before = (copy.deepcopy(roll.selection), roll.horizontalScrollBar().value(),
                  roll.verticalScrollBar().value(), copy.deepcopy(window.loop_range),
                  window.loop.isChecked(), harmony.current_id, roll.selected_chord)
        for enabled in (False, True):
            window.rhythm_recognition_action.trigger()
            self.assertEqual(rhythm_preferences.enabled(), enabled)
            self.assertEqual((roll.selection, roll.horizontalScrollBar().value(),
                              roll.verticalScrollBar().value(), window.loop_range,
                              window.loop.isChecked(), harmony.current_id, roll.selected_chord), before)
            self.assertEqual(i18n.tr(PATTERNS['quarters']) in harmony.summary.toolTip(), enabled)
            self.assertFalse(harmony.summary.toolTip().endswith(' · '))

    def test_card_text_hides_patterns_and_cached_paint_reacts_to_global_switch(self):
        project = song(); roll = PianoRoll(project)
        self.addCleanup(roll.close)
        roll.resize(1000, 500); roll.show(); APP.processEvents()
        lane = roll.lane
        chord = project.chords[0]
        def card_text():
            image = QImage(lane.size(), QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
            painter = QPainter(image); recording = RecordingPainter(painter)
            try:
                lane.paint_card(recording, chord, chord)
            finally:
                painter.end()
            return recording.texts
        enabled_text = card_text()
        self.assertTrue(any(i18n.tr(PATTERNS['quarters']) in text for text in enabled_text), enabled_text)
        lane.grab(); renders = lane.cache_renders
        lane.grab(); self.assertEqual(lane.cache_renders, renders)
        rhythm_preferences.set_enabled(False)
        off_text = card_text()
        self.assertNotEqual(enabled_text, off_text)
        self.assertEqual(off_text[-1], 'C')
        self.assertTrue(all(not text.endswith(' · ') for text in off_text))
        lane.grab(); self.assertGreater(lane.cache_renders, renders)
        off_renders = lane.cache_renders
        lane.grab(); self.assertEqual(lane.cache_renders, off_renders)
        rhythm_preferences.set_enabled(True)
        self.assertEqual(card_text(), enabled_text)
        lane.grab(); self.assertGreater(lane.cache_renders, off_renders)


if __name__ == '__main__':
    unittest.main()
