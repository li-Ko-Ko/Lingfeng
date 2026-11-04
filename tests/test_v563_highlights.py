"""Manual symbols guide melody-roll matching without rewriting performed MIDI."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QEvent, QPointF
from PySide6.QtWidgets import QApplication, QDialog

from lingfeng.audio.midi import event_list, export_midi
from lingfeng.audio.midi_import import read_midi
from lingfeng.engraving.notation import is_chord_tone
from lingfeng.music.model import Chord, Note, Project
from lingfeng.music.recognition import set_marker, set_recognition_disabled
from lingfeng.ui import theme
from lingfeng.ui.dialogs import ChordMarkerDialog
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.piano_roll import PianoRoll

APP = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parents[1]


def song():
    project = Project()
    project.notes = [Note(0, 1920, 64, 89), Note(1920, 1920, 62, 97)]
    project.chords = [Chord(0, 3840, notes=[Note(0, 3840, pitch, velocity)
                                         for pitch, velocity in ((36, 47), (48, 81), (52, 93), (55, 102))])]
    return project


def performed(chord):
    return [(n.id, n.event_id, n.start, n.duration, n.pitch, n.velocity) for n in chord.render_notes()]


def inside(project, tick=120, role='melody'):
    cache = {}
    return {pitch for pitch in range(12) if project.category(pitch, tick, role, cache) in ('both', 'chord')}


class SymbolMatchingTests(unittest.TestCase):
    def test_marked_root_quality_and_slash_bass_define_matching_without_changing_midi(self):
        for root, quality, bass, expected in ((2, 'm7', 6, {0, 2, 5, 6, 9}),
                                             (6, 'aug', 11, {2, 6, 10, 11}),
                                             (2, 'no5', 1, {1, 2, 6})):
            with self.subTest(root=root, quality=quality, bass=bass):
                project = song(); chord = project.chords[0]
                before = performed(chord); events = event_list(project)
                expected_notes = [(n.start, n.duration, n.pitch, n.velocity) for n in chord.render_notes()]
                set_marker(chord, root, quality, bass)
                self.assertEqual(inside(project), expected)
                self.assertEqual(chord.pcs, {0, 4, 7})
                self.assertEqual(performed(chord), before)
                self.assertEqual(event_list(project), events)
                # Export carries the new display symbol as marker text, while
                # every performed note-on/off event remains unchanged.
                with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as folder:
                    path = Path(folder) / 'marked.mid'; export_midi(project, path)
                    exported = read_midi(path)
                self.assertEqual([(n.start, n.duration, n.pitch, n.velocity) for n in exported.tracks[2].notes], expected_notes)
                self.assertEqual({pitch for pitch in range(12) if is_chord_tone(project, pitch, 120)}, expected)
                self.assertEqual({pitch for pitch in range(12) if is_chord_tone(project, pitch + 72, 120)}, expected)

    def test_unmarked_incomplete_or_unrecognized_notes_keep_actual_pitch_classes(self):
        for recognized in (True, False):
            with self.subTest(recognized=recognized):
                project = Project(); project.chords = [Chord(0, 3840, notes=[Note(0, 3840, 60), Note(0, 3840, 64)], recognized=recognized)]
                self.assertEqual(inside(project), {0, 4})
                set_marker(project.chords[0], 0, '')
                self.assertEqual(inside(project), {0, 4, 7})

    def test_short_unmarked_arpeggio_matches_only_its_performed_tones(self):
        project = Project(); project.chords = [Chord(0, 240, pattern='up')]
        self.assertEqual(inside(project), {0})
        set_marker(project.chords[0], 0, '')
        self.assertEqual(inside(project), {0, 4, 7})
        set_recognition_disabled(project.chords[0], False, project)
        self.assertEqual(inside(project), {0})

    def test_empty_manual_marker_has_symbol_tones_and_survives_native_save(self):
        project = Project(); project.chords = [Chord(0, 3840, notes=[], recognized=False)]
        chord = project.chords[0]
        self.assertEqual(inside(project), set())
        set_marker(chord, 1, 'm7', 8)
        expected = {1, 4, 8, 11}
        self.assertEqual(inside(project), expected)
        self.assertEqual(chord.pcs, set()); self.assertEqual(project.harmony_notes(), [])
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as folder:
            path = Path(folder) / 'empty-marker.lfs'; project.save(path)
            restored = Project.load(path)
        self.assertEqual(inside(restored), expected)
        self.assertEqual(restored.chords[0].notes, [])
        self.assertEqual(event_list(restored), [])

    def test_disabled_unmarked_and_resumed_recognition_use_performed_notes(self):
        project = song(); chord = project.chords[0]; before = performed(chord)
        set_recognition_disabled(chord, True, project)
        self.assertFalse(chord.marked)
        self.assertEqual(inside(project), {0, 4, 7})
        set_marker(chord, 2, 'm7', 6)
        self.assertEqual(inside(project), {0, 2, 5, 6, 9})
        set_recognition_disabled(chord, False, project)
        self.assertFalse(chord.marked or chord.recognition_disabled)
        self.assertEqual(inside(project), {0, 4, 7})
        self.assertEqual(performed(chord), before)

    def test_harmony_roll_matching_still_uses_overlapping_melody_notes(self):
        project = song(); before = inside(project, role='harmony')
        self.assertEqual(before, {2, 4})
        set_marker(project.chords[0], 1, '7', 6)
        for tick in (0, 1919, 1920, 3839):
            self.assertEqual(inside(project, tick, 'harmony'), before)
        self.assertEqual(inside(project, 3840, 'harmony'), set())


class RollRenderingTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(theme.apply_theme, theme.is_dark())
        self.addCleanup(theme.set_roll_coloring, copy.deepcopy(theme.ROLL_COLORING))
        self.addCleanup(theme.set_roll_palettes, copy.deepcopy(theme.CUSTOM_PALETTES))
        self.addCleanup(theme.set_note_degrees, theme.SHOW_NOTE_DEGREES)
        theme.set_roll_coloring({}); theme.set_roll_palettes({}); theme.set_note_degrees(False)

    def roll(self, project):
        roll = PianoRoll(project); self.addCleanup(roll.close)
        roll.resize(1000, 650); roll.selection = []; roll.chord_highlights = set()
        roll.show(); APP.processEvents(); roll.center_pitch(64); roll.refresh(); APP.processEvents()
        return roll

    def image(self, roll):
        APP.processEvents()
        return roll.viewport().grab().toImage()

    def pixel(self, roll, image, pitch, tick):
        ratio = image.devicePixelRatio()
        return image.pixelColor(round(roll.x_at(tick) * ratio), round((roll.y_at(pitch) + roll.row_height / 2) * ratio)).name()

    def test_background_and_note_colors_follow_markers_in_both_themes(self):
        for dark in (False, True):
            with self.subTest(dark=dark):
                theme.apply_theme(dark)
                project = song(); roll = self.roll(project); before = self.image(roll)
                self.assertEqual(self.pixel(roll, before, 64, 900), theme.roll_color('both', 'note').name())
                self.assertEqual(self.pixel(roll, before, 64, 3000), theme.roll_color('both').name())
                self.assertEqual(self.pixel(roll, before, 62, 1000), theme.roll_color('scale').name())
                set_marker(project.chords[0], 2, 'm7', 6); roll.set_project(project); roll.selection = []; roll.refresh()
                after = self.image(roll)
                self.assertEqual(self.pixel(roll, after, 64, 900), theme.roll_color('scale', 'note').name())
                self.assertEqual(self.pixel(roll, after, 64, 3000), theme.roll_color('scale').name())
                self.assertEqual(self.pixel(roll, after, 62, 1000), theme.roll_color('both').name())
                self.assertEqual(self.pixel(roll, after, 62, 2800), theme.roll_color('both', 'note').name())

    def test_selected_chord_overlay_uses_marker_tones_including_empty_markers(self):
        for empty in (False, True):
            with self.subTest(empty=empty):
                project = song(); chord = project.chords[0]
                if empty:chord.notes = []; chord.recognized = False
                roll = self.roll(project); roll.chord_highlights = {chord.id}
                set_marker(chord, 2, 'm7', 6); roll.set_project(project); roll.selection = []; roll.refresh()
                highlighted = self.image(roll)
                self.assertEqual(self.pixel(roll, highlighted, 64, 3000), theme.roll_color('scale').name())
                self.assertNotEqual(self.pixel(roll, highlighted, 66, 3000), theme.roll_color('chord').name())
                roll.chord_highlights = set(); roll.refresh(); plain = self.image(roll)
                self.assertEqual(self.pixel(roll, plain, 66, 3000), theme.roll_color('chord').name())

    def test_mark_undo_redo_resume_and_reopen_refresh_cached_colors_and_keep_note_hits(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as folder:
            with patch('lingfeng.ui.main_window.user_data_dir', return_value=Path(folder)):
                window = MainWindow(song()); window.timer.stop(); window.autosave.stop()
                def close():
                    window.dirty = False; window.close(); window.deleteLater()
                    APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                self.addCleanup(close)
                roll = window.roll; window.show(); window.resize(1250, 900)
                window.melody_window.setFloating(True); window.melody_window.resize(1000, 650)
                APP.processEvents(); roll.center_pitch(64); roll.selection = []; roll.refresh()
                chord_id = window.project.chords[0].id
                original = event_list(window.project); self.image(roll); initial_key = roll.layer_key
                initial_hits = [(n.id, tuple((r.x(), r.y(), r.width(), r.height()))) for r, n in roll.hit_notes]
                def accept(dialog):
                    dialog.root.setCurrentIndex(dialog.root.findData(2)); dialog.quality.setCurrentIndex(dialog.quality.findData('m7'))
                    dialog.bass.setCurrentIndex(dialog.bass.findData(6))
                    return QDialog.DialogCode.Accepted
                with patch.object(ChordMarkerDialog, 'exec', accept):
                    window.chord_command('mark', chord_id, roll)
                self.image(roll); self.assertNotEqual(roll.layer_key, initial_key)
                self.assertEqual(roll.category(64, 120), 'scale'); self.assertEqual(roll.category(66, 120), 'chord')
                self.assertEqual([(n.id, tuple((r.x(), r.y(), r.width(), r.height()))) for r, n in roll.hit_notes], initial_hits)
                point = QPointF(roll.x_at(900), roll.y_at(64) + roll.row_height / 2)
                self.assertEqual(roll.note_hit(point)[1].id, window.project.notes[0].id)
                marked_key = roll.layer_key
                window.undo(); self.image(roll)
                self.assertNotEqual(roll.layer_key, marked_key); self.assertEqual(roll.category(64, 120), 'both')
                window.redo(); self.image(roll); self.assertEqual(roll.category(64, 120), 'scale')
                path = Path(folder) / 'marked.lfs'; window.project.save(path)
                self.assertEqual(inside(Project.load(path)), {0, 2, 5, 6, 9})
                window.replace_project(Project.load(path)); self.image(roll)
                self.assertEqual(roll.category(64, 120), 'scale'); self.assertEqual(roll.category(66, 120), 'chord')
                window.chord_command('recognition:0', {chord_id}, roll)
                self.image(roll); self.assertEqual(roll.category(64, 120), 'both')
                self.assertEqual(event_list(window.project), original)


if __name__ == '__main__':
    unittest.main()
