import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import ast,copy,json,tempfile,unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtTest import QTest
from popscore.model import Project,Note,Chord,MODES,PPQ
from popscore.operations import NoteClipboard,shift_in_scale,can_join,join_notes,can_split,split_notes,resize_chord
from popscore.notation import ScoreLayout,export_pdf
from popscore.editor import PianoRoll
from popscore.i18n import EN,set_language

APP=QApplication.instance() or QApplication([])


class SelectionTests(unittest.TestCase):
    def setUp(self):
        set_language('zh');self.p=Project();self.notes=[Note(i*480,480,pitch,80+i,str(i)) for i,pitch in enumerate([48,50,53,52])]
        self.p.notes=copy.deepcopy(self.notes)
    def test_four_copy_transforms(self):
        expected={'direct':[48,50,53,52],'retrograde':[52,53,50,48],'inversion':[53,52,48,50],'retrograde_inversion':[50,48,52,53]}
        for mode,pitches in expected.items():
            copied=NoteClipboard.capture(self.notes,self.p,mode).paste(self.p,3840)
            self.assertEqual([n.pitch for n in copied],pitches)
            self.assertEqual([n.start for n in copied],[3840,4320,4800,5280])
            self.assertTrue({n.id for n in copied}.isdisjoint(n.id for n in self.notes))
        self.assertEqual(self.p.notes,self.notes)
    def test_retrograde_preserves_gaps_durations_and_polyphony(self):
        notes=[Note(960,240,48),Note(1200,720,50),Note(1200,240,55),Note(2400,480,52)]
        c=NoteClipboard.capture(notes,self.p,'retrograde');result=c.paste(self.p,3840)
        self.assertEqual([(n.start-3840,n.duration,n.pitch) for n in result],[(0,480,52),(960,720,50),(1440,240,55),(1680,240,48)])
    def test_paste_maps_every_target_context_and_all_modes(self):
        c=NoteClipboard.capture(self.p.notes,self.p,'retrograde')
        for mode in MODES:
            self.p.set_context([[3840,4320]],tonic=53,mode=mode)
            self.p.set_context([[4320,7680]],tonic=55,mode=mode)
            result=c.paste(self.p,3840)
            self.assertEqual(result[0].pitch,53+MODES[mode][2])
            for n in result:
                ctx=self.p.context_at(n.start);self.assertIn((n.pitch-ctx.tonic)%12,MODES[ctx.mode])
    def test_step_shift_and_chromatic_resolution(self):
        self.assertEqual([n.pitch for n in shift_in_scale(self.notes,self.p,1)],[50,52,55,53])
        self.assertEqual(shift_in_scale([Note(0,480,49)],self.p,-1)[0].pitch,48)
        self.assertEqual(shift_in_scale([Note(0,480,49)],self.p,1)[0].pitch,50)
        with self.assertRaises(ValueError):shift_in_scale([Note(0,480,108)],self.p,1)
    def test_join_requires_contiguous_rows_and_split_halves_independently_of_grid(self):
        notes=[Note(0,480,60,85,'你'),Note(480,480,60,95,'好'),Note(0,960,64)]
        self.assertTrue(can_join(notes));joined=join_notes(notes)
        self.assertEqual([(n.pitch,n.duration,n.lyric) for n in joined],[(60,960,'你好'),(64,960,'')])
        notes[1].start+=240;self.assertFalse(can_join(notes))
        self.assertTrue(can_split(joined,240));self.assertEqual(len(split_notes(joined,240)),4)
        self.assertEqual([n.lyric for n in split_notes(joined,240)][:4],['你好','','',''])
        self.assertTrue(can_split([Note(80,960,60)],240));self.assertTrue(can_split([Note(0,240,60),Note(480,960,64)],240))
    def test_resize_union_is_transitive_and_keeps_edited_identity(self):
        self.p.notes=[Note(0,480,60,lyric='你'),Note(480,480,60,lyric='好'),Note(960,480,60,lyric='呀'),Note(0,960,64)]
        n=copy.deepcopy(self.p.notes[0]);n.duration=1080;self.p.add_note(n,merge=True);self.p.validate()
        self.assertEqual([(v.start,v.duration,v.pitch) for v in self.p.notes],[(0,1440,60),(0,960,64)])
        self.assertEqual(self.p.notes[0].id,n.id)
        self.assertEqual(self.p.notes[0].lyric,'你好呀')
    def test_harmony_resize_union(self):
        c=Chord(0,3840,48,notes=[Note(0,480,60),Note(480,480,60)]);self.p.chords=[c]
        n=c.render_notes()[0];n.duration=720;self.p.edit_harmony(n,merge=True);self.p.validate()
        self.assertEqual([(n.start,n.duration) for n in c.notes],[(0,960)])
    def test_chord_left_and_right_resize_take_priority(self):
        left=Chord(0,960,48,pattern='eighths');middle=Chord(960,960,53);right=Chord(1920,1920,55,pattern='eighths')
        self.p.chords=[left,middle,right]
        self.p.put_chord(resize_chord(middle,480,2400));self.p.validate()
        self.assertEqual([(c.start,c.end) for c in self.p.chords],[(0,480),(480,2400),(2400,3840)])
        self.assertEqual(self.p.chords[1].id,middle.id)
    def test_custom_chord_left_resize_preserves_absolute_note_times(self):
        chord=Chord(960,1920,48,notes=[Note(0,960,60),Note(960,960,64)])
        extended=resize_chord(chord,480,2880,fill_pattern=False)
        self.assertEqual([(n.start,n.end) for n in extended.render_notes()],[(960,1920),(1920,2880)])
        trimmed=resize_chord(chord,1440,2400)
        self.assertEqual([(n.start,n.end) for n in trimmed.render_notes()],[(1440,1920),(1920,2400)])
    def test_harmony_color_follows_active_melody_pitch_classes(self):
        self.p.notes=[Note(0,480,60),Note(480,480,61)];self.p.chords=[Chord(0,3840,48)]
        self.assertEqual(self.p.category(48,0,'harmony'),'both')
        self.assertEqual(self.p.category(48,480,'harmony'),'both')
        self.assertEqual(self.p.category(49,480,'harmony'),'chord')
        self.assertEqual(self.p.category(49,960,'harmony'),'chord')
    def render(self,p,page=0):
        layout=ScoreLayout(p);image=QImage(900,1273,QImage.Format.Format_RGB32);paint=QPainter(image);layout.draw(paint,page);paint.end();return layout,image
    def test_cross_bar_tie_is_one_continuous_path(self):
        self.p.notes=[Note(11040,720,57)];self.p.notation['style']='traditional'
        layout,_=self.render(self.p);paths=[item for item in layout.tie_paths if item[0]==self.p.notes[0].id]
        self.assertEqual([kind for _,kind,_ in paths],['continuous'])
        a=paths[0][2].elementAt(0);b=paths[0][2].currentPosition();barline=next(rect.x() for page,rect,bar in layout.hit_bars if bar==3)
        self.assertLess(a.x,barline);self.assertGreater(b.x(),barline)
    def test_system_and_page_ties_have_paired_open_arcs(self):
        self.p.notes=[Note(15120,480,60)];self.p.notation['per_line']=4
        layout,_=self.render(self.p);self.assertEqual([kind for _,kind,_ in layout.tie_paths],['outgoing','incoming'])
        self.p.notation['per_line']=2;self.p.notation['row_gap']=32
        # Force a page boundary while preserving one sustained note across it.
        p=Project();p.notation.update(per_line=2,row_gap=32)
        p.notes=[Note(i*3840,240,21 if i%2==0 else 108) for i in range(len(p.measures))]
        layout=ScoreLayout(p);first=next(s for s in layout.systems if s.page==1);tick=p.starts[first.bars[0]]
        p.notes.append(Note(tick-120,240,60));layout,_=self.render(p,0)
        self.assertIn('outgoing',[kind for nid,kind,_ in layout.tie_paths if nid==p.notes[-1].id])
        layout,_=self.render(p,1);self.assertIn('incoming',[kind for nid,kind,_ in layout.tie_paths if nid==p.notes[-1].id])
    def test_english_catalog_covers_ui_sources_and_placeholders(self):
        import string
        formatter=string.Formatter()
        for path in Path('popscore').glob('*.py'):
            if path.name=='i18n.py':continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='tr' and node.args and isinstance(node.args[0],ast.Constant):
                    source=node.args[0].value
                    if isinstance(source,str) and any('\u4e00'<=c<='\u9fff' for c in source):
                        self.assertIn(source,EN)
                        self.assertEqual({f for _,f,_,_ in formatter.parse(source) if f is not None},{f for _,f,_,_ in formatter.parse(EN[source]) if f is not None})


