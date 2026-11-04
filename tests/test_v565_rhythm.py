"""A full-bar bass under full-beat upper chord voices in every local meter."""
import copy
from pathlib import Path
import tempfile
import unittest

from lingfeng.audio.midi import export_midi
from lingfeng.audio.midi_import import read_midi
from lingfeng.music.chord_operations import can_apply_pattern, change_chords
from lingfeng.music.meter import moved_chord, rescan_chord
from lingfeng.music.model import Chord, Context, Measure, PATTERNS, PPQ, Project, QUALITIES
from lingfeng.music.progressions import apply, common_patterns
from lingfeng.music.rhythm import Rhythm, analyze, analyze_performed, regenerate, supports


PATTERN = 'sustained_bass_beats'


def project(numerator=4, denominator=4, bars=2):
    p = Project(measures=[Measure(numerator, denominator) for _ in range(bars)])
    p.contexts = [Context(0, p.end)]
    return p


def events(chord):
    return sorted((n.start, n.duration, n.pitch, n.velocity) for n in chord.render_notes())


def expected(p, start, end, pitches, velocity):
    """Independent bar/beat reference, cropped to the requested chord region."""
    result = []
    for bar, origin in zip(p.measures, p.starts):
        beat = 4 * PPQ // bar.denominator
        voices = [(origin, bar.ticks, pitches[0])]
        voices.extend((origin + i * beat, beat, pitch)
                      for i in range(bar.numerator) for pitch in pitches[1:])
        for t, length, pitch in voices:
            left, right = max(start, t), min(end, t + length)
            if left < right:result.append((left, right - left, pitch, velocity))
    return sorted(result)


