"""Compact traditional engraving and display-only isolated 32nd pairs."""
import copy,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter
from PySide6.QtCore import QPointF
from popscore.model import Project,Note,Measure,Context
from popscore.notation import ScoreLayout,fragment_style,PAPER_W,PAPER_H,MARGIN
from popscore.scoreview import ScoreCanvas
from popscore.midi import export_midi
APP=QApplication.instance() or QApplication([])

def song(durations=(720,120,120,960,1920),style='spatial'):
    p=Project();p.measures=[Measure()];p.contexts=[Context(0,p.end)];p.chords=[];p.notes=[];tick=0
    for i,d in enumerate(durations):p.notes.append(Note(tick,d,60+i%5));tick+=d
    p.notation.update(style=style,per_line=1,font_size=15,circles=False,lyrics=False)
    return p

def render(p):
    layout=ScoreLayout(p);im=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);q=QPainter(im);layout.draw(q,0);q.end();return layout,im

class ShortPairTests(unittest.TestCase):
    def test_spacing_equals_eighth_sixteenth_sixteenth_in_all_styles(self):
        for style in ('spatial','compact','traditional'):
            p=song(style=style);q=song((480,240,240,960,1920),style)
            actual,_=render(p);expected,_=render(q)
            self.assertEqual(actual.width_cache,expected.width_cache)
            self.assertEqual(actual.systems[0].bar_widths,expected.systems[0].bar_widths)
            ax=[r.center().x() for _,r,_ in actual.hit_notes];bx=[r.center().x() for _,r,_ in expected.hit_notes]
            self.assertEqual(len(ax),len(bx))
            for a,b in zip(ax,bx):self.assertAlmostEqual(a,b)
            f=actual.systems[0].fragments[0]
            self.assertEqual([fragment_style(n)[:2] for n in f[:3]],[(1,False),(3,False),(3,False)])
            self.assertEqual([(n.start,n.duration) for n in f[:3]],[(0,720),(720,120),(840,120)])

    def test_long_note_tail_is_split_and_tied_without_a_dot(self):
        p=song((1680,120,120,1920));layout,_=render(p);f=layout.systems[0].fragments[0]
        self.assertEqual([(n.start,n.duration) for n in f[:4]],[(0,960),(960,720),(1680,120),(1800,120)])
        self.assertEqual([fragment_style(n)[:2] for n in f[:4]],[(0,False),(1,False),(3,False),(3,False)])
        self.assertTrue(f[0].continues and f[1].continuation)
        self.assertTrue(any(nid==p.notes[0].id and kind=='continuous' for nid,kind,_ in layout.tie_paths))

    def test_following_dotted_eighth_can_supply_the_space(self):
        p=song((120,120,720,960,1920));layout=ScoreLayout(p);f=layout.systems[0].fragments[0]
        self.assertEqual([layout.spacing_tick(0,t) for t in (0,120,240,960)],[0,240,480,960])
        self.assertEqual([fragment_style(n)[:2] for n in f[:3]],[(3,False),(3,False),(1,False)])

    def test_dotted_rest_has_the_same_spacing_rule(self):
        p=song();p.notes.pop(0);layout=ScoreLayout(p);f=layout.systems[0].fragments[0]
        self.assertIsNone(f[0].pitch);self.assertEqual(fragment_style(f[0])[:2],(1,False))
        self.assertEqual([layout.spacing_tick(0,t) for t in (0,720,840,960)],[0,480,720,960])

    def test_extra_short_notes_or_sixteenths_disable_shorthand(self):
        for durations in ((240,120,120,480,960,1920),(600,120,120,120,960,1920),(480,120,120,120,120,960,1920)):
            p=song(durations);layout=ScoreLayout(p);self.assertFalse(layout.rhythm_adjustments[0])
        p=song();p.notes.append(Note(120,240,72));self.assertFalse(ScoreLayout(p).rhythm_adjustments[0])

    def test_meter_denominator_defines_eligibility_and_preserves_beat_width(self):
        p=song();p.measures=[Measure(2,2)];p.contexts=[Context(0,p.end)]
        layout=ScoreLayout(p);self.assertTrue(layout.rhythm_adjustments[0])
        p.notes.append(Note(1200,240,72));self.assertFalse(ScoreLayout(p).rhythm_adjustments[0])
        p.measures=[Measure(4,4)];self.assertTrue(ScoreLayout(p).rhythm_adjustments[0])
        p=song();p.measures=[Measure(8,8)];self.assertFalse(ScoreLayout(p).rhythm_adjustments[0])
        layout=ScoreLayout(song());s=layout.systems[0];points,xs,*_=layout.bar_map(s,0,0,s.bar_widths[0])
        edges=[layout.interpolate(points,xs,t) for t in (0,960,1920,2880,3840)]
        for a,b in zip(edges,edges[1:]):self.assertAlmostEqual(b-a,s.bar_widths[0]/4)

    def test_separate_pair_in_each_beat_and_long_continuation(self):
        p=song((720,120,120)*4);layout=ScoreLayout(p);self.assertEqual(len(layout.rhythm_adjustments[0]),4)
        p=Project();p.chords=[];p.notes=[Note(3000,1560,60),Note(4560,120,62),Note(4680,120,64)]
        layout=ScoreLayout(p);f=layout.systems[0].fragments[1][0]
        self.assertEqual((f.start,f.duration,f.display_duration),(3840,720,480));self.assertTrue(f.continuation)

    def test_hits_and_playhead_retain_real_ticks(self):
        for style in ('spatial','compact','traditional'):
            p=song(style=style);canvas=ScoreCanvas(p);canvas.grid=60;canvas.resize(1000,1600);layout,_=render(p);canvas.layout=layout
            page,rect,bar,points,xs=layout.hit_times[0]
            for tick in (0,240,480,720,780,840,900,960):
                x=layout.interpolate(points,xs,tick);ox,oy=canvas.page_origin(page)
                self.assertEqual(canvas.timeline_at(QPointF(ox+(x+.001)*canvas.scale,oy+rect.center().y()*canvas.scale)),(0,tick))
                self.assertAlmostEqual(layout.time_position(tick)[1],x)
            canvas.deleteLater()

    def test_project_and_midi_bytes_unchanged_by_every_style(self):
        p=song();before=copy.deepcopy(p.to_dict())
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            a=Path(folder)/'before.mid';b=Path(folder)/'after.mid';export_midi(p,a)
            for style in ('spatial','compact','traditional'):
                q=Project.from_dict(before);q.notation['style']=style;state=copy.deepcopy(q.to_dict());render(q)
                self.assertEqual(q.to_dict(),state);export_midi(q,b);self.assertEqual(a.read_bytes(),b.read_bytes())
        self.assertEqual(p.to_dict(),before)

