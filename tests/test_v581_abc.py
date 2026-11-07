import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from lingfeng.engraving.lyrics import apply_range, edit_lyric_track
from lingfeng.music.abc_export import serialize_abc, sheetsage_reason, write_abc
from lingfeng.music.abc_import import parse_abc, project_from_abc, read_abc
from lingfeng.music.model import Chord, Context, Measure, Note, Project


def imported(text, **overrides):
    data = parse_abc(text)
    return project_from_abc(data, **(data.defaults() | overrides))


def performed(notes):
    return [(n.start, n.duration, n.pitch, n.lyric) for n in notes]


class AbcInterchangeTests(unittest.TestCase):
    def test_standard_lyrics_space_syllables_and_leave_rap_slots_blank(self):
        project = Project(
            measures=[Measure(), Measure()], contexts=[Context(0, 7680)],
            notes=[Note(i*960, 960, 60) for i in range(4)]
                  + [Note(3840+i*480, 480, 62) for i in range(8)],
            instrument_notes=[Note(3840+i*960, 960, 64) for i in range(4)],
        )
        apply_range(project, '/x{甲乙丙丁}|中文/x{说} English _ * 再来', 0, 2)
        edit_lyric_track(project, 1, lambda track: apply_range(track, 'Rhythm/4 第一次', 1, 1))

        text = serialize_abc(project)
        self.assertEqual([line for line in text.splitlines() if line.startswith('w:')],
                         ['w:', 'w: 中 文 * English _ * 再 来', 'w: * 第 一 次'])
        restored = imported(text)
        self.assertEqual([n.lyric for n in restored.notes],
                         ['', '', '', '', '中', '文', '', 'English', '', '', '再', '来'])
        self.assertEqual([n.lyric for n in restored.instrument_notes], ['', '第', '一', '次'])
        self.assertNotIn('w:', serialize_abc(project, sheetsage=True))

    def test_standard_lyrics_keep_joins_and_escape_single_note_text(self):
        project = Project(notes=[Note(0, 960, 60), Note(960, 960, 62)])
        apply_range(project, r'well-known~word\-word', 0, 1)
        self.assertIn('w: well- known~word\\-word\n', serialize_abc(project))

    def test_native_accidental_scope_and_ties(self):
        data = '''X:1
T:
M:4/4
L:1/8
V: Vocal name="Vocal Melody"
V: Ins name="Ins Melody"
K:C
% interlude
V: Vocal
"C##m(maj7)/Ebb"^F2f2F4-|F2F6|
V: Ins
Z2|
'''
        project = imported(data)
        self.assertEqual(project.sections(), [('interlude', 0, 2)])
        self.assertEqual(performed(project.notes), [
            (0, 960, 66, ''), (960, 960, 78, ''), (1920, 2880, 66, ''), (4800, 2880, 65, ''),
        ])
        self.assertEqual(project.chords[0].name, 'DmM7/D')
        self.assertEqual(project.chords[-1].name, 'N.C.')
        self.assertEqual(imported(data, section_mapping={'interlude': 'Solo'}).sections(), [('solo', 0, 2)])
        self.assertEqual(imported(data, section_mapping={}).sections(), [('interlude', 0, 2)])
        self.assertEqual(imported('%abc-2.1\n'+data).notes[1].pitch, 77)

    def test_standard_roundtrip_with_polyphony_custom_names_and_ties(self):
        project = Project(
            title='百分比 100%', author='甲 % 乙',
            melody_names=['Lead "A"', '乐器旋律'],
            measures=[Measure(section='Link'), Measure(3, 4)],
            contexts=[Context(0, 4090), Context(4090, 6720, 55)],
            notes=[Note(200, 4000, 66, lyric='a-word'), Note(1000, 400, 73, lyric='爱')],
            instrument_notes=[Note(3900, 450, 70, lyric='音')],
            chords=[Chord(0, 3840, root=54, notes=[Note(0, 3840, 54), Note(120, 480, 61)]),
                    Chord(3840, 2880, root=48, quality='mM7')],
        )
        project.validate()
        self.assertTrue(sheetsage_reason(project))
        with self.assertRaises(ValueError):
            serialize_abc(project, sheetsage=True)
        with TemporaryDirectory() as temp:
            path = Path(temp)/'roundtrip.abc'
            write_abc(project, path, section_mapping={'Link': 'custom fill'})
            data = read_abc(path)
            restored = project_from_abc(data, **data.defaults(), section_mapping={'custom fill': 'Link'})
        self.assertEqual(restored.title, project.title)
        self.assertEqual(restored.author, project.author)
        self.assertEqual(restored.melody_names, project.melody_names)
        self.assertEqual(restored.starts, project.starts)
        self.assertEqual(restored.sections(), project.sections())
        self.assertEqual([c.start for c in restored.contexts], [0, 4090])
        self.assertEqual(performed(restored.notes), performed(project.notes))
        self.assertEqual(performed(restored.instrument_notes), performed(project.instrument_notes))
        self.assertEqual(performed(restored.harmony_notes()), performed(project.harmony_notes()))

    def test_native_roundtrip_splits_sustains_without_extra_attacks(self):
        project = Project(
            measures=[Measure(section='Link'), Measure(3, 4, 'Verse')],
            contexts=[Context(0, 2880, 54), Context(2880, 6720, 48)],
            notes=[Note(0, 4200, 66), Note(4200, 1080, 65)],
            instrument_notes=[Note(3840, 2400, 74)],
            chords=[Chord(0, 1440, 54, 'mM7'), Chord(1440, 2400, 55, '7')],
        )
        self.assertFalse(sheetsage_reason(project))
        text = serialize_abc(project, sheetsage=True)
        self.assertTrue(text.startswith('X:1\nT:\n'))
        self.assertIn('% interlude', text)
        self.assertIn('"F#m(maj7)"', text)
        self.assertNotIn('V: Chord', text)
        self.assertNotIn('w:', text)
        restored = imported(text)
        self.assertEqual(restored.sections(), [('interlude', 0, 1), ('verse', 1, 2)])
        self.assertEqual(restored.starts, project.starts)
        self.assertEqual(performed(restored.notes), performed(project.notes))
        self.assertEqual(performed(restored.instrument_notes), performed(project.instrument_notes))
        self.assertEqual([(c.start, c.name) for c in restored.chords],
                         [(0, 'F#mM7'), (1440, 'G7'), (3840, 'N.C.')])
        self.assertIn('% interlude', serialize_abc(project, sheetsage=True, section_mapping={}))

    def test_native_track_selection_and_reviewed_chord_replacement(self):
        from lingfeng.music.abc_export import sheetsage_chord_changes
        project = Project(measures=[Measure(section='Link')],
                          notes=[Note(0, 960, 60)], instrument_notes=[Note(960, 960, 67)],
                          chords=[Chord(0, 3840, 48, 'maj9', marked=True)])
        self.assertEqual(sheetsage_chord_changes(project), [(0, 'Cmaj9', 'Cmaj7')])
        options = dict(sheetsage=True, which=('melody', 'chords'))
        text = serialize_abc(project, chord_overrides={0: 'Dm7/F'}, **options)
        self.assertIn('"Dm7/F"', text)
        self.assertIn('% interlude', text)
        self.assertIn('V: Ins\nZ|', text)
        self.assertEqual(project.chords[0].quality, 'maj9')
        with self.assertRaises(ValueError):
            serialize_abc(project, chord_overrides={0: 'C13'}, **options)
        self.assertNotIn('V: Ins', serialize_abc(project, which=('melody', 'chords')))

    def test_optional_yue2_rules_and_chords_inside_held_notes(self):
        from lingfeng.music.abc_export import sheetsage_chord_changes
        project = Project(measures=[Measure(section='Link-2')], contexts=[Context(0, 3840)],
                          notes=[Note(0, 1920, 69)], chords=[
                              Chord(0, 960, 50, 'mM7'),
                              Chord(960, 1920, 55, '9'),
                          ])
        self.assertEqual(sheetsage_chord_changes(project), [(960, 'G9', 'G7')])
        with self.assertRaisesRegex(ValueError, 'link'):
            serialize_abc(project, sheetsage=True, rewrite_links=False)
        with self.assertRaises(ValueError):
            serialize_abc(project, sheetsage=True, convert_chords=False)
        text = serialize_abc(project, sheetsage=True, convert_chords=False, chord_overrides={960: 'G7'})
        self.assertIn('% interlude-2', text)
        self.assertIn('"Dm(maj7)"A8-"G7"A8', text)
        self.assertIn('% section: link-2', serialize_abc(project))
        restored = imported(text)
        self.assertEqual(performed(restored.notes), performed(project.notes))

    def test_export_uses_displayed_combined_chord_without_changing_performance(self):
        project = Project(
            chords=[Chord(0, 3840, include_instrument_in_recognition=True)],
            instrument_notes=[Note(0, 960, 71)],
        )
        project.rescan_instrument_recognition()
        self.assertEqual(project.chords[0].name, 'Cmaj7')
        standard = serialize_abc(project)
        self.assertIn('"Cmaj7"', standard)
        self.assertIn('"Cmaj7"', serialize_abc(project, sheetsage=True))
        self.assertEqual(performed(imported(standard).harmony_notes()), performed(project.harmony_notes()))

    def test_full_export_preserves_chromatic_voicing_and_compatible_keeps_just_symbols(self):
        project = Project(
            measures=[Measure(), Measure()], contexts=[Context(0, 7680)],
            notes=[Note(0, 480, 67)], instrument_notes=[Note(3840, 960, 64)],
            chords=[Chord(0, 7680, quality='m7', bass=3,
                          notes=[Note(0, 4600, 61), Note(3840, 480, 60), Note(4320, 240, 55)])],
        )
        full = serialize_abc(project)
        native = serialize_abc(project, sheetsage=True)
        self.assertIn('V: Chord clef=bass', full)
        self.assertLess(full.index('X:1'), full.index('%%MIDI gchordoff'))
        self.assertIn('"Cm7/Eb"', full)
        self.assertIn('"Cm7/Eb"', native)
        self.assertNotIn('V: Chord', native)
        self.assertNotIn('%%MIDI gchordoff', native)
        restored = imported(full)
        self.assertEqual(restored.chords[0].name, project.chords[0].name)
        self.assertEqual(performed(restored.harmony_notes()), performed(project.harmony_notes()))


if __name__ == '__main__':
    unittest.main()
