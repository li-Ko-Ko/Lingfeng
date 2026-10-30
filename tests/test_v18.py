"""Chord region overwrite, packed clipboard, isolated selection and editing keys."""
import copy,os,sys,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage,QPainter,QKeySequence
from PySide6.QtWidgets import QApplication,QLineEdit,QMessageBox
from PySide6.QtTest import QTest
from lingfeng.music.model import Project, Chord, Note, PPQ, PATTERNS, Measure
from lingfeng.music.chord_operations import blank_chord, pattern_template, ChordClipboard, split_chords, merge_chords, can_merge_chords, move_chords
from lingfeng.music.note_operations import repartition_chord
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.keybindings import normalized, validate, KeyBindingsDialog
from lingfeng.engraving.notation import ScoreLayout
from tests.test_v14 import Synth
from tests.music_reference import bar_events

APP=QApplication.instance() or QApplication([])

def events(notes):return sorted((n.start,n.duration,n.pitch,n.velocity) for n in notes)

class ChordOperationsTests(unittest.TestCase):
    def test_shrink_deletes_outside_without_neighbor_expansion(self):
        p=Project();p.chords=[Chord(0,3840,pattern='up'),Chord(3840,3840,55)]
        old=p.chords[0];expected=events(old.clip(480,2880).render_notes());neighbor=copy.deepcopy(p.chords[1])
        repartition_chord(p,old.id,480,2880)
        self.assertEqual(len(p.chords),2);self.assertEqual(events(p.chords[0].render_notes()),expected)
        self.assertEqual(p.chords[1],neighbor);self.assertIsNone(p.chord_at(100));self.assertIsNone(p.chord_at(3000))

    def test_custom_expansion_preserves_own_notes_and_overwrites_neighbor_only(self):
        p=Project();p.chords=[Chord(0,3840,notes=[Note(120,300,60,88)]),Chord(3840,3840,pattern='up')]
        own=events(p.chords[0].render_notes());remaining=events(p.chords[1].clip(4800,7680).render_notes())
        repartition_chord(p,p.chords[0].id,0,4800)
        self.assertEqual(events(p.chords[0].render_notes()),own);self.assertEqual(events(p.chords[1].render_notes()),remaining);p.validate()

    def test_generated_and_materialized_patterns_extend_identically(self):
        for code in PATTERNS:
            for materialized in (False,True):
                with self.subTest(pattern=code,materialized=materialized):
                    p=Project();c=Chord(960,3840,pattern=code,gate=.73,velocity=81);p.chords=[c,Chord(4800,3840,55)]
                    if materialized:c.materialize()
                    template=pattern_template(c);self.assertIsNotNone(template);self.assertEqual(template.pattern,code)
                    expected=bar_events(template,p,480,5760)
                    repartition_chord(p,c.id,480,5760)
                    self.assertEqual(events(p.chords[0].render_notes()),expected);self.assertEqual(p.chords[1].start,5760)

    def test_nonpattern_rhythm_and_velocity_edits_remain_custom(self):
        c=Chord(0,3840,pattern='up');c.materialize();c.notes[0].start+=20
        self.assertIsNone(pattern_template(c));c.notes[0].start-=20;c.notes[0].velocity+=1;self.assertIsNone(pattern_template(c))

    def test_insert_options_can_overwrite_middle_and_preserve_both_sides(self):
        for length,duration in [('beats:1',960),('beats:2',1920),('beats:3',2880),('bars:1',3840),('bars:2',7680),('bars:3',11520),('bars:4',15360)]:
            p=Project();old=Chord(0,p.end,pattern='eighths');p.chords=[old]
            blank=blank_chord(p,960,length);self.assertEqual(blank.duration,duration);p.put_chord(blank);p.validate()
            self.assertEqual(blank.notes,[]);self.assertEqual(events(p.chords[0].render_notes()),events(old.clip(0,960).render_notes()))
            self.assertEqual(events(p.chords[-1].render_notes()),events(old.clip(blank.end,old.end).render_notes()))
        p.chords=[Chord(2400,960)];self.assertEqual(blank_chord(p,960).end,2400)
        self.assertEqual(blank_chord(p,p.end-60,'bars:4').duration,60)

    def test_insert_meter_beat_and_bars_lengths(self):
        p=Project();p.measures[0]=Measure(6,8);p.measures[1]=Measure(3,4)
        self.assertEqual(blank_chord(p,240,'beats:3').duration,1440)
        self.assertEqual(blank_chord(p,240,'bars:2').duration,2640)

    def test_split_preserves_performed_notes_with_boundary_cuts(self):
        p=Project();c=Chord(0,2880,pattern='block');p.chords=[c];ids=split_chords(p,{c.id})
        self.assertEqual([x.duration for x in p.chords if x.id in ids],[1440,1440]);self.assertEqual(len(ids),2)
        for t in range(0,2880,40):self.assertEqual(sorted(n.pitch for n in c.render_notes() if n.start<=t<n.end),sorted(n.pitch for n in p.harmony_notes() if n.start<=t<n.end))
        p.chords=[Chord(0,120),Chord(120,80)];split_chords(p,{c.id for c in p.chords});self.assertEqual([c.duration for c in p.chords if c.start<200],[60,60,40,40])
        with self.assertRaises(ValueError):split_chords(p,{c.id for c in p.chords})

    def test_merge_requires_same_name_recognition_and_adjacency(self):
        p=Project();p.chords=[Chord(0,1920,pattern='up'),Chord(1920,1920,pattern='down')];before=events(p.harmony_notes())
        self.assertTrue(can_merge_chords(p.chords));merge_chords(p,{c.id for c in p.chords});self.assertEqual(events(p.harmony_notes()),before)
        for second in (Chord(1920,1920,55),Chord(2400,1920),Chord(1920,1920,recognized=False),Chord(1920,1920,bass=4)):
            self.assertEqual(can_merge_chords([Chord(0,1920),second]),second.start==1920)

    def test_copy_noncontiguous_packs_in_time_order_and_preserves_relative_notes(self):
        p=Project();a=Chord(960,960,pattern='up');b=Chord(5760,1440,55,notes=[Note(240,240,67)]);clip=ChordClipboard.capture([b,a])
        p.chords=[Chord(0,16000)];ids=clip.paste(p,2400);copied=[c for c in p.chords if c.id in ids]
        self.assertEqual([(c.start,c.duration) for c in copied],[(2400,960),(3360,1440)])
        self.assertEqual(copied[1].notes[0].start,240);self.assertNotEqual(copied[1].notes[0].id,b.notes[0].id)
        self.assertEqual(a.start,960);self.assertEqual(b.start,5760);p.validate()
        with self.assertRaises(ValueError):clip.paste(p,p.end-100)

    def test_moving_multiple_chords_keeps_selection_intact_and_crops_unselected(self):
        p=Project();p.chords=[Chord(0,960),Chord(960,960),Chord(1920,3840,55)];ids={c.id for c in p.chords[:2]}
        move_chords(p,ids,480);self.assertEqual([(c.start,c.end) for c in p.chords],[(480,1440),(1440,2400),(2400,5760)]);p.validate()
        move_chords(p,ids,-960)
        self.assertEqual([(c.start,c.end) for c in p.chords],[(0,480),(480,1440),(2400,5760)]);p.validate()

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.errors=[];self.hook=patch.object(sys,'excepthook',lambda typ,value,tb:self.errors.append(str(value)));self.hook.start()
        p=Project();p.notes=[Note(960,480,60)];p.chords=[Chord(0,3840),Chord(3840,3840),Chord(7680,3840,55)]
        self.w=MainWindow(p);self.w.change_language('zh',False);self.w.keybindings=normalized({});self.w.resize(1280,900);self.w.show();self.w.open_harmony();QTest.qWait(30)
        self.w.timer.stop();self.w.autosave.stop();self.w.transport.close();self.w.transport.synth=Synth()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.hook.stop();self.assertFalse(self.errors)
    def test_local_chord_selection_hover_and_mutations(self):
        w=self.w;r=w.harmony_window.roll;w.harmony_window.setFloating(True);QTest.qWait(30)
        w.chord_selection(set());w.chord_hover('');lane=r.lane;pos=QPoint(round(lane.x_at(1000)),25)
        QTest.mouseMove(lane,pos);QTest.mouseClick(lane,Qt.MouseButton.LeftButton,pos=pos)
        self.assertEqual(r.selected_chords,{w.project.chords[0].id});self.assertFalse(w.roll.selected_chords);self.assertEqual(w.roll.hovered_chord,'')
        w.chord_command('root:2',set(r.selected_chords),r);self.assertEqual(w.main_roll.project.chords[0].root%12,2)
        self.assertFalse(w.roll.selected_chords);self.assertEqual(w.roll.selected_chord,'')
        w.chord_selection({w.project.chords[1].id},w.roll);self.assertEqual(r.selected_chords,{w.project.chords[0].id})
    def test_docked_selection_remains_shared(self):
        w=self.w;cid=w.project.chords[1].id;w.harmony_window.roll.chordSelection.emit({cid});self.assertEqual(w.roll.selected_chords,{cid})
    def test_structure_lane_has_main_lane_geometry_and_resizes(self):
        w=self.w;r=w.harmony_window.roll;w.harmony_window.setFloating(True);QTest.qWait(30);lane=r.lane
        self.assertEqual(lane.height(),w.chord_lane.height());self.assertEqual(lane.y(),r.timeline_height)
        box,c=lane.boxes[0];a=QPoint(round(box.right()-2),round(box.center().y()));b=QPoint(round(lane.x_at(4800)),a.y())
        QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=a);QTest.qWait(300);QTest.mouseMove(lane,b);QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=b)
        self.assertEqual(w.project.chords[0].end,4800);self.assertEqual(w.project.chords[1].start,4800)
    def test_empty_hover_arrow_selection_cross_only(self):
        r=self.w.roll;r.center_pitch(72);pos=QPoint(round(r.x_at(2400)+20),round(r.y_at(72)+10));QTest.mouseMove(r.viewport(),pos)
        self.assertEqual(r.viewport().cursor().shape(),Qt.CursorShape.ArrowCursor)
        QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=pos);self.assertEqual(r.viewport().cursor().shape(),Qt.CursorShape.ArrowCursor)
        QTest.qWait(280);self.assertEqual(r.viewport().cursor().shape(),Qt.CursorShape.CrossCursor)
        QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=pos);self.assertEqual(r.viewport().cursor().shape(),Qt.CursorShape.ArrowCursor)
    def test_insert_and_paste_menus_use_anchor_not_moving_playhead(self):
        w=self.w;r=w.roll;r.anchor_tick=1920;r.cursor_tick=4800;r.play_tick=6000;w.note_command(r,'copy:direct')
        r.selected_ids={w.project.notes[0].id};w.note_command(r,'copy:direct')
        menu=r.note_menu(QPoint(round(r.x_at(7680)),r.ruler_height+20));next(a for a in menu.actions() if a.text()=='在定位线处粘贴音符').trigger()
        self.assertEqual(r.position_tick(),1920)
        menu=r.lane.context_menu(QPoint(round(r.x_at(5000)),25));sub=next(a.menu() for a in menu.actions() if a.text()=='在定位线处插入空白和弦')
        self.assertEqual(len(sub.actions()),8);sub.actions()[2].trigger();c=w.project.chord_at(1920);self.assertEqual((c.start,c.duration,c.notes),(1920,1920,[]))
    def test_wasd_and_tools_no_change_to_playhead(self):
        w=self.w;r=w.roll;r.selected_ids={w.project.notes[0].id};r.edit_target='notes';w.activateWindow();r.setFocus();APP.processEvents();head=w.playhead
        QTest.keyClick(r,Qt.Key.Key_W);self.assertEqual(w.project.notes[0].pitch,61)
        QTest.keyClick(r,Qt.Key.Key_S);self.assertEqual(w.project.notes[0].pitch,60)
        QTest.keyClick(r,Qt.Key.Key_D);self.assertEqual(w.project.notes[0].start,960+r.grid)
        QTest.keyClick(r,Qt.Key.Key_A);self.assertEqual(w.project.notes[0].start,960)
        QTest.keyClick(r,Qt.Key.Key_Q);self.assertEqual(r.tool,'draw');QTest.keyClick(r,Qt.Key.Key_Q);self.assertEqual(r.tool,'smart');self.assertEqual(w.playhead,head)
    def test_chord_diatonic_and_horizontal_keys_ctrl_clipboard_is_packed(self):
        w=self.w;w.visibility_actions['chords'].setChecked(True);r=w.roll;lane=w.chord_lane;w.chord_selection({w.project.chords[0].id,w.project.chords[2].id},r);r.edit_target='chords';w.activateWindow();lane.setFocus();APP.processEvents()
        before=events(w.project.harmony_notes());QTest.keyClick(lane,Qt.Key.Key_W);self.assertNotEqual(events(w.project.harmony_notes()),before);self.assertEqual([c.name for c in w.project.chords if c.id in r.selected_chords],['C#','G#'])
        QTest.keyClick(lane,Qt.Key.Key_D);self.assertEqual([c.start for c in w.project.chords if c.id in r.selected_chords],[r.grid,7680+r.grid])
        w.copy_selection();w.seek(16000);w.paste_selection();self.assertEqual([(c.start,c.end) for c in w.project.chords if c.start>=16000 and c.notes!=[]],[(16000,19840),(19840,23680)])
    def test_custom_bindings_text_entry_and_validation(self):
        w=self.w;r=w.roll;r.selected_ids={w.project.notes[0].id};w.keybindings['up']='I';w.activateWindow();r.setFocus();APP.processEvents()
        QTest.keyClick(r,Qt.Key.Key_W);self.assertEqual(w.project.notes[0].pitch,60);QTest.keyClick(r,Qt.Key.Key_I);self.assertEqual(w.project.notes[0].pitch,61)
        field=QLineEdit(w);field.show();field.setFocus();APP.processEvents();QTest.keyClicks(field,'wasdiqe');self.assertEqual(field.text(),'wasdiqe');self.assertEqual(w.project.notes[0].pitch,61)
        dialog=KeyBindingsDialog(w.keybindings,w);dialog.fields['up'].setKeySequence(QKeySequence('D'))
        with patch('lingfeng.ui.keybindings.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):dialog.accept()
        self.assertEqual(dialog.value()['right'],'');self.assertEqual(dialog.value()['up'],'D');dialog.deleteLater()
        with self.assertRaises(ValueError):validate(normalized({'up':'Ctrl+S'}))
        with self.assertRaises(ValueError):validate({'up':'W','down':'W'})

class ScoreHeaderTests(unittest.TestCase):
    def test_changed_key_and_meter_are_combined_in_reserved_header(self):
        p=Project();p.set_markers([3],51,'Phrygian',4,4);p.notes=[Note(p.starts[3]+i*320,320,75+i) for i in range(3)]
        for style in ('traditional','spatial','compact'):
            p.notation['style']=style;layout=ScoreLayout(p);self.assertEqual(layout.context_labels(3),[(11520,'1 = D#3 · Phrygian')])
            system=layout.systems[0];self.assertGreaterEqual(system.context_height,22)
            labels=[];original=layout.text
            def draw(painter,x,y,text,*args,**kw):
                if 'Phrygian' in text:labels.append((text,painter.transform().map(QPoint(round(x),round(y))).y()))
                return original(painter,x,y,text,*args,**kw)
            image=QImage(900,1273,QImage.Format.Format_RGB32);painter=QPainter(image)
            with patch.object(layout,'text',side_effect=draw):layout.draw(painter,0)
            painter.end();self.assertEqual(len(labels),1)
            top=min(rect.top() for pg,rect,nid in layout.hit_notes);self.assertLess(labels[0][1]+8,top)
        p.set_markers([3],51,'Phrygian',3,4);layout=ScoreLayout(p);self.assertEqual(len(layout.context_labels(3)),1);self.assertIn('3/4',layout.context_labels(3)[0][1])

if __name__=='__main__':unittest.main()
