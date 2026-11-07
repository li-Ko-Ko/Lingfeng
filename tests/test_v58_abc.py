"""ABC mapping preserves written timing, note identities and project metadata."""

from pathlib import Path
import tempfile
import unittest

from lingfeng.engraving.lyrics import events, lyric_track
from lingfeng.music.abc_import import parse_abc, project_from_abc, read_abc
from lingfeng.music.model import PPQ, Project


TUNE = """X:1
T:Round trip
C:Composer
M:4/4
L:1/8
Q:1/8=160
V:Vocal name="Vocal Melody"
V:Ins name="Ins Melody"
V:Chord name="Harmony"
K:F# clef=treble
% intro
V:Vocal
"F#maj7"F2 F2 A2 c2-| "C#7"c2 z6|
w: one two three four
V:Ins
Z| z2f2g4|
w: up now
V:Chord
[F,A,C]8| [C,E,G]4 [C,E,G]4|
% section: Bridge
V:Vocal
M:3/4
"D#m"z6|
V:Ins
M:3/4
Z|
V:Chord
M:3/4
Z|
"""


class AbcImportTests(unittest.TestCase):
    def test_abc_lyric_markers_preserve_alignment_and_notation(self):
        data = parse_abc(r'''%abc-2.1
X:1
M:4/4
L:1/8
V:Vocal
V:Ins
K:C
V:Vocal
C D E F G A B c|
w: to--geth-er_ * 中 of~the\-day
V:Ins
C D E F G A z2|
w: sing- ing _ 文 \- \u005f
''')
        project = project_from_abc(data, **data.defaults())

        def lyrics(track):
            return [(e['tick'], e['text'], bool(e.get('join_next')), bool(e.get('melisma')))
                    for e in events(lyric_track(project, track))]

        self.assertEqual(lyrics(0), [(0, 'to', True, False), (960, 'geth', True, False),
                                     (1440, 'er', False, False), (1920, '', False, True),
                                     (2880, '中', False, False), (3360, 'of the-day', False, False)])
        self.assertEqual(lyrics(1), [(0, 'sing', True, False), (480, 'ing', False, False),
                                     (960, '', False, True), (1440, '文', False, False),
                                     (1920, '-', False, False), (2400, '_', False, False)])

    def test_defaults_create_project_with_separate_timelines_and_lyrics(self):
        source = parse_abc(TUNE)
        self.assertEqual(source.defaults(), {
            'vocal': 'Vocal', 'instrument': 'Ins', 'harmony': 'Chord',
            'symbols': 'Vocal', 'sections': True, 'pattern': 'block',
        })
        project = project_from_abc(source, **source.defaults())
        self.assertEqual((project.title, project.author, project.bpm), ('Round trip', 'Composer', 80))
        self.assertEqual(project.starts, [0, 4*PPQ, 8*PPQ, 11*PPQ])
        self.assertEqual(project.sections(), [('intro', 0, 2), ('bridge', 2, 3)])
        self.assertEqual(project.contexts[0].tonic, 54)
        self.assertEqual([(n.start, n.pitch, n.lyric) for n in project.notes], [
            (0, 66, 'one'), (PPQ, 66, 'two'), (2*PPQ, 70, 'three'), (3*PPQ, 73, 'four'),
        ])
        self.assertEqual(project.notes[-1].duration, 2*PPQ)
        self.assertEqual([(n.start, n.pitch, n.lyric) for n in project.instrument_notes], [
            (5*PPQ, 78, 'up'), (6*PPQ, 80, 'now'),
        ])
        self.assertEqual({n.start for n in project.harmony_notes()}, {0, 4*PPQ, 6*PPQ})
        self.assertEqual(Project.from_dict(project.to_dict()).to_dict(), project.to_dict())

    def test_mapping_and_generated_rhythm_are_independent(self):
        source = parse_abc(TUNE)
        options = source.defaults() | {
            'vocal': 'Ins', 'instrument': None, 'harmony': None, 'sections': False,
            'pattern': 'quarters',
        }
        project = project_from_abc(source, **options)
        self.assertEqual([n.pitch for n in project.notes], [78, 80])
        self.assertEqual(project.instrument_notes, [])
        self.assertEqual(project.sections(), [])
        self.assertEqual({n.start for n in project.chords[0].render_notes()}, {0, PPQ, 2*PPQ, 3*PPQ})
        self.assertEqual([c.name for c in project.chords], ['F#maj7', 'C#7', 'D#m'])

    def test_pickup_broken_rhythm_tuplets_accidentals_and_written_repeats(self):
        source = parse_abc('X:1\nM:2/4\nL:1/8\nK:C\n^C|: C>D (3EFF | [K:G] =F F F F :|')
        project = project_from_abc(source, **source.defaults())
        self.assertEqual(project.starts, [0, PPQ//2, 5*PPQ//2, 9*PPQ//2])
        self.assertEqual([n.pitch for n in project.notes], [61, 60, 62, 64, 65, 65, 65, 65, 65, 65])
        self.assertEqual([n.duration for n in project.notes[:6]], [480, 720, 240, 320, 320, 320])
        self.assertEqual([context.tonic for context in project.contexts], [48, 55])

    def test_inline_voice_and_part_fields_and_symbol_only_harmony(self):
        source = parse_abc('X:1\nM:4/4\nL:1/4\nK:C\n[V:Vocal][P:A] C4|\n[V:Chord]"C/E"|"N.C."|')
        project = project_from_abc(source, **source.defaults())
        self.assertEqual(project.sections(), [('A', 0, 2)])
        self.assertEqual([c.name for c in project.chords], ['C/E', 'N.C.'])
        self.assertEqual(project.instrument_notes, [])

    def test_read_abc_uses_file_stem_when_no_title_is_present(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'demo.abc'
            path.write_text('X:1\nL:1/4\nK:C\nC4|', encoding='utf-8-sig')
            self.assertEqual(read_abc(path).title, 'demo')

    def test_invalid_inputs_explain_rejection(self):
        with self.assertRaisesRegex(ValueError, '第 4 行'):
            parse_abc('X:1\nL:1/4\nK:C\nC0|')
        source = parse_abc('X:1\nL:1/4\nK:C\nC5|')
        with self.assertRaisesRegex(ValueError, '超过拍号长度'):
            project_from_abc(source, **source.defaults())


if __name__ == '__main__':
    unittest.main()
