"""Chord-label circles agree across screen geometry and PDF without MIDI edits."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QImage, QPainter, QTransform
from PySide6.QtWidgets import QApplication
from lingfeng.audio.midi import event_list, export_midi
from lingfeng.engraving.notation import PAPER_H, PAPER_W, ScoreLayout, export_pdf, is_chord_tone
from lingfeng.music.model import Chord, Context, Measure, Note, Project
from lingfeng.music.recognition import set_marker, set_recognition_disabled
from lingfeng.platform import i18n
from lingfeng.ui.main_window import MainWindow

APP = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parents[1]
STYLES = ('spatial', 'compact', 'traditional')


def song(style='spatial', empty=False):
    project = Project(measures=[Measure()])
    project.contexts = [Context(0, project.end)]
    project.notes = [Note(index * 240, 240, pitch, 83 + index) for index, pitch in enumerate((64, 62, 65, 66))]
    project.chords = [Chord(0, project.end, notes=[] if empty else [Note(0, project.end, p, 67) for p in (48, 52, 55)])]
    project.notation.update(style=style, circles=True, lyrics=False, per_line=1, font_size=15, font_layout_version=45)
    return project


def circle_pcs(project, tick=120):
    return {pitch for pitch in range(12) if is_chord_tone(project, pitch + 60, tick)}


class CirclePainter(QPainter):
    def __init__(self, device):
        super().__init__(device)
        self.circles = []; self.page_inverse = QTransform()

    def drawEllipse(self, *args):
        if len(args) == 3 and isinstance(args[0], QPointF):
            center, rx, ry = args
            if abs(rx - ry) > 1e-7:
                half = self.pen().widthF() / 2
                rect = QRectF(center.x() - rx - half, center.y() - ry - half,
                              2 * (rx + half), 2 * (ry + half))
                self.circles.append(self.page_inverse.mapRect(self.worldTransform().mapRect(rect)))
        return super().drawEllipse(*args)


def screen_circles(layout):
    image = QImage(PAPER_W, PAPER_H, QImage.Format.Format_RGB32); image.fill(0xffffffff)
    painter = CirclePainter(image)
    try:
        layout.draw(painter, 0)
        return list(painter.circles)
    finally:
        painter.end()


def geometry(rectangles):
    return [tuple(round(value, 5) for value in (rect.x(), rect.y(), rect.width(), rect.height())) for rect in rectangles]


class CircleRuleTests(unittest.TestCase):
    def test_manual_root_quality_and_arbitrary_slash_bass_define_circles(self):
        for root, quality, bass, expected in ((2, 'm7', 6, {0, 2, 5, 6, 9}),
                                             (6, 'aug', 11, {2, 6, 10, 11}),
                                             (2, 'no5', 1, {1, 2, 6})):
            with self.subTest(root=root, quality=quality, bass=bass):
                project = song(); chord = project.chords[0]
                before = copy.deepcopy(chord.render_notes()); events = event_list(project)
                set_marker(chord, root, quality, bass)
                self.assertEqual(circle_pcs(project), expected)
                self.assertEqual(chord.pcs, {0, 4, 7})
                self.assertEqual(chord.render_notes(), before); self.assertEqual(event_list(project), events)
                self.assertFalse(is_chord_tone(project, 62, project.end))

    def test_empty_manual_marker_has_circles_without_creating_harmony_notes(self):
        project = song(empty=True); chord = project.chords[0]
        self.assertEqual(circle_pcs(project), set()); original = event_list(project)
        set_marker(chord, 2, 'm7', 6)
        self.assertEqual(circle_pcs(project), {0, 2, 5, 6, 9})
        self.assertEqual(project.harmony_notes(), []); self.assertEqual(event_list(project), original)
        for style in STYLES:
            project.notation['style'] = style
            self.assertEqual(len(screen_circles(ScoreLayout(project))), 3)

    def test_unmarked_cropped_arpeggio_and_disabled_recognition_keep_actual_tones(self):
        project = song(); chord = Chord(0, 240, pattern='up'); project.chords = [chord]
        actual = {note.pitch % 12 for note in chord.render_notes()}
        self.assertEqual(actual, {0}); self.assertEqual(circle_pcs(project), actual)
        set_recognition_disabled(chord, True, project)
        self.assertFalse(chord.marked); self.assertEqual(circle_pcs(project), actual)
        set_marker(chord, 0, '')
        self.assertEqual(circle_pcs(project), {0, 4, 7})
        set_recognition_disabled(chord, False, project)
        self.assertEqual(circle_pcs(project), actual)
        chord.recognized = False
        self.assertEqual(circle_pcs(project), actual)

    def test_marker_save_reopen_and_resume_keep_performed_events(self):
        project = song(); chord = project.chords[0]; before = event_list(project)
        set_marker(chord, 2, 'm7', 6)
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as folder:
            path = Path(folder) / 'marked.lfs'; project.save(path); loaded = Project.load(path)
        self.assertEqual(circle_pcs(loaded), {0, 2, 5, 6, 9}); self.assertEqual(event_list(loaded), before)
        set_recognition_disabled(loaded.chords[0], False, loaded)
        self.assertFalse(loaded.chords[0].marked); self.assertEqual(circle_pcs(loaded), {0, 4, 7})
        self.assertEqual(event_list(loaded), before)

    def test_marker_undo_redo_resume_and_score_reentry_update_visible_circles(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as folder, patch.dict(os.environ, {
                'LINGFENG_USER_DATA': folder, 'LINGFENG_SYNTH_CACHE': str(Path(folder) / 'index.json')}):
            previous_language = i18n.LANGUAGE
            window = MainWindow(song()); window.timer.stop(); window.autosave.stop()
            try:
                before = event_list(window.project); chord_id = window.project.chords[0].id
                self.assertTrue(window.switch_workspace('score'))
                self.assertEqual(len(screen_circles(window.score_view.canvas.layout)), 1)
                frozen = window.score_view.canvas.project
                window.mutate('mark', lambda p: set_marker(p.chords[0], 2, 'm7', 6), source='harmony')
                self.assertIs(window.score_view.canvas.project, frozen)
                self.assertFalse(frozen.chords[0].marked)
                self.assertEqual(circle_pcs(frozen), {0, 4, 7})
                self.assertEqual(circle_pcs(window.project), {0, 2, 5, 6, 9})
                self.assertEqual(len(screen_circles(window.score_view.canvas.layout)), 1)
                def count_after_reentry():
                    window.switch_workspace('compose'); window.switch_workspace('score')
                    return len(screen_circles(window.score_view.canvas.layout))
                self.assertEqual(count_after_reentry(), 3)
                window.undo(); self.assertEqual(count_after_reentry(), 1)
                window.redo(); self.assertEqual(count_after_reentry(), 3)
                window.chord_command('recognition:0', {chord_id}, window.harmony_window.roll)
                self.assertEqual(count_after_reentry(), 1); self.assertEqual(event_list(window.project), before)
            finally:
                window.dirty = False; window.close(); i18n.set_language(previous_language)


class CircleGeometryTests(unittest.TestCase):
    def test_marker_rule_drives_glyph_reserve_and_ink_envelope_in_every_style(self):
        for style in STYLES:
            with self.subTest(style=style):
                project = song(style); set_marker(project.chords[0], 2, 'm7', 6)
                before = copy.deepcopy(project.to_dict()); midi = export_midi(project, None)
                layout = ScoreLayout(project)
                fragments = [fragment for system in layout.systems for parts in system.fragments.values()
                             for fragment in parts if fragment.note and fragment.start == fragment.note.start]
                by_pitch = {fragment.pitch: fragment for fragment in fragments}
                self.assertEqual(layout.glyph_extents(by_pitch[64]), (7, 7))
                for pitch in (62, 65):
                    self.assertEqual(layout.glyph_extents(by_pitch[pitch]), (11, 11))
                    ink = layout.symbol_ink(by_pitch[pitch], layout.systems[0])
                    self.assertLessEqual(ink[0], -10); self.assertGreaterEqual(ink[2], 10)
                self.assertEqual(layout.glyph_extents(by_pitch[66]), (18, 11))
                circles = screen_circles(layout)
                self.assertEqual(len(circles), 3)
                circled_ids = set()
                for circle in circles:
                    hits = [(rect, note_id) for _, rect, note_id in layout.hit_notes if rect.contains(circle.center())]
                    self.assertEqual(len(hits), 1)
                    rect, note_id = hits[0]; circled_ids.add(note_id)
                    self.assertGreaterEqual(rect.width() + 1e-6, circle.width())
                    self.assertGreaterEqual(rect.height() + 1e-6, circle.height())
                self.assertEqual(circled_ids, {note.id for note in project.notes if note.pitch != 64})
                self.assertEqual(project.to_dict(), before); self.assertEqual(export_midi(project, None), midi)

    def test_real_pdf_painter_draws_same_circles_and_geometry_as_screen(self):
        for style in STYLES:
            with self.subTest(style=style), tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as folder:
                project = song(style); set_marker(project.chords[0], 2, 'm7', 6)
                before = copy.deepcopy(project.to_dict()); expected = screen_circles(ScoreLayout(project))
                painters = []; original = ScoreLayout.draw
                class PdfPainter(CirclePainter):
                    def __init__(self, device):
                        super().__init__(device); painters.append(self)
                def draw(layout, current, page, *args, **kwargs):
                    current.page_inverse = current.worldTransform().inverted()[0]
                    return original(layout, current, page, *args, **kwargs)
                target = Path(folder) / (style + '.pdf')
                with patch('lingfeng.engraving.notation.QPainter', PdfPainter), patch.object(ScoreLayout, 'draw', draw):
                    self.assertEqual(export_pdf(project, target), 1)
                self.assertEqual(geometry(painters[0].circles), geometry(expected))
                self.assertTrue(target.read_bytes().startswith(b'%PDF')); self.assertEqual(project.to_dict(), before)


if __name__ == '__main__':
    unittest.main()
