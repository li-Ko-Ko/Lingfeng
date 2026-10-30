"""Page justification and an explicit, effective font-size range."""
import copy,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from lingfeng.ui.main_window import MainWindow
from lingfeng.music.model import Project, Note, Measure, Context
from lingfeng.engraving.notation import ScoreLayout, PAPER_W, PAPER_H, MARGIN
from lingfeng.engraving.presentation import apply_forced_row, add_compression, visible_bars
APP=QApplication.instance() or QApplication([])

def song(count=9,step=480,style='traditional'):
    p=Project();p.measures=[Measure() for _ in range(count)];p.contexts=[Context(0,p.end)];p.chords=[]
    p.notes=[Note(t,step,(60,62,64,65,67,69,71,72)[((t%3840)//step)%8]) for t in range(0,p.end,step)]
    p.notation.update(style=style,per_line=4,font_size=15,font_layout_version=45,circles=False,lyrics=False)
    return p

def render(layout,page=0):
    im=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);paint=QPainter(im);layout.draw(paint,page);paint.end();return im

class JustificationTests(unittest.TestCase):
    def assertMargins(self,p):
        layout=ScoreLayout(p)
        self.assertEqual([b for s in layout.systems for b in s.bars],visible_bars(p))
        for s in layout.systems:
            self.assertEqual(s.left,MARGIN);self.assertAlmostEqual(s.left+sum(s.bar_widths),PAPER_W-MARGIN)
        for page in range(layout.pages):render(layout,page)
        for page,rect,bar in layout.hit_bars:
            s=next(s for s in layout.systems if bar in s.bars)
            self.assertAlmostEqual(rect.left(),s.left+sum(s.bar_widths[:s.bars.index(bar)]))
        return layout

    def test_regular_final_and_explicit_break_rows_reach_both_margins(self):
        for count in (1,5,24):
            p=song(count);p.measures[0].break_after=True
            layout=self.assertMargins(p)
            self.assertTrue(all(len(s.bars)<=4 for s in layout.systems))

    def test_forced_and_hidden_repeat_rows_keep_margins_and_font_ratio(self):
        p=song(12);add_compression(p,list(range(4)),'repeat');apply_forced_row(p,list(range(4,10)))
        layout=self.assertMargins(p);forced=next(s for s in layout.systems if s.bars[0]==4)
        self.assertEqual(forced.bars,list(range(4,10)))
        self.assertAlmostEqual(forced.symbol_scale,layout.glyph_scale*2/3)

    def test_justification_expands_beat_gaps_without_stretching_symbol_cells(self):
        one=song(1);four=song(4)
        layouts=[ScoreLayout(p) for p in (one,four)]
        centers=[]
        for layout in layouts:
            s=layout.systems[0];points,xs,*_=layout.bar_map(s,0,0,s.bar_widths[0])
            centers.append([sum(layout.traditional_cell(0,t,points,xs))/2 for t in range(0,3840,480)])
        self.assertAlmostEqual(layouts[0].traditional_cell_width(0),layouts[1].traditional_cell_width(0))
        for a,b in zip(centers[0][::2],centers[0][1::2]):self.assertAlmostEqual(b-a,centers[1][1]-centers[1][0])
        self.assertGreater(centers[0][2]-centers[0][1],centers[1][2]-centers[1][1])

    def test_single_beat_bar_has_finite_map_and_contained_notes(self):
        p=song(1);p.measures=[Measure(1,4)];p.contexts=[Context(0,p.end)];p.notes=p.notes[:2]
        layout=self.assertMargins(p);s=layout.systems[0]
        for _,rect,_ in layout.hit_notes:
            self.assertGreaterEqual(rect.left(),MARGIN);self.assertLessEqual(rect.right(),PAPER_W-MARGIN)
        self.assertEqual(layout.beat_gap_count(0),0)
        points,xs,*_=layout.bar_map(s,0,MARGIN,s.bar_widths[0])
        self.assertAlmostEqual(xs[-1],PAPER_W-MARGIN)

    def test_spatial_styles_keep_their_pitch_label_margin_and_equal_beats(self):
        for style in ('spatial','compact'):
            layout=ScoreLayout(song(style=style));s=layout.systems[0]
            self.assertEqual(s.left,MARGIN+40);self.assertAlmostEqual(s.left+sum(s.bar_widths),PAPER_W-MARGIN)
            points,xs,*_=layout.bar_map(s,0,s.left,s.bar_widths[0])
            edges=[layout.interpolate(points,xs,t) for t in range(0,3841,960)]
            for a,b in zip(edges,edges[1:]):self.assertAlmostEqual(b-a,s.bar_widths[0]/4)

class FontLimitTests(unittest.TestCase):
    def setUp(self):
        self.pref=patch.object(MainWindow,'save_preferences');self.pref.start()
        self.w=MainWindow(song());self.w.timer.stop();self.w.autosave.stop();self.w.change_language('zh',False)
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.pref.stop()
    def enter(self,p=None):
        if p is not None:self.w.replace_project(p)
        self.w.switch_workspace('score');return self.w.score_view.canvas
    def assertEffective(self):
        w=self.w;canvas=w.score_view.canvas;layout=canvas.layout
        self.assertEqual(w.note_font.value(),w.project.notation['font_size'])
        self.assertEqual(w.note_font.value(),canvas.project.notation['font_size'])
        self.assertAlmostEqual(w.note_font.value(),15*layout.glyph_scale)
        self.assertEqual(w.note_font.maximum(),layout.font_limit)
        self.assertIn(f'{layout.font_limit:g}',w.font_limit_label.text())
        self.assertLessEqual(w.note_font.value(),layout.max_font_size+1e-7)

    def test_existing_oversized_value_is_normalized_and_saved_with_same_size(self):
        p=song(step=120);p.notation['font_size']=26;self.enter(p);w=self.w
        self.assertLess(w.note_font.maximum(),26);self.assertEffective();self.assertTrue(w.dirty)
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            file=Path(folder)/'font.lfs';w.project.save(file);w.replace_project(Project.load(file))
            self.assertEffective()

    def test_buttons_and_typed_value_cannot_exceed_visible_cap(self):
        self.enter();w=self.w;cap=w.note_font.maximum();w.note_font.setValue(cap);w.note_font.stepUp()
        self.assertEffective();self.assertEqual(w.note_font.value(),cap)
        editor=w.note_font.lineEdit();editor.selectAll();QTest.keyClicks(editor,'99');QTest.keyClick(editor,Qt.Key.Key_Return)
        self.assertEffective();self.assertLessEqual(w.note_font.value(),cap)

    def test_every_accepted_font_changes_glyph_scale_without_changing_rows(self):
        for style in ('spatial','compact','traditional'):
            self.enter(song(style=style));w=self.w;groups=[s.bars for s in w.score_view.canvas.layout.systems]
            for value in (1,2.5,w.note_font.maximum()):
                w.note_font.setValue(value);self.assertEffective()
                self.assertEqual([s.bars for s in w.score_view.canvas.layout.systems],groups)
                render(w.score_view.canvas.layout)
                self.assertTrue(all(abs(size-value)<1e-7 for _,size in w.score_view.canvas.layout.glyph_sizes))

    def test_per_line_change_updates_limit_and_undo_redo_restores_font(self):
        self.enter();w=self.w;w.note_font.setValue(w.note_font.maximum());first=(w.note_font.value(),w.note_font.maximum())
        w.set_notation('per_line',8);self.assertEffective();second=(w.note_font.value(),w.note_font.maximum())
        self.assertLess(second[1],first[1]);self.assertEqual(len(w.score_view.canvas.layout.systems[0].bars),8)
        w.undo();self.assertEffective();self.assertEqual((w.note_font.value(),w.note_font.maximum()),first)
        w.redo();self.assertEffective();self.assertEqual((w.note_font.value(),w.note_font.maximum()),second)

    def test_pitch_gap_and_forced_row_recompute_safe_limit(self):
        p=song(style='spatial');p.notes=[Note(0,960,60),Note(0,960,62)];p.notation.update(row_gap=16,font_size=26)
        self.enter(p);w=self.w;first=w.note_font.maximum();w.set_notation('row_gap',8)
        self.assertLess(w.note_font.maximum(),first);self.assertEffective()
        w.mutate('merge',lambda q:apply_forced_row(q,list(range(6))),source='score');self.assertEffective()
        s=w.score_view.canvas.layout.systems[0];self.assertEqual(s.bars,list(range(6)))
        self.assertAlmostEqual(s.symbol_scale,w.note_font.value()/15*2/3)

    def test_music_snapshot_keeps_limit_until_reentry_and_compose_is_idle(self):
        canvas=self.enter();w=self.w;old=canvas.layout;cap=w.note_font.maximum()
        w.mutate('dense',lambda p:setattr(p,'notes',song(step=120).notes))
        self.assertIs(canvas.layout,old);self.assertEqual(w.note_font.maximum(),cap)
        w.switch_workspace('compose')
        with patch('lingfeng.ui.score_view.ScoreLayout',wraps=ScoreLayout) as build:
            w.refresh();w.show_cursor(120);build.assert_not_called()
        w.switch_workspace('score');self.assertLess(w.note_font.maximum(),cap);self.assertEffective()

    def test_language_rebuild_keeps_limit_value_and_layout(self):
        canvas=self.enter();layout=canvas.layout;w=self.w;w.note_font.setValue(2);layout=canvas.layout
        w.change_language('en',False);self.assertEffective();self.assertIs(w.score_view.canvas.layout,layout)
        self.assertIn('Max',w.font_limit_label.text());self.assertIn('measures per line',w.note_font.toolTip())

    def test_dense_sub_unit_limit_is_explicit_and_persists(self):
        p=song(count=16,step=60);p.notation.update(per_line=16,style='spatial',font_size=26)
        before=copy.deepcopy(p.notes);canvas=self.enter(p);cap=canvas.layout.font_limit
        self.assertLess(cap,1);self.assertGreaterEqual(cap,.0001);self.assertEffective()
        p.validate();restored=Project.from_dict(p.to_dict());self.assertEqual(restored.notation['font_size'],cap)
        self.assertEqual(before,p.notes);self.assertEqual(len(canvas.layout.systems),1)
        self.assertTrue(all(canvas.layout.width_cache[b]*canvas.layout.glyph_scale<=w+1e-7 for s in canvas.layout.systems for b,w in zip(s.bars,s.bar_widths)))

if __name__=='__main__':unittest.main()
