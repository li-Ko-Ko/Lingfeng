import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from popscore.model import Project,Note,Chord,PATTERNS,PPQ,demo_project
from popscore.recognition import recognize
from popscore.midi import export_midi,export_daw_bundle,event_list
from tests.test_music import TEST_TEMP,read_midi


class HarmonyTests(unittest.TestCase):
    def test_patterns_are_anchored_to_free_beats_and_clipped(self):
        for pattern in PATTERNS:
            with self.subTest(pattern=pattern):
                c=Chord(3360,2640,48,'maj7',pattern=pattern,gate=.83)
                notes=c.render_notes()
                self.assertTrue(notes)
                self.assertTrue(all(c.start<=n.start<n.end<=c.end for n in notes))
                self.assertEqual(min(n.start for n in notes),c.start+(480 if pattern=='offbeat' else 0))
                self.assertEqual([(n.id,n.start,n.duration) for n in notes],[(n.id,n.start,n.duration) for n in c.render_notes()])
                moved=copy.deepcopy(c);moved.start+=240
                self.assertEqual([(n.start+240,n.duration,n.pitch) for n in notes],[(n.start,n.duration,n.pitch) for n in moved.render_notes()])

    def test_custom_notes_change_sound_and_recognize_inversion(self):
        p=Project();c=Chord(480,3360,notes=[]);p.chords=[c]
        for pitch in [52,55,60]:p.edit_harmony(Note(960,1440,pitch,velocity=80+pitch%10))
        self.assertEqual(c.name,'C/E');self.assertEqual(c.roman(48),'I/3');p.validate()
        n=p.harmony_notes()[0];n.duration=1920;p.edit_harmony(n)
        self.assertIn((n.end,0,1,n.pitch,0),event_list(p))
        p.edit_harmony(Note(1440,480,61));self.assertFalse(c.recognized);self.assertEqual(c.roman(48),'?')
        self.assertIn(1,c.pcs)

    def test_ambiguity_and_octave_duplicates(self):
        names=[c.name for c in recognize([48,60,64,67,69])]
        self.assertIn('C6',names);self.assertIn('Am7/C',names)
        self.assertEqual(recognize([48,60,64,67,69],preferred=(9,'m7'))[0].name,'Am7/C')
        self.assertEqual(recognize([60,61,65]),[])
        self.assertEqual(recognize([]),[])

    def test_overwrite_splits_preserve_original_performance_phase(self):
        p=Project();old=Chord(480,5280,48,pattern='up');p.chords=[old]
        original=old.render_notes();p.put_chord(Chord(2400,960,50,'m'));p.validate()
        self.assertEqual([(c.start,c.end) for c in p.chords],[(480,2400),(2400,3360),(3360,5760)])
        right=p.chords[-1].render_notes()
        expected=[(max(n.start,3360),n.end,n.pitch) for n in original if n.end>3360]
        self.assertEqual([(n.start,n.end,n.pitch) for n in right],expected)

    def test_manual_overlap_and_outside_rejected(self):
        p=Project();p.chords=[Chord(960,2880,notes=[])]
        p.edit_harmony(Note(960,960,60))
        with self.assertRaises(ValueError):p.edit_harmony(Note(1440,960,60))
        p.edit_harmony(Note(3360,960,64))
        with self.assertRaises(ValueError):p.edit_harmony(Note(p.end-120,960,67))
        p.edit_harmony(Note(960,960,64));p.validate()

    def test_meter_shortening_protects_custom_harmony(self):
        p=Project();p.chords=[Chord(0,3840,notes=[Note(2880,960,60)])]
        with self.assertRaises(ValueError):p.change_meter(0,3,4)
        p=Project();p.chords=[Chord(3840,3840,notes=[Note(480,960,60)])]
        p.change_meter(0,3,4);self.assertEqual(p.harmony_notes()[0].start,3360)

    def test_native_format_and_v2_migration_and_checksum(self):
        p=demo_project();p.volumes={'melody':51,'chords':0};p.chords[0].materialize()
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as folder:
            assert Path(folder).resolve().is_relative_to(TEST_TEMP.resolve())
            path=Path(folder)/'native.lfs';p.save(path)
            self.assertTrue(zipfile.is_zipfile(path));self.assertEqual(Project.load(path).to_dict(),p.to_dict())
            legacy=Project().to_dict();legacy['schema_version']=2;del legacy['volumes']
            path.write_text(json.dumps(legacy),encoding='utf-8')
            with self.assertRaises(ValueError):Project.load(path)
            p.save(path)
            with zipfile.ZipFile(path) as archive:manifest=archive.read('manifest.json')
            with zipfile.ZipFile(path,'w') as archive:
                archive.writestr('manifest.json',manifest);archive.writestr('project.json',b'{}')
            with self.assertRaisesRegex(ValueError,'校验'):Project.load(path)

    def test_midi_performed_harmony_volume_and_bundle_alignment(self):
        p=Project();p.chords=[Chord(3360,2640,48,'7',pattern='up')];p.volumes={'melody':44,'chords':73}
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as folder:
            assert Path(folder).resolve().is_relative_to(TEST_TEMP.resolve())
            path=Path(folder)/'test.mid';export_midi(p,path)
            fmt,ppq,tracks=read_midi(path)
            self.assertIn((0,0xB0,bytes([7,44])),tracks[1]);self.assertIn((0,0xB1,bytes([7,73])),tracks[2])
            ons=[(t,d[0],d[1]) for t,s,*rest in tracks[2] if s==0x91 for d in rest]
            self.assertEqual(ons,[(n.start,n.pitch,n.velocity) for n in p.harmony_notes()])
            bundle=Path(folder)/'DAW.zip';export_daw_bundle(p,bundle)
            with zipfile.ZipFile(bundle) as archive:
                self.assertEqual(len(archive.namelist()),5)
                path.write_bytes(archive.read('02_Chords.mid'))
                _,_,ch=read_midi(path)
                self.assertEqual(next(t for t,s,*rest in ch[1] if s==0x91),3360)
                self.assertTrue(all(t[-1][0]==p.end for t in ch))


if __name__=='__main__':unittest.main()
