"""PyChord catalogue coverage, extended spelling and legacy voicing compatibility."""
import importlib.metadata
import tempfile
import unittest
from pathlib import Path

from pychord import QualityManager

from lingfeng.music.model import Chord, Note, Project, PPQ, QUALITIES, PATTERNS
from lingfeng.music.quality_catalog import QUALITY_RELATIONS, QUALITY_LABELS, degree_formula
from lingfeng.music.chord_operations import quality_items, quality_voicing, chord_pitch_name
from lingfeng.music.progressions import resolve, tokens, apply
from lingfeng.music.recognition import recognize, set_marker
from lingfeng.platform.i18n import EN


class EngineTests(unittest.TestCase):
    def test_pinned_upstream_catalogue_matches_every_public_definition(self):
        self.assertEqual(importlib.metadata.version('pychord'), '1.4.2')
        upstream = QualityManager().get_qualities()
        self.assertEqual(set(QUALITIES), set(upstream) | {'add2'})
        for code, quality in upstream.items():
            with self.subTest(code=code):
                self.assertEqual(QUALITY_RELATIONS[code], tuple(quality.intervals))
                self.assertEqual(QUALITIES[code], quality.components)

    def test_all_names_have_preview_degrees_and_translated_labels(self):
        self.assertEqual(len(quality_items()), len(QUALITIES))
        for code in QUALITIES:
            with self.subTest(code=code):
                self.assertEqual(degree_formula(code).split(), list(QUALITY_RELATIONS[code]))
                self.assertIn(QUALITY_LABELS[code], EN)
        self.assertEqual(degree_formula('dim7'), '1 b3 b5 bb7')
        self.assertEqual(degree_formula('7b9#9'), '1 3 5 b7 b9 #9')

    def test_all_quality_pattern_combinations_generate_valid_project_events(self):
        for code in QUALITIES:
            for pattern in PATTERNS:
                with self.subTest(code=code, pattern=pattern):
                    p = Project(); p.chords = [Chord(0, 4 * PPQ, quality=code, pattern=pattern)]
                    p.validate()
                    self.assertTrue(p.chords[0].render_notes())

    def test_legacy_labels_lead_alias_candidates_and_preferred_symbol_wins(self):
        for quality in ('', 'm', 'maj7', 'm7', 'add2', 'dim7'):
            chord = Chord(0, PPQ, quality=quality)
            candidates = recognize(chord.pitches, preferred=(0, quality))
            self.assertEqual((candidates[0].root, candidates[0].quality), (0, quality))
        self.assertEqual(recognize([36, 48, 52, 55])[0].quality, '')
        extended = Chord(0, PPQ, quality='13#11')
        self.assertIn((0, '13#11'), [(c.root, c.quality) for c in recognize(extended.pitches)])

    def test_roman_roundtrip_keeps_every_quality_interval_and_explicit_bass(self):
        for quality in QUALITIES:
            for root, tonic in ((48, 48), (54, 53), (59, 50)):
                with self.subTest(quality=quality, root=root, tonic=tonic):
                    source = Chord(0, PPQ, root, quality, bass=2)
                    restored = resolve(source.roman(tonic), tonic)
                    self.assertEqual(restored.root % 12, source.root % 12)
                    self.assertEqual(restored.bass, source.bass)
                    self.assertEqual(set(QUALITIES[restored.quality]), set(QUALITIES[source.quality]))
        self.assertEqual(Chord(0, PPQ, quality='m11').roman(48), 'i11')
        self.assertEqual(Chord(0, PPQ, quality='-').roman(48), 'i')

    def test_numeric_extensions_and_hyphen_separators_are_distinct(self):
        self.assertEqual(tokens('I-V-vi-IV'), ['I', 'V', 'vi', 'IV'])
        self.assertEqual(tokens('I7-5 I- i11'), ['I7-5', 'I-', 'i11'])
        self.assertEqual(resolve('I7-5', 0).quality, '7-5')
        self.assertEqual(resolve('Iadd9', 0).quality, 'add9')
        self.assertEqual(resolve('iadd9', 0).quality, 'madd9')

    def test_simultaneous_flat_and_sharp_ninths_survive_voicing_and_spelling(self):
        p = Project(); dual = Chord(0, PPQ, quality='7b9#9')
        self.assertEqual(quality_voicing(dual, dual.quality, dual.pitches), tuple(dual.pitches))
        plain = Chord(0, PPQ, quality='7')
        self.assertEqual(quality_voicing(plain, dual.quality, plain.pitches), tuple(dual.pitches))
        self.assertEqual(chord_pitch_name(p, dual, 61), 'Db4')
        self.assertEqual(chord_pitch_name(p, dual, 63), 'D#4')

    def test_current_add9_roundtrip_and_legacy_add9_migration_keep_their_voicings(self):
        p = Project(); p.chords = [Chord(0, PPQ, quality='add9')]
        self.assertIn(62, p.chords[0].pitches)
        self.assertNotIn(50, p.chords[0].pitches)
        self.assertEqual(Project.from_dict(p.to_dict()).chords[0].quality, 'add9')
        with tempfile.TemporaryDirectory(dir='tmp') as directory:
            path = Path(directory) / 'extended.lfs'; p.save(path)
            self.assertEqual(Project.load(path).chords[0].pitches, p.chords[0].pitches)
        legacy = p.to_dict(); entry = legacy['chords'][0]
        entry.pop('recognition_disabled'); entry.pop('marked')
        migrated = Project.from_dict(legacy).chords[0]
        self.assertEqual(migrated.quality, 'add2'); self.assertIn(50, migrated.pitches)
        entry['notes'] = [vars(Note(0, PPQ, 74, 83))]
        self.assertEqual(Project.from_dict(legacy).chords[0].notes[0].pitch, 74)

    def test_explicit_progression_replaces_marked_music_and_resumes_recognition(self):
        p = Project(); chord = Chord(0, 4 * PPQ); p.chords = [chord]
        set_marker(chord, 2, 'm11', 5)
        apply(p, chord.id, 'I13#11', keep_rhythm=False)
        result = p.chords[0]
        self.assertFalse(result.marked); self.assertFalse(result.recognition_disabled)
        self.assertEqual(result.quality, '13#11'); p.validate()


if __name__ == '__main__':
    unittest.main()
