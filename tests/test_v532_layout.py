"""Traditional beat spelling and imported short-tail voice placement."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPointF,QRectF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Context,Measure,Note,PPQ,Project
from lingfeng.audio.midi import event_list,export_midi
from lingfeng.engraving.notation import (
    Fragment,LEGATO_TAIL_MAX,PAPER_H,PAPER_W,ScoreLayout,beat_rhythm_parts,
    export_pdf,fragment_style,fragments_for_bar,voice_lanes,
)

APP=QApplication.instance() or QApplication([])


def song(notes,measures=None,style='traditional'):
    p=Project(measures=measures or [Measure()])
    p.contexts=[Context(0,p.end)];p.notes=notes;p.chords=[]
    p.notation.update(style=style,per_line=len(p.measures),font_size=15,circles=False,lyrics=False)
    return p


def render(layout):
    ties=[]
    for page in range(layout.pages):
        image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);image.fill(0xffffffff)
        painter=QPainter(image)
        try:layout.draw(painter,page);ties.extend(layout.tie_paths)
        finally:painter.end()
    return ties


class BeatSpellingTests(unittest.TestCase):
    def test_offbeat_eighth_crossing_a_beat_has_two_tied_sixteenths(self):
        note=Note(720,480,57,lyric='la');p=song([note])
        played=[f for f in fragments_for_bar(p,0) if f.note]
        self.assertEqual([(f.start,f.duration) for f in played],[(720,240),(960,240)])
        self.assertTrue(all(f.note is note for f in played))
        self.assertEqual([(f.continuation,f.continues,f.lyric) for f in played],[(False,True,'la'),(True,False,'')])
        ties=render(ScoreLayout(p));self.assertEqual([(nid,kind) for nid,kind,_ in ties],[(note.id,'continuous')])
        path=ties[0][2]
        self.assertLess(path.pointAtPercent(.5).y(),min(path.pointAtPercent(0).y(),path.pointAtPercent(1).y()))

    def test_dotted_values_never_cross_their_meter_beat(self):
        for start,duration in ((0,1440),(480,720),(720,720),(240,1440)):
            with self.subTest(start=start,duration=duration):
                note=Note(start,duration,60);p=song([note]);played=[f for f in fragments_for_bar(p,0) if f.note]
                self.assertEqual(sum(f.duration for f in played),duration)
                self.assertEqual(played[0].start,start);self.assertEqual(played[-1].end,note.end)
                for f in played:
                    if fragment_style(f)[1]:self.assertLessEqual(f.end,((f.start//PPQ)+1)*PPQ)
                self.assertEqual(len([t for t in render(ScoreLayout(p)) if t[0]==note.id]),len(played)-1)

    def test_beat_contained_dots_and_aligned_integral_sustains_keep_their_spelling(self):
        self.assertEqual(beat_rhythm_parts(240,720,0,PPQ),[(240,720)])
        for count in (1,2,3,4,5,6):
            duration=count*PPQ
            p=song([Note(0,duration,60)],measures=[Measure(max(4,count),4)]);played=[f for f in fragments_for_bar(p,0) if f.note]
            self.assertEqual(len(played),1);self.assertEqual(fragment_style(played[0])[3],duration//PPQ-1)
            self.assertFalse(render(ScoreLayout(p)))

    def test_mixed_denominators_use_local_bar_beat_anchors(self):
        p=song([],measures=[Measure(3,8),Measure(3,2)])
        first=Note(360,240,60);second=Note(p.starts[1]+1440,960,64)
        p.notes=[first,second]
        self.assertEqual([(f.start,f.duration) for f in fragments_for_bar(p,0) if f.note],[(360,120),(480,120)])
        offset=p.starts[1]
        self.assertEqual([(f.start-offset,f.duration) for f in fragments_for_bar(p,1) if f.note],[(1440,480),(1920,480)])
        self.assertEqual({nid for nid,_,_ in render(ScoreLayout(p))},{first.id,second.id})

    def test_bar_and_system_continuations_keep_one_source_identity(self):
        note=Note(3600,720,60);p=song([note],measures=[Measure(),Measure()]);p.notation['per_line']=1
        pieces=[f for bar in (0,1) for f in fragments_for_bar(p,bar) if f.note]
        self.assertEqual([(f.start,f.duration) for f in pieces],[(3600,240),(3840,480)])
        self.assertEqual({id(f.note) for f in pieces},{id(note)})
        self.assertEqual([(nid,kind) for nid,kind,_ in render(ScoreLayout(p))],[(note.id,'outgoing'),(note.id,'incoming')])

    def test_conversion_remainders_do_not_create_tiny_beat_fragments(self):
        for delta in (-2,-1,0,1,2):
            with self.subTest(delta=delta):
                self.assertEqual(beat_rhythm_parts(0,PPQ+delta,0,PPQ),[(0,PPQ+delta)])
                self.assertEqual(beat_rhythm_parts(PPQ+delta,480,0,PPQ),[(PPQ+delta,480)])
        self.assertEqual(beat_rhythm_parts(720,241,0,PPQ),[(720,241)])

    def test_spatial_and_compact_share_beat_spelling_without_changing_source_notes(self):
        for style in ('spatial','compact'):
            p=song([Note(720,480,60),Note(1920,1440,62)],style=style)
            before=copy.deepcopy(p.to_dict())
            self.assertEqual([(f.start,f.duration) for f in fragments_for_bar(p,0) if f.note],[(720,240),(960,240),(1920,960),(2880,480)])
            self.assertEqual([(nid,kind) for nid,kind,_ in render(ScoreLayout(p))],[(n.id,'continuous') for n in p.notes])
            self.assertEqual(before,p.to_dict())


class VoicePlacementTests(unittest.TestCase):
    def lanes(self,notes):
        return voice_lanes([Fragment(n.start,n.duration,n.pitch,n) for n in notes],legato=True)

    def test_authentic_short_tail_pattern_stays_on_one_melody_row_without_trimming(self):
        prior=Note(0,320,60);following=Note(240,720,57)
        p=song([prior,following]);before=copy.deepcopy(p.to_dict());layout=ScoreLayout(p)
        self.assertEqual(set(layout.systems[0].voices.values()),{0})
        played=[f for f in layout.systems[0].fragments[0] if f.note]
        self.assertEqual([(f.start,f.duration) for f in played],[(0,320),(240,720)])
        self.assertGreater(played[0].end,played[1].start)
        render(layout);self.assertEqual(p.to_dict(),before)

    def test_absolute_and_fractional_tail_thresholds_are_inclusive_and_bounded(self):
        self.assertEqual(LEGATO_TAIL_MAX,120)
        for prior_duration,next_duration,overlap,expected in ((960,960,120,1),(960,960,121,2),
                (320,720,80,1),(320,720,81,2),(960,320,80,1),(960,320,81,2)):
            with self.subTest(prior=prior_duration,following=next_duration,overlap=overlap):
                notes=[Note(0,prior_duration,60),Note(prior_duration-overlap,next_duration,64)]
                self.assertEqual(len(set(self.lanes(notes).values())),expected)

    def test_genuine_simultaneous_and_sustained_polyphony_retains_separate_lanes(self):
        for notes in ([Note(0,480,pitch) for pitch in (60,64,67)],
                      [Note(0,1920,60),Note(480,960,64)],
                      [Note(0,960,60),Note(60,960,64)]):
            with self.subTest(notes=[(n.start,n.duration,n.pitch) for n in notes]):
                p=song(notes);layout=ScoreLayout(p)
                self.assertEqual(len(set(layout.systems[0].voices.values())),len(notes))
                render(layout)
                centers={round(rect.center().y(),6) for _,rect,_ in layout.hit_notes}
                self.assertEqual(len(centers),len(notes))

    def test_visible_fragment_occupancy_does_not_reserve_an_invisible_note_tail(self):
        long=Note(0,4*PPQ,60);following=Note(240,480,64)
        fragments=[Fragment(0,240,60,long),Fragment(240,480,64,following)]
        self.assertEqual(set(voice_lanes(fragments,legato=True).values()),{0})
        self.assertEqual(long.duration,4*PPQ)
        # Distinct source attacks already active at a row entry remain voices.
        entering=Note(120,2*PPQ,67)
        clipped=[Fragment(PPQ,PPQ,60,long),Fragment(PPQ,PPQ,67,entering)]
        self.assertEqual(len(set(voice_lanes(clipped,legato=True).values())),2)

    def test_render_hit_mapping_pdf_and_midi_share_the_same_unchanged_sources(self):
        p=song([Note(720,480,57,lyric='la'),Note(1920,320,60),Note(2160,720,57)])
        before=copy.deepcopy(p.to_dict());events=event_list(p);midi=export_midi(p,None)
        layout=ScoreLayout(p);ties=render(layout)
        self.assertEqual({nid for _,_,nid in layout.hit_notes},{n.id for n in p.notes})
        self.assertTrue(ties);self.assertEqual(set(layout.systems[0].voices.values()),{0})
        for _,_,_,points,xs in layout.hit_times:self.assertTrue(all(b>a for a,b in zip(xs,xs[1:])))
        observed=[];original=ScoreLayout.draw
        def capture(current,*args,**kwargs):
            original(current,*args,**kwargs)
            observed.extend((nid,kind) for nid,kind,_ in current.tie_paths)
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            path=Path(folder)/'beat-ties.pdf'
            with patch.object(ScoreLayout,'draw',capture):export_pdf(p,path)
            self.assertTrue(path.read_bytes().startswith(b'%PDF'))
        self.assertEqual(observed,[(nid,kind) for nid,kind,_ in ties])
        self.assertEqual(p.to_dict(),before);self.assertEqual(event_list(p),events);self.assertEqual(export_midi(p,None),midi)


class DotPainter(QPainter):
    """Record the actual ellipse geometry after the painter's full transform."""
    def __init__(self,image):super().__init__(image);self.dots=[]
    def drawEllipse(self,*args):
        if len(args)==3 and isinstance(args[0],QPointF):
            center,rx,ry=args
            self.dots.append(self.worldTransform().mapRect(QRectF(center.x()-rx,center.y()-ry,2*rx,2*ry)))
        return super().drawEllipse(*args)


