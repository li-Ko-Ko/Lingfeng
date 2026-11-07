"""MIDI source mappings build an insertable three-track fragment."""
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from lingfeng.audio.midi_import import MidiData, MidiTrack, project_from_midi
from lingfeng.music.model import Context, Note, Project
from lingfeng.ui.import_dialog import MidiImportDialog


APP = QApplication.instance() or QApplication([])


def source():
    return MidiData([MidiTrack('Conductor'), MidiTrack('Vocal', [Note(140, 210, 63, 89)], 3840),
                     MidiTrack('Ins Melody', [Note(319, 320, 70, 91)], 3840),
                     MidiTrack('Chords', [Note(2500, 600, pitch, 72) for pitch in (48, 52, 55)], 3840)],
                    [(0, 132), (1440, 94)], [(0, 3, 4), (2880, 2, 4)])


class MidiFragmentTests(unittest.TestCase):
    def test_maps_three_roles_and_preserves_harmony_across_meter_boundary(self):
        data = source()
        mapping = data.default_mapping()
        self.assertEqual(mapping, {'melody': [1], 'instrument': [2], 'chords': [3]})
        project = project_from_midi(data, mapping, import_meter=True, import_tempo=True,
                                    context=Context(0, 3840, 54, 'Dorian'))
        self.assertEqual(project.starts, [0, 2880, 4800])
        self.assertEqual(project.bpm, 132)
        self.assertEqual((project.contexts[0].tonic, project.contexts[0].mode), (54, 'Dorian'))
        self.assertEqual([(n.start, n.pitch, n.velocity) for n in project.notes], [(140, 63, 89)])
        self.assertEqual([(n.start, n.pitch, n.velocity) for n in project.instrument_notes], [(319, 70, 91)])
        self.assertEqual([(n.start, n.duration, n.pitch) for n in project.harmony_notes()],
                         [(2500, 600, pitch) for pitch in (48, 52, 55)])
        self.assertEqual([chord.name for chord in project.chords], ['C', 'C'])

    def test_uses_destination_meter_and_ignores_unmapped_notes(self):
        data = source()
        data.tracks[3].notes[0].pitch = 0
        mapping = {'melody': [1, 2], 'instrument': [2], 'chords': []}
        project = project_from_midi(data, mapping, meter=(2, 4), quantization={'grid': 240})
        self.assertEqual(project.starts, [0, 1920, 3840])
        self.assertEqual([n.start for n in project.notes], [240, 240])
        self.assertEqual(project.instrument_notes[0].start, 240)
        self.assertNotEqual(project.notes[1].id, project.instrument_notes[0].id)
        self.assertEqual(project.harmony_notes(), [])
        self.assertEqual(data.tracks[1].notes[0].start, 140)
        with self.assertRaisesRegex(ValueError, '88'):
            project_from_midi(data, {'chords': [3]})

    def test_mixed_meter_must_align_unless_ignored(self):
        data = source()
        data.meters = [(0, 3, 4), (480, 2, 4)]
        with self.assertRaisesRegex(ValueError, 'MIDI 拍号变化'):
            project_from_midi(data, data.default_mapping(), import_meter=True)
        self.assertEqual(project_from_midi(data, data.default_mapping()).starts, [0, 3840])

    def test_overlapping_same_pitch_keeps_later_attacks_and_uncovered_tails(self):
        notes = [Note(0, 960, 60, 70), Note(240, 240, 60, 80), Note(300, 420, 60, 90), Note(960, 240, 60, 100)]
        data = MidiData([MidiTrack('Vocal', notes, 1200)], [], [])
        project = project_from_midi(data, data.default_mapping())
        self.assertEqual([(n.start, n.end, n.velocity) for n in project.notes],
                         [(0, 240, 70), (240, 300, 80), (300, 720, 90), (720, 960, 70), (960, 1200, 100)])

    def test_dialog_includes_all_sources_and_accepts_append_bar(self):
        project = Project(melody_names=['Singer', 'Lead'])
        dialog = MidiImportDialog(project, source(), bar_index=2)
        try:
            self.assertEqual(dialog.tabs.tabText(0), 'Singer')
            self.assertEqual(dialog.tabs.tabText(1), 'Lead')
            self.assertEqual(dialog.value()['bar_index'], 2)
            self.assertFalse(dialog.value()['import_meter'])
            self.assertFalse(dialog.value()['import_tempo'])
            dialog.bar.setValue(len(project.measures) + 1)
            self.assertEqual(dialog.value()['bar_index'], len(project.measures))
            instrument = dialog.sources['instrument']
            instrument.item(0).setCheckState(Qt.CheckState.Checked)
            self.assertEqual(dialog.value()['mapping']['instrument'], [1, 2])
            for tracks in dialog.sources.values():
                for i in range(tracks.count()):
                    tracks.item(i).setCheckState(Qt.CheckState.Unchecked)
            self.assertFalse(dialog.confirm.isEnabled())
        finally:
            dialog.close()
