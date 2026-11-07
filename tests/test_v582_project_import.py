import unittest

from lingfeng.music.model import Chord, Context, Measure, Note, Project
from lingfeng.music.project_import import insert_project


def lyrics(section_id, tick, text, duration=None):
    event = dict(id='lyric-'+section_id, section_id=section_id, tick=tick, text=text)
    if duration:
        event.update(kind='rap', duration=duration)
    return event


class ProjectInsertionTests(unittest.TestCase):
    def test_middle_insertion_preserves_both_scores_and_performed_harmony(self):
        target = Project(
            title='Target', author='Keep', bpm=91, melody_names=['Keep vocal', 'Keep ins'],
            measures=[Measure(section='Verse'), Measure(section='Chorus'), Measure(3, 4)],
            contexts=[Context(0, 10560, 48)], marks=[0, 2],
            notes=[Note(3600, 800, 64, 73, 'held', id='shared'), Note(6000, 400, 62, id='future')],
            instrument_notes=[Note(3800, 200, 70, id='instrument')],
            chords=[Chord(3000, 2400, notes=[Note(200, 1700, 45, id='held-bass', event_id='sustain'),
                                          Note(1500, 500, 48, id='later-bass')], id='region')],
            groups={'work': [[3000, 4200]]},
        )
        source = Project(
            title='Source', bpm=140,
            measures=[Measure(2, 4, 'Intro'), Measure(6, 8, 'Link')],
            contexts=[Context(0, 1920, 55), Context(1920, 4800, 57, 'Aeolian')], marks=[0, 1],
            notes=[Note(0, 480, 67, lyric='new', id='shared')],
            instrument_notes=[Note(2400, 480, 74, id='instrument')],
            chords=[Chord(0, 1920, notes=[Note(1200, 720, 55, id='held-bass', event_id='sustain')]),
                    Chord(1920, 2880, notes=[Note(0, 720, 55, id='later-bass', event_id='sustain')])],
            groups={'work': [[0, 1920]]},
        )
        original = source.to_dict()
        metadata = (target.title, target.author, target.bpm, target.melody_names, target.audio, target.volumes)

        self.assertEqual(insert_project(target, 1, source), (3840, 8640))
        self.assertEqual(source.to_dict(), original)
        self.assertEqual((target.title, target.author, target.bpm, target.melody_names, target.audio, target.volumes), metadata)
        self.assertEqual(target.starts, [0, 3840, 5760, 8640, 12480, 15360])
        self.assertEqual([m.section for m in target.measures], ['verse', 'intro', 'link', 'chorus', ''])
        self.assertEqual(target.marks, [0, 1, 2, 4])
        self.assertEqual([(c.start, c.end, c.tonic) for c in target.contexts],
                         [(0, 3840, 48), (3840, 5760, 55), (5760, 8640, 57), (8640, 15360, 48)])
        self.assertEqual([(n.start, n.duration, n.pitch, n.lyric) for n in target.notes],
                         [(3600, 240, 64, 'held'), (3840, 480, 67, 'new'), (8640, 560, 64, ''), (10800, 400, 62, '')])
        self.assertEqual((target.notes[0].id, target.notes[-1].id), ('shared', 'future'))
        self.assertNotEqual(target.notes[1].id, 'shared')
        self.assertEqual([(n.start, n.duration, n.pitch) for n in target.instrument_notes],
                         [(3800, 40, 70), (6240, 480, 74), (8640, 160, 70)])
        self.assertEqual([(n.start, n.duration, n.pitch) for n in target.harmony_notes()],
                         [(3200, 640, 45), (5040, 1440, 55), (8640, 1060, 45), (9300, 500, 48)])
        self.assertEqual(target.chord_at(3200).id, 'region')
        self.assertEqual(target.groups['work'], [[3000, 3840], [3840, 5760], [8640, 9000]])

    def test_lyrics_and_presentation_use_bar_and_tick_offsets(self):
        target = Project(measures=[Measure(), Measure(), Measure()], contexts=[Context(0, 11520)])
        target.notation['lyric_events'] = [lyrics('section', 3600, 'cross', duration=480)]
        target.notation['lyric_sections'] = [
            dict(id='section', text='cross', start=3600, end=4080, verse=0),
        ]
        target.notation['instrument_lyric_events'] = [lyrics('ins', 3840, 'shift')]
        target.notation['forced_rows'] = [[1, 3]]
        target.notation['symbols'] = [dict(kind='double_bar', start=0, end=3840)]

        source = Project(measures=[Measure(), Measure()], contexts=[Context(0, 7680)],
                         notes=[Note(0, 480, 60, id='lead'), Note(480, 480, 62, id='lead2')])
        source.notation['lyric_events'] = [lyrics('section', 0, 'insert')]
        source.notation['lyric_sections'] = [dict(id='section', text='insert', start=0, end=480, verse=0)]
        source.notation['symbols'] = [dict(kind='slur', start=0, end=960, note_ids=['lead', 'lead2'])]
        insert_project(target, 1, source)

        events = target.notation['lyric_events']
        self.assertEqual([(e['tick'], e.get('duration'), e['text']) for e in events],
                         [(3600, 240, 'cross'), (3840, None, 'insert'), (11520, 240, '')])
        self.assertEqual(events[0]['id'], 'lyric-section')
        self.assertTrue(events[-1]['continuation'])
        sections = target.notation['lyric_sections']
        self.assertEqual((sections[0]['id'], sections[0]['end']), ('section', 11760))
        self.assertEqual(sections[1]['id'], events[1]['section_id'])
        self.assertNotEqual(sections[1]['id'], 'section')
        self.assertEqual(target.notation['instrument_lyric_events'][0]['tick'], 11520)
        self.assertEqual(target.notation['forced_rows'], [[3, 5]])
        first, second = target.notation['symbols']
        self.assertEqual(first['end'], 3840)
        self.assertEqual((second['start'], second['end']), (3840, 4800))
        self.assertEqual(second['note_ids'], [note.id for note in target.notes])

    def test_beginning_and_append_insert_even_in_empty_project(self):
        for index, start in ((0, 0), (8, 30720)):
            target = Project()
            source = Project(measures=[Measure(3, 4)], contexts=[Context(0, 2880)], notes=[Note(0, 480, 60)])
            self.assertEqual(insert_project(target, index, source), (start, start+2880))
            self.assertEqual(len(target.measures), 9)
            self.assertEqual(target.measures[index].ticks, 2880)
            self.assertEqual(target.notes[0].start, start)

    def test_invalid_position_and_size_leave_target_unchanged(self):
        target = Project()
        before = target.to_dict()
        with self.assertRaises(ValueError):
            insert_project(target, -1, Project())
        source = Project(measures=[Measure() for _ in range(993)], contexts=[Context(0, 993*3840)])
        with self.assertRaises(ValueError):
            insert_project(target, 0, source)
        self.assertEqual(target.to_dict(), before)


if __name__ == '__main__':
    unittest.main()
