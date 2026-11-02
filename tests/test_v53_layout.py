"""Spatial beat proportions and shared score mapping, with advisory font fitting."""
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
from lingfeng.music.model import Project,Measure,Context,Note,Chord,PPQ
from lingfeng.audio.midi import event_list,export_midi
from lingfeng.engraving.notation import ScoreLayout,PAPER_W,PAPER_H,MARGIN,SYMBOL_PADDING,export_pdf
from lingfeng.engraving.presentation import apply_forced_row,add_compression
from lingfeng.ui.score_view import ScoreCanvas
from tests.test_v54_layout import assert_numeric_cells

APP=QApplication.instance() or QApplication([])
STYLES=('spatial','compact')


class PartialMeasure(Measure):
    """Exercise actual short-bar duration without introducing a file-format field."""
    def __init__(self,ticks,numerator=4,denominator=4):
        super().__init__(numerator,denominator);self.actual_ticks=ticks

    @property
    def ticks(self):return self.actual_ticks


def song(meters,patterns):
    p=Project(measures=[Measure(*meter) for meter in meters])
    p.contexts=[Context(0,p.end)];p.chords=[];p.notes=[]
    p.notation.update(per_line=len(meters),font_size=15,circles=False,lyrics=False)
    for bar,counts in enumerate(patterns):
        beat=PPQ*4//p.measures[bar].denominator
        for offset,count in enumerate(counts):
            for i in range(count):
                p.notes.append(Note(p.starts[bar]+offset*beat+i*beat//count,beat//count,(60,62,64,65)[i%4]))
    return p


def render(layout):
    for page in range(layout.pages):
        image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);image.fill(0xffffffff)
        painter=QPainter(image)
        try:layout.draw(painter,page)
        finally:painter.end()


def fit_symbol_cells(project):
    """Use a conservative cell-fitting size when testing legacy cell bounds.

    0.53.1 advice can safely cross time cells at different pitches; these
    historical assertions deliberately exercise the narrower cell fit too.
    """
    layout=ScoreLayout(project);safe=layout.font_limit
    for system in layout.systems:
        if project.notation['style']=='traditional':
            required=max((2*max(layout.column_extents(f))+SYMBOL_PADDING
                          for parts in system.fragments.values() for f in parts),default=1)
            safe=min(safe,15*system.cell_width/required/system.font_ratio)
        else:
            safe=min(safe,min(15*width/layout.width_cache[bar]/system.font_ratio
                              for bar,width in zip(system.bars,system.bar_widths)))
    project.notation['font_size']=max(.0001,safe*.999)
    return ScoreLayout(project)


class PerBeatWidthTests(unittest.TestCase):
    def assert_widths(self,project,weights):
        for style in STYLES:
            with self.subTest(style=style):
                checked=copy.deepcopy(project);checked.notation['style']=style
                layout=fit_symbol_cells(checked);system=layout.systems[0]
                unit=sum(system.bar_widths)/sum(weights)
                for width,weight in zip(system.bar_widths,weights):self.assertAlmostEqual(width,unit*weight)
                self.assertAlmostEqual(sum(system.bar_widths),PAPER_W-MARGIN-system.left)
                for bar,width in zip(system.bars,system.bar_widths):
                    start,end=project.starts[bar:bar+2];beat=PPQ*4//project.measures[bar].denominator
                    points,xs,*_=layout.bar_map(system,bar,0,width);edges=[*range(start,end,beat),end]
                    for a,b in zip(edges,edges[1:]):
                        span=layout.interpolate(points,xs,b)-layout.interpolate(points,xs,a)
                        self.assertAlmostEqual(span/((b-a)/beat),width/((end-start)/beat))
                render(layout)
                for _,_,left,right,cell_left,cell_right in layout.symbol_boxes:
                    self.assertGreaterEqual(left,cell_left-1e-7);self.assertLessEqual(right,cell_right+1e-7)

    def test_two_four_and_four_four_have_equal_beat_width_and_one_to_two_bars(self):
        p=song([(2,4),(4,4)],[[2]*2,[2]*4]);self.assert_widths(p,[4,8])
        for style in STYLES:
            p.notation['style']=style;system=ScoreLayout(p).systems[0]
            self.assertAlmostEqual(system.bar_widths[0]/2,system.bar_widths[1]/4)

    def test_original_four_to_two_example_is_preserved(self):
        self.assert_widths(song([(4,4)]*2,[[1,2,3,4],[2]*4]),[16,8])

    def test_density_and_meter_length_both_contribute_instead_of_total_notes(self):
        # Five attacks in the shorter bar versus eight in the longer bar, but
        # the respective 4 and 2 maximums yield equal full-bar weights.
        self.assert_widths(song([(2,4),(4,4)],[[4,1],[2]*4]),[8,8])

    def test_denominator_beats_and_compound_meters_use_actual_beat_counts(self):
        for meters,patterns,weights in (
                ([(2,2),(4,4)],[[2]*2,[2]*4],[4,8]),
                ([(6,8),(3,4)],[[2]*6,[2]*3],[12,6]),
                ([(9,8),(3,8)],[[3]*9,[1]*3],[27,3]),
                ([(3,16),(5,8)],[[2]*3,[2]*5],[6,10])):
            with self.subTest(meters=meters):self.assert_widths(song(meters,patterns),weights)

    def test_fractional_pickups_use_actual_duration_instead_of_nominal_numerator(self):
        for actual_beats in (.5,1.5):
            with self.subTest(actual_beats=actual_beats):
                ticks=round(actual_beats*PPQ)
                p=song([(4,4),(4,4)],[[],[1]*4]);p.measures[0]=PartialMeasure(ticks)
                p.contexts=[Context(0,p.end)]
                p.notes=[Note(t,min(PPQ,ticks-t),60) for t in range(0,ticks,PPQ)]
                p.notes.extend(Note(ticks+i*PPQ,PPQ,62) for i in range(4))
                self.assert_widths(p,[actual_beats,4])
                for style in ('spatial','compact'):
                    p.notation['style']=style;layout=ScoreLayout(p);system=layout.systems[0]
                    points,xs,*_=layout.bar_map(system,0,0,system.bar_widths[0])
                    self.assertAlmostEqual(layout.interpolate(points,xs,ticks),system.bar_widths[0])
                    self.assertAlmostEqual(layout.interpolate(points,xs,ticks/2),system.bar_widths[0]/2)

    def test_chords_cross_bar_ties_and_rests_preserve_column_density(self):
        p=song([(2,4),(4,4)],[[],[]]);self.assert_widths(p,[2,4])
        p.notes=[Note(0,p.end,60),Note(0,p.end,64)]
        self.assert_widths(p,[2,4])
        for style in STYLES:
            p.notation['style']=style;layout=ScoreLayout(p);render(layout)
            self.assertEqual({ident for ident,_,_ in layout.tie_paths},{n.id for n in p.notes})
        p=song([(2,4),(4,4)],[[1]*2,[2]*4])
        for n in p.notes:
            if n.start<p.starts[1]:n.duration=PPQ//2
        # Each short first-bar note is followed by a notated rest; both occupy
        # a column, matching the two attacks in every beat of the second bar.
        self.assert_widths(p,[4,8])

    def test_linear_beat_spacing_and_click_playhead_roundtrip_in_mixed_meter(self):
        p=song([(2,4),(6,8)],[[2]*2,[2]*6]);p.notation['font_size']=8
        for style in STYLES:
            with self.subTest(style=style):
                p.notation['style']=style;canvas=ScoreCanvas(p);canvas.grid=60;canvas.resize(1100,1700)
                try:
                    layout=canvas.layout=ScoreLayout(p);render(layout);beat_widths=[]
                    for page,rect,bar,points,xs in layout.hit_times:
                        start,end=p.starts[bar:bar+2];beat=PPQ*4//p.measures[bar].denominator
                        edges=[layout.interpolate(points,xs,t) for t in range(start,end+1,beat)]
                        beat_widths.extend(right-left for left,right in zip(edges,edges[1:]))
                        ox,oy=canvas.page_origin(page)
                        for tick in range(start,end,120):
                            x=layout.interpolate(points,xs,tick)
                            hit=canvas.timeline_at(QPointF(ox+(x+.001)*canvas.scale,oy+rect.center().y()*canvas.scale))
                            self.assertEqual(hit,(bar,tick));self.assertAlmostEqual(layout.time_position(tick)[1],x)
                    for width in beat_widths:self.assertAlmostEqual(width,beat_widths[0])
                finally:canvas.deleteLater();APP.processEvents()

    def test_traditional_syncopation_without_a_beat_attack_has_monotone_time_map(self):
        p=song([(4,4),(6,8)],[[],[]]);p.notation['style']='traditional'
        p.notes=[Note(0,1440,60),Note(1440,480,62),Note(1920,1920,64),
                 Note(3840,1440,65),Note(5280,1440,67)]
        p.notation['font_size']=ScoreLayout(p).recommended_font_size
        layout=ScoreLayout(p);system=layout.systems[0]
        for bar,width in zip(system.bars,system.bar_widths):
            points,xs,*_=layout.bar_map(system,bar,0,width)
            self.assertTrue(all(b>a for a,b in zip(xs,xs[1:])))
            start,end=p.starts[bar:bar+2];beat=PPQ*4//p.measures[bar].denominator
            edges=[layout.interpolate(points,xs,t) for t in range(start,end+1,beat)]
            self.assertTrue(all(b>a for a,b in zip(edges,edges[1:])))
        render(layout)
        assert_numeric_cells(self,layout)

    def test_repeat_clearance_does_not_shift_equal_beat_anchors(self):
        p=song([(2,4),(4,4)]*2,[[2]*2,[2]*4]*2)
        add_compression(p,[0,1,2,3],'repeat');self.assert_widths(p,[4,8])

    def test_traditional_labels_and_lyrics_do_not_change_numeric_unit_budget(self):
        p=song([(4,4)],[[4]*4]);p.notation.update(style='traditional',font_size=26,lyrics=True)
        p.chords=[Chord(0,240,48,'maj7'),Chord(240,240,50,'7b5'),Chord(480,480,53,'mM7'),Chord(960,2880,55,'7')]
        for n in p.notes:n.lyric='long syllable'
        p.notation['font_size']=ScoreLayout(p).recommended_font_size;layout=ScoreLayout(p)
        plain=copy.deepcopy(p);plain.chords=[];plain.notation['lyrics']=False;baseline=ScoreLayout(plain)
        before=copy.deepcopy(p.to_dict());render(layout)
        self.assertEqual({ident for _,_,ident in layout.hit_chords},{chord.id for chord in p.chords})
        self.assertEqual(layout.recommended_font_size,baseline.recommended_font_size)
        self.assertEqual(layout.cell_width,baseline.cell_width)
        self.assertEqual(layout.systems[0].unit_count,baseline.systems[0].unit_count)
        self.assertEqual(len(layout.lyric_positions),len(p.notes));assert_numeric_cells(self,layout)
        self.assertEqual(before,p.to_dict())

    def test_forced_row_font_and_glyph_safety_fit_duration_weighted_bars(self):
        p=song([(2,4),(3,4),(4,4),(4,4)],[[2]*2,[2]*3,[2]*4,[1]*4])
        p.notation.update(per_line=2,font_size=26);apply_forced_row(p,[0,1,2])
        for style in STYLES:
            p.notation.update(style=style,font_size=26)
            layout=fit_symbol_cells(p);system=layout.systems[0]
            self.assertEqual(system.bars,[0,1,2]);self.assertAlmostEqual(system.symbol_scale/layout.glyph_scale,2/3)
            for width,beats in zip(system.bar_widths,(2,3,4)):
                self.assertAlmostEqual(width/beats,system.bar_widths[0]/2)
            for current in layout.systems:
                for bar,width in zip(current.bars,current.bar_widths):
                    self.assertLessEqual(layout.width_cache[bar]*current.symbol_scale,width+1e-7)
            render(layout)

    def test_pdf_screen_and_midi_share_mixed_meter_layout_without_music_edits(self):
        p=song([(2,4),(4,4)],[[2]*2,[2]*4]);music=event_list(p)
        original=ScoreLayout.draw
        for style in STYLES:
            p.notation['style']=style;state=copy.deepcopy(p.to_dict());expected=ScoreLayout(p);render(expected)
            seen=[]
            def record(layout,painter,page,*args,**kwargs):
                result=original(layout,painter,page,*args,**kwargs)
                seen.append(([list(s.bar_widths) for s in layout.systems],[(bar,rect.left(),rect.width()) for _,rect,bar in layout.hit_bars]))
                return result
            with tempfile.TemporaryDirectory(dir='tmp') as folder:
                folder=Path(folder);export_midi(p,folder/'before.mid')
                with patch.object(ScoreLayout,'draw',record):export_pdf(p,folder/'meter.pdf')
                export_midi(p,folder/'after.mid')
                self.assertEqual((folder/'before.mid').read_bytes(),(folder/'after.mid').read_bytes())
                self.assertGreater((folder/'meter.pdf').stat().st_size,0)
            self.assertEqual(seen[-1],([list(s.bar_widths) for s in expected.systems],[(bar,rect.left(),rect.width()) for _,rect,bar in expected.hit_bars]))
            self.assertEqual(p.to_dict(),state);self.assertEqual(event_list(p),music)


if __name__=='__main__':unittest.main()
