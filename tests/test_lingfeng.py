import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy,json,hashlib,tempfile,unittest,zipfile
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtTest import QTest
from lingfeng.music.model import Project, Note, Chord, PPQ
from lingfeng.music.note_operations import NoteClipboard
from lingfeng.engraving.presentation import same_segment, compression_candidate, add_compression, active_compressions, visible_bars, forced_row_allowed, apply_forced_row, annotation_allowed, add_annotation
from lingfeng.engraving.notation import ScoreLayout, fragments_for_bar
from lingfeng.ui.score_view import ScoreView
from lingfeng.ui.piano_roll import PianoRoll
from lingfeng.audio.midi import export_midi
from lingfeng.platform.i18n import set_language
from lingfeng.ui.theme import set_roll_palettes, roll_color, apply_theme

APP=QApplication.instance() or QApplication([])
TEMP=Path('tmp/tests');TEMP.mkdir(parents=True,exist_ok=True)

def repeated():
    p=Project()
    for i in range(8):
        p.notes.extend([Note(i*3840+480,480,60+i%4,80,'词'),Note(i*3840+1440,960,67)])
        p.chords.append(Chord(i*3840,3840,48+i%4,pattern='quarters'))
    return p

def render(p):
    layout=ScoreLayout(p);image=QImage(900,1273,QImage.Format.Format_RGB32);paint=QPainter(image)
    layout.draw(paint,0);paint.end();return layout,image

