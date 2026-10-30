"""Equal score geometry and shared, selectable live/offline synthesis."""
import copy,json,os,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication,QDialog
from popscore.model import Project,Note,Chord,Measure,Context
from popscore.notation import ScoreLayout
from popscore.editor import PianoRoll
from popscore.audio import Transport,MidiRouter
from popscore.dialogs import SoundSettingsDialog
from popscore.exporting import offline_pcm
APP=QApplication.instance() or QApplication([])

def draw(p):
    layout=ScoreLayout(p);im=QImage(900,1273,QImage.Format.Format_RGB32);paint=QPainter(im);layout.draw(paint,0);paint.end();return layout

class LayoutTests(unittest.TestCase):
    def music(self):
        p=Project();p.notes=[Note(0,960,60),Note(3840,960,62)]
        p.notes += [Note(7680+i*120,120,60+i%5) for i in range(32)]
        p.chords=[Chord(0,3840),Chord(3840,3840,55,'7'),Chord(7680,3360),Chord(11040,240,48,'7b5'),Chord(11280,240,53,'maj7')]
        return p
    def test_density_allocates_width_and_spatial_time_remains_linear(self):
        p=self.music();before=p.to_dict()
        for style in ('spatial','compact'):
            p.notation['style']=style;layout=draw(p)
            self.assertGreater(layout.systems[0].bar_widths[2],layout.systems[0].bar_widths[0])
            for _,rect,bar,ticks,xs in layout.hit_times:
                for t,x in zip(ticks,xs):self.assertAlmostEqual(x,rect.left()+rect.width()*(t-p.starts[bar])/p.measures[bar].ticks)
        self.assertEqual(p.notes,Project.from_dict(before).notes)
    def test_dense_bar_limits_one_global_size_including_sparse_bars(self):
        p=self.music();p.notation.update(font_size=12);layout=draw(p);s=layout.systems[0]
        self.assertLess(s.bar_scales[0],.8);self.assertEqual(s.bar_scales[2],s.bar_scales[0])
        offset=0
        for bar in s.bars:
            count=len(s.fragments[bar]);sizes=[size for _,size in layout.glyph_sizes[offset:offset+count]];offset+=count
            self.assertEqual(set(sizes),{15*s.bar_scales[bar]})
    def test_mixed_meter_and_forced_rows_preserve_geometry_and_hit_positions(self):
        p=Project();p.measures[1]=Measure(6,8);p.contexts=[Context(0,p.end)];p.notes=[Note(p.starts[i],240,60+i) for i in range(6)];p.notation['forced_rows']=[[0,6]];layout=draw(p)
        self.assertEqual(len(layout.systems[0].bars),6);self.assertEqual(layout.systems[0].layout_scale,1)
        self.assertAlmostEqual(layout.systems[0].symbol_scale,layout.glyph_scale*4/6)
        for bar in range(6):
            a=layout.time_position(p.starts[bar]);b=layout.time_position(p.starts[bar]+p.measures[bar].ticks//2)
            self.assertAlmostEqual(b[1]-a[1],layout.systems[0].bar_widths[bar]/2)
    def test_tiny_cells_accidentals_and_dots_stay_inside_equal_bars(self):
        p=Project();p.notation.update(per_line=8,font_size=26)
        p.notes=[Note(i*3840+90,90,66) for i in range(8)]+[Note(i*3840+3570,270,61) for i in range(8)]
        layout=draw(p)
        for _,_,left,right,a,b in layout.symbol_boxes:self.assertGreaterEqual(left,a-1e-6);self.assertLessEqual(right,b+1e-6)
    def test_chord_labels_do_not_overlap_adjacent_labels_or_bar(self):
        p=self.music();layout=draw(p)
        boxes=[rect for page,rect,cid in layout.hit_chords]
        for left,right in zip(boxes,boxes[1:]):
            if abs(left.bottom()-right.bottom())<20:self.assertLessEqual(left.right(),right.left())
    def test_simultaneous_close_pitches_reduce_local_symbols(self):
        p=Project();p.notes=[Note(0,960,60),Note(0,960,62)];p.notation.update(row_gap=8,font_size=15)
        layout=draw(p);self.assertLess(layout.systems[0].bar_scales[0],1);self.assertEqual(layout.systems[0].row_gap,8)

if __name__=='__main__':unittest.main()
