import copy
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from popscore.model import Note, Project
from popscore.notation import ScoreLayout, fragments_for_bar, rhythm_parts, rhythm_style


APP = QApplication.instance() or QApplication([])


class NotationTimingTests(unittest.TestCase):
    def render(self, project):
        layout = ScoreLayout(project)
        image = QImage(900, 1273, QImage.Format.Format_RGB32)
        painter = QPainter(image)
        layout.draw(painter, 0)
        painter.end()
        return layout

    def test_two_tick_midi_remainder_does_not_create_tie_or_rest(self):
        # A short-note run with the same timing pattern as the reported score:
        # the second beat is offset by 2 ticks and its last note lasts 118.
        p = Project()
        p.notes = [Note(i * 120, 120, 60 + i % 4) for i in range(8)]
        p.notes += [Note(962 + i * 120, 118 if i == 7 else 120, 60 + i % 4)
                    for i in range(8)]
        p.notes.append(Note(1920, 120, 60))
        before = copy.deepcopy(p.to_dict())
        fragments = fragments_for_bar(p, 0)
        played = [f for f in fragments if f.note]
        self.assertEqual([(f.start, f.duration) for f in played],
                         [(n.start, n.duration) for n in p.notes])
        self.assertFalse(any(f.pitch is None and f.start == 960 for f in fragments))
        self.assertFalse(any(f.continuation or f.continues for f in played))
        self.assertEqual(rhythm_style(118), rhythm_style(120))
        layout = self.render(p)
        self.assertEqual(layout.tie_paths, [])
        points, weights = layout.time_slots(0, fragments)
        self.assertLess(weights[points.index(960)], 1)
        self.assertEqual(p.to_dict(), before)

    def test_tolerance_preserves_straight_dotted_and_triplet_styles(self):
        for value in (3840, 1440, 960, 720, 640, 480, 320, 180, 120, 90, 80, 60, 45, 40, 30):
            for delta in (-2, -1, 0, 1, 2):
                with self.subTest(value=value, delta=delta):
                    self.assertEqual(rhythm_parts(17, value + delta), [(17, value + delta)])
                    self.assertEqual(rhythm_style(value + delta), rhythm_style(value))

    def test_tolerance_is_not_general_quantization(self):
        self.assertEqual(rhythm_parts(0, 117), [(0, 90), (90, 27)])
        p = Project()
        p.notes = [Note(0, 120, 60), Note(123, 120, 62)]
        rests = [f for f in fragments_for_bar(p, 0) if f.pitch is None]
        self.assertTrue(any((f.start, f.duration) == (120, 3) for f in rests))

    def test_real_short_notes_and_rests_are_retained(self):
        p = Project()
        p.notes = [Note(0, 30, 60), Note(60, 40, 62), Note(102, 2, 64)]
        fragments = fragments_for_bar(p, 0)
        self.assertEqual([(f.start, f.duration) for f in fragments if f.note],
                         [(0, 30), (60, 40), (102, 2)])
        self.assertTrue(any(f.pitch is None and (f.start, f.duration) == (30, 30)
                            for f in fragments))

    def test_real_duration_decomposition_still_has_a_tie(self):
        p = Project()
        p.notes = [Note(1920, 1200, 84), Note(3120, 480, 84)]
        fragments = [f for f in fragments_for_bar(p, 0) if f.note]
        self.assertEqual([(f.start, f.duration) for f in fragments],
                         [(1920, 960), (2880, 240), (3120, 480)])
        layout = self.render(p)
        self.assertEqual([(nid, kind) for nid, kind, path in layout.tie_paths],
                         [(p.notes[0].id, 'continuous')])

    def test_adjacent_repeated_notes_remain_separate_without_ties(self):
        p = Project()
        p.notes = [Note(0, 120, 60), Note(120, 118, 60), Note(240, 120, 60)]
        layout = self.render(p)
        self.assertEqual(layout.tie_paths, [])
        self.assertEqual({nid for page, rect, nid in layout.hit_notes},
                         {n.id for n in p.notes})

    def test_cross_bar_ties_keep_exact_timing(self):
        p = Project()
        p.notes = [Note(3600, 480, 60)]
        fragments = [f for bar in (0, 1) for f in fragments_for_bar(p, bar) if f.note]
        self.assertEqual([(f.start, f.duration, f.continuation, f.continues) for f in fragments],
                         [(3600, 240, False, True), (3840, 240, True, False)])
        self.assertEqual([kind for nid, kind, path in self.render(p).tie_paths], ['continuous'])


if __name__ == '__main__':
    unittest.main()
