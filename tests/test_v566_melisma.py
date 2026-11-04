"""Lyric melismas take precedence over conflicting manual slurs."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from lingfeng.audio.midi import export_midi
from lingfeng.engraving.lyrics import (
    apply_range, delete_range, events, melisma_links,
)
from lingfeng.engraving.notation import PAPER_H, PAPER_W, ScoreLayout, export_pdf
from lingfeng.engraving.presentation import add_slur, can_add_slur, slur_conflicts, add_annotation
from lingfeng.music.model import Context, Measure, Note, Project
from lingfeng.ui.main_window import MainWindow

APP = QApplication.instance() or QApplication([])
STYLES = ('traditional', 'spatial', 'compact')


def song(bars=4):
    p = Project(measures=[Measure() for _ in range(bars)])
    p.contexts = [Context(0, p.end)]
    p.notes = [Note(bar * 3840 + tick, 480, pitch) for bar in range(bars)
               for tick, pitch in ((0, 60), (480, 64), (960, 62))]
    p.notation.update(per_line=1, font_size=12, circles=False)
    return p


def render(layout, page=0):
    image = QImage(PAPER_W, PAPER_H, QImage.Format.Format_RGB32)
    image.fill(0xffffffff); painter = QPainter(image)
    try:layout.draw(painter, page)
    finally:painter.end()
    return image


class AutomaticAnnotationTests(unittest.TestCase):
    def test_adjacent_links_remain_separate_and_metadata_does_not_persist_symbols(self):
        p = song(); apply_range(p, '春/-/-', 0, 1)
        before = copy.deepcopy(p.to_dict()); midi = export_midi(p, None)
        self.assertEqual([(a, b) for a, b, _, _ in melisma_links(p)], [(0, 480), (480, 960)])
        self.assertFalse(p.notation.get('symbols'))
        for style in STYLES:
            p.notation['style'] = style; layout = ScoreLayout(p); render(layout)
            self.assertEqual([(a, b, kind) for a, b, kind, _ in layout.melisma_paths],
                             [(0, 480, 'continuous'), (480, 960, 'continuous')])
        p.notation['style'] = before['notation']['style']
        self.assertEqual(p.to_dict(), before); self.assertEqual(export_midi(p, None), midi)

    def test_multiple_stanzas_share_one_automatic_arc(self):
        p = song(); apply_range(p, '春/-/-', 0, 1); apply_range(p, '风/-/-', 0, 1, verse=2)
        self.assertEqual(len(melisma_links(p)), 2)
        p.notes.append(Note(480, 240, 76)); p.notation['style'] = 'spatial'
        self.assertEqual(len(melisma_links(p)), 2)
        layout = ScoreLayout(p); render(layout); self.assertEqual(len(layout.melisma_paths), 2)

    def test_polyphonic_lyric_voices_resolve_their_own_preceding_pitch(self):
        p = song(1)
        p.notes = [Note(0, 480, 60), Note(0, 480, 72), Note(480, 480, 62), Note(480, 480, 74)]
        p.notation['lyric_events'] = [
            dict(id='word-0', tick=0, text='春', verse=0, voice=0, pitch=60),
            dict(id='word-1', tick=0, text='风', verse=0, voice=1, pitch=72),
            dict(id='melisma-0', tick=480, text='', skip=True, melisma=True, verse=0, voice=0, pitch=62),
            dict(id='melisma-1', tick=480, text='', skip=True, melisma=True, verse=0, voice=1, pitch=74),
        ]
        self.assertEqual([(left, right) for _, _, left, right in melisma_links(p)],
                         [(p.notes[0].id, p.notes[2].id), (p.notes[1].id, p.notes[3].id)])

    def test_legacy_skips_do_not_create_automatic_annotations(self):
        p = song(); apply_range(p, '春/s/s', 0, 1)
        p.notation['lyric_sections'][0].update(text='春/-/-', syntax_version=3)
        before = p.to_dict(); self.assertFalse(melisma_links(p)); self.assertEqual(p.to_dict(), before)

    def test_cross_page_intermediate_rest_and_sustain_rows_keep_continuation_arcs(self):
        for style in STYLES:
            for sustain in (False, True):
                with self.subTest(style=style, sustain=sustain):
                    p = song(16); last = p.starts[-2]
                    p.notes = [Note(0, last if sustain else 480, 60), Note(last, 480, 62)]
                    p.notation.update(style=style, lyrics=False)
                    plain = ScoreLayout(p)
                    apply_range(p, '/-', 15, 1)
                    before = copy.deepcopy(p.to_dict()); midi = export_midi(p, None)
                    layout = ScoreLayout(p); self.assertGreater(layout.pages, 1)
                    paths = []; rests = {}
                    for page in range(layout.pages):
                        render(layout, page); paths.extend(layout.melisma_paths)
                        rests.update((tick,y) for tick,_,_,y in layout.rest_positions)
                    self.assertEqual([kind for _, _, kind, _ in paths],
                                     ['outgoing'] + ['through'] * 14 + ['incoming'])
                    for system, (_, _, kind, path), original in zip(layout.systems, paths, plain.systems):
                        self.assertGreater(path.boundingRect().width(), 0)
                        self.assertGreaterEqual(path.boundingRect().top(), system.top)
                        self.assertLessEqual(path.boundingRect().bottom(), system.top + system.height)
                        if kind == 'through':
                            self.assertTrue(system.melisma_through)
                            self.assertGreater(system.extra_header, original.extra_header)
                            self.assertGreater(system.height, original.height)
                            if not sustain:
                                first,last=p.starts[system.bars[0]],p.starts[system.bars[-1]+1]
                                self.assertLess(path.boundingRect().bottom(),min(y for tick,y in rests.items() if first<=tick<last))
                    self.assertEqual(p.to_dict(), before); self.assertEqual(export_midi(p, None), midi)

    def test_pdf_and_screen_share_all_cross_page_paths_and_keep_manual_slurs_separate(self):
        for style in STYLES:
            with self.subTest(style=style):
                p = song(12); last = p.starts[-2]
                p.notes = [Note(0, 480, 60), Note(last, 480, 62)]
                p.notation['style'] = style; add_slur(p, [n.id for n in p.notes])
                apply_range(p, '/-', 11, 1)
                before = p.to_dict(); midi = export_midi(p, None); layout = ScoreLayout(p)
                screen = []
                for page in range(layout.pages):
                    render(layout, page)
                    screen.extend((a, b, kind) for a, b, kind, _ in layout.melisma_paths)
                    self.assertFalse(layout.manual_slur_paths)
                seen = []; original = ScoreLayout.draw
                def record(current, *args, **kwargs):
                    original(current, *args, **kwargs)
                    seen.extend((a, b, kind) for a, b, kind, _ in current.melisma_paths)
                with tempfile.TemporaryDirectory(dir='tmp') as folder:
                    target = Path(folder) / 'automatic.pdf'
                    with patch.object(ScoreLayout, 'draw', record):export_pdf(p, target)
                    self.assertTrue(target.read_bytes().startswith(b'%PDF'))
                    saved = Path(folder) / 'automatic.lfs'; p.save(saved)
                    self.assertEqual(Project.load(saved).to_dict(), before)
                self.assertEqual(seen, screen); self.assertEqual(p.to_dict(), before)
                self.assertEqual(export_midi(p, None), midi)


class SlurPriorityTests(unittest.TestCase):
    def test_same_voice_positive_overlap_is_blocked_but_touching_endpoints_are_allowed(self):
        p=song(1);apply_range(p,'春/-/s',0,1)
        before=p.to_dict()
        for notes in (p.notes[:2],p.notes):
            ids=[n.id for n in notes]
            self.assertFalse(can_add_slur(p,ids));self.assertTrue(slur_conflicts(p,dict(note_ids=ids)))
            with self.assertRaisesRegex(ValueError,'歌词连音优先'):add_slur(p,ids)
            self.assertEqual(p.to_dict(),before)
        self.assertTrue(can_add_slur(p,[n.id for n in p.notes[1:]]))
        add_slur(p,[n.id for n in p.notes[1:]])
        layout=ScoreLayout(p);render(layout)
        self.assertEqual(len(layout.melisma_paths),1);self.assertEqual(len(layout.manual_slur_paths),1)

    def test_independent_polyphonic_voice_can_overlap_the_lyric_arc(self):
        p=song(1);p.notation['style']='spatial'
        p.notes=[Note(t,480,pitch) for t in (0,480,960) for pitch in (72+t//480,60+t//480)]
        apply_range(p,'春/-/-',0,1)
        lower=[n.id for n in p.notes if n.pitch<70];upper=[n.id for n in p.notes if n.pitch>=70]
        self.assertTrue(can_add_slur(p,lower));self.assertFalse(can_add_slur(p,upper))
        add_slur(p,lower);layout=ScoreLayout(p);render(layout)
        self.assertEqual(len(layout.manual_slur_paths),1);self.assertEqual(len(layout.melisma_paths),2)

    def test_short_legato_tails_do_not_evade_same_voice_priority(self):
        p=song(1);p.notes[0].duration=500;p.notation['style']='spatial'
        apply_range(p,'春/-/-',0,1)
        self.assertFalse(can_add_slur(p,[n.id for n in p.notes]))

    def test_loaded_conflicts_keep_original_symbol_indexes_and_ordinary_marks(self):
        p=song(1);add_slur(p,[n.id for n in p.notes[:2]])
        add_slur(p,[n.id for n in p.notes[1:]]);add_annotation(p,'rit',0,1440)
        apply_range(p,'春/-/s',0,1);before=p.to_dict();p.validate()
        q=Project.from_dict(before);layout=ScoreLayout(q);render(layout)
        self.assertEqual([index for index,_,_ in layout.manual_slur_paths],[1])
        self.assertNotIn(('symbols',0),[key for _,_,key in layout.hit_symbols])
        self.assertIn(('symbols',1),[key for _,_,key in layout.hit_symbols])
        self.assertIn(('symbols',2),[key for _,_,key in layout.hit_symbols])
        self.assertEqual(q.to_dict(),before)
        delete_range(q,0,1);layout=ScoreLayout(q);render(layout)
        self.assertEqual([index for index,_,_ in layout.manual_slur_paths],[0,1])


class AutomaticAnnotationPanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='tmp'); self.addCleanup(self.temp.cleanup)
        self.pref = patch('lingfeng.ui.main_window.user_data_dir', return_value=Path(self.temp.name))
        self.pref.start(); self.addCleanup(self.pref.stop)
        self.w = MainWindow(song()); self.w.timer.stop(); self.w.autosave.stop()
        self.w.change_language('zh', False); self.w.resize(1160, 870); self.w.show()
        self.w.switch_workspace('score'); self.w.show_score_panel('annotations'); APP.processEvents()
        self.addCleanup(self.close)

    def close(self):
        self.w.dirty = False; self.w.close(); self.w.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete); APP.processEvents()

    def commit(self, text, first=0, count=1, verse=0):
        return self.w.mutate('lyrics', lambda p: apply_range(p, text, first, count, verse, replace=True), source='lyrics')

    def select(self, notes):
        canvas=self.w.score_view.canvas;canvas.set_selection_unit('note');canvas.selected_notes={n.id for n in notes}
        panel=self.w.annotation_panel;panel.kind.setCurrentIndex(panel.kind.findData('slur'));panel.refresh()

    def test_conflicting_create_is_disabled_but_ordinary_marks_and_touching_arcs_are_allowed(self):
        w=self.w;self.commit('春/-/s');self.select(w.project.notes[:2]);panel=w.annotation_panel
        self.assertFalse(panel.add_button.isEnabled());self.assertIn('歌词',panel.add_button.toolTip())
        self.assertFalse(can_add_slur(w.project,[n.id for n in w.project.notes[:2]]))
        self.assertEqual(panel.items.count(),0)  # lyric arcs stay outside manual marks
        self.select(w.project.notes[1:3]);self.assertTrue(panel.add_button.isEnabled());panel.add()
        self.assertEqual(len(w.project.notation['symbols']),1)
        panel.kind.setCurrentIndex(panel.kind.findData('rit'));w.score_view.canvas.selected_bars={0};panel.refresh()
        self.assertTrue(panel.add_button.isEnabled());panel.add()
        self.assertEqual([e['kind'] for e in w.project.notation['symbols']],['slur','rit'])

    def test_same_onset_invalid_selection_does_not_claim_a_lyric_conflict(self):
        w=self.w;w.mutate('polyphonic attack',lambda p:p.notes.append(Note(0,240,72)),source=w.roll)
        self.select([w.project.notes[0],w.project.notes[-1]])
        self.assertFalse(w.annotation_panel.add_button.isEnabled())
        self.assertEqual(w.annotation_panel.add_button.toolTip(),'')

    def test_lyrics_commit_hides_existing_manual_arc_delete_and_undo_restore_it(self):
        w=self.w;self.commit('春/s/s');self.select(w.project.notes[:3]);w.annotation_panel.add()
        before=export_midi(w.project,None);saved=copy.deepcopy(w.project.notation['symbols'])
        self.commit('春/-/-');layout=ScoreLayout(w.score_view.canvas.project);render(layout)
        self.assertTrue(layout.melisma_paths);self.assertFalse(layout.manual_slur_paths)
        self.assertEqual(w.project.notation['symbols'],saved);self.assertEqual(w.annotation_panel.items.count(),1)
        w.undo();layout=ScoreLayout(w.score_view.canvas.project);render(layout)
        self.assertTrue(layout.manual_slur_paths);self.assertFalse(layout.melisma_paths)
        w.redo();self.commit('春/s/s');layout=ScoreLayout(w.score_view.canvas.project);render(layout)
        self.assertTrue(layout.manual_slur_paths);self.assertFalse(layout.melisma_paths)
        self.assertEqual(w.project.notation['symbols'],saved);self.assertEqual(export_midi(w.project,None),before)

    def test_rendering_priority_uses_the_current_score_music_snapshot(self):
        w=self.w;self.select(w.project.notes[:3]);w.annotation_panel.add();self.commit('春/-/-')
        snapshot=copy.deepcopy(w.score_view.canvas.project.to_dict())
        w.mutate('move attack',lambda p:setattr(p.notes[1],'start',240),source=w.roll)
        self.assertEqual(w.score_view.canvas.project.to_dict(),snapshot)
        layout=ScoreLayout(w.score_view.canvas.project);render(layout)
        self.assertEqual(len(layout.melisma_paths),2);self.assertFalse(layout.manual_slur_paths)
        w.score_view.canvas.rebuild(w.project);layout=ScoreLayout(w.score_view.canvas.project);render(layout)
        self.assertEqual(len(layout.melisma_paths),1);self.assertFalse(layout.manual_slur_paths)

    def test_conflicting_saved_mark_stays_selectable_and_can_be_deleted_without_affecting_lyrics(self):
        w=self.w;self.select(w.project.notes[:3]);w.annotation_panel.add();self.commit('春/-/-')
        panel=w.annotation_panel;panel.items.setCurrentRow(0);before=copy.deepcopy(events(w.project))
        self.assertTrue(panel.remove_button.isEnabled());panel.remove()
        self.assertFalse(w.project.notation['symbols']);self.assertEqual(events(w.project),before)
        w.undo();self.assertEqual(len(w.project.notation['symbols']),1)
        self.assertEqual(events(w.project),before)


if __name__ == '__main__':unittest.main()
