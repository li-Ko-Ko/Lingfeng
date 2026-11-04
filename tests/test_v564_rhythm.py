"""Offbeat-first spelling for pitched values requiring multiple tied symbols."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from lingfeng.audio.midi import event_list, export_midi
from lingfeng.engraving.notation import (
    PAPER_H, PAPER_W, ScoreLayout, beat_rhythm_parts, export_pdf,
    fragment_style, fragments_for_bar, rhythm_parts,
)
from lingfeng.music.model import Context, Measure, Note, PPQ, Project

APP = QApplication.instance() or QApplication([])
STYLES = ('spatial', 'compact', 'traditional')


def song(notes, *, style='spatial', measures=None):
    project = Project(measures=measures or [Measure(), Measure()])
    project.contexts = [Context(0, project.end)]
    project.notes = list(notes); project.chords = []
    project.notation.update(style=style, per_line=1, font_size=15, circles=False, lyrics=False)
    return project


def played(project):
    return [fragment for bar in range(len(project.measures))
            for fragment in fragments_for_bar(project, bar) if fragment.note]


def signature(layout):
    return [(bar, fragment.start, fragment.duration, fragment.note.id,
             fragment.continuation, fragment.continues)
            for system in layout.systems for bar, fragments in system.fragments.items()
            for fragment in fragments if fragment.note]


def render(layout):
    ties = []
    for page in range(layout.pages):
        image = QImage(PAPER_W, PAPER_H, QImage.Format.Format_RGB32)
        image.fill(0xffffffff); painter = QPainter(image)
        try:layout.draw(painter, page); ties.extend((nid, kind) for nid, kind, _ in layout.tie_paths)
        finally:painter.end()
    return ties


class OffbeatSpellingTests(unittest.TestCase):
    def test_unrepresentable_last_beat_value_prefers_its_offbeat_over_a_small_tail(self):
        note = Note(3000, 840, 65, lyric='la'); project = song([note])
        fragments = played(project)
        self.assertEqual([(f.start, f.duration) for f in fragments], [(3000, 360), (3360, 480)])
        self.assertEqual([fragment_style(f)[:2] for f in fragments], [(2, True), (1, False)])
        self.assertEqual([(f.continuation, f.continues, f.lyric) for f in fragments],
                         [(False, True, 'la'), (True, False, '')])
        self.assertTrue(all(f.note is note for f in fragments))

    def test_880_tick_source_keeps_its_offbeat_fragments_and_performed_midi(self):
        for style in STYLES:
            with self.subTest(style=style):
                note = Note(80, 880, 84); project = song([Note(0, 80, 60), note], style=style)
                before = copy.deepcopy(project.to_dict()); midi = export_midi(project, None)
                fragments = [f for f in played(project) if f.note is note]
                self.assertEqual([(f.start, f.duration) for f in fragments],
                                 [(80, 360), (440, 40), (480, 480)])
                self.assertEqual(fragments[-1].end, 960)
                self.assertEqual(sum(f.duration for f in fragments), 880)
                self.assertTrue(all(f.note.id == note.id for f in fragments))
                self.assertEqual(render(ScoreLayout(project)), [(note.id, 'continuous')] * 2)
                self.assertEqual(project.to_dict(), before)
                self.assertEqual(export_midi(project, None), midi)

    def test_beat_contained_single_dots_and_triplets_do_not_gain_an_offbeat_tie(self):
        for start, duration in ((3000, 720), (240, 720), (0, 640), (320, 640), (0, 360)):
            with self.subTest(start=start, duration=duration):
                self.assertEqual(beat_rhythm_parts(start, duration, 0, PPQ), [(start, duration)])
        self.assertEqual(beat_rhythm_parts(0, 1440, 0, 1920), [(0, 1440)])

    def test_cross_beat_ties_take_precedence_over_known_values_and_offbeat_preference(self):
        for start, duration, expected in ((0, 1440, [(0, 960), (960, 480)]),
                                          (480, 720, [(480, 480), (960, 240)]),
                                          (720, 480, [(720, 240), (960, 240)]),
                                          (3000, 960, [(3000, 360), (3360, 480), (3840, 120)])):
            with self.subTest(start=start, duration=duration):
                self.assertEqual(beat_rhythm_parts(start, duration, 0, PPQ), expected)

    def test_half_and_eighth_note_meters_use_the_local_bar_and_beat_midpoint(self):
        self.assertEqual(beat_rhythm_parts(240, 1680, 0, 1920), [(240, 720), (960, 960)])
        self.assertEqual(beat_rhythm_parts(1500, 420, 1440, 480), [(1500, 180), (1680, 240)])
        project = song([], measures=[Measure(3, 8), Measure(2, 2)])
        project.notes = [Note(60, 420, 60), Note(1680, 1680, 64)]
        self.assertEqual([(f.start, f.duration) for f in played(project)],
                         [(60, 180), (240, 240), (1680, 720), (2400, 960)])

    def test_integral_quarter_sustains_and_leading_dashes_are_preserved(self):
        for beat in (1920, 960, 480, 240):
            for count in range(1, 7):
                with self.subTest(beat=beat, count=count):
                    self.assertEqual(beat_rhythm_parts(0, count * PPQ, 0, beat), [(0, count * PPQ)])
            tail = [(1920, 240), (2160, 240)] if beat == 240 else [(1920, 480)]
            self.assertEqual(beat_rhythm_parts(0, 2400, 0, beat), [(0, 1920), *tail])
        self.assertEqual(beat_rhythm_parts(0, 1680, 0, 960), [(0, 960), (960, 720)])
        project = song([Note(0, 2400, 60)])
        self.assertEqual([fragment_style(f)[3] for f in played(project)], [1, 0])

    def test_conversion_tolerance_near_offbeat_does_not_create_a_tiny_fragment(self):
        for start in (478, 479, 480, 481, 482):
            with self.subTest(start=start):
                self.assertEqual(beat_rhythm_parts(start, 365, 0, 960), [(start, 360), (start + 360, 5)])
        self.assertEqual(beat_rhythm_parts(100, 381, 0, 960), [(100, 360), (460, 21)])
        for delta in (-2, -1, 0, 1, 2):
            self.assertEqual(beat_rhythm_parts(3000 + delta, 840 - delta, 0, 960),
                             [(3000 + delta, 360 - delta), (3360, 480)])

    def test_nonstandard_ticks_stay_exact_and_contiguous(self):
        for beat in (1920, 960, 480, 240):
            for start in (0, 17, 123, beat // 2 - 3, beat // 2 + 2):
                for duration in (3, 117, 365, 837, 841, 1683, 2403):
                    with self.subTest(beat=beat, start=start, duration=duration):
                        parts = beat_rhythm_parts(start, duration, 0, beat)
                        self.assertTrue(all(length > 0 for _, length in parts))
                        self.assertEqual(parts[0][0], start)
                        self.assertEqual(parts[-1][0] + parts[-1][1], start + duration)
                        self.assertEqual(sum(length for _, length in parts), duration)
                        self.assertTrue(all(a + length == b for (a, length), (b, _) in zip(parts, parts[1:])))

    def test_context_and_bar_boundaries_keep_exact_source_continuations(self):
        note = Note(3000, 1800, 65); project = song([note])
        project.contexts = [Context(0, 3240), Context(3240, project.end, tonic=50)]
        fragments = played(project)
        self.assertEqual([(f.start, f.duration) for f in fragments],
                         [(3000, 240), (3240, 120), (3360, 480), (3840, 960)])
        self.assertEqual({f.note.id for f in fragments}, {note.id})
        self.assertTrue(all(f.continues for f in fragments[:-1]))
        self.assertTrue(all(f.continuation for f in fragments[1:]))

    def test_rest_and_rap_decomposition_keeps_its_existing_nonmetric_path(self):
        self.assertEqual(rhythm_parts(3000, 840), [(3000, 720), (3720, 120)])
        project = song([])
        ghosts = [f for f in fragments_for_bar(project, 0, [dict(kind='rap', tick=3000, duration=840)]) if f.ghost]
        self.assertEqual([(f.start, f.duration) for f in ghosts], [(3000, 720), (3720, 120)])


class OffbeatRenderingTests(unittest.TestCase):
    def test_all_styles_and_pdf_share_fragments_ties_ids_and_unchanged_midi(self):
        for style in STYLES:
            with self.subTest(style=style):
                note = Note(3000, 1800, 65); project = song([note], style=style)
                before = copy.deepcopy(project.to_dict()); midi = export_midi(project, None); events = event_list(project)
                layout = ScoreLayout(project); screen = render(layout)
                self.assertEqual(screen, [(note.id, 'continuous'), (note.id, 'outgoing'), (note.id, 'incoming')])
                self.assertEqual({nid for _, _, nid in layout.hit_notes}, {note.id})
                for _, _, _, points, xs in layout.hit_times:
                    self.assertTrue(all(b > a for a, b in zip(xs, xs[1:])))
                pdf = []; pdf_fragments = []; original = ScoreLayout.draw
                def record(current, *args, **kwargs):
                    original(current, *args, **kwargs)
                    pdf.extend((nid, kind) for nid, kind, _ in current.tie_paths)
                    pdf_fragments.append(signature(current))
                with tempfile.TemporaryDirectory(dir='tmp') as folder:
                    path = Path(folder) / (style + '.pdf')
                    with patch.object(ScoreLayout, 'draw', record):export_pdf(project, path)
                    self.assertTrue(path.read_bytes().startswith(b'%PDF'))
                self.assertEqual(pdf, screen)
                self.assertTrue(all(parts == signature(layout) for parts in pdf_fragments))
                self.assertEqual(project.to_dict(), before); self.assertEqual(event_list(project), events)
                self.assertEqual(export_midi(project, None), midi)

    def test_identical_adjacent_source_attacks_do_not_become_ties(self):
        for style in STYLES:
            project = song([Note(3000, 360, 65), Note(3360, 480, 65)], style=style)
            self.assertEqual(render(ScoreLayout(project)), [])

    def test_source_triplet_groups_survive_split_fragments_without_new_groups(self):
        for style in STYLES:
            triplets = [Note(t, 640, 60 + index) for index, t in enumerate((0, 640, 1280))]
            long = Note(6840, 800, 65)
            project = song([*triplets, long], style=style); before = copy.deepcopy(project.to_dict())
            layout = ScoreLayout(project); render(layout)
            self.assertEqual(len(layout.tuplet_groups), 1)
            self.assertEqual(set(layout.tuplet_groups[0]['source_ids']), {n.id for n in triplets})
            self.assertTrue(layout.tuplet_marks)
            self.assertTrue(all(long.id not in mark['source_ids'] for mark in layout.tuplet_marks))
            self.assertEqual({f.note.id for system in layout.systems for parts in system.fragments.values()
                              for f in parts if f.note}, {n.id for n in project.notes})
            self.assertEqual(project.to_dict(), before)


if __name__ == '__main__':
    unittest.main()