class SustainedBassBeatTests(unittest.TestCase):
    def test_every_meter_has_one_full_bar_bass_and_one_full_chord_per_beat(self):
        self.assertIn(PATTERN, PATTERNS)
        for numerator in range(1, 17):
            for denominator in (2, 4, 8, 16):
                with self.subTest(numerator=numerator, denominator=denominator):
                    p = project(numerator, denominator)
                    c = Chord(0, p.end, quality='maj7', pattern=PATTERN, gate=.61, velocity=83)
                    self.assertTrue(supports(PATTERN, p, 0))
                    p.put_chord(c); c = p.chords[0]
                    self.assertEqual(events(c), expected(p, 0, p.end, c.pitches, 83))
                    self.assertEqual(analyze(c, p).pattern, PATTERN)
                    self.assertEqual(analyze_performed(c, p).pattern, PATTERN)
                    p.validate()

    def test_full_sustains_ignore_gate_as_the_sustain_pattern_does(self):
        p = project(3, 8)
        reference = None
        for gate in (.05, .5, .9, 1):
            c = regenerate(Chord(0, p.end, pattern=PATTERN, gate=gate), 0, p.end, p)
            self.assertEqual(events(c), expected(p, 0, p.end, c.pitches, c.velocity))
            if reference is not None:self.assertEqual(events(c), reference)
            reference = events(c)

    def test_partial_regions_crop_the_bar_bass_and_the_current_beat(self):
        p = project(3, 8, bars=3)
        for start, end in ((120, 1200), (600, 2650), (1550, 4200)):
            with self.subTest(start=start, end=end):
                c = Chord(start, end - start, 53, 'm7', bass=9, pattern=PATTERN)
                c = regenerate(c, start, end, p)
                self.assertEqual(events(c), expected(p, start, end, c.pitches, c.velocity))
                self.assertEqual(analyze(c, p).pattern, PATTERN)
                self.assertEqual(min(n.pitch for n in c.notes), 45)

    def test_equal_bar_lengths_follow_the_denominator_for_upper_beats(self):
        a, b = project(2, 4), project(4, 8)
        chords = [regenerate(Chord(0, 1920, pattern=PATTERN), 0, 1920, p) for p in (a, b)]
        self.assertEqual([[(n.start, n.duration) for n in c.notes if n.pitch == 36]
                          for c in chords], [[(0, 1920)], [(0, 1920)]])
        self.assertEqual([(n.start, n.duration) for n in chords[0].notes if n.pitch == 48],
                         [(0, 960), (960, 960)])
        self.assertEqual([(n.start, n.duration) for n in chords[1].notes if n.pitch == 48],
                         [(0, 480), (480, 480), (960, 480), (1440, 480)])

    def test_all_qualities_keep_the_full_upper_voicing_and_requested_bass(self):
        for quality in QUALITIES:
            with self.subTest(quality=quality):
                p = project(5, 16, bars=1)
                p.put_chord(Chord(0, p.end, quality=quality, bass=2, pattern=PATTERN))
                c = p.chords[0]; rescan_chord(p, c)
                self.assertEqual(events(c), expected(p, 0, p.end, c.pitches, c.velocity))
                self.assertEqual(c.quality, quality)
                self.assertEqual(analyze(c, p).pattern, PATTERN)

    def test_detects_actual_texture_and_does_not_match_edited_voice_lengths(self):
        p = project(5, 8)
        c = regenerate(Chord(0, p.end, pattern=PATTERN), 0, p.end, p)
        c.pattern = 'block'
        self.assertEqual(analyze(c, p).pattern, PATTERN)
        c.notes[-1].duration -= 20
        self.assertIsNone(analyze(c, p))
        c.custom_rhythm = True
        self.assertIsNone(analyze_performed(c, p))

    def test_pattern_commands_root_quality_progression_and_move_preserve_texture(self):
        p = project(3, 8, bars=4)
        p.put_chord(Chord(0, 1440))
        c = p.chords[0]
        self.assertTrue(can_apply_pattern(p, [c], PATTERN))
        self.assertIn(PATTERN, common_patterns(p, [c]))
        change_chords(p, {c.id}, 'pattern:' + PATTERN)
        for command in ('quality:m7', 'root:5'):
            change_chords(p, {c.id}, command)
            self.assertEqual(analyze(c, p).pattern, PATTERN)
            self.assertEqual(events(c), expected(p, c.start, c.end, c.pitches, c.velocity))
        moved = moved_chord(p, c, 1620)
        self.assertEqual(events(moved), expected(p, moved.start, moved.end, moved.pitches, moved.velocity))
        apply(p, c.id, 'Vmaj7/7', keep_rhythm=True)
        c = p.chords[0]
        self.assertEqual(analyze(c, p).pattern, PATTERN)
        self.assertEqual(events(c), expected(p, c.start, c.end, c.pitches, c.velocity))

    def test_legacy_generator_stable_ids_and_clips_retain_performed_notes(self):
        c = Chord(120, 3000, pattern=PATTERN, gate=.05)
        reference = sorted((120 + t, d, pitch, c.velocity)
                           for t, d, pitch in Rhythm(PATTERN, tuple(c.pitches), c.gate).events(3000))
        self.assertEqual(events(c), reference)
        self.assertEqual([n.id for n in c.render_notes()], [n.id for n in c.render_notes()])
        clipped = c.clip(600, 2000)
        self.assertEqual(events(clipped), sorted((max(600, t), min(2000, t + d) - max(600, t), pitch, v)
                         for t, d, pitch, v in reference if t < 2000 and t + d > 600))

    def test_native_roundtrip_and_midi_keep_beat_retriggers_and_bar_bass_ends(self):
        p = project(5, 8)
        p.put_chord(Chord(0, p.end, 50, 'm7', bass=5, pattern=PATTERN, velocity=67))
        before = copy.deepcopy(p.to_dict())
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            native, midi = Path(folder) / 'pattern.lfs', Path(folder) / 'pattern.mid'
            p.save(native); restored = Project.load(native)
            self.assertEqual(restored.to_dict(), before)
            export_midi(restored, midi, which='chords')
            parsed = [n for track in read_midi(midi).tracks for n in track.notes]
            self.assertEqual(sorted((n.start, n.duration, n.pitch, n.velocity) for n in parsed),
                             events(p.chords[0]))
        self.assertEqual(p.to_dict(), before)


if __name__ == '__main__':unittest.main()
