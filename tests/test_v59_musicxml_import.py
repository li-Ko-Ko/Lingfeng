"""Partwise MusicXML timing, part mapping, harmony and compressed scores."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from lingfeng.music.musicxml_import import project_from_musicxml, read_musicxml


ROOT = Path(__file__).resolve().parents[1]


def score(parts, headers='', identification=''):
    return (f'<?xml version="1.0"?><score-partwise xmlns="urn:musicxml" version="4.0">'
            '<work><work-title>Imported score</work-title></work>'
            f'<identification><creator type="composer">Composer</creator>{identification}</identification>'
            f'<part-list>{headers}</part-list>{parts}</score-partwise>')


def note(pitch, length, extra='', prefix='', octave=4):
    return (f'<note>{prefix}<pitch><step>{pitch}</step><octave>{octave}</octave></pitch>'
            f'<duration>{length}</duration>{extra}</note>')


class MusicXmlImportTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory(dir=ROOT/'tmp')
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def read(self, content):
        path = self.folder/'fixture.musicxml'
        path.write_text(content, encoding='utf-8')
        return read_musicxml(path)

    def test_polyphony_mixed_meter_ties_lyrics_and_sections(self):
        bar1 = ('<attributes><divisions>3</divisions><key><fifths>1</fifths><mode>minor</mode></key>'
                '<time><beats>3</beats><beat-type>4</beat-type></time></attributes>'
                '<direction><direction-type><rehearsal>Interlude</rehearsal></direction-type><sound tempo="133"/></direction>'
                + note('D', 1, '<voice>1</voice><lyric number="1"><text>词</text></lyric>')
                + note('F', 1, '<voice>1</voice>', '<chord/>')
                + '<forward><duration>5</duration></forward>'
                + note('G', 3, '<tie type="start"/><voice>1</voice>')
                + '<backup><duration>9</duration></backup>'
                + note('C', 9, '<voice>2</voice>'))
        bar2 = ('<attributes><divisions>6</divisions><time><beats>2</beats><beat-type>4</beat-type></time></attributes>'
                + note('G', 6, '<tie type="stop"/><voice>1</voice>')
                + note('A', 6, '<voice>1</voice><lyric number="2"><text>verse two</text></lyric>')
                + '<barline location="right"><bar-style>light-heavy</bar-style></barline>')
        parts = f'<part id="A"><measure number="1">{bar1}</measure><measure number="2">{bar2}</measure></part>'
        data = self.read(score(parts, '<score-part id="A"><part-name>Voice</part-name></score-part>'))
        project = project_from_musicxml(data, data.default_mapping())
        self.assertEqual((project.title, project.author, project.bpm), ('Imported score', 'Composer', 133))
        self.assertEqual(project.starts, [0, 2880, 4800])
        self.assertEqual(project.measures[0].section, 'interlude')
        self.assertEqual((project.contexts[0].tonic, project.contexts[0].mode), (52, 'Aeolian'))
        self.assertEqual([(n.start,n.duration,n.pitch) for n in project.notes],
                         [(0,2880,60),(0,320,62),(0,320,65),(1920,1920,67),(3840,960,69)])
        self.assertEqual([(e['tick'], e['text'], e['verse']) for e in project.notation['lyric_events']],
                         [(0,'词',0),(3840,'verse two',1)])
        self.assertIn(dict(kind='final_bar', start=2880, end=4800), project.notation['symbols'])

    def test_lead_sheet_can_supply_both_vocal_and_harmony_symbols(self):
        part = ('<part id="Lead"><measure number="1"><attributes><divisions>2</divisions></attributes>'
                '<harmony><root><root-step>C</root-step></root><kind>major</kind>'
                '<degree><degree-value>9</degree-value><degree-alter>0</degree-alter><degree-type>add</degree-type></degree></harmony>'
                '<harmony><root><root-step>G</root-step></root><kind>dominant</kind>'
                '<bass><bass-step>B</bass-step></bass><offset>4</offset></harmony>'
                + note('E', 8) + '</measure></part>')
        data = self.read(score(part))
        self.assertEqual(data.default_mapping(), dict(melody='Lead', instrument=None, chords=None, symbols='Lead'))
        project = project_from_musicxml(data, data.default_mapping())
        self.assertEqual([chord.name for chord in project.chords], ['Cadd9', 'G7/B'])
        self.assertEqual([chord.duration for chord in project.chords], [1920, 1920])
        self.assertTrue(project.harmony_notes())

    def test_native_roles_metadata_and_performed_harmony(self):
        def header(ident, name, role):
            return (f'<score-part id="{ident}"><part-name>{name}</part-name><identification><miscellaneous>'
                    f'<miscellaneous-field name="lingfeng-role">{role}</miscellaneous-field>'
                    '</miscellaneous></identification></score-part>')
        headers = header('A','Custom a','melody')+header('B','Custom b','instrument')+header('C','Custom c','chords')
        lead = '<part id="A"><measure number="1">'+note('C',4)+'</measure></part>'
        ins = '<part id="B"><measure number="1">'+note('G',4,'<lyric><text>ins</text></lyric>')+'</measure></part>'
        chord = ('<part id="C"><measure number="1"><harmony><root><root-step>F</root-step></root><kind>minor</kind></harmony>'
                 +note('C',4,octave=3)+'</measure></part>')
        exact = ('<miscellaneous><miscellaneous-field name="lingfeng-key-contexts">[[0,65,"Lydian"],[1920,61,"Aeolian"]]'
                 '</miscellaneous-field></miscellaneous>')
        data = self.read(score(lead+ins+chord,headers,exact))
        project = project_from_musicxml(data,data.default_mapping())
        self.assertEqual(project.melody_names,['Custom a','Custom b'])
        self.assertEqual(project.instrument_notes[0].pitch,67)
        self.assertEqual(project.notation['instrument_lyric_events'][0]['text'],'ins')
        self.assertEqual([(c.start,c.tonic,c.mode) for c in project.contexts],[(0,65,'Lydian'),(1920,61,'Aeolian')])
        self.assertEqual([(n.start,n.duration,n.pitch) for n in project.harmony_notes()],[(0,3840,48)])
        self.assertTrue(project.chords[0].marked)
        self.assertEqual(project.chords[0].name,'Fm')

    def test_mxl_safe_read_and_short_pickup(self):
        part = ('<part id="P"><measure number="0" implicit="yes">'+note('A',1)+'</measure>'
                '<measure number="1">'+note('G',4)+'</measure></part>')
        path = self.folder/'fixture.mxl'
        container = ('<container><rootfiles><rootfile full-path="nested/score.xml" '
                     'media-type="application/vnd.recordare.musicxml+xml"/></rootfiles></container>')
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('META-INF/container.xml',container)
            archive.writestr('nested/score.xml',score(part))
        data = read_musicxml(path)
        project = project_from_musicxml(data,data.default_mapping())
        self.assertEqual(project.starts,[0,960,4800])
        self.assertEqual([n.start for n in project.notes],[0,960])
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('META-INF/container.xml',container.replace('nested/score.xml','../outside.xml'))
            archive.writestr('../outside.xml',score(part))
        with self.assertRaisesRegex(ValueError,'MXL'):
            read_musicxml(path)

    def test_rejects_bad_cursor_and_does_not_expand_entities(self):
        with self.assertRaisesRegex(ValueError,'MusicXML'):
            self.read(score('<part id="P"><measure><backup><duration>4</duration></backup></measure></part>'))
        with self.assertRaisesRegex(ValueError,'MusicXML'):
            self.read('<!DOCTYPE score-partwise [<!ENTITY x "expanded">]><score-partwise/>')

    def test_timewise_aligns_parts_when_a_measure_is_missing(self):
        bars = ('<measure number="1"><part id="V">'+note('C',4)+'</part></measure>'
                '<measure number="2"><part id="V">'+note('D',4)+'</part>'
                '<part id="I">'+note('F',4)+'</part></measure>')
        data = self.read(score(bars).replace('score-partwise','score-timewise'))
        project = project_from_musicxml(data,data.default_mapping())
        self.assertEqual(project.starts,[0,3840,7680])
        self.assertEqual([(n.start,n.pitch) for n in project.notes],[(0,60),(3840,62)])
        self.assertEqual([(n.start,n.pitch) for n in project.instrument_notes],[(3840,65)])

    def test_arbitrary_loop_export_import_pads_partial_bars_without_moving_local_notes(self):
        from lingfeng.music.model import Context, Measure, Note, Project
        from lingfeng.music.musicxml_export import export_musicxml

        source = Project(measures=[Measure(), Measure()], contexts=[Context(0,3840), Context(3840,7680,65,'Lydian')],
                         notes=[Note(100,900,60), Note(3500,600,65), Note(3900,400,63)])
        path = self.folder/'range.musicxml'
        export_musicxml(source, path, 'melody', 123, 4801)
        data = read_musicxml(path)
        project = project_from_musicxml(data,data.default_mapping())
        self.assertEqual(project.starts,[0,3840,5040])
        self.assertEqual([(n.start,n.duration,n.pitch) for n in project.notes],[(0,877,60),(3377,723,65),(3900,400,63)])
        self.assertEqual([(c.start,c.tonic%12,c.mode) for c in project.contexts],[(0,0,'Ionian'),(3840,5,'Lydian')])
