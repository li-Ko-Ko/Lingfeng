"""Independent track selection and settings in MIDI, MP3 and DAW export."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tests.test_music import TEST_TEMP, read_midi
from PySide6.QtWidgets import QWidget
from lingfeng.audio.events import INSTRUMENT_CHANNEL
from lingfeng.audio.exporting import audio_notes
from lingfeng.audio.midi import export_daw_bundle, export_midi
from lingfeng.audio.soundbanks import DEFAULT_DEVICE, export_instruments
from lingfeng.music.model import Chord, Note, Project
from lingfeng.ui.export_dialog import ExportDialog


class ThreeTrackExportTests(unittest.TestCase):
    def setUp(self):
        self.project=Project(melody_names=['主唱','器乐 Solo'],notes=[Note(240,240,60,95,lyric='唱')],
                             instrument_notes=[Note(360,240,64,80,lyric='乐')],
                             chords=[Chord(480,480,notes=[Note(0,240,48,71)])])
        self.settings={'melody':(0,11,100,60),'instrument':(INSTRUMENT_CHANNEL,21,40,64),'chords':(1,31,80,48)}
        for role,(_,program,volume,_) in self.settings.items():
            self.project.audio[role]={'device':'default','program':program}
            self.project.volumes[role]=volume
        folder=tempfile.TemporaryDirectory(dir=TEST_TEMP);self.addCleanup(folder.cleanup)
        self.folder=Path(folder.name)

    def check_midi(self,data,roles,end):
        path=self.folder/'check.mid';path.write_bytes(data)
        fmt,_,tracks=read_midi(path)
        self.assertEqual(fmt,1);self.assertEqual(len(tracks),1+len(roles))
        self.assertTrue(all(track[-1][0]==end for track in tracks))
        names={'melody':'主唱','instrument':'器乐 Solo','chords':'Chords'}
        lyrics={'melody':'唱','instrument':'乐'}
        for role,track in zip(roles,tracks[1:]):
            channel,program,volume,pitch=self.settings[role]
            self.assertIn((0,255,3,names[role].encode()),track)
            self.assertIn((0,0xc0|channel,bytes([program])),track)
            self.assertIn((0,0xb0|channel,bytes([7,volume])),track)
            self.assertEqual([msg[2][0] for msg in track if msg[1]==0x90|channel],[pitch])
            if role in lyrics:self.assertIn(lyrics[role].encode(),[msg[3] for msg in track if msg[1:3]==(255,5)])

    def test_midi_all_tracks_and_single_selections(self):
        p=self.project;before=p.to_dict()
        self.check_midi(export_midi(p,None,'both',start=120,end=840),('melody','chords','instrument'),720)
        for role in self.settings:
            with self.subTest(role=role):self.check_midi(export_midi(p,None,role),(role,),p.end)
        self.assertEqual(p.to_dict(),before)

    def test_daw_archive_has_three_independent_stems_with_common_timeline(self):
        path=self.folder/'DAW.zip';p=self.project;export_daw_bundle(p,path)
        with zipfile.ZipFile(path) as bundle:
            for filename,role in [('01_Melody.mid','melody'),('02_Chords.mid','chords'),('03_Instrument.mid','instrument')]:
                self.check_midi(bundle.read(filename),(role,),p.end)
            timeline=json.loads(bundle.read('timeline.json'))
            self.assertEqual(timeline['volumes_cc7'],p.volumes)
            self.assertEqual(timeline['tracks'][-1],dict(role='instrument',name='器乐 Solo',channel=INSTRUMENT_CHANNEL+1))

    def test_audio_notes_and_synth_credits_use_only_selected_sound(self):
        p=self.project
        for role,(_,_,volume,pitch) in self.settings.items():
            notes=audio_notes(p,role,0,p.end)
            self.assertEqual(len(notes),1)
            self.assertEqual((notes[0][2],notes[0][4]),(pitch,role))
            velocity={'melody':95,'instrument':80,'chords':71}[role]
            self.assertAlmostEqual(notes[0][3],velocity*volume/127**2)
        p.audio['instrument']=dict(device=DEFAULT_DEVICE,program=0)
        self.assertEqual(len(export_instruments(p,'instrument',0,p.end)),1)
        self.assertEqual(export_instruments(p,'instrument',600,p.end),[])
        with self.assertRaises(ValueError):export_instruments(p,'both',0,p.end)

    def test_both_export_dialogs_offer_separate_named_tracks(self):
        owner=QWidget();self.addCleanup(owner.deleteLater);owner.project=self.project;owner.loop_range=None
        for fmt in ('midi','mp3'):
            dialog=ExportDialog(owner,fmt,'instrument');self.addCleanup(dialog.deleteLater)
            self.assertEqual(dialog.tracks.checks['instrument'].text(),'器乐 Solo')
            self.assertEqual(dialog.options()['which'],('instrument',))
            dialog.tracks.checks['chords'].setChecked(True)
            self.assertEqual(dialog.options()['which'],('instrument','chords'))


if __name__=='__main__':unittest.main()
