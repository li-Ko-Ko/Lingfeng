"""Circle-sized traditional units, integer advice and row-aligned underlines."""
import copy
import math
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPointF,QRectF
from PySide6.QtGui import QFontMetricsF,QImage,QPainter,QPainterPath
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Chord,Context,Measure,Note,PPQ,Project
from lingfeng.audio.midi import event_list,export_midi
from lingfeng.engraving.lyrics import apply_section
from lingfeng.engraving.notation import ScoreLayout,fragment_style,export_pdf,PAPER_W,PAPER_H,MARGIN

APP=QApplication.instance() or QApplication([])


def song(bars=4,subdivisions=4):
    p=Project(measures=[Measure() for _ in range(bars)]);p.contexts=[Context(0,p.end)]
    p.notes=[Note(start+i*PPQ//subdivisions,PPQ//subdivisions,48) for start in p.starts[:-1] for i in range(4*subdivisions)]
    p.chords=[Chord(0,p.end,48)]
    p.notation.update(style='traditional',per_line=2,font_size=15,circles=True,lyrics=False)
    return p


class GeometryPainter(QPainter):
    def __init__(self,image):
        super().__init__(image);self.circles=[];self.lower_dots=[];self.underlines=[];self.digits=[];self.last_digit=None
    def drawText(self,*args):
        if len(args)==2 and isinstance(args[0],QPointF) and args[1] in tuple('01234567x') and self.font().pixelSize()==18:
            point=args[0];center=QPointF(point.x()+QFontMetricsF(self.font()).horizontalAdvance(args[1])/2,point.y())
            self.last_digit=(args[1],self.worldTransform().map(center))
            self.digits.append(self.last_digit)
        return super().drawText(*args)
    def drawEllipse(self,*args):
        if len(args)==3 and isinstance(args[0],QPointF):
            center,rx,ry=args
            if abs(rx-ry)>1e-7:
                half=self.pen().widthF()/2
                rect=QRectF(center.x()-rx-half,center.y()-ry-half,2*(rx+half),2*(ry+half))
                self.circles.append(self.worldTransform().mapRect(rect))
            elif self.last_digit and self.worldTransform().map(center).y()>self.last_digit[1].y():
                self.lower_dots.append((self.last_digit,self.worldTransform().mapRect(QRectF(center.x()-rx,center.y()-ry,2*rx,2*ry))))
        return super().drawEllipse(*args)
    def drawLine(self,*args):
        if (len(args)==2 and all(isinstance(point,QPointF) for point in args) and
                abs(args[1].x()-args[0].x()-11)<1e-7 and abs(args[1].y()-args[0].y())<1e-7 and self.last_digit):
            self.underlines.append((self.last_digit,self.worldTransform().map(args[0]),self.worldTransform().map(args[1])))
        return super().drawLine(*args)


def paint(layout):
    results=[]
    for page in range(layout.pages):
        image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);image.fill(0xffffffff);painter=GeometryPainter(image)
        try:layout.draw(painter,page);results.append((page,painter.circles,painter.underlines,painter.digits,painter.lower_dots))
        finally:painter.end()
    return results


class CircleUnitTests(unittest.TestCase):
    def test_actual_circle_outline_matches_every_uniform_cell_and_neighbor_circles_do_not_overlap(self):
        for size in (12.5,15,26,72):
            p=song(bars=1,subdivisions=8);p.notation['font_size']=size;layout=ScoreLayout(p);system=layout.systems[0]
            circles=paint(layout)[0][1];self.assertEqual(len(circles),32)
            for circle in circles:self.assertAlmostEqual(circle.width(),system.cell_width*system.layout_scale)
            for left,right in zip(circles,circles[1:]):self.assertLessEqual(left.right(),right.left()+1e-7)
            self.assertAlmostEqual(layout.numeric_advance,20.95)
            self.assertAlmostEqual(layout.circle_width_ratio,20.95/layout.digit_advance)
            for a,b in system.traditional_cells.values():self.assertAlmostEqual(b-a,system.cell_width)

    def test_circle_reserve_is_stable_when_display_is_off_and_also_covers_rests_x_and_dashes(self):
        p=song(bars=2);p.notes=[Note(0,3*PPQ,48),Note(3840+240,240,48)]
        p.notation['lyrics']=True
        rap_note=p.notes[-1]
        apply_section(p,r'\x{rap}',rap_note.start)
        on=ScoreLayout(p);p.notation['circles']=False;off=ScoreLayout(p)
        self.assertEqual(on.cell_width,off.cell_width);self.assertEqual(on.max_font_size,off.max_font_size)
        self.assertEqual([s.bar_widths for s in on.systems],[s.bar_widths for s in off.systems])
        fragments=[f for s in off.systems for parts in s.fragments.values() for f in parts]
        self.assertEqual([(f.start,f.duration,f.source_ids) for f in fragments if f.ghost],
                         [(rap_note.start,rap_note.duration,(rap_note.id,))])
        self.assertTrue(any(f.pitch is None and not f.ghost for f in fragments))
        self.assertTrue(any(fragment_style(f)[3]==2 for f in fragments))
        for s in off.systems:
            self.assertAlmostEqual(s.beat_gap,2*s.bar_side_gap)
            for a,b in s.traditional_cells.values():self.assertAlmostEqual(b-a,off.cell_width)

    def test_recommendation_floors_the_raw_circle_unit_fit_and_manual_fraction_is_preserved(self):
        p=song();p.notation['font_size']=12.5;before=copy.deepcopy(p.to_dict());layout=ScoreLayout(p)
        raw=15*(PAPER_W-2*MARGIN)/max(s.unit_count for s in layout.systems)/20.95
        self.assertAlmostEqual(layout.max_font_size,raw)
        self.assertEqual(layout.recommended_font_size,math.floor(raw));self.assertIsInstance(layout.recommended_font_size,int)
        self.assertEqual(layout.font_limit,layout.recommended_font_size)
        self.assertEqual(layout.font_size,12.5);self.assertEqual(p.to_dict(),before)

    def test_positive_sub_one_fit_recommends_one_without_clamping_manual_fraction(self):
        p=song(bars=16,subdivisions=8);p.notation.update(per_line=16,font_size=.5)
        layout=ScoreLayout(p);self.assertGreater(layout.max_font_size,0);self.assertLess(layout.max_font_size,1)
        self.assertEqual(layout.font_limit,1);self.assertEqual(layout.recommended_font_size,1);self.assertEqual(layout.font_size,.5)


class RowUnderlineTests(unittest.TestCase):
    def fixture(self,style='traditional'):
        p=song(bars=2);p.notation.update(style=style,per_line=1,lyrics=True,circles=False)
        p.notes=[Note(0,240,48,lyric='a'),Note(240,120,24,lyric='b'),
                 Note(960,480,60,lyric='c'),Note(3840,240,48,lyric='d')]
        apply_section(p,'rap/16',480)
        return p

    def test_every_note_rest_and_x_uses_one_row_relative_underline_level(self):
        for size in (12.5,26,72):
            p=self.fixture();p.notation['font_size']=size;layout=ScoreLayout(p);records=paint(layout)
            first,second=layout.systems;self.assertEqual(first.lower_octave_dots,2);self.assertEqual(first.underline_offset,19)
            self.assertEqual(second.lower_octave_dots,0);self.assertEqual(second.underline_offset,11)
            underlines=[line for _,_,lines,_,_ in records for line in lines]
            kinds=set()
            for (text,anchor),a,b in underlines:
                kinds.add(text);system=first if anchor.y()<second.top else second
                offset=(a.y()-anchor.y())/(system.symbol_scale*system.layout_scale)
                self.assertTrue(any(abs(offset-(system.underline_offset+4*k))<1e-7 for k in range(3)))
                self.assertAlmostEqual(a.y(),b.y())
            self.assertTrue({'0','x','1'}.issubset(kinds))
            # Each glyph's first recorded underline is exactly the common row
            # offset; second and third lines stay parallel four base units apart.
            groups={}
            for owner,a,b in underlines:groups.setdefault((owner[0],owner[1].x(),owner[1].y()),[]).append(a.y())
            for (_,_,baseline),ys in groups.items():
                system=first if baseline<second.top else second
                scale=system.symbol_scale*system.layout_scale
                self.assertAlmostEqual(min(ys)-baseline,system.underline_offset*scale)
                for a,b in zip(ys,ys[1:]):self.assertAlmostEqual(b-a,4*scale)
            lower_dots=[item for _,_,_,_,dots in records for item in dots]
            self.assertEqual(len(lower_dots),2)
            for (text,anchor),dot in lower_dots:
                first_line=min(groups[(text,anchor.x(),anchor.y())])
                scale=first.symbol_scale*first.layout_scale
                self.assertGreater(first_line-.5*scale,dot.bottom()+2*scale)

    def test_row_bottom_voice_spacing_lyrics_and_pages_include_the_common_underlines(self):
        p=self.fixture();p.notation['font_size']=26;layout=ScoreLayout(p);paint(layout)
        for system in layout.systems:
            fragments=[f for parts in system.fragments.values() for f in parts]
            bottom=max(layout.vertical_extents(f,system)[1] for f in fragments)
            self.assertAlmostEqual(system.notation_bottom,bottom)
            for f in fragments:
                _,_,_,ink_bottom=layout.symbol_ink(f,system)
                self.assertLessEqual(ink_bottom,bottom)
            self.assertGreater(system.grid_bottom,system.note_baseline+bottom*system.symbol_scale)
            lyrics=[y for _,_,_,y in layout.lyric_positions if system.top<=y<system.top+system.height]
            if lyrics:self.assertGreater(min(lyrics),layout.system_transform(system).map(QPointF(system.left,system.grid_bottom)).y())
        self.assertTrue(all(s.top+s.height<=PAPER_H-70 for s in layout.systems))

    def test_legacy_polyphonic_lanes_align_relative_to_their_own_baselines(self):
        p=song(bars=1);p.notation.update(circles=False,lyrics=False)
        p.notes=[Note(0,240,24),Note(0,240,48),Note(240,120,60),Note(240,120,36)]
        layout=ScoreLayout(p);system=layout.systems[0];lines=paint(layout)[0][2]
        self.assertGreater(len(set(system.voices.values())),1)
        for (_,baseline),a,b in lines:
            offset=(a.y()-baseline.y())/(system.symbol_scale*system.layout_scale)
            self.assertTrue(any(abs(offset-(system.underline_offset+4*k))<1e-7 for k in range(3)))
        self.assertGreater(system.voice_gap,(system.underline_offset+8)*system.symbol_scale)

    def test_spatial_and_compact_keep_per_note_underlines_and_existing_font_advice(self):
        for style in ('spatial','compact'):
            p=self.fixture(style);layout=ScoreLayout(p)
            by_pitch={f.pitch:layout.underline_y(f) for s in layout.systems for parts in s.fragments.values() for f in parts if f.note}
            self.assertEqual(by_pitch[24],19);self.assertEqual(by_pitch[48],11)
            self.assertEqual(layout.recommended_font_size,min(15,layout.font_limit))
            self.assertFalse(hasattr(layout,'circle_width_ratio'))

    def test_screen_pdf_and_midi_leave_source_events_and_requested_fraction_unchanged(self):
        p=self.fixture();p.notation['font_size']=12.5;before=copy.deepcopy(p.to_dict());midi=export_midi(p,None);events=event_list(p)
        layout=ScoreLayout(p);paint(layout)
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            path=Path(folder)/'circles-and-underlines.pdf';export_pdf(p,path);self.assertTrue(path.read_bytes().startswith(b'%PDF'))
        self.assertEqual(p.to_dict(),before);self.assertEqual(export_midi(p,None),midi);self.assertEqual(event_list(p),events)


if __name__=='__main__':unittest.main()
