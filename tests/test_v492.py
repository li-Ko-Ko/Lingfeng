"""Valid example sections, bilingual lyric roundtrips and tighter safe spacing."""
import copy,json,os,tempfile,unittest,zipfile
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QFont,QFontMetricsF
from lingfeng.music.model import Project, Note, Measure, Context, Chord, SECTIONS, demo_project, spelling
from lingfeng.engraving.lyrics import tokenize, apply_range, range_source, events, matching_issues
from lingfeng.engraving.notation import ScoreLayout, PAPER_W, PAPER_H
from lingfeng.audio.midi import event_list, export_midi
from lingfeng.ui.main_window import MainWindow
from tests.test_music import read_midi
from tests.test_v54_layout import assert_numeric_cells

APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]

def song(pitch=60):
    p=Project();p.measures=[Measure() for _ in range(4)];p.contexts=[Context(0,p.end)]
    p.notes=[Note(i*480,480,pitch) for i in range(32)]
    p.notation.update(font_size=26,font_layout_version=45)
    return p

def draw(p):
    layout=ScoreLayout(p);im=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);im.fill(0xffffffff)
    painter=QPainter(im);layout.draw(painter,0);painter.end();return layout

class ExampleTests(unittest.TestCase):
    def test_every_shipped_project_loads_with_current_section_choices(self):
        from lingfeng.music.model import section_name
        for path in [*ROOT.glob('examples/*.lfs'),*ROOT.glob('examples/*.popscore')]:
            with zipfile.ZipFile(path) as z:data=json.loads(z.read('project.json'))
            self.assertTrue(all(not m.get('section') or section_name(m['section']) in SECTIONS for m in data['measures']),path.name)
        p=demo_project();self.assertEqual([(i,m.section) for i,m in enumerate(p.measures) if m.section],[(0,'verse'),(8,'chorus')])
        p=Project.load(ROOT/'examples/lingfeng-sections.lfs')
        self.assertEqual([(i,m.section) for i,m in enumerate(p.measures) if m.section],[(0,'intro'),(2,'verse'),(4,'verse'),(6,'outro')])

    def test_midi_demo_uses_the_same_section_names(self):
        from lingfeng.music.model import section_name
        _,_,tracks=read_midi(ROOT/'examples/demo.mid')
        self.assertEqual([(e[0],section_name(e[3].decode('utf-8'))) for e in tracks[0] if e[1:3]==(255,6)],[(0,'verse'),(30720,'chorus')])

class MixedLyricsTests(unittest.TestCase):
    def test_adjacent_languages_contractions_quotes_and_rap(self):
        text="我love你，I'm ready！ /x{‘中文’ rapper's flow}/s尾"
        tokens=tokenize(text)
        self.assertEqual([t.text for t in tokens],['我','love','你，',"I'm",'ready！','‘中','文’',"rapper's",'flow','','尾'])
        self.assertEqual([i for i,t in enumerate(tokens) if t.rap],[5,6,7,8])
        self.assertEqual([t.text for t in tokenize('“don’t stop”唱「Hello世界」')],['“don’t','stop”','唱','「Hello','世','界」'])

    def test_quotes_do_not_turn_skips_or_empty_slots_into_words(self):
        self.assertEqual([(t.text,t.skip) for t in tokenize('“我” /s， &。你')],[('“我”，。',False),('',True),('&',False),('你',False)])

    def test_mixed_text_autofill_save_and_midi_lyrics_roundtrip(self):
        for text in ("我love你，I'm ready一起sing",'/x{"Hello world"}我唱“don’t stop”',"‘我爱’rock’n’roll /x{中文rapper}/s"):
            p=song();midi=event_list(p);apply_range(p,text,0,2);before=events(p)
            loaded,equivalent=range_source(p,0,2);self.assertTrue(equivalent,(text,loaded));self.assertEqual(matching_issues(p),[])
            apply_range(p,loaded,0,2,replace=True)
            signature=lambda values:[(e['tick'],e['text'],e['kind']) for e in values]
            self.assertEqual(signature(events(p)),signature(before));self.assertEqual(event_list(p),midi)
            with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as folder:
                path=Path(folder)/'mixed.lfs';p.save(path);q=Project.load(path)
                self.assertEqual(events(q),events(p));out=Path(folder)/'mixed.mid';export_midi(q,out)
                _,_,tracks=read_midi(out)
                self.assertEqual([e[3].decode('utf-8') for e in tracks[1] if e[1:3]==(255,5)],
                                 [e['text'] for e in events(p) if e['text'] and e.get('kind') not in ('rap','rap_note')])

    def test_editor_confirms_and_reloads_mixed_language_text(self):
        w=MainWindow(song());w.save_preferences=lambda:None;w.timer.stop();w.autosave.stop();w.switch_workspace('score')
        try:
            panel=w.lyric_panel;panel.count.setValue(1);panel.text.setPlainText("我love你，I'm ready一起sing")
            self.assertTrue(panel.check());panel.commit();before=events(w.project)
            panel.start.setValue(2);panel.start.setValue(1)
            self.assertIn("I'm",panel.text.toPlainText());self.assertTrue(panel.check());panel.commit()
            self.assertEqual([(e['tick'],e['text']) for e in events(w.project)],[(e['tick'],e['text']) for e in before])
        finally:w.dirty=False;w.close();w.deleteLater();APP.processEvents()