class MarqueeTests(unittest.TestCase):
    def setUp(self):
        set_language('zh');self.p=Project();self.p.notes=[Note(960,480,60),Note(1440,480,62),Note(2880,480,65)]
        self.roll=PianoRoll(self.p);self.roll.resize(1000,650);self.roll.show();APP.processEvents();self.roll.center_pitch(62)
    def tearDown(self):self.roll.close()
    def point(self,tick,pitch):return QPoint(round(self.roll.x_at(tick)),round(self.roll.y_at(pitch)+10))
    def drag(self,a,b,modifier=Qt.KeyboardModifier.NoModifier):
        QTest.mousePress(self.roll.viewport(),Qt.MouseButton.LeftButton,modifier,pos=a);QTest.mouseMove(self.roll.viewport(),b);QTest.mouseRelease(self.roll.viewport(),Qt.MouseButton.LeftButton,modifier,pos=b);APP.processEvents()
    def test_marquee_and_ctrl_additive_selection(self):
        self.drag(self.point(720,63),self.point(2160,59));self.assertEqual(self.roll.selected_ids,{n.id for n in self.p.notes[:2]})
        self.drag(self.point(2640,66),self.point(3600,64),Qt.KeyboardModifier.ControlModifier);self.assertEqual(len(self.roll.selected_ids),3)
        QTest.keyClick(self.roll,Qt.Key.Key_Escape);self.assertFalse(self.roll.selected_ids)
    def test_group_move_and_cancelled_drawing(self):
        self.roll.selected_ids={n.id for n in self.p.notes[:2]};batches=[];self.roll.notesBatch.connect(lambda added,deleted:batches.append(added))
        a=self.point(1200,60);self.drag(a,QPoint(a.x()+78,a.y()-22));self.assertEqual([(n.start,n.pitch) for n in batches[0]],[(1920,61),(2400,63)])
        added=[];self.roll.noteAdded.connect(added.append);self.roll.tool='draw';a=self.point(4000,70)
        QTest.mousePress(self.roll.viewport(),Qt.MouseButton.LeftButton,pos=a);QTest.mouseMove(self.roll.viewport(),self.point(4800,70));QTest.keyClick(self.roll,Qt.Key.Key_Escape);QTest.mouseRelease(self.roll.viewport(),Qt.MouseButton.LeftButton,pos=a)
        self.assertFalse(added)
    def test_chord_edge_requires_hold_and_resizes_left(self):
        self.p.chords=[Chord(960,1920,48)];self.roll.set_project(self.p);APP.processEvents();lane=self.roll.lane
        changed=[];self.roll.chordMoved.connect(changed.append);a=QPoint(round(self.roll.x_at(960)+3),30);b=QPoint(round(self.roll.x_at(480)),30)
        QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=a);QTest.mouseMove(lane,b);QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=b);self.assertFalse(changed)
        QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=a);QTest.qWait(310);QTest.mouseMove(lane,b);QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=b)
        self.assertEqual((changed[0].start,changed[0].end),(480,2880))


if __name__=='__main__':unittest.main()