class LingfengTests(unittest.TestCase):
    def setUp(self):set_language('zh')
    def test_schema5_and_legacy4_zip(self):
        p=repeated();add_compression(p,list(range(8)),'repeat');apply_forced_row(p,[0,1,2,3]);add_annotation(p,'double_bar',0,3840)
        with tempfile.TemporaryDirectory(dir=TEMP) as folder:
            path=Path(folder)/'project.lfs';p.save(path);self.assertEqual(Project.load(path).to_dict(),p.to_dict())
            with zipfile.ZipFile(path) as z:self.assertEqual(json.loads(z.read('manifest.json'))['format'],'org.lingfeng.leadsheet')
            data=p.to_dict();data['schema_version']=5;payload=json.dumps(data).encode();manifest={'format':'org.lingfeng.leadsheet','version':5,'sha256':hashlib.sha256(payload).hexdigest()}
            with zipfile.ZipFile(path,'w') as z:z.writestr('manifest.json',json.dumps(manifest));z.writestr('project.json',payload)
            self.assertEqual(Project.load(path).schema_version,6)
    def test_direct_copy_is_exact_and_chromatic_transforms_are_rejected(self):
        p=Project();p.notes=[Note(0,480,61),Note(480,480,64)]
        clip=NoteClipboard.capture(p.notes,p,'direct');p.set_context([[3840,7680]],tonic=53,mode='Aeolian')
        self.assertEqual([n.pitch for n in clip.paste(p,3840)],[61,64])
        for kind in ('retrograde','inversion','retrograde_inversion'):
            with self.assertRaisesRegex(ValueError,'调外音'):NoteClipboard.capture(p.notes,p,kind)
    def test_color_covers_chord_duration_in_both_rolls(self):
        p=Project();p.notes=[Note(480,480,61),Note(3700,300,64)]
        p.chords=[Chord(0,7680,notes=[Note(480,480,66)])]
        for tick in (0,480,4000,7679):self.assertEqual(p.category(66,tick),'chord')
        self.assertEqual(p.category(66,7680),'other')
        for tick in (0,2000,3839):self.assertEqual(p.category(61,tick,'harmony'),'chord')
        self.assertEqual(p.category(61,3840,'harmony'),'chord')
        self.assertEqual(p.category(61,7680,'harmony'),'other')
        self.assertEqual(p.category(64,5000,'harmony'),'both')
        p.chords=[Chord(0,240,48,pattern='up')]
        self.assertEqual(p.category(60,0),'both');self.assertEqual(p.category(64,0),'scale')
    def test_spatial_rests_include_leading_silence_and_are_centered(self):
        p=Project();p.notes=[Note(480,480,60),Note(1920,480,67)]
        for style in ('spatial','compact'):
            p.notation['style']=style;layout,_=render(p)
            first=[(t,y) for t,_,_,y in layout.rest_positions if t<3840]
            self.assertEqual([t for t,_ in first],[0,960,2400,2880])
            self.assertEqual(len({y for _,y in first}),1)
        p.notation['style']='traditional';layout,_=render(p);self.assertIn(0,[t for t,_,_,_ in layout.rest_positions])
    def test_polyphonic_rest_follows_latest_ending_note(self):
        p=Project();p.notes=[Note(0,1920,60),Note(0,480,72)]
        rests=[f for f in fragments_for_bar(p,0) if f.pitch is None]
        self.assertEqual([(f.start,f.rest_pitch) for f in rests],[(1920,60),(2880,60)])
    def test_forced_row_is_local_and_recomputes_compact_range(self):
        p=repeated();p.append_measures(4);p.notes.append(Note(7*3840,240,84));p.notation['style']='compact'
        old=ScoreLayout(p);self.assertTrue(forced_row_allowed(p,list(range(8)),old.systems));self.assertFalse(forced_row_allowed(p,[1,2],old.systems));self.assertFalse(forced_row_allowed(p,[0,2],old.systems))
        apply_forced_row(p,list(range(8)));new,_=render(p)
        self.assertEqual([s.bars for s in new.systems],[list(range(8)),list(range(8,12))])
        self.assertEqual(new.systems[0].layout_scale,1);self.assertEqual(new.systems[1].layout_scale,1)
        self.assertLess(min(new.systems[0].bar_scales.values()),1)
        self.assertEqual(new.systems[1].height,old.systems[2].height);self.assertGreaterEqual(max(new.systems[0].pitches),84)
        self.assertTrue(all(rect.right()<=849 for _,rect,_ in new.hit_bars))
        self.assertTrue(all(new.systems[0].top<=rect.top()<new.systems[0].top+new.systems[0].height for _,rect,b in new.hit_bars if b<8))
    def test_repeat_compression_preserves_midi_and_expands_after_edit(self):
        p=repeated();self.assertTrue(same_segment(p,0,4,4,8))
        with tempfile.TemporaryDirectory(dir=TEMP) as folder:
            before=Path(folder)/'before.mid';after=Path(folder)/'after.mid';export_midi(p,before)
            add_compression(p,list(range(8)),'repeat');p.validate();export_midi(p,after)
            self.assertEqual(before.read_bytes(),after.read_bytes());self.assertEqual(visible_bars(p),[0,1,2,3])
            layout,_=render(p);self.assertEqual([k for k,_,_ in layout.symbol_marks],['repeat_start','repeat_end'])
            p.notes[-1].pitch+=1;self.assertFalse(active_compressions(p));self.assertEqual(len(visible_bars(p)),8)
    def test_repeats_compare_velocity_key_and_crossing_sustains(self):
        for change in ('velocity','context','sustain','chord'):
            p=repeated()
            if change=='velocity':p.notes[8].velocity+=1
            elif change=='context':p.set_context([[4*3840,5*3840]],tonic=53,mode='Ionian')
            elif change=='chord':p.chords[4].root=55
            else:p.notes.append(Note(4*3840-120,240,80))
            self.assertIsNone(compression_candidate(p,list(range(8)),'repeat'),change)
        self.assertIsNone(compression_candidate(repeated(),[0,2,4,6],'repeat'))
    def test_dc_ds_nr_and_coda_have_valid_paired_marks(self):
        for kind in ('dc','ds','dc_nr','ds_nr'):
            p=repeated();add_compression(p,list(range(8)),kind);layout,_=render(p)
            marks=[k for k,_,_ in layout.symbol_marks];self.assertIn(kind,marks)
            if kind.startswith('ds'):self.assertIn('segno',marks)
        p=Project();p.notes=[Note(i*3840,960,n) for i,n in enumerate([60,62,60,65])]
        item=compression_candidate(p,[0,1,2,3],'coda');self.assertEqual((item['hidden_start'],item['hidden_end']),(2,3))
        add_compression(p,[0,1,2,3],'coda');layout,_=render(p)
        self.assertEqual([k for k,_,_ in layout.symbol_marks],['segno','to_coda','ds_coda','coda'])
    def test_symbols_validate_positions_and_do_not_change_midi(self):
        p=Project();p.notes=[Note(0,960,60),Note(3840,960,64)]
        self.assertFalse(annotation_allowed(p,'fine',0,960));self.assertFalse(annotation_allowed(p,'final_bar',0,3840));self.assertFalse(annotation_allowed(p,'rit',2000,2880))
        for kind in ('fine','fade','rit','adlib'):self.assertTrue(annotation_allowed(p,kind,3840,4800))
        self.assertTrue(annotation_allowed(p,'double_bar',0,3840));self.assertFalse(annotation_allowed(p,'segno',480,960))
        with tempfile.TemporaryDirectory(dir=TEMP) as folder:
            a=Path(folder)/'a.mid';b=Path(folder)/'b.mid';export_midi(p,a);add_annotation(p,'rit',3840,4800);export_midi(p,b);self.assertEqual(a.read_bytes(),b.read_bytes())
    def test_presentation_tracks_insertions_and_meter_changes(self):
        p=Project();p.notes=[Note(3840,960,60)];apply_forced_row(p,[0,1,2,3]);add_annotation(p,'rit',3840,4800)
        p.insert_measure(0);self.assertEqual(p.notation['forced_rows'],[[1,5]]);self.assertEqual(p.notation['symbols'][0]['start'],7680)
        p.change_meter(0,3,4);self.assertEqual(p.notation['symbols'][0]['start'],6720)
    def test_insert_after_repeat_preserves_it_and_barline_replaces_style(self):
        p=repeated();add_compression(p,list(range(8)),'repeat');p.insert_measure(8)
        self.assertEqual(visible_bars(p),[0,1,2,3,8])
        add_annotation(p,'double_bar',0,3840);add_annotation(p,'barline',0,3840)
        self.assertEqual([a['kind'] for a in p.notation['symbols']],['barline'])
    def test_custom_palette_is_per_theme_and_print_unaffected(self):
        set_roll_palettes({'light':{'background':{'both':'#123456'},'note':{'both':'#ffffff'}},'dark':{'background':{'both':'#654321'}}})
        self.assertEqual(roll_color('both',dark=False).name(),'#123456');self.assertEqual(roll_color('both',dark=True).name(),'#654321')
        _,image=render(Project());self.assertEqual(image.pixelColor(10,10).name(),'#ffffff');set_roll_palettes({})

