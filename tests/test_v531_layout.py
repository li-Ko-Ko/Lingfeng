"""Per-beat traditional columns and advisory, pitch-aware score typography."""
import copy
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage,QPainter,QFontMetricsF
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Project,Measure,Context,Note,Chord,PPQ,FONT_SIZE_MAX
from lingfeng.audio.midi import event_list,export_midi
from lingfeng.engraving.notation import ScoreLayout,PAPER_W,PAPER_H,MARGIN,export_pdf
from lingfeng.engraving.presentation import apply_forced_row
from lingfeng.ui.score_view import ScoreCanvas

APP=QApplication.instance() or QApplication([])


def song(patterns,style='traditional'):
    p=Project(measures=[Measure(len(pattern),4) for pattern in patterns])
    p.contexts=[Context(0,p.end)];p.chords=[];p.notes=[]
    p.notation.update(style=style,per_line=len(patterns),font_size=15,circles=False,lyrics=False)
    for bar,counts in enumerate(patterns):
        for beat,count in enumerate(counts):
            p.notes.extend(Note(p.starts[bar]+beat*PPQ+i*PPQ//count,PPQ//count,(60,62,64,65)[i%4]) for i in range(count))
    return p


class InkPainter(QPainter):
    """Measure actual Qt text calls after the renderer's full transform."""
    def __init__(self,image):super().__init__(image);self.digits=[]
    def drawText(self,*args):
        if len(args)==2 and isinstance(args[0],QPointF) and self.font().pixelSize()==18 and args[1] in '01234567x':
            rect=QFontMetricsF(self.font()).tightBoundingRect(args[1]);rect.translate(args[0])
            self.digits.append(self.worldTransform().mapRect(rect))
        return super().drawText(*args)


def render(layout):
    digits=[]
    for page in range(layout.pages):
        image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);image.fill(0xffffffff);painter=InkPainter(image)
        try:layout.draw(painter,page);digits.extend(painter.digits)
        finally:painter.end()
    return digits


class TraditionalColumnTests(unittest.TestCase):
    def test_each_beat_uses_its_own_count_and_one_common_row_cell_width(self):
        p=song([[1,2,3,4],[2]*4]);layout=ScoreLayout(p);s=layout.systems[0]
        self.assertEqual([b['count'] for b in s.beat_cells],[1,2,3,4,2,2,2,2])
        for beat in s.beat_cells:self.assertAlmostEqual(beat['right']-beat['left'],beat['count']*s.cell_width)
        self.assertAlmostEqual(sum(b['right']-b['left'] for b in s.beat_cells[:4])/sum(b['right']-b['left'] for b in s.beat_cells[4:]),10/8)
        for (bar,tick),(left,right) in s.traditional_cells.items():self.assertAlmostEqual(right-left,s.cell_width)

    def test_beat_gap_is_twice_barline_side_gap_across_the_row(self):
        p=song([[1,2,3,4],[2]*4]);layout=ScoreLayout(p);s=layout.systems[0]
        self.assertGreater(s.beat_gap,0);self.assertAlmostEqual(s.beat_gap,2*s.bar_side_gap)
        for left,right in zip(s.beat_cells,s.beat_cells[1:]):self.assertAlmostEqual(right['left']-left['right'],s.beat_gap)
        x=s.left
        for bar,width in zip(s.bars,s.bar_widths):
            last=next(b for b in reversed(s.beat_cells) if b['bar']==bar)
            self.assertAlmostEqual(last['right']+s.bar_side_gap,x+width)
            last_tick=last['slots'][-1];self.assertAlmostEqual(s.traditional_cells[(bar,last_tick)][1]+s.bar_side_gap,width)
            x+=width
        self.assertAlmostEqual(x,PAPER_W-MARGIN)

    def test_traditional_forced_row_font_and_cells_bind_to_the_normal_unit_budget(self):
        p=song([[2]*4]*8);p.notation.update(per_line=4,font_size=36);apply_forced_row(p,list(range(6)))
        layout=ScoreLayout(p);first,last=layout.systems
        self.assertEqual(first.bars,list(range(6)));self.assertEqual(layout.font_size,36)
        self.assertEqual((first.unit_count,last.unit_count),(96,32))
        self.assertEqual(layout.reference_unit_count,32)
        self.assertAlmostEqual(first.forced_font_ratio,1/3)
        self.assertAlmostEqual(first.symbol_scale,last.symbol_scale/3)
        self.assertAlmostEqual(first.cell_width,last.cell_width/3)
        self.assertEqual((first.layout_scale,last.layout_scale),(1,1))
        self.assertAlmostEqual(first.beat_gap,2*first.bar_side_gap)
        self.assertEqual([b for s in layout.systems for b in s.bars],list(range(8)))

    def test_chord_labels_do_not_create_extra_melody_cells(self):
        p=song([[1,2,3,4]]);before=ScoreLayout(p).systems[0]
        p.chords=[Chord(120,240,48,'maj7'),Chord(480,PPQ*4-480,53,'m')]
        after=ScoreLayout(p).systems[0]
        self.assertEqual([b['count'] for b in before.beat_cells],[b['count'] for b in after.beat_cells])
        self.assertEqual(before.cell_width,after.cell_width);self.assertEqual(before.bar_widths,after.bar_widths)

    def test_rests_tied_continuations_and_extension_dashes_keep_visible_columns(self):
        p=song([[1]*4]);p.notes=[Note(PPQ,2*PPQ,60)]
        layout=ScoreLayout(p);s=layout.systems[0]
        self.assertEqual([b['count'] for b in s.beat_cells],[1,1,1,1])
        self.assertEqual([b['slots'] for b in s.beat_cells],[[0],[PPQ],[2*PPQ],[3*PPQ]])
        self.assertEqual(len(render(layout)),3)  # two rests and one sustained note digit

    def test_time_map_is_monotone_and_click_playhead_roundtrip_preserves_ticks(self):
        p=song([[1,2,3,4],[2]*4]);p.notation['font_size']=8
        canvas=ScoreCanvas(p);canvas.grid=60;canvas.resize(1100,1600)
        try:
            layout=canvas.layout=ScoreLayout(p);render(layout)
            for page,rect,bar,points,xs in layout.hit_times:
                self.assertTrue(all(right>left for left,right in zip(xs,xs[1:])))
                ox,oy=canvas.page_origin(page)
                for tick in range(p.starts[bar],p.starts[bar+1],120):
                    x=layout.interpolate(points,xs,tick)
                    self.assertEqual(canvas.timeline_at(QPointF(ox+(x+.001)*canvas.scale,oy+rect.center().y()*canvas.scale)),(bar,tick))
                    self.assertAlmostEqual(layout.time_position(tick)[1],x)
        finally:canvas.deleteLater();APP.processEvents()


class AdvisoryFontTests(unittest.TestCase):
    def test_requested_fonts_change_real_ink_without_a_whole_row_transform(self):
        for style in ('traditional','spatial','compact'):
            p=song([[4]*4]*4,style);p.notation['font_size']=24;low=ScoreLayout(p);a=render(low)
            p.notation['font_size']=60;high=ScoreLayout(p);b=render(high)
            self.assertEqual(high.font_size,60);self.assertGreater(high.font_size,high.font_limit)
            self.assertEqual(len(a),len(b))
            self.assertEqual((low.systems[0].layout_scale,high.systems[0].layout_scale),(1,1))
            self.assertAlmostEqual(b[0].height()/a[0].height(),60/24)

    def test_sparse_pitch_separation_relaxes_advice_without_requiring_duration_cells(self):
        # Keep the second source a single representable value, followed by a
        # rest; tied fragments would add an unrelated same-pitch bottleneck.
        sparse=song([[1]*4],'spatial');sparse.notes=[Note(0,80,60),Note(80,640,84)]
        dense=copy.deepcopy(sparse);dense.notes[1].pitch=60
        sparse.notation['row_gap']=dense.notation['row_gap']=18
        a,b=ScoreLayout(sparse),ScoreLayout(dense)
        self.assertGreater(a.font_limit,b.font_limit*2);self.assertGreater(a.font_limit,20)
        sparse.notation['font_size']=a.font_limit;layout=ScoreLayout(sparse);boxes=render(layout)
        for rect in boxes:self.assertGreaterEqual(rect.left(),MARGIN-1e-6);self.assertLessEqual(rect.right(),PAPER_W-MARGIN+1e-6)
        for i,left in enumerate(boxes):
            for right in boxes[i+1:]:self.assertFalse(left.intersects(right))

    def test_spatial_and_compact_retain_maximum_density_times_actual_beats(self):
        for style in ('spatial','compact'):
            p=song([[2]*2,[2]*4],style);s=ScoreLayout(p).systems[0]
            self.assertAlmostEqual(s.bar_widths[0]/s.bar_widths[1],.5)
            p=song([[1,2,3,4],[2]*4],style);s=ScoreLayout(p).systems[0]
            self.assertAlmostEqual(s.bar_widths[0]/s.bar_widths[1],2)

    def test_advice_and_rendering_leave_project_midi_and_pdf_layout_consistent(self):
        p=song([[1,2,3,4],[2]*4]);p.notation['font_size']=40
        before=copy.deepcopy(p.to_dict());music=event_list(p);layout=ScoreLayout(p);render(layout)
        seen=[];original=ScoreLayout.draw
        def capture(current,painter,page,*args,**kwargs):
            seen.append((current.font_size,[(s.cell_width,s.beat_gap,list(s.bar_widths)) for s in current.systems]))
            return original(current,painter,page,*args,**kwargs)
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            folder=Path(folder);export_midi(p,folder/'a.mid')
            with patch.object(ScoreLayout,'draw',capture):export_pdf(p,folder/'score.pdf')
            export_midi(p,folder/'b.mid');self.assertEqual((folder/'a.mid').read_bytes(),(folder/'b.mid').read_bytes())
            self.assertGreater((folder/'score.pdf').stat().st_size,0)
        self.assertEqual(seen[0],(40,[(s.cell_width,s.beat_gap,list(s.bar_widths)) for s in layout.systems]))
        self.assertEqual(before,p.to_dict());self.assertEqual(music,event_list(p))

    def test_dense_advice_reflow_is_bounded_without_hard_clamping(self):
        p=song([[16]*4]*16,'spatial');p.notation.update(per_line=16,font_size=FONT_SIZE_MAX)
        started=time.perf_counter();layout=ScoreLayout(p)
        self.assertLess(time.perf_counter()-started,4)
        self.assertEqual(layout.font_size,FONT_SIZE_MAX);self.assertGreater(layout.font_limit,0)
        self.assertLess(layout.font_limit,1)


if __name__=='__main__':unittest.main()