class PhysicalDotTests(unittest.TestCase):
    def dotted_song(self,bars=4,size=15):
        p=song([],measures=[Measure() for _ in range(bars)])
        p.notation['font_size']=size
        p.notes=[Note(start+beat*PPQ+240,720,48) for start in p.starts[:-1] for beat in range(4)]
        return p

    def dots(self,layout):
        dots=[]
        for page in range(layout.pages):
            image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);image.fill(0xffffffff);painter=DotPainter(image)
            try:layout.draw(painter,page);dots.extend(painter.dots)
            finally:painter.end()
        return dots

    def assert_contained(self,layout,dots):
        beats=[dict(left=layout.system_transform(system).map(QPointF(beat['left'],0)).x(),
                    right=layout.system_transform(system).map(QPointF(beat['right'],0)).x())
               for system in layout.systems for beat in system.beat_cells]
        self.assertEqual(len(dots),len(beats))
        for dot,beat in zip(dots,beats):
            self.assertGreaterEqual(dot.left(),beat['left']-1e-7)
            self.assertLessEqual(dot.right(),beat['right']+1e-7)
            self.assertGreater(dot.width(),0)

    def test_actual_dots_stay_inside_beat_at_15_26_and_72_without_changing_font_or_gap(self):
        for size in (15,26,72):
            with self.subTest(size=size):
                p=self.dotted_song(size=size);layout=ScoreLayout(p);dots=self.dots(layout)
                self.assert_contained(layout,dots)
                self.assertEqual(layout.font_size,size)
                self.assertAlmostEqual(layout.systems[0].beat_gap,2*layout.systems[0].bar_side_gap)
                scales=[s.layout_scale for s in layout.systems for bar in s.bars for f in s.fragments[bar]if fragment_style(f)[1]]
                for dot,scale in zip(dots,scales):self.assertAlmostEqual(dot.width(),2.8*size/15*scale)
                self.assertEqual({size for _,size in layout.glyph_sizes},{size})

    def test_numeric_advice_keeps_physical_dots_inside_beat_without_reducing_digit_size(self):
        p=self.dotted_song();advice=ScoreLayout(p).font_limit;p.notation['font_size']=advice
        layout=ScoreLayout(p);dots=self.dots(layout);self.assert_contained(layout,dots)
        expected=[]
        for system in layout.systems:
            x=system.left
            for bar,width in zip(system.bars,system.bar_widths):
                for f in system.fragments[bar]:
                    if fragment_style(f)[1]:
                        a,b=system.traditional_cells[(bar,f.start)];expected.append(layout.system_transform(system).map(QPointF(x+(a+b)/2+13*system.symbol_scale,0)).x())
                x+=width
        self.assertEqual(layout.font_size,advice)
        self.assertTrue(any(dot.center().x()<center-1e-7 for dot,center in zip(dots,expected)))
        scales=[s.layout_scale for s in layout.systems for bar in s.bars for f in s.fragments[bar]if fragment_style(f)[1]]
        for dot,center,scale in zip(dots,expected,scales):
            self.assertLessEqual(dot.center().x(),center+1e-7)
            self.assertAlmostEqual(dot.width(),2.8*advice/15*scale)

    def test_oversized_manual_font_keeps_full_dot_radius_without_a_row_transform(self):
        p=self.dotted_song(bars=16,size=72);before=copy.deepcopy(p.to_dict());layout=ScoreLayout(p)
        dots=self.dots(layout);self.assert_contained(layout,dots)
        scales=[s.layout_scale for s in layout.systems for bar in s.bars for f in s.fragments[bar]if fragment_style(f)[1]]
        self.assertTrue(all(scale==1 for scale in scales))
        for dot,scale in zip(dots,scales):self.assertAlmostEqual(dot.width(),2.8*72/15*scale)
        self.assertEqual(layout.font_size,72);self.assertEqual({size for _,size in layout.glyph_sizes},{72})
        system=layout.systems[0]
        self.assertAlmostEqual(system.beat_gap,2*system.cell_width)
        self.assertGreater(sum(system.bar_widths),PAPER_W-2*system.left)
        self.assertEqual(p.to_dict(),before)


if __name__=='__main__':unittest.main()
