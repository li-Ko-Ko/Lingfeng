import copy
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import *
from lingfeng.audio.midi import export_midi
from lingfeng.engraving.notation import ScoreLayout, fragments_for_bar

APP=QApplication.instance() or QApplication([])
TEST_TEMP=Path(__file__).resolve().parent.parent/'tmp'/'test-runs'
TEST_TEMP.mkdir(parents=True,exist_ok=True)


def read_midi(path):
    """Independent SMF reader for export assertions (no dependency on exporter helpers)."""
    data=Path(path).read_bytes()
    assert data[:4]==b'MThd'
    fmt,count,ppq=struct.unpack('>HHH',data[8:14]);offset=14;tracks=[]
    for _ in range(count):
        assert data[offset:offset+4]==b'MTrk'
        length=int.from_bytes(data[offset+4:offset+8],'big');buf=data[offset+8:offset+8+length];offset+=8+length
        i=0;tick=0;events=[]
        def var():
            nonlocal i
            n=0
            while True:
                b=buf[i];i+=1;n=n*128+(b&127)
                if b<128:return n
        while i<len(buf):
            tick+=var();status=buf[i];i+=1
            if status==255:
                kind=buf[i];i+=1;size=var();payload=buf[i:i+size];i+=size;events.append((tick,status,kind,payload))
            else:
                size=1 if status>>4 in (12,13) else 2
                payload=buf[i:i+size];i+=size;events.append((tick,status,payload))
        tracks.append(events)
    assert offset==len(data)
    return fmt,ppq,tracks


class MusicTests(unittest.TestCase):
    def test_parallel_major_degrees(self):
        self.assertEqual([degree_text(48+x,48,True,False) for x in MODES['Aeolian']],['1','2','b3','4','5','b6','b7'])
        self.assertEqual([degree_text(48+x,48,False,False) for x in MODES['Aeolian']],['1','2','#2','4','5','#5','#6'])
        self.assertEqual(Chord(0,960,48,'').roman(48),'I')
        self.assertEqual(Chord(0,960,48,'m').roman(48),'i')

    def test_four_categories(self):
        p=Project();p.chords=[Chord(0,3840,50,'7')]
        self.assertEqual([p.category(n,0) for n in [48,52,54,56]],['both','scale','chord','other'])

    def test_context_groups_do_not_transpose(self):
        p=demo_project();before=[n.pitch for n in p.notes];p.set_context([[960,1920],[3840,4800]],tonic=48,mode='Aeolian')
        self.assertEqual([n.pitch for n in p.notes],before)
        self.assertEqual(p.context_at(960).mode,'Aeolian');self.assertEqual(p.context_at(1920).mode,'Ionian')
        p.validate()

    def test_spelling_only_changes_display(self):
        p=Project();n=Note(0,960,51);p.add_note(n);before=p.to_dict();n.flat=True
        self.assertEqual(n.pitch,51);self.assertEqual(n.duration,960)
        self.assertEqual(degree_text(n.pitch,48,n.flat),'♭3')

    def test_compact_each_system_is_independent(self):
        p=Project();p.notation.update(style='compact',per_line=4)
        p.notes=[Note(0,960,48),Note(960,960,55),Note(4*3840,960,72),Note(4*3840+960,960,76)]
        layout=ScoreLayout(p)
        self.assertEqual(layout.systems[0].pitches,[48,55]);self.assertEqual(layout.systems[1].pitches,[72,76,79])
        p.set_context([[0,p.end]],low=-14,high=21)
        self.assertEqual([s.pitches for s in ScoreLayout(p).systems],[[48,55],[72,76,79]])

    def test_accidental_between_rows(self):
        p=Project();p.notation['style']='compact';p.notes=[Note(0,960,48),Note(960,960,49),Note(1920,960,50)]
        system=ScoreLayout(p).systems[0]
        self.assertLess(system.pitch_position(48),system.pitch_position(49));self.assertLess(system.pitch_position(49),system.pitch_position(50))

    def test_sustained_note_split_keeps_identity(self):
        p=Project();n=Note(2880,1920,60);p.add_note(n)
        first=[f for f in fragments_for_bar(p,0) if f.note];second=[f for f in fragments_for_bar(p,1) if f.note]
        self.assertTrue(first[0].continues);self.assertTrue(second[0].continuation)
        self.assertEqual(first[0].note.id,second[0].note.id)
        self.assertEqual(sum(f.duration for f in first+second),1920)

    def test_triplets_and_mixed_meter(self):
        p=Project();p.add_note(Note(0,320,60));p.add_note(Note(320,320,62));p.add_note(Note(640,320,64));p.add_note(Note(3840,960,65))
        p.change_meter(0,3,4);self.assertEqual(p.notes[-1].start,2880)
        self.assertEqual(p.contexts[-1].end,p.end);p.validate()

    def test_reject_overlaps_and_destructive_shortening(self):
        p=Project();p.add_note(Note(2880,960,60))
        with self.assertRaises(ValueError):p.add_note(Note(3000,240,60))
        with self.assertRaises(ValueError):p.change_meter(0,3,4)

    def test_save_load(self):
        p=demo_project();p.notes[0].flat=True;p.measures[3].break_after=True
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as folder:
            assert Path(folder).resolve().is_relative_to(TEST_TEMP.resolve())
            path=Path(folder)/'roundtrip.lfs';p.save(path);q=Project.load(path)
            self.assertEqual(p.to_dict(),q.to_dict())

    def test_midi_round_trip_and_tracks(self):
        p=demo_project()
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as folder:
            assert Path(folder).resolve().is_relative_to(TEST_TEMP.resolve())
            path=Path(folder)/'demo.mid';export_midi(p,path)
            fmt,ppq,tracks=read_midi(path)
            self.assertEqual((fmt,ppq,len(tracks)),(1,960,3))
            self.assertIn((0,0xC0,b'\x01'),tracks[1]);self.assertIn((0,0xC1,b'\x00'),tracks[2])
            actual=[(t,data[0],data[1]) for t,status,*tail in tracks[1] if status==0x90 for data in tail]
            self.assertEqual(actual,[(n.start,n.pitch,n.velocity) for n in p.notes])
            endings=[(t,tail[0][0]) for t,status,*tail in tracks[1] if status==0x80]
            self.assertEqual(endings,[(n.end,n.pitch) for n in p.notes])
            self.assertTrue(all(track[-1][0]==p.end for track in tracks))
            export_midi(p,path,'chords');self.assertEqual(len(read_midi(path)[2]),2)


if __name__=='__main__':unittest.main()
