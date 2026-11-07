"""Two melody tracks share score timing and retain independent lyric lanes."""
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication
from lingfeng.engraving.lyrics import apply_range, edit_lyric_track, events, lyric_track
from lingfeng.engraving.notation import PAPER_H, PAPER_W, ScoreLayout, MELODY_COLORS, MUTED, fragment_style
from lingfeng.engraving.presentation import same_segment
from lingfeng.music.bar_operations import delete_bars
from lingfeng.music.model import Chord, Note, PPQ, Project

APP=QApplication.instance() or QApplication([])


def draw(layout):
    image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_ARGB32)
    painter=QPainter(image)
    try:layout.draw(painter,0)
    finally:painter.end()
    return image


class TwoMelodyScoreTests(unittest.TestCase):
    def setUp(self):
        self.project=Project()
        p=self.project
        p.notation['per_line']=1
        p.notes=[Note(480,480,60),Note(960,480,64),Note(p.starts[1],480,62)]
        p.instrument_notes=[Note(480,480,60),Note(960,960,66),Note(p.starts[2],480,62)]
        p.chords=[Chord(p.starts[3],3840)]

    def test_traditional_lanes_share_onsets_and_hide_missing_rolls(self):
        p=self.project;p.notation['style']='traditional'
        layout=ScoreLayout(p);draw(layout)
        self.assertEqual([s.tracks for s in layout.systems[:4]],[(0,1),(0,),(1,),()])
        self.assertFalse(layout.systems[3].fragments[3])
        self.assertEqual(layout.systems[2].track_voices,{1:0})
        rects={ident:rect for _,rect,ident in layout.hit_notes}
        for a,b in zip(p.notes[:2],p.instrument_notes[:2]):
            first,second=rects[a.id],rects[b.id]
            cells=[box[4:] for box in layout.symbol_boxes if box[0]==a.start]
            self.assertEqual(cells[0],cells[1])
            self.assertLess(first.bottom(),second.bottom())

    def test_spatial_shares_onset_even_with_different_accidental_extents(self):
        p=self.project
        for style in ('spatial','compact'):
            with self.subTest(style=style):
                p.notation['style']=style;layout=ScoreLayout(p);image=draw(layout)
                colors={image.pixelColor(x,y).name() for y in range(140,430) for x in range(92,849)}
                self.assertTrue({c.name() for c in MELODY_COLORS}<=colors)
                rects={ident:rect for _,rect,ident in layout.hit_notes}
                self.assertAlmostEqual(rects[p.notes[0].id].center().x(),rects[p.instrument_notes[0].id].center().x())
                boxes=[box for box in layout.symbol_boxes if box[0]==960]
                self.assertEqual(len(boxes),2)
                origins=[box[2]+layout.glyph_extents(f)[0]*layout.systems[0].symbol_scale
                         for box,f in zip(boxes,[f for f in layout.systems[0].fragments[0] if f.start==960])]
                self.assertAlmostEqual(*origins)

    def test_spatial_draws_one_neutral_rest_only_during_shared_silence(self):
        p=self.project
        p.notes=[Note(240,480,60),Note(1080,480,64)]
        p.instrument_notes=[Note(0,480,67),Note(960,480,62)]
        for style in ('spatial','compact'):
            with self.subTest(style=style):
                p.notation['style']=style
                layout=ScoreLayout(p);system=layout.systems[0];draw(layout)
                fragments=system.fragments[0]
                rests=[f for f in fragments if f.pitch is None]
                self.assertEqual([(f.start,f.end) for f in rests[:2]],[(720,960),(1560,1920)])
                self.assertTrue(all(layout.melody_color(system,f,MUTED)==MUTED for f in rests))
                self.assertEqual(len({f.start for f in rests}),len(rests))
                self.assertFalse(system.unisons)

    def test_spatial_sustain_ties_to_digit_when_last_dash_shares_pitch_and_column(self):
        p=self.project
        sustain=Note(0,4*PPQ,60)
        p.notes=[sustain]
        p.instrument_notes=[Note(2*PPQ,PPQ,64),Note(3*PPQ,PPQ,60)]
        for style in ('spatial','compact','traditional'):
            with self.subTest(style=style):
                p.notation['style']=style
                before=p.to_dict()
                layout=ScoreLayout(p);draw(layout)
                system=layout.systems[0]
                parts=[f for f in system.fragments[0] if f.note is sustain]
                ties=[path for ident,kind,path in layout.tie_paths if ident==sustain.id and kind=='continuous']
                if style=='traditional':
                    self.assertEqual([(f.start,fragment_style(f)[3]) for f in parts],[(0,3)])
                    self.assertFalse(ties)
                else:
                    self.assertEqual([(f.start,fragment_style(f)[3]) for f in parts],[(0,2),(3*PPQ,0)])
                    self.assertIn((3*PPQ,60),system.unisons)
                    self.assertEqual(len(ties),1)
                    path=ties[0]
                    self.assertLess(path.elementAt(0).x,layout.time_position(PPQ)[1])
                    self.assertGreater(path.currentPosition().x(),layout.time_position(2*PPQ)[1])
                self.assertEqual(p.to_dict(),before)

    def test_lyric_tracks_save_retime_and_draw_as_two_lines(self):
        p=self.project
        apply_range(p,'风',0,1)
        edit_lyric_track(p,1,lambda melody:apply_range(melody,'云',0,1))
        layout=ScoreLayout(p);draw(layout)
        self.assertEqual(layout.systems[0].lyric_rows,2)
        (a,_,x,y),(b,_,other_x,other_y)=layout.lyric_positions[:2]
        self.assertNotEqual(a,b);self.assertAlmostEqual(x,other_x);self.assertLess(y,other_y)
        reloaded=Project.from_dict(p.to_dict())
        reloaded.insert_measure(0)
        self.assertEqual(events(lyric_track(reloaded,1))[0]['tick'],reloaded.starts[1]+480)
        delete_bars(reloaded,[0])
        self.assertEqual([(e['text'],e['tick']) for e in events(reloaded)],[('风',480)])
        self.assertEqual([(e['text'],e['tick']) for e in events(lyric_track(reloaded,1))],[('云',480)])

    def test_instrument_notes_participate_in_repeat_comparison(self):
        p=self.project;p.notes=[];p.chords=[]
        p.instrument_notes=[Note(0,480,60),Note(p.starts[1],480,60)]
        self.assertTrue(same_segment(p,0,1,1,2))
        p.instrument_notes[-1].pitch=61
        self.assertFalse(same_segment(p,0,1,1,2))


if __name__=='__main__':unittest.main()