class SpacingTests(unittest.TestCase):
    def test_font_caps_fit_density_widths_with_same_rows_and_pitch_spacing(self):
        for p in (demo_project(),song(61)):
            # Keep the pre-rap fixtures, but the 0.49.1 font thresholds assumed
            # glyph-weighted bar widths. The busiest beat now fixes each beat's
            # width, and the common font must fit that full-bar allocation.
            p.notation.pop('lyric_events',None);p.notation.pop('lyric_sections',None)
            music=event_list(p)
            for style in ('traditional','spatial','compact'):
                p.notation.update(style=style,font_size=26,per_line=4,row_gap=15)
                p.notation['font_size']=ScoreLayout(p).font_limit;layout=ScoreLayout(p)
                self.assertGreater(layout.font_limit,0);self.assertLessEqual(layout.font_limit,72)
                self.assertEqual(layout.font_size,p.notation['font_size'])
                for system in layout.systems:
                    weights=[]
                    attacks={n.start for n in p.notes+p.instrument_notes+p.harmony_notes()}
                    for bar in system.bars:
                        counts={};beat=3840//p.measures[bar].denominator
                        for tick in sorted(t for t in attacks if p.starts[bar]<=t<p.starts[bar+1]):
                            group=(tick-p.starts[bar])//beat;counts[group]=counts.get(group,0)+1
                        weights.append(max(1,max(counts.values(),default=0))*(p.starts[bar+1]-p.starts[bar])/beat)
                    if style!='traditional':
                        for width,weight in zip(system.bar_widths,weights):
                            self.assertAlmostEqual(width/weight,sum(system.bar_widths)/sum(weights))
                    else:
                        for beat in system.beat_cells:self.assertAlmostEqual(beat['right']-beat['left'],beat['count']*system.cell_width)
                    if style!='traditional':self.assertTrue(layout.ink_fits(layout.ink_descriptors(system),system.symbol_scale))
                if style=='traditional':assert_numeric_cells(self,layout)
                for page in range(layout.pages):
                    image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);painter=QPainter(image)
                    try:layout.draw(painter,page)
                    finally:painter.end()
                for _,size in layout.glyph_sizes:self.assertAlmostEqual(size,layout.font_size)
                self.assertEqual([s.bars for s in layout.systems],[list(range(i,min(i+4,len(p.measures)))) for i in range(0,len(p.measures),4)])
                self.assertTrue(all(s.row_gap==15 for s in layout.systems));self.assertEqual(event_list(p),music)

    def test_dense_mixed_lyrics_and_accidentals_stay_contained_at_new_cap(self):
        for style in ('traditional','spatial','compact'):
            p=song(61);p.notation['style']=style;apply_range(p,"我love你，I'm ready一起sing",0,1)
            p.notation['font_size']=ScoreLayout(p).font_limit;layout=draw(p);self.assertEqual(layout.font_size,p.notation['font_size'])
            if style=='traditional':
                assert_numeric_cells(self,layout)
                self.assertEqual(len({s.cell_width for s in layout.systems}),1)
                for system in layout.systems:self.assertAlmostEqual(system.beat_gap,2*system.bar_side_gap)
            else:
                for system in layout.systems:self.assertTrue(layout.ink_fits(layout.ink_descriptors(system),system.symbol_scale))
            boxes=[]
            for ident,_,x,y in layout.lyric_positions:
                event=next(e for e in events(p) if e['id']==ident);half=layout.text_width(event['text'],11)*layout.glyph_scale/2
                boxes.append((x-half,x+half))
            if style!='traditional':self.assertTrue(all(a[1]<=b[0] for a,b in zip(boxes,boxes[1:])))
            self.assertEqual(len(boxes),len([event for event in events(p) if event.get('text')]))

    def test_actual_glyphs_fit_the_tighter_envelopes_in_all_styles(self):
        for style in ('traditional','spatial','compact'):
            p=song();p.notation['style']=style;p.notes=[Note(i*480,360,60+i) for i in range(12)];p.chords=[Chord(0,p.end)]
            layout=ScoreLayout(p)
            for s in layout.systems:
                for fs in s.fragments.values():
                    for f in fs:
                        if f.pitch is None:continue
                        degree,accidental,_=spelling(f.pitch,p.context_at(f.start).tonic,f.note.flat,mode=p.context_at(f.start).mode)
                        font=QFont('Microsoft YaHei');font.setPixelSize(18);m=QFontMetricsF(font);r=m.tightBoundingRect(str(degree));half=m.horizontalAdvance(str(degree))/2
                        left,right=layout.glyph_extents(f);self.assertGreaterEqual(r.left()-half,-left);self.assertLessEqual(r.right()-half,right)
                        if accidental:
                            font.setPixelSize(13);r=QFontMetricsF(font).tightBoundingRect('♭' if accidental<0 else '♯')
                            self.assertGreaterEqual(-17+r.left(),-left);self.assertLessEqual(-17+r.right(),right)

if __name__=='__main__':unittest.main()
