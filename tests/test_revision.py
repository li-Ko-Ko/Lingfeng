import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy
import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QColor
from popscore.model import Project,Note,Chord,PPQ,spelling,BACKGROUND_COLORS,NOTE_COLORS
from popscore.notation import ScoreLayout,fragments_for_bar
from popscore.editor import PianoRoll
from popscore.controls import GridSelector
from popscore.midi import export_midi
from tests.test_music import read_midi,TEST_TEMP

APP=QApplication.instance() or QApplication([])


class RevisionTests(unittest.TestCase):
    def test_polyphony_and_rest_union(self):
        p=Project()
        for start,duration,pitch in [(0,3840,60),(240,240,64),(1920,480,67)]:p.add_note(Note(start,duration,pitch))
        p.validate();frags=fragments_for_bar(p,0)
        self.assertFalse(any(f.pitch is None for f in frags))
        self.assertEqual({f.note.id for f in frags},{n.id for n in p.notes})
        with self.assertRaises(ValueError):p.add_note(Note(960,240,60))

    def test_marker_inheritance_and_equal_boundaries(self):
        p=Project();p.set_marker(4,48,'Aeolian',3,4);p.set_marker(0,53,'Ionian',4,4)
        self.assertEqual([p.marker_value(i) for i in range(4)],[(4,4,53,'Ionian')]*4)
        self.assertEqual(p.marker_value(4),(3,4,48,'Aeolian'))
        self.assertEqual([i for i in range(8) if p.marker_visible(i)],[0,4])
        p.set_marker(2,53,'Ionian',4,4);self.assertFalse(p.marker_visible(2))
        p.set_marker(0,55,'Dorian',4,4)
        self.assertEqual(p.marker_value(2),(4,4,53,'Ionian'))

    def test_insert_splits_sustains_and_preserves_chord_phase(self):
        p=Project();p.notes=[Note(2880,1920,60),Note(7680,960,64)]
        p.chords=[Chord(480,7200,48,pattern='up')];p.groups={'verse':[[0,7680]]}
        before=copy.deepcopy(p.harmony_notes());p.insert_measure(1,3,4,53,'Dorian')
        self.assertEqual([(n.start,n.duration) for n in p.notes],[(2880,960),(6720,960),(10560,960)])
        self.assertEqual(p.groups['verse'],[[0,3840],[6720,10560]])
        self.assertEqual(p.marks,[0,1,2]);self.assertEqual(p.marker_value(1),(3,4,53,'Dorian'))
        self.assertEqual(p.marker_value(2),(4,4,48,'Ionian'))
        self.assertFalse(any(n.start<6720 and n.end>3840 for n in p.harmony_notes()))
        actual=[(n.start,n.end,n.pitch) for n in p.harmony_notes()]
        for n in before:
            expected=[]
            if n.start<3840:expected.append((n.start,min(n.end,3840),n.pitch))
            if n.end>3840:expected.append((max(n.start,3840)+2880,n.end+2880,n.pitch))
            for event in expected:self.assertIn(event,actual)
        p.set_marker(0,55,'Ionian',4,4)
        self.assertEqual(p.marker_value(1),(3,4,53,'Dorian'));p.validate()

    def test_insert_at_start_and_end_roundtrip(self):
        p=Project();p.add_note(Note(0,960,60));p.insert_measure(0,4,4,53,'Ionian')
        self.assertEqual(p.notes[0].start,3840);self.assertEqual(p.marks,[0,1])
        p.insert_measure(len(p.measures),6,8,55,'Mixolydian')
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as folder:
            path=Path(folder)/'markers.lfs';p.save(path);self.assertEqual(Project.load(path).to_dict(),p.to_dict())

    def test_beat_context_boundaries_become_bar_markers(self):
        p=Project();p.set_context([[3840,7680]],tonic=53)
        self.assertEqual(p.marks,[0,1,2]);p.set_marker(0,55,'Ionian',4,4)
        self.assertEqual(p.context_at(3840).tonic,53);self.assertEqual(p.context_at(7680).tonic,48)

    def test_dense_score_honors_bar_count_and_manual_break(self):
        p=Project();p.notes=[Note(t,240,60+(t//240)%8) for t in range(0,p.end,240)]
        for per_line,counts in [(2,[2,2,2,2]),(3,[3,3,2]),(4,[4,4]),(6,[6,2]),(8,[8])]:
            p.notation['per_line']=per_line;layout=ScoreLayout(p)
            self.assertEqual([len(s.bars) for s in layout.systems],counts)
            self.assertTrue(all(sum(s.bar_widths)<=796 for s in layout.systems))
        p.measures[2].break_after=True;self.assertEqual(ScoreLayout(p).systems[0].bars,[0,1,2])

    def test_system_boundaries_and_octave_dots(self):
        p=Project();p.notes=[Note(0,960,57),Note(3840,960,65),Note(4*3840,960,77)]
        for style in ['spatial','compact']:
            p.notation['style']=style;s1,s2=ScoreLayout(p).systems
            self.assertEqual((s1.pitches[0],s1.pitches[-1]),(55,67))
            self.assertEqual((s2.pitches[0],s2.pitches[-1]),(72,79))
            self.assertTrue(set(s1.boundaries)<=set(s1.pitches))
            self.assertEqual([spelling(pitch,s1.tonic)[0::2] for pitch in s1.boundaries],[(5,0),(1,1),(5,1)])

    def test_polyphonic_traditional_hit_regions_are_distinct(self):
        p=Project();p.notation['style']='traditional';p.notes=[Note(0,960,pitch) for pitch in (60,64,67)]
        layout=ScoreLayout(p);image=QImage(900,1273,QImage.Format.Format_ARGB32);painter=QPainter(image);layout.draw(painter,0);painter.end()
        self.assertEqual(len({rect.y() for page,rect,nid in layout.hit_notes}),3)

    def test_compact_roll_maps_only_used_pitches_and_panels(self):
        p=Project();p.notes=[Note(0,960,48),Note(0,960,76)]
        r=PianoRoll(p);r.resize(1000,600);r.show();APP.processEvents();r.set_compact(True)
        self.assertEqual(r.pitches,[76,48]);r.set_row_height(32)
        for pitch in r.pitches:self.assertEqual(r.pitch_at(r.y_at(pitch)+16),pitch)
        before=r.viewport().height()
        for key in ('velocity','chords','navigator'):r.set_panel(key,False)
        APP.processEvents();self.assertGreater(r.viewport().height(),before+100)
        r.set_panel('ruler',False);self.assertEqual(r.ruler_height,52)
        r.set_compact(False);self.assertEqual((len(r.pitches),r.pitches[-1],r.pitches[0]),(88,21,108));r.close()

    def test_triplet_grid_and_selection(self):
        g=GridSelector();g.setCurrentIndex(g.findData(480));g.set_triplet(True);self.assertEqual(g.currentData(),320)
        r=PianoRoll(Project());r.grid=g.currentData();self.assertEqual(r.bucket(501),[320,640])
        self.assertEqual(r.snapped(620),640);g.set_triplet(False);self.assertEqual(g.currentData(),480);r.close()

    def test_sound_programs_are_saved_and_exported(self):
        p=Project();p.audio={'melody':dict(device='default',program=16),'chords':dict(device='default',program=11)}
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as folder:
            path=Path(folder)/'voices.mid';export_midi(p,path);tracks=read_midi(path)[2]
            self.assertIn((0,0xC0,bytes([16])),tracks[1]);self.assertIn((0,0xC1,bytes([11])),tracks[2])
            path=Path(folder)/'voices.lfs';p.save(path);self.assertEqual(Project.load(path).audio,p.audio)

    def test_palette_order_is_opposite_for_background_and_notes(self):
        def luminance(hex):
            c=QColor(hex);values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in (c.redF(),c.greenF(),c.blueF())]
            return sum(a*b for a,b in zip(values,(.2126,.7152,.0722)))
        keys=['both','scale','chord','other'];bg=[luminance(BACKGROUND_COLORS[k]) for k in keys]
        contrast=[(luminance(BACKGROUND_COLORS[k])+.05)/(luminance(NOTE_COLORS[k])+.05) for k in keys]
        self.assertEqual(bg,sorted(bg));self.assertEqual(contrast,sorted(contrast))


if __name__=='__main__':unittest.main()
