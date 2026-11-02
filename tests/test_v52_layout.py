"""Spatial rows retain busiest-beat bar weights (traditional changed in 0.53.1)."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Project,Measure,Context,Note,PPQ
from lingfeng.engraving.notation import ScoreLayout,PAPER_W,PAPER_H,MARGIN,export_pdf
from lingfeng.engraving.presentation import add_compression,apply_forced_row,visible_bars
from lingfeng.ui.score_view import ScoreCanvas

APP=QApplication.instance() or QApplication([])
STYLES=('spatial','compact')


def song(patterns,meters=None):
    meters=meters or [(len(pattern),4) for pattern in patterns]
    p=Project(measures=[Measure(*meter) for meter in meters])
    p.contexts=[Context(0,p.end)];p.chords=[];p.notes=[]
    p.notation.update(per_line=len(patterns),font_size=15,circles=False,lyrics=False)
    for bar,pattern in enumerate(patterns):
        beat=PPQ*4//p.measures[bar].denominator
        for offset,count in enumerate(pattern):
            for i in range(count):
                p.notes.append(Note(p.starts[bar]+offset*beat+i*beat//count,beat//count,60+i%5))
    return p


def render(layout):
    for page in range(layout.pages):
        image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32)
        painter=QPainter(image)
        try:layout.draw(painter,page)
        finally:painter.end()


class DensityWidthTests(unittest.TestCase):
    def test_user_example_allocates_four_to_two_in_spatial_styles(self):
        p=song([[1,2,3,4],[2,2,2,2]])
        for style in STYLES:
            with self.subTest(style=style):
                p.notation['style']=style;layout=ScoreLayout(p);system=layout.systems[0]
                self.assertAlmostEqual(system.bar_widths[0]/system.bar_widths[1],2)
                self.assertAlmostEqual(sum(system.bar_widths),PAPER_W-MARGIN-system.left)
                render(layout)
                self.assertEqual({size for _,size in layout.glyph_sizes},{layout.font_size})

    def test_maximum_beat_count_is_independent_of_total_notes_per_equal_length_bar(self):
        p=song([[4,1,1,1],[4,4,4,4],[4,1,1]],[(4,4),(4,4),(3,4)])
        for style in STYLES:
            p.notation['style']=style;system=ScoreLayout(p).systems[0]
            self.assertAlmostEqual(system.bar_widths[0],system.bar_widths[1])
            self.assertAlmostEqual(system.bar_widths[2]/system.bar_widths[0],3/4)

    def test_denominator_defines_beat_counting(self):
        for denominator in (2,4,8,16):
            p=song([[1,2,3,4],[2,2,2,2]],[(4,denominator)]*2)
            for style in STYLES:
                with self.subTest(denominator=denominator,style=style):
                    p.notation['style']=style;layout=ScoreLayout(p);system=layout.systems[0]
                    self.assertAlmostEqual(system.bar_widths[0]/system.bar_widths[1],2)

    def test_chord_tones_share_onsets_and_annotations_do_not_add_density(self):
        p=song([[2]*4,[2]*4]);original=list(p.notes)
        p.notes.extend(Note(n.start,n.duration,n.pitch+12) for n in original if n.start<p.starts[1])
        p.notation['symbols']=[dict(kind='rit',start=0,end=p.end)]
        for style in STYLES:
            p.notation['style']=style;layout=ScoreLayout(p);system=layout.systems[0]
            self.assertAlmostEqual(system.bar_widths[0],system.bar_widths[1])
            self.assertEqual([layout.bar_spacing_weight(b,system.fragments[b]) for b in system.bars],[8,8])

    def test_empty_rest_and_sustained_bars_keep_minimum_weight(self):
        p=song([[1]*4,[1]*4,[1]*4]);p.notes=[Note(p.starts[1],p.measures[1].ticks,60)]
        for style in STYLES:
            p.notation['style']=style;layout=ScoreLayout(p);system=layout.systems[0]
            self.assertEqual([layout.bar_spacing_weight(b,system.fragments[b]) for b in system.bars],[4,4,4])
            for width in system.bar_widths:self.assertAlmostEqual(width,system.bar_widths[0])

    def test_wide_glyphs_and_lyrics_reduce_common_font_without_changing_ratio(self):
        p=song([[1,2,3,4],[2]*4]);p.notation.update(font_size=26,lyrics=True)
        for n in p.notes:
            if n.start>=p.starts[1]:n.pitch=61;n.lyric='long syllable'
        for style in STYLES:
            p.notation.update(style=style,font_size=26)
            p.notation['font_size']=ScoreLayout(p).font_limit
            layout=ScoreLayout(p);system=layout.systems[0];render(layout)
            self.assertAlmostEqual(system.bar_widths[0]/system.bar_widths[1],2)
            for b,width in zip(system.bars,system.bar_widths):
                self.assertLessEqual(layout.width_cache[b]*system.symbol_scale,width+1e-7)
            for _,_,left,right,cell_left,cell_right in layout.symbol_boxes:
                self.assertGreaterEqual(left,cell_left-1e-7);self.assertLessEqual(right,cell_right+1e-7)

    def test_equal_time_beats_and_click_playhead_maps_use_each_bar_width(self):
        p=song([[1,2,3,4],[2]*4]);p.notation.update(font_size=8)
        for style in ('spatial','compact'):
            p.notation['style']=style;canvas=ScoreCanvas(p);canvas.grid=60;canvas.resize(1000,1600)
            try:
                layout=canvas.layout=ScoreLayout(p);render(layout)
                for page,rect,bar,points,positions in layout.hit_times:
                    start=p.starts[bar];ox,oy=canvas.page_origin(page)
                    edges=[layout.interpolate(points,positions,start+i*PPQ) for i in range(5)]
                    for left,right in zip(edges,edges[1:]):self.assertAlmostEqual(right-left,rect.width()/4)
                    for tick in range(start,p.starts[bar+1],240):
                        x=layout.interpolate(points,positions,tick)
                        hit=canvas.timeline_at(QPointF(ox+(x+.001)*canvas.scale,oy+rect.center().y()*canvas.scale))
                        self.assertEqual(hit,(bar,tick));self.assertAlmostEqual(layout.time_position(tick)[1],x)
            finally:canvas.deleteLater();APP.processEvents()

    def test_forced_rows_repeats_and_page_breaks_keep_requested_proportions(self):
        patterns=[[1,2,3,4],[2]*4]*12;p=song(patterns);p.notation['per_line']=4
        add_compression(p,list(range(4)),'repeat');apply_forced_row(p,list(range(4,10)))
        p.measures[11].break_after=True
        for style in STYLES:
            p.notation['style']=style;layout=ScoreLayout(p)
            self.assertEqual([b for s in layout.systems for b in s.bars],visible_bars(p))
            forced=next(s for s in layout.systems if s.bars[0]==4)
            self.assertEqual(forced.bars,list(range(4,10)))
            self.assertAlmostEqual(forced.symbol_scale/layout.glyph_scale,4/6)
            self.assertTrue(any(s.bars[-1]==11 for s in layout.systems))
            for s in layout.systems:
                self.assertAlmostEqual(sum(s.bar_widths),PAPER_W-MARGIN-s.left)
                for b,width in zip(s.bars,s.bar_widths):
                    weight=4 if b%2==0 else 2
                    self.assertAlmostEqual(width/weight,s.bar_widths[0]/(4 if s.bars[0]%2==0 else 2))
            render(layout)

    def test_pdf_and_screen_share_density_layout_without_editing_music(self):
        p=song([[1,2,3,4],[2]*4]);before=copy.deepcopy(p.to_dict());seen=[]
        original=ScoreLayout.draw
        def record(layout,painter,page,*args,**kwargs):
            seen.append([list(s.bar_widths) for s in layout.systems])
            return original(layout,painter,page,*args,**kwargs)
        for style in STYLES:
            p.notation['style']=style;state=copy.deepcopy(p.to_dict())
            expected=[list(s.bar_widths) for s in ScoreLayout(p).systems]
            with tempfile.TemporaryDirectory(dir='tmp') as folder:
                output=Path(folder)/'density.pdf'
                with patch.object(ScoreLayout,'draw',record):export_pdf(p,output)
                self.assertGreater(output.stat().st_size,0)
            self.assertEqual(seen[-1],expected);self.assertEqual(p.to_dict(),state)
        p.notation['style']=before['notation']['style'];self.assertEqual(p.to_dict(),before)


if __name__=='__main__':unittest.main()
