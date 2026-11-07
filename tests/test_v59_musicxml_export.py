"""Standard MusicXML score timing and MusicXML ZIP container export."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZIP_STORED, ZipFile

from lingfeng.engraving.lyrics import apply_range, edit_lyric_track, events, lyric_track
from lingfeng.music.model import Chord, Context, Measure, Note, Project
from lingfeng.music.musicxml_export import export_musicxml
from lingfeng.music.musicxml_import import project_from_musicxml, read_musicxml
from lingfeng.music.note_operations import window_notes


def song():
    p=Project(title='三轨 & MusicXML',author='Composer',bpm=112,
              measures=[Measure(4,4,'Verse'),Measure(3,4,'Chorus'),Measure(6,8)],
              melody_names=['人声 <Vocal>','独奏 & Keys'])
    p.contexts=[Context(0,3000,48,'Ionian'),Context(3000,p.end,67,'Mixolydian')]
    p.notes=[Note(180,480,60,95),Note(180,480,64,85),Note(420,121,67,77),Note(2880,1201,70,100,flat=True)]
    p.instrument_notes=[Note(240,640,71,99),Note(4080,960,73,74)]
    p.chords=[Chord(240,720,48,'7b9',bass=4,notes=[Note(0,480,48,72),Note(120,600,52,73)]),
              Chord(3500,1000,55,'m',notes=[Note(0,1000,55,78)])]
    p.audio['instrument']=dict(device='default',program=13)
    p.volumes['instrument']=45
    apply_range(p,'唱/-',0,1)
    edit_lyric_track(p,1,lambda melody:apply_range(melody,'器',0,1))
    return p


def performed(part):
    """Read standard cursor/tie tokens independently of the exporter."""
    ticks=0;active={};notes=[]
    for measure in part.findall('measure'):
        cursor=furthest=last_onset=ticks
        for item in measure:
            duration=int(item.findtext('duration','0'))
            if item.tag=='backup':cursor-=duration
            elif item.tag=='forward':cursor+=duration
            elif item.tag=='note':
                if item.find('chord') is None:
                    last_onset=cursor;cursor+=duration
                if (pitch:=item.find('pitch')) is not None:
                    key=int(pitch.findtext('octave'))*12+12+dict(C=0,D=2,E=4,F=5,G=7,A=9,B=11)[pitch.findtext('step')]
                    key+=int(pitch.findtext('alter','0'))
                    velocity=round(float(item.get('dynamics'))*90/100)
                    ties={node.get('type') for node in item.findall('tie')}
                    voice_key=item.findtext('voice'),key
                    start=active.pop(voice_key) if 'stop' in ties else last_onset
                    if 'start' in ties:active[voice_key]=start
                    else:notes.append((start,last_onset+duration-start,key,velocity))
            furthest=max(cursor,furthest)
        ticks=furthest
    assert not active
    return ticks,sorted(notes)


class MusicXMLExportTests(unittest.TestCase):
    def test_mxl_rap_keeps_speech_rhythm_lyrics_and_existing_melody(self):
        p=Project(notes=[Note(2880,480,60),Note(3600,120,62),Note(3720,120,64)],
                  instrument_notes=[Note(0,480,72),Note(480,480,74)])
        apply_range(p,r'唱 \x{Rap} Timed/4',0,2)
        edit_lyric_track(p,1,lambda track:apply_range(track,r'\x{Speak *}',0,1))
        before=p.to_dict()
        with TemporaryDirectory(dir='tmp') as folder:
            path=Path(folder)/'rap.mxl';export_musicxml(p,path)
            with ZipFile(path) as archive:xml=archive.read('score.musicxml')
            self.assertEqual(xml,export_musicxml(p))
            root=ET.fromstring(xml)
            speech=[note for note in root.iter('note') if note.find('unpitched') is not None]
            self.assertEqual([(note.findtext('duration'),note.findtext('notehead'),note.findtext('lyric/text'))
                              for note in speech],[('120','x','Timed'),('840','x',None)])
            self.assertEqual([note.find('tie').get('type') for note in speech],['start','stop'])
            data=read_musicxml(path)
            restored=project_from_musicxml(data,data.default_mapping())
        def pitch_events(notes):return [(note.start,note.duration,note.pitch) for note in notes]
        def lyric_events(project,track):
            return [(e['tick'],e['duration'],e['text'],e['kind'],bool(e.get('skip')))
                    for e in events(lyric_track(project,track))]
        self.assertEqual(pitch_events(restored.notes),pitch_events(p.notes))
        self.assertEqual(pitch_events(restored.instrument_notes),pitch_events(p.instrument_notes))
        for track in (0,1):self.assertEqual(lyric_events(restored,track),lyric_events(p,track))
        self.assertEqual(p.to_dict(),before)

    def test_all_parts_preserve_timing_symbols_and_attached_lyrics(self):
        p=song();before=p.to_dict();root=ET.fromstring(export_musicxml(p))
        self.assertEqual((root.tag,root.get('version')),('score-partwise','4.0'))
        self.assertEqual(root.findtext('movement-title'),p.title)
        self.assertEqual(root.findtext('identification/creator'),p.author)
        headers=root.findall('part-list/score-part')
        self.assertEqual([node.findtext('part-name') for node in headers],[*p.melody_names,'Chords'])
        self.assertEqual([node.findtext('midi-instrument/midi-channel') for node in headers],['1','7','2'])
        self.assertEqual(headers[1].findtext('midi-instrument/midi-program'),'14')
        self.assertAlmostEqual(float(headers[1].findtext('midi-instrument/volume'))*127/100,45)
        parts=root.findall('part')
        for part,source in zip(parts,(p.notes,p.instrument_notes,p.harmony_notes())):
            expected=sorted((note.start,note.duration,note.pitch,note.velocity) for note in source)
            self.assertEqual(performed(part),(p.end,expected))
        self.assertEqual([e.text for e in parts[0].iter('rehearsal')],['verse','chorus'])
        self.assertEqual([e.text for e in parts[0].iter('beats')],['4','3','6'])
        self.assertEqual([e.text for e in parts[0].iter('mode')],['major','mixolydian'])
        self.assertEqual(parts[0].find('measure/direction/sound').get('tempo'),'112')
        self.assertEqual(parts[0].findtext('.//lyric/text'),'唱')
        self.assertEqual(parts[0].find('.//lyric/extend').get('type'),'start')
        self.assertEqual(parts[1].findtext('.//lyric/text'),'器')
        harmonies=parts[2].findall('.//harmony')
        self.assertEqual([(e.findtext('kind'),e.findtext('offset')) for e in harmonies],
                         [('other','240'),('none','960'),('minor','3500'),('none','660')])
        self.assertEqual(harmonies[0].find('kind').get('text'),'7b9')
        self.assertEqual(harmonies[0].findtext('bass/bass-step'),'E')
        self.assertEqual(p.to_dict(),before)

    def test_partial_range_and_selected_part_keep_exact_boundaries(self):
        p=song();start,end=350,4350
        root=ET.fromstring(export_musicxml(p,which='chords',start=start,end=end))
        parts=root.findall('part');self.assertEqual([part.get('id') for part in parts],['P3'])
        expected=sorted((note.start,note.duration,note.pitch,note.velocity) for note in window_notes(p.harmony_notes(),start,end))
        self.assertEqual(performed(parts[0]),(end-start,expected))
        self.assertEqual([measure.get('implicit') for measure in parts[0].findall('measure')],['yes','yes'])
        self.assertEqual(parts[0].findtext('measure/harmony/kind'),'other')

    def test_mxl_container_points_at_valid_score_and_empty_parts_are_kept(self):
        p=Project()
        with TemporaryDirectory(dir='tmp') as folder:
            path=Path(folder)/'score.mxl';data=export_musicxml(p,path)
            self.assertEqual(path.read_bytes(),data)
            with ZipFile(path) as archive:
                entries=archive.infolist();self.assertEqual((entries[0].filename,entries[0].compress_type),('mimetype',ZIP_STORED))
                self.assertEqual(archive.read('mimetype'),b'application/vnd.recordare.musicxml')
                rootfile=ET.fromstring(archive.read('META-INF/container.xml')).find('rootfiles/rootfile')
                self.assertEqual(rootfile.get('media-type'),'application/vnd.recordare.musicxml+xml')
                xml=archive.read(rootfile.get('full-path'));self.assertEqual(xml,export_musicxml(p))
                self.assertEqual(len(ET.fromstring(xml).findall('part')),3)
            with self.assertRaises(ValueError):export_musicxml(p,path,start=p.end)
            self.assertEqual(path.read_bytes(),data)


if __name__=='__main__':unittest.main()
