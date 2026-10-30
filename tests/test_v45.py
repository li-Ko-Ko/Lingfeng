"""Global score typography, whole-bar packing and symbol-based traditional spacing."""
import copy,os,unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from popscore.model import Project,Note,Chord,Measure,Context
from popscore.notation import ScoreLayout,PAPER_W,PAPER_H,MARGIN
from popscore.presentation import apply_forced_row,shift_presentation
from popscore.scoreview import ScoreCanvas
APP=QApplication.instance() or QApplication([])

def music():
    p=Project();p.title='Global engraving'
    p.notes=[Note(0,960,60),Note(960,480,62),Note(1440,240,63),Note(1680,240,64),Note(1920,1920,67)]
    p.notes += [Note(3840+i*120,120,61+i%7) for i in range(32)]
    p.notes += [Note(7680,2880,65),Note(10560,960,67)]
    p.chords=[Chord(0,3840),Chord(3840,3840,55,'7b5'),Chord(7680,3840,53,'maj7')]
    return p

def render(p):
    layout=ScoreLayout(p);image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);paint=QPainter(image)
    layout.draw(paint,0);paint.end();return layout,image

class EngravingTests(unittest.TestCase):
    def test_global_size_includes_sparse_rows_rests_and_rap(self):
        from popscore.lyrics import apply_section
        p=music();apply_section(p,'我/64.爱/64你/64',14400)
        for style in ('spatial','compact','traditional'):
            p.notation.update(style=style,font_size=26);layout,_=render(p)
            self.assertEqual(len({v for _,v in layout.glyph_sizes}),1)
            self.assertEqual({v for _,v in layout.glyph_sizes},{15*layout.glyph_scale})
            self.assertTrue({'0','x'}.issubset({v for v,_ in layout.glyph_sizes}))

    def test_variable_bars_equal_beats_all_denominators(self):
        for numerator,denominator in ((2,2),(4,4),(6,8),(8,16),(3,4),(5,8)):
            p=music();p.measures[2]=Measure(numerator,denominator);p.contexts=[Context(0,p.end)]
            for style in ('spatial','compact'):
                p.notation['style']=style;layout,_=render(p);s=layout.systems[0]
                self.assertGreater(s.bar_widths[1],s.bar_widths[0])
                for _,rect,bar,points,xs in layout.hit_times:
                    for t,x in zip(points,xs):self.assertAlmostEqual(x,rect.left()+rect.width()*(t-p.starts[bar])/p.measures[bar].ticks)

    def test_traditional_symbols_not_durations_own_equal_slots(self):
        p=Project();p.notation.update(style='traditional',per_line=1)
        p.notes=[Note(0,240,60),Note(240,720,61),Note(960,1920,64),Note(2880,960,65)]
        layout,_=render(p);s=layout.systems[0];slots=layout.engraving_slots(0,s.fragments[0])
        self.assertEqual(slots,[0,240,960,1920,2880,3840]) # 1920 is the long-note dash.
        points,xs,*_=layout.bar_map(s,0,0,s.bar_widths[0]);positions=[layout.interpolate(points,xs,t) for t in slots]
        unit=layout.traditional_cell_width(0);extra=(s.bar_widths[0]-7.25*unit)/3
        for position,wanted,gaps in zip(positions,[0,1,2.75,4.5,6.25,7.25],[0,0,1,2,3,3]):self.assertAlmostEqual(position,wanted*unit+gaps*extra)
        # Accidentals change the glyph envelope, but note centers use each slot midpoint.
        hits={nid:r for pg,r,nid in layout.hit_notes}
        first=hits[p.notes[0].id];third=hits[p.notes[2].id]
        self.assertAlmostEqual(third.center().x()-first.center().x(),2.75*unit+extra)

    def test_forced_rows_scale_from_global_and_remember_original_count(self):
        p=music();apply_forced_row(p,list(range(6)))
        for style in ('spatial','compact','traditional'):
            p.notation['style']=style
            for size in (2,4):
                p.notation['font_size']=size;layout,_=render(p)
                self.assertEqual(layout.systems[0].bars,list(range(6)))
                for s in layout.systems:
                    ratio=2/3 if s is layout.systems[0] else 1
                    for scale in s.bar_scales.values():self.assertAlmostEqual(scale,layout.glyph_scale*ratio)
            p.notation['per_line']=8
            layout=ScoreLayout(Project.from_dict(p.to_dict()))
            self.assertAlmostEqual(layout.systems[0].symbol_scale/layout.glyph_scale,2/3)

    def test_short_forced_rows_never_enlarge_font(self):
        p=music();apply_forced_row(p,[0,1]);layout=ScoreLayout(p)
        self.assertEqual(layout.systems[0].symbol_scale,layout.glyph_scale)

    def test_all_bars_once_at_line_and_page_boundaries(self):
        p=music();p.measures=[Measure() for _ in range(90)];p.contexts=[Context(0,p.end)]
        p.measures[1].break_after=True;apply_forced_row(p,list(range(2,8)))
        layout=ScoreLayout(p);self.assertGreater(layout.pages,1)
        self.assertEqual([b for s in layout.systems for b in s.bars],list(range(90)))
        self.assertEqual(layout.systems[0].bars,[0,1]);self.assertEqual(layout.systems[1].bars,list(range(2,8)))
        for s in layout.systems:self.assertAlmostEqual(sum(s.bar_widths),PAPER_W-2*MARGIN-40)

    def test_dense_accidentals_dots_and_lyrics_stay_inside_cells(self):
        p=Project();p.notation.update(per_line=8,font_size=26)
        p.notes=[Note(i*3840+90,90,66,lyric='bright') for i in range(8)]+[Note(i*3840+3570,270,61,lyric='longword') for i in range(8)]
        for style in ('spatial','compact','traditional'):
            p.notation['style']=style;layout,_=render(p)
            for _,_,left,right,a,b in layout.symbol_boxes:
                self.assertGreaterEqual(left,a-1e-6);self.assertLessEqual(right,b+1e-6)
            for nid,verse,x,y in layout.lyric_positions:
                rect=next(r for _,r,bar in layout.hit_bars if p.starts[bar]<=next(e['tick'] for e in layout.lyrics if e['id']==nid)<p.starts[bar+1])
                text=next(e['text'] for e in layout.lyrics if e['id']==nid)
                half=layout.text_width(text,11)*layout.glyph_scale/2
                self.assertGreaterEqual(x-half,rect.left()-1e-6);self.assertLessEqual(x+half,rect.right()+1e-6)

    def test_recommendation_and_layout_do_not_edit_music(self):
        p=music();before=copy.deepcopy(p.to_dict());layout=ScoreLayout(p)
        self.assertLess(layout.recommended_font_size,15);self.assertEqual(before,p.to_dict())
        p.notation['font_size']=layout.recommended_font_size;fitted=ScoreLayout(p)
        self.assertAlmostEqual(fitted.glyph_scale,p.notation['font_size']/15)

    def test_repeated_bars_and_symbols_reserve_space(self):
        from popscore.presentation import add_compression
        p=Project();p.notes=[Note(b*3840,960,61) for b in range(8)]
        add_compression(p,list(range(8)),'repeat')
        for style in ('traditional','spatial'):
            p.notation['style']=style;layout,_=render(p)
            self.assertEqual([b for s in layout.systems for b in s.bars],list(range(4)))
            for _,_,left,right,a,b in layout.symbol_boxes:self.assertGreaterEqual(left,a-1e-6);self.assertLessEqual(right,b+1e-6)

    def test_engraving_time_map_roundtrip_for_clicks(self):
        p=music();apply_forced_row(p,list(range(6)))
        for style in ('spatial','traditional'):
            p.notation['style']=style;canvas=ScoreCanvas(p);canvas.resize(1000,2000);canvas.layout,_=render(p)
            for page,rect,bar,points,xs in canvas.layout.hit_times:
                for tick in range(p.starts[bar],p.starts[bar+1],240):
                    x=canvas.layout.interpolate(points,xs,tick);ox,oy=canvas.page_origin(page)
                    hit=canvas.timeline_at(QPointF(ox+(x+.001)*canvas.scale,oy+rect.center().y()*canvas.scale))
                    self.assertEqual(hit,(bar,tick))
            canvas.deleteLater()

    def test_forced_font_metadata_moves_with_insertions(self):
        p=music();apply_forced_row(p,list(range(2,6)));shift_presentation(p,0,0,3840)
        self.assertEqual(p.notation['forced_rows'],[[3,7]]);self.assertEqual(p.notation['forced_row_fonts'],[[3,7,4]])

    def test_octave_marks_and_underlines_have_vertical_room(self):
        p=Project();p.notes=[Note(0,120,106),Note(0,120,108)];p.notation.update(font_size=26,row_gap=8)
        layout=ScoreLayout(p);s=layout.systems[0];lower,upper=s.fragments[0][:2]
        distance=abs(s.pitch_position(upper.pitch)-s.pitch_position(lower.pitch))*s.row_gap
        needed=(layout.vertical_extents(upper)[1]+layout.vertical_extents(lower)[0])*layout.glyph_scale
        self.assertGreater(distance,needed);self.assertEqual(s.row_gap,8)
        p.notes=[Note(0,240,21,lyric='低音')];p.notation.update(per_line=1,row_gap=15)
        layout,_=render(p);s=layout.systems[0];f=s.fragments[0][0]
        baseline=s.top+60+s.extra_header+(len(s.pitches)-1-s.pitch_position(21))*s.row_gap
        bottom=baseline+layout.vertical_extents(f)[1]*s.symbol_scale
        self.assertLess(bottom,s.top+s.grid_bottom)

    def test_forced_font_metadata_survives_bar_deletion_and_validation(self):
        from popscore.bar_edit import delete_bars
        p=music();apply_forced_row(p,list(range(2,8)));delete_bars(p,[0,3]);p.validate()
        self.assertEqual(p.notation['forced_rows'],[[1,6]])
        self.assertEqual(p.notation['forced_row_fonts'],[[1,6,4]])
        layout=ScoreLayout(p);s=next(s for s in layout.systems if s.bars[0]==1)
        self.assertAlmostEqual(s.symbol_scale/layout.glyph_scale,4/5)

class CreationTests(unittest.TestCase):
    def test_first_entry_recommends_once_style_and_explicit_recommend_are_undoable(self):
        from popscore.app import MainWindow
        with patch.object(MainWindow,'save_preferences'):
            w=MainWindow(music());w.timer.stop();w.autosave.stop()
            try:
                recommended=ScoreLayout(w.project).recommended_font_size
                w.switch_workspace('score');self.assertEqual(w.project.notation['font_size'],recommended)
                w.note_font.setValue(2);w.switch_workspace('compose');w.switch_workspace('score')
                self.assertEqual(w.project.notation['font_size'],2)
                saved=Project.from_dict(w.project.to_dict());w.replace_project(saved)
                self.assertEqual(w.project.notation['font_size'],2)
                w.recommend_score_font();self.assertEqual(w.project.notation['font_size'],recommended)
                w.undo();self.assertEqual(w.project.notation['font_size'],2)
                w.set_notation('style','traditional');self.assertEqual(w.project.notation['font_size'],ScoreLayout(w.project).recommended_font_size)
                w.undo();self.assertEqual(w.project.notation['style'],'spatial')
            finally:w.dirty=False;w.close();w.deleteLater();APP.processEvents()

if __name__=='__main__':unittest.main()