class ScoreSelectionTests(unittest.TestCase):
    def setUp(self):
        set_language('zh');self.p=repeated();self.view=ScoreView(self.p);self.view.resize(1100,1000);self.view.show();QTest.qWait(30);self.canvas=self.view.canvas
    def tearDown(self):self.view.close()
    def point(self,bar):
        page,rect,_=next(item for item in self.canvas.layout.hit_bars if item[2]==bar);x,y=self.canvas.page_origin(page)
        return QPoint(round(x+rect.center().x()*self.canvas.scale),round(y+(rect.top()+12)*self.canvas.scale))
    def click(self,bar,modifier=Qt.KeyboardModifier.NoModifier):QTest.mouseClick(self.canvas,Qt.MouseButton.LeftButton,modifier,pos=self.point(bar));APP.processEvents()
    def test_control_shift_and_marquee_selection(self):
        self.click(0);self.click(2,Qt.KeyboardModifier.ControlModifier);self.assertEqual(self.canvas.selected_bars,{0,2})
        self.click(0);self.click(3,Qt.KeyboardModifier.ShiftModifier);self.assertEqual(self.canvas.selected_bars,{0,1,2,3})
        a=self.point(4);b=self.point(7);QTest.mousePress(self.canvas,Qt.MouseButton.LeftButton,pos=a);QTest.mouseMove(self.canvas,b);QTest.mouseRelease(self.canvas,Qt.MouseButton.LeftButton,pos=b)
        self.assertEqual(self.canvas.selected_bars,{4,5,6,7})
    def test_score_context_availability_and_beat_ranges(self):
        self.canvas.selected_bars=set(range(8));menu=self.canvas.context_menu(self.point(0))
        self.assertTrue(next(a for a in menu.actions() if a.text()=='强制合并为一行').isEnabled())
        self.assertTrue(menu.compression_menu.actions()[0].isEnabled());self.canvas.set_selection_unit('beat')
        self.click(0);self.assertEqual(len(self.canvas.selected_beats),1);a,b=next(iter(self.canvas.selected_beats));self.assertEqual(b-a,PPQ)
    def test_draw_single_delete_and_structure_frame_resize(self):
        r=PianoRoll(self.p,role='harmony');r.resize(1000,650);r.set_panel('chords',False);r.show();QTest.qWait(30);r.center_pitch(60)
        self.assertFalse(r.panels['velocity']);self.assertEqual(len(r.lane.boxes),3)
        moved=[];r.chordStructureChanged.connect(moved.append);rect,c=r.lane.boxes[0]
        a=QPoint(round(rect.right()-2),round(rect.center().y()));b=QPoint(round(r.x_at(4800)),a.y())
        QTest.mousePress(r.lane,Qt.MouseButton.LeftButton,pos=a);QTest.qWait(310);QTest.mouseMove(r.lane,b);QTest.mouseRelease(r.lane,Qt.MouseButton.LeftButton,pos=b)
        self.assertEqual(moved[0].end,4800);r.close()

if __name__=='__main__':unittest.main()