class CompactTraditionalTests(unittest.TestCase):
    def test_sparse_row_keeps_compact_height_and_short_barlines(self):
        p=song((960,960,960,960),'traditional');layout=ScoreLayout(p);s=layout.systems[0]
        self.assertEqual(s.left,MARGIN);self.assertAlmostEqual(sum(s.bar_widths),PAPER_W-2*MARGIN)
        self.assertLess(s.height,100)
        a,b=layout.barline_bounds(s);self.assertAlmostEqual(b-a,30*s.symbol_scale)
        p.notation['per_line']=4;other=ScoreLayout(p);self.assertEqual(other.systems[0].bar_widths,s.bar_widths)

    def test_short_barline_symbols_and_lyrics_clear_notes(self):
        p=song(style='traditional');p.notation.update(lyrics=True,circles=True)
        for n in p.notes:n.lyric='歌';n.pitch-=36
        p.notation['symbols']=[dict(kind='repeat_end',start=3840,end=3840,id='end')]
        layout,_=render(p);s=layout.systems[0]
        self.assertLess(s.top+s.grid_bottom,min(y for _,_,_,y in layout.lyric_positions))
        for f in s.fragments[0]:
            self.assertLess(s.top+s.note_baseline+layout.vertical_extents(f)[1]*s.symbol_scale,s.top+s.grid_bottom)

    def test_polyphonic_voice_spacing_retains_room(self):
        p=song(style='traditional');p.notes.extend([Note(0,960,84),Note(0,960,24)])
        layout=ScoreLayout(p);s=layout.systems[0];notes=s.fragments[0]
        for f in notes:
            for g in notes:
                if f.note==g.note or f.end<=g.start or g.end<=f.start:continue
                dy=abs(s.voices[f.note.id]-s.voices[g.note.id])*s.voice_gap
                self.assertGreaterEqual(dy,(layout.vertical_extents(f)[0]+layout.vertical_extents(g)[1])*s.symbol_scale)

    def test_compose_does_not_rebuild_repaint_or_seek_cached_score(self):
        from popscore.app import MainWindow
        with patch.object(MainWindow,'save_preferences'):
            w=MainWindow(song());w.timer.stop();w.autosave.stop();w.show();w.switch_workspace('score');APP.processEvents()
            canvas=w.score_view.canvas;layout=canvas.layout;count=canvas.cache_renders;w.switch_workspace('compose')
            with patch('popscore.scoreview.ScoreLayout',wraps=ScoreLayout) as build,patch.object(canvas,'update') as update,patch.object(w.score_view,'locate_bar') as locate:
                w.show_cursor(720);w.mutate('edit',lambda p:setattr(p.notes[0],'pitch',69));w.return_to_start();APP.processEvents()
                build.assert_not_called();update.assert_not_called();locate.assert_not_called()
                self.assertIs(layout,canvas.layout);self.assertEqual(count,canvas.cache_renders);self.assertTrue(canvas.suspended)
            w.switch_workspace('score');self.assertFalse(canvas.suspended);self.assertEqual(canvas.project.notes[0].pitch,69)
            w.dirty=False;w.close();w.deleteLater();APP.processEvents()

if __name__=='__main__':unittest.main()
