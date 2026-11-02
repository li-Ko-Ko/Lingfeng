"""Score-wide traditional units and beat-aware spelling in every score style."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPointF,QRectF
from PySide6.QtGui import QFont,QFontMetricsF,QImage,QPainter,QPainterPath,QPainterPathStroker
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Context,Measure,Note,PPQ,Project,spelling
from lingfeng.audio.midi import event_list,export_midi
from lingfeng.engraving.notation import ScoreLayout,fragments_for_bar,fragment_style,export_pdf,PAPER_W,PAPER_H,MARGIN
from lingfeng.engraving.presentation import apply_forced_row,add_compression

APP=QApplication.instance() or QApplication([])
STYLES=('traditional','spatial','compact')


def song(patterns,style='traditional',per_line=2):
    p=Project(measures=[Measure(len(pattern),4) for pattern in patterns]);p.notes=[];p.chords=[]
    p.contexts=[Context(0,p.end)];p.notation.update(style=style,per_line=per_line,font_size=15,circles=False,lyrics=False)
    for bar,pattern in enumerate(patterns):
        for beat,count in enumerate(pattern):
            p.notes.extend(Note(p.starts[bar]+beat*PPQ+i*PPQ//count,PPQ//count,48) for i in range(count))
    return p


class EllipsePainter(QPainter):
    def __init__(self,image):super().__init__(image);self.ellipses=[];self.associations=[];self.last_digit=None
    def drawText(self,*args):
        if len(args)==2 and isinstance(args[0],QPointF) and args[1] in tuple('01234567x') and self.font().pixelSize()==18:
            path=QPainterPath();path.addText(args[0],self.font(),args[1])
            self.last_digit=(args[1],self.worldTransform().map(path))
        return super().drawText(*args)
    def drawEllipse(self,*args):
        if len(args)==3 and isinstance(args[0],QPointF):
            center,rx,ry=args
            rect=self.worldTransform().mapRect(QRectF(center.x()-rx,center.y()-ry,2*rx,2*ry))
            self.ellipses.append(rect)
            if self.last_digit:self.associations.append((rect,*self.last_digit))
        return super().drawEllipse(*args)


def render(layout):
    ellipses=[];ties=[]
    for page in range(layout.pages):
        image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);image.fill(0xffffffff);painter=EllipsePainter(image)
        try:layout.draw(painter,page);ellipses.extend(painter.ellipses);ties.extend(layout.tie_paths)
        finally:painter.end()
    return ellipses,ties


def assert_numeric_cells(test,layout):
    """Independent Qt digit ink, excluding optional annotation envelopes."""
    font=QFont('Microsoft YaHei');font.setPixelSize(18);metrics=QFontMetricsF(font)
    for system in layout.systems:
        x=system.left
        for bar,width in zip(system.bars,system.bar_widths):
            for f in system.fragments[bar]:
                text='x' if f.ghost else '0' if f.pitch is None else str(spelling(f.pitch,layout.project.context_at(f.start).tonic,f.note.flat,mode=layout.project.context_at(f.start).mode)[0])
                rect=metrics.tightBoundingRect(text);advance=metrics.horizontalAdvance(text)
                a,b=system.traditional_cells[(bar,f.start)];center=x+(a+b)/2
                left=center+(rect.left()-advance/2)*system.symbol_scale
                right=center+(rect.right()-advance/2)*system.symbol_scale
                test.assertGreaterEqual(left,x+a-1e-7);test.assertLessEqual(right,x+b+1e-7)
                test.assertGreaterEqual(left,MARGIN-1e-7)
                if layout.font_size<=layout.recommended_font_size:test.assertLessEqual(right,PAPER_W-MARGIN+1e-7)
            x+=width


class GlobalTraditionalUnitsTests(unittest.TestCase):
    def project(self):return song([[1]*4,[2]*4,[4]*4,[1]*4])

    def test_font_drives_one_common_cell_width_across_heavy_and_light_rows(self):
        p=self.project();low=ScoreLayout(p);p.notation['font_size']=26;high=ScoreLayout(p)
        for layout in (low,high):
            self.assertEqual(len({s.cell_width for s in layout.systems}),1)
            self.assertAlmostEqual(layout.cell_width,layout.numeric_advance*layout.font_size/15)
            for s in layout.systems:
                for left,right in s.traditional_cells.values():self.assertAlmostEqual(right-left,layout.cell_width)
                for beat in s.beat_cells:
                    self.assertAlmostEqual(beat['right']-beat['left'],beat['count']*layout.cell_width)
                    cells=[s.traditional_cells[(beat['bar'],tick)] for tick in beat['slots']]
                    for left,right in zip(cells,cells[1:]):self.assertAlmostEqual(left[1],right[0])
        self.assertAlmostEqual(high.cell_width/low.cell_width,26/15)

    def test_heaviest_row_sets_the_integer_circle_unit_recommendation_without_a_15_cap(self):
        p=self.project();layout=ScoreLayout(p);available=PAPER_W-2*MARGIN
        self.assertEqual([s.unit_count for s in layout.systems],[28,36])
        expected=15*available/36/layout.numeric_advance
        self.assertGreater(expected,15)
        self.assertAlmostEqual(layout.max_font_size,expected)
        self.assertEqual(layout.recommended_font_size,max(1,int(expected)))
        self.assertGreaterEqual(expected-layout.recommended_font_size,0)
        self.assertLess(expected-layout.recommended_font_size,1)
        p.notation['font_size']=layout.recommended_font_size;fitted=ScoreLayout(p)
        heavy=max(fitted.systems,key=lambda s:s.unit_count);light=min(fitted.systems,key=lambda s:s.unit_count)
        self.assertGreaterEqual(heavy.bar_side_gap,heavy.cell_width)
        self.assertGreater(light.bar_side_gap,heavy.bar_side_gap)
        for s in fitted.systems:self.assertAlmostEqual(sum(s.bar_widths),available)
        # The next integer exceeds the heaviest row's unit budget, proving
        # this remains the largest fitting integer rather than a default cap.
        p.notation['font_size']=layout.recommended_font_size+1;larger=ScoreLayout(p)
        heavy=max(larger.systems,key=lambda s:s.unit_count)
        self.assertGreater(sum(heavy.bar_widths),available)

    def test_gap_units_are_two_between_beats_and_one_on_each_side_of_every_barline(self):
        layout=ScoreLayout(self.project())
        for s in layout.systems:
            self.assertEqual(s.gap_units,2*len(s.beat_cells));self.assertEqual(s.unit_count,s.symbol_count+s.gap_units)
            self.assertAlmostEqual(s.beat_gap,2*s.bar_side_gap)
            for left,right in zip(s.beat_cells,s.beat_cells[1:]):self.assertAlmostEqual(right['left']-left['right'],s.beat_gap)
            x=s.left
            for bar,width in zip(s.bars,s.bar_widths):
                beats=[beat for beat in s.beat_cells if beat['bar']==bar]
                self.assertAlmostEqual(beats[0]['left']-x,s.bar_side_gap)
                self.assertAlmostEqual(x+width-beats[-1]['right'],s.bar_side_gap)
                x+=width
            self.assertAlmostEqual(x,PAPER_W-MARGIN)

    def test_oversized_manual_font_keeps_natural_cells_and_positive_unit_gaps(self):
        p=self.project();p.notation['font_size']=72;layout=ScoreLayout(p)
        self.assertEqual(layout.font_size,72);self.assertLess(layout.recommended_font_size,72)
        heavy=max(layout.systems,key=lambda s:s.unit_count)
        self.assertGreater(sum(heavy.bar_widths),PAPER_W-2*MARGIN)
        self.assertAlmostEqual(heavy.bar_side_gap,heavy.cell_width)
        self.assertAlmostEqual(sum(heavy.bar_widths),heavy.unit_count*heavy.cell_width)
        self.assertTrue(all(s.beat_gap>0 for s in layout.systems))
        render(layout);self.assertEqual({size for _,size in layout.glyph_sizes},{72})

    def test_forced_merged_row_uses_normal_reference_and_its_full_symbol_budget(self):
        p=song([[2]*4]*8,per_line=4);apply_forced_row(p,list(range(6)));layout=ScoreLayout(p)
        self.assertEqual(layout.systems[0].bars,list(range(6)))
        forced,normal=layout.systems
        self.assertEqual((forced.unit_count,normal.unit_count),(96,32))
        self.assertEqual(layout.reference_unit_count,32)
        self.assertAlmostEqual(forced.forced_font_ratio,1/3)
        self.assertEqual(normal.font_ratio,1)
        self.assertAlmostEqual(forced.cell_width,normal.cell_width/3)
        self.assertAlmostEqual(forced.symbol_scale,normal.symbol_scale/3)
        self.assertTrue(all(s.layout_scale==1 for s in layout.systems))
        expected=15*(PAPER_W-2*MARGIN)/32/layout.numeric_advance
        self.assertAlmostEqual(layout.max_font_size,expected)

    def test_tied_fragments_crossbar_fragments_and_extension_dashes_each_own_a_cell(self):
        p=song([[1]*4]*2,per_line=2)
        p.notes=[Note(720,480,48),Note(1920,PPQ*2,48),Note(7680-240,240,48)]
        # Replace the sustain with a crossbar source in a separate layout too.
        layout=ScoreLayout(p);s=layout.systems[0]
        self.assertIn((0,720),s.traditional_cells);self.assertIn((0,960),s.traditional_cells)
        self.assertIn((0,1920),s.traditional_cells);self.assertIn((0,2880),s.traditional_cells)
        p.notes=[Note(3600,480,48)];layout=ScoreLayout(p);s=layout.systems[0]
        self.assertIn((0,3600),s.traditional_cells);self.assertIn((1,3840),s.traditional_cells)
        self.assertEqual(len([f for parts in s.fragments.values() for f in parts if f.note]),2)

    def test_actual_repeat_dot_ellipses_fit_the_existing_barline_side_units(self):
        p=song([[1]*4]*4);add_compression(p,list(range(4)),'repeat')
        p.notation['font_size']=ScoreLayout(p).recommended_font_size;layout=ScoreLayout(p)
        dots,_=render(layout);self.assertEqual(len(dots),4);system=layout.systems[0]
        left=system.left;right=left+sum(system.bar_widths)
        for dot in dots[:2]:
            self.assertGreaterEqual(dot.left(),left)
            self.assertLessEqual(dot.right(),left+system.bar_side_gap)
        for dot in dots[2:]:
            self.assertGreaterEqual(dot.left(),right-system.bar_side_gap)
            self.assertLessEqual(dot.right(),right)
        self.assertEqual(system.unit_count,system.symbol_count+2*len(system.beat_cells))
        assert_numeric_cells(self,layout)


class AllStyleBeatTests(unittest.TestCase):
    def test_traditional_dots_attach_to_their_own_rest_or_note_before_the_following_digit(self):
        for rest_first in (True,False):
            for chosen in (15,26,72,'recommended'):
                with self.subTest(rest=rest_first,font=chosen):
                    p=song([[1]*4,[1]*4,[8]*4,[8]*4])
                    for bar,start in enumerate(p.starts[:-1]):
                        p.notes=[n for n in p.notes if not start<=n.start<start+PPQ]
                        p.notes.append(Note(start+720,240,50))
                        if not rest_first:p.notes.append(Note(start,720,53))
                    p.notation['font_size']=ScoreLayout(p).recommended_font_size if chosen=='recommended' else chosen
                    before=copy.deepcopy(p.to_dict());layout=ScoreLayout(p);associations=[]
                    for page in range(layout.pages):
                        image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);image.fill(0xffffffff);painter=EllipsePainter(image)
                        try:layout.draw(painter,page);associations.extend(painter.associations)
                        finally:painter.end()
                    owners=[(s,bar) for s in layout.systems for bar in s.bars]
                    self.assertEqual(len(associations),len(owners))
                    for (dot,text,ink),(system,bar) in zip(associations,owners):
                        self.assertEqual(text,'0' if rest_first else '4')
                        origin=system.left+sum(system.bar_widths[:system.bars.index(bar)])
                        a,b=system.traditional_cells[(bar,p.starts[bar])]
                        transform=layout.system_transform(system)
                        cell=transform.mapRect(QRectF(origin+a,0,b-a,1))
                        self.assertGreaterEqual(dot.left(),cell.left()-1e-7)
                        self.assertLessEqual(dot.right(),cell.right()+1e-7)
                        self.assertGreater(dot.width(),.5*system.symbol_scale*system.layout_scale)
                        ellipse=QPainterPath();ellipse.addEllipse(dot)
                        stroke=QPainterPathStroker();stroke.setWidth(.2*system.symbol_scale*system.layout_scale)
                        self.assertFalse(ellipse.intersects(ink.united(stroke.createStroke(ink))))
                        c,d=system.traditional_cells[(bar,p.starts[bar]+720)]
                        self.assertLess(dot.right(),transform.map(QPointF(origin+(c+d)/2,0)).x())
                    self.assertEqual(layout.font_size,p.notation['font_size'])
                    self.assertEqual(p.to_dict(),before)

    def test_crossbeat_notes_split_and_tie_same_source_in_all_styles(self):
        for style in STYLES:
            with self.subTest(style=style):
                p=song([[1]*4],style);note=Note(720,480,48,lyric='la');p.notes=[note]
                played=[f for f in fragments_for_bar(p,0) if f.note]
                self.assertEqual([(f.start,f.duration) for f in played],[(720,240),(960,240)])
                self.assertTrue(all(f.note is note for f in played));self.assertEqual([f.lyric for f in played],['la',''])
                _,ties=render(ScoreLayout(p));self.assertEqual([(nid,kind) for nid,kind,_ in ties],[(note.id,'continuous')])

    def test_dotted_quarters_split_but_aligned_integral_sustains_keep_dashes_in_all_styles(self):
        for style in STYLES:
            p=song([[1]*6],style);p.notes=[Note(0,1440,48)]
            played=[f for f in fragments_for_bar(p,0) if f.note]
            self.assertEqual([(f.start,f.duration) for f in played],[(0,960),(960,480)])
            self.assertTrue(all(not fragment_style(f)[1] for f in played))
            p.notes=[Note(0,6*PPQ,48)];played=[f for f in fragments_for_bar(p,0) if f.note]
            self.assertEqual(len(played),1);self.assertEqual(fragment_style(played[0]),(0,False,False,5))

    def test_actual_dot_ellipses_stay_inside_real_beats_at_manual_15_26_72(self):
        for style in STYLES:
            for size in (15,26,72):
                with self.subTest(style=style,size=size):
                    p=song([[1]*4]*4,style,per_line=4);p.notation['font_size']=size
                    p.notes=[Note(start+beat*PPQ+240,720,48) for start in p.starts[:-1] for beat in range(4)]
                    layout=ScoreLayout(p);dots,_=render(layout)
                    beats=[(s,layout.beat_cell(s,bar,p.starts[bar]+beat*PPQ)) for s in layout.systems for bar in s.bars for beat in range(4)]
                    self.assertEqual(len(dots),len(beats))
                    for dot,(system,beat) in zip(dots,beats):
                        cell=layout.system_transform(system).mapRect(QRectF(beat['left'],0,beat['right']-beat['left'],1))
                        self.assertGreaterEqual(dot.left(),cell.left()-1e-7);self.assertLessEqual(dot.right(),cell.right()+1e-7)
                    self.assertEqual(layout.font_size,size)

    def test_spatial_bar_density_and_actual_beat_widths_are_preserved(self):
        for style in ('spatial','compact'):
            p=song([[2]*2,[2]*4],style);layout=ScoreLayout(p);s=layout.systems[0]
            self.assertAlmostEqual(s.bar_widths[0]/s.bar_widths[1],.5)
            for bar,width in zip(s.bars,s.bar_widths):
                cells=[layout.beat_cell(s,bar,tick) for tick in range(p.starts[bar],p.starts[bar+1],PPQ)]
                for cell in cells:self.assertAlmostEqual(cell['right']-cell['left'],width/len(cells))

    def test_layout_hit_sources_pdf_and_midi_preserve_the_same_music(self):
        for style in STYLES:
            p=song([[1]*4]*2,style);p.notes=[Note(720,480,48),Note(3600,720,50)]
            before=copy.deepcopy(p.to_dict());midi=export_midi(p,None);events=event_list(p)
            layout=ScoreLayout(p);_,ties=render(layout)
            self.assertEqual({nid for _,_,nid in layout.hit_notes},{note.id for note in p.notes})
            for _,_,_,points,xs in layout.hit_times:self.assertTrue(all(b>a for a,b in zip(xs,xs[1:])))
            seen=[];original=ScoreLayout.draw
            def capture(current,*args,**kwargs):
                original(current,*args,**kwargs);seen.extend((nid,kind) for nid,kind,_ in current.tie_paths)
            with tempfile.TemporaryDirectory(dir='tmp') as folder:
                path=Path(folder)/'units.pdf'
                with patch.object(ScoreLayout,'draw',capture):export_pdf(p,path)
                self.assertTrue(path.read_bytes().startswith(b'%PDF'))
            self.assertEqual(seen,[(nid,kind) for nid,kind,_ in ties])
            self.assertEqual(p.to_dict(),before);self.assertEqual(export_midi(p,None),midi);self.assertEqual(event_list(p),events)


if __name__=='__main__':unittest.main()
