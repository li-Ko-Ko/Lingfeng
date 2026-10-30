"""Consistent menus, explicit rhythm mode, element selection and audition."""
import os,sys,copy,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication,QMenu
from PySide6.QtTest import QTest
from lingfeng.music.model import Project, Chord, Note
from lingfeng.ui.main_window import MainWindow
from lingfeng.music.rhythm import analyze, label
from lingfeng.music.chord_operations import change_chords, move_chords, split_chords, merge_chords, ChordClipboard
from lingfeng.music.note_operations import repartition_chord
from lingfeng.audio.transport import Transport
from lingfeng.engraving.notation import ScoreLayout
from lingfeng.ui.keybindings import normalized
from tests.music_reference import bar_events

APP=QApplication.instance() or QApplication([])
sig=lambda ns:sorted((n.start,n.duration,n.pitch,n.velocity) for n in ns)
labels=lambda menu:[a.text() for a in menu.actions()]
find=lambda menu,text:next(a for a in menu.actions() if a.text()==text)

class MusicTests(unittest.TestCase):
    def test_custom_lock_roundtrip_move_resize_and_unlock_are_lossless(self):
        p=Project();p.put_chord(Chord(0,3840,pattern='up'));c=p.chords[0]
        for n in c.notes:n.velocity=111
        before=sig(c.render_notes());change_chords(p,{c.id},'custom:1')
        self.assertTrue(c.custom_rhythm);self.assertIsNone(analyze(c,p));self.assertEqual(label(c,p),'自定义（锁定）');self.assertEqual(sig(c.render_notes()),before)
        p=Project.from_dict(p.to_dict());move_chords(p,{c.id},240);c=p.chords[0]
        self.assertEqual(sig(c.render_notes()),[(a+240,d,k,v) for a,d,k,v in before])
        repartition_chord(p,c.id,0,4800);c=p.chords[0];self.assertEqual(sig(c.render_notes()),[(a+240,d,k,v) for a,d,k,v in before])
        change_chords(p,{c.id},'custom:0');self.assertFalse(c.custom_rhythm);self.assertEqual(sig(c.render_notes()),[(a+240,d,k,v) for a,d,k,v in before])
        # An exact legacy pattern recognizes again without changing a single event.
        c=Chord(0,3840,pattern='up');p.chords=[c];change_chords(p,{c.id},'custom:1');before=sig(c.render_notes())
        change_chords(p,{c.id},'custom:0');self.assertEqual(analyze(c,p).pattern,'up');self.assertEqual(sig(c.render_notes()),before)
        move_chords(p,{c.id},240);c=p.chords[0];self.assertEqual(sig(c.render_notes()),bar_events(c,p,c.start,c.end))
    def test_fixed_transposition_locks_actual_notes_but_root_command_does_not(self):
        for delta in (-12,-1,1,12):
            p=Project();c=Chord(0,3840,pattern='up');p.chords=[c];before=sig(c.render_notes())
            change_chords(p,{c.id},f'transpose:{delta}');self.assertTrue(c.custom_rhythm)
            self.assertEqual(sig(c.render_notes()),[(a,d,k+delta,v) for a,d,k,v in before]);self.assertIsNone(analyze(c,p))
        p.chords=[Chord(0,3840)];change_chords(p,{p.chords[0].id},'root_step:1');self.assertFalse(p.chords[0].custom_rhythm)
    def test_lock_survives_split_merge_clipboard_and_pattern_application_unlocks(self):
        p=Project();c=Chord(0,3840,pattern='up');p.chords=[c];change_chords(p,{c.id},'custom:1')
        ids=split_chords(p,{c.id});self.assertTrue(all(c.custom_rhythm for c in p.chords if c.notes!=[]));ids=merge_chords(p,ids)
        copied=ChordClipboard.capture([c for c in p.chords if c.id in ids]).paste(p,7680);self.assertTrue(all(c.custom_rhythm for c in p.chords if c.notes!=[]))
        change_chords(p,copied,'pattern:quarters');c=next(c for c in p.chords if c.id in copied)
        self.assertFalse(c.custom_rhythm);self.assertEqual(analyze(c,p).pattern,'quarters');p.validate()
    def test_multiple_actual_auditions_are_chronological_and_cancel_stale_events(self):
        class Synth:
            def __init__(self):self.events=[]
            def send(self,*args):self.events.append(args)
        t=Transport();t.synth=Synth();callbacks=[]
        a=Chord(0,960,notes=[Note(240,240,60,45)]);b=Chord(5000,960,notes=[Note(0,480,64,99)])
        with patch('lingfeng.audio.transport.QTimer.singleShot',side_effect=lambda ms,obj,fn:callbacks.append((ms,fn))):t.begin_chords_audition([b,a],120)
        self.assertEqual([ms for ms,fn in callbacks],[125,250,500,750]);self.assertEqual(t.synth.events,[])
        for ms,fn in callbacks:fn()
        self.assertEqual(t.synth.events,[(0x93,60,45),(0x83,60),(0x93,64,99),(0x83,64)])
        t.begin_audition([67]);before=list(t.synth.events)
        for ms,fn in callbacks:fn()
        self.assertEqual(t.synth.events,before);t.synth=None

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.errors=[];self.hook=patch.object(sys,'excepthook',lambda typ,value,tb:self.errors.append(str(value)));self.hook.start()
        self.warning=patch('lingfeng.ui.main_window.QMessageBox.warning',side_effect=AssertionError('Unexpected warning'));self.warning.start()
        p=Project();p.notes=[Note(0,480,60),Note(480,480,60)];p.chords=[Chord(0,3840,pattern='up'),Chord(3840,3840)]
        self.w=MainWindow(p);self.w.change_language('zh',False);self.w.keybindings=normalized({});self.w.show();self.w.resize(1250,900);self.w.timer.stop();self.w.autosave.stop()
        for button in self.w.mute_buttons.values():button.setChecked(True)
        QTest.qWait(30)
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.hook.stop();self.warning.stop();self.assertFalse(self.errors)
    def test_notes_and_chords_are_mutually_exclusive_even_across_floating_windows(self):
        w=self.w;r=w.roll;h=w.harmony_window.roll;w.open_harmony();w.harmony_window.setFloating(True)
        h.lane.selection_event({w.project.chords[0].id});r.center_pitch(60);r.tool='smart'
        point=QPoint(round(r.x_at(1920)),round(r.y_at(60)+10));QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=point)
        self.assertFalse(h.selected_chords);self.assertFalse(r.selected_chords);QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=point)
        r.selected_ids={n.id for n in w.project.notes};r.refresh();h.lane.selection_event({w.project.chords[0].id})
        self.assertFalse(r.selected_ids);self.assertFalse(r.selected_note)
        h.selected_ids={h.notes[0].id};h.refresh();h.noteSelected.emit(h.notes[0].id)
        self.assertFalse(h.selected_chords);self.assertFalse(h.selected_chord)
    def test_chord_menu_keeps_same_list_for_one_many_and_empty_with_right_selection(self):
        w=self.w;lane=w.chord_lane;r=lane.editor;a,b=w.project.chords
        point=QPoint(round(lane.x_at(960)),25);single=lane.context_menu(point);self.assertEqual(r.selected_chords,{a.id})
        self.assertEqual(lane.highlight_ids,{a.id});lane.hover_event('');self.assertIn(a.id,w.roll.chord_highlights)
        self.assertTrue(find(single,'编辑和弦…').isEnabled());self.assertFalse(find(single,'合并相邻和弦').isEnabled())
        lane.selection_event({a.id,b.id});multi=lane.context_menu(point)
        self.assertEqual(labels(single),labels(multi));self.assertFalse(find(multi,'编辑和弦…').isEnabled());self.assertFalse(multi.root_menu.isEnabled())
        self.assertTrue(find(multi,'合并相邻和弦').isEnabled());self.assertTrue(find(multi,'试听实际和弦').isEnabled())
        multi.custom_rhythm_action.trigger();self.assertTrue(all(c.custom_rhythm for c in w.project.chords if c.notes!=[]))
        w.project.chords=[c for c in w.project.chords if c.notes!=[]];w.refresh();lane.selection_event(set());blank=lane.context_menu(QPoint(round(lane.x_at(9000)),25));self.assertEqual(labels(single),labels(blank));self.assertFalse(find(blank,'复制所选和弦').isEnabled())
    def test_note_menu_same_list_properties_single_only_and_no_time_commands(self):
        r=self.w.roll;r.selected_ids={self.w.project.notes[0].id};r.refresh();one=QMenu();r.selection_menu(one,0)
        r.selected_ids={n.id for n in self.w.project.notes};r.refresh();many=QMenu();r.selection_menu(many,0)
        self.assertEqual(labels(one),labels(many));self.assertTrue(find(one,'音符属性…').isEnabled());self.assertFalse(find(many,'音符属性…').isEnabled())
        self.assertFalse(find(one,'合并相邻音符').isEnabled());self.assertTrue(find(many,'合并相邻音符').isEnabled())
        blank=r.note_menu(QPoint(round(r.x_at(960)),r.ruler_height+10));self.assertFalse(any('小节' in x for x in labels(blank)))
    def test_timeline_menu_has_only_bar_actions_and_disables_nonbroadcast_commands(self):
        r=self.w.roll;r.selected_ids={self.w.project.notes[0].id};r.refresh();point=QPoint(round(r.x_at(480)),10)
        r.selection=[[0,3840]];one=r.timeline_menu(point);r.selection=[[0,7680]];many=r.timeline_menu(point)
        self.assertEqual(labels(one),labels(many));self.assertFalse(any('音符' in x or '和弦' in x for x in labels(many)))
        self.assertTrue(find(many,'设置所选小节拍号与调性…').isEnabled())
        for text in ('将本小节调性应用至后续所有小节','将本小节拍号应用至后续所有小节','在此小节前插入…','在此小节后插入…'):
            self.assertTrue(find(one,text).isEnabled());self.assertFalse(find(many,text).isEnabled())
    def test_open_existing_harmony_locates_without_seeking_in_each_container(self):
        w=self.w;p=w.project;p.chords.append(Chord(24000,3840));w.refresh();cid=p.chords[-1].id;head=w.playhead
        for floating in (False,True):
            w.harmony_window.setFloating(floating);w.open_harmony(cid);QTest.qWait(30);r=w.harmony_window.roll
            self.assertTrue(w.harmony_window.isVisible());self.assertEqual(r.selected_chords,{cid});self.assertLessEqual(r.x_at(24000),r.viewport().width())
            self.assertGreaterEqual(r.x_at(24000),66);self.assertEqual(w.playhead,head)
        w.harmony_window.setFloating(False);w.switch_workspace('score');w.score_tabs.setCurrentIndex(2);w.set_score_panel_visible('harmony',False);w.open_harmony(cid);QTest.qWait(30)
        self.assertEqual(w.score_tabs.currentIndex(),1);self.assertTrue(w.score_panel_state['harmony']['visible']);self.assertEqual(w.playhead,head)
        before=w.score_tabs.currentIndex();w.open_harmony(cid);self.assertEqual(w.score_tabs.currentIndex(),before)
    def test_language_rebuild_with_inspected_chord_does_not_reset_note_selection_or_view(self):
        w=self.w;w.open_harmony(w.project.chords[0].id);QTest.qWait(10)
        w.harmony_window.setFloating(True);r=w.harmony_window.roll;r.horizontalScrollBar().setValue(500)
        w.roll.selected_ids={w.project.notes[0].id};w.roll.refresh();w.harmony_window.transport_controls.follow.setChecked(True)
        offset=r.horizontalScrollBar().value();w.change_language('en',False);QTest.qWait(40)
        self.assertEqual(w.harmony_window.roll.horizontalScrollBar().value(),offset);self.assertTrue(w.harmony_window.transport_controls.follow.isChecked());self.assertEqual(w.roll.selected_ids,{w.project.notes[0].id})
    def test_click_deselect_and_tab_preview_block_and_actual_menu_previews_multiple(self):
        w=self.w;heard=[];holds=[];actual=[];lane=w.chord_lane;point=QPoint(round(lane.x_at(960)),25)
        with patch.object(w.transport,'begin_audition',side_effect=lambda pitches,harmony=False:heard.append(list(pitches))),patch.object(w.transport,'extend_audition',side_effect=lambda h,sec:holds.append(sec)),patch.object(w.transport,'begin_chords_audition',side_effect=lambda cs,bpm:actual.append((cs,bpm))):
            w.activateWindow();QTest.mouseClick(lane,Qt.MouseButton.LeftButton,pos=point);QTest.mouseClick(lane,Qt.MouseButton.LeftButton,pos=point)
            self.assertEqual(heard,[w.project.chords[0].pitches]*2);self.assertAlmostEqual(holds[0],4*60/w.project.bpm)
            lane.selection_event({w.project.chords[0].id});lane.setFocus();APP.processEvents();QTest.keyClick(lane,Qt.Key.Key_Tab)
            self.assertEqual(heard[-1],w.project.chords[1].pitches)
            lane.selection_event({c.id for c in w.project.chords});menu=lane.context_menu(point);find(menu,'试听实际和弦').trigger()
            self.assertEqual([c.id for c in actual[0][0]],[c.id for c in w.project.chords])
    def test_score_bar_menu_keeps_fixed_commands_and_disables_single_target_operations(self):
        w=self.w;w.switch_workspace('score');QTest.qWait(30);canvas=w.score_view.canvas;pg,rect,bar=canvas.layout.hit_bars[0]
        x,y=canvas.page_origin(pg);point=QPointF(x+(rect.left()+2)*canvas.scale,y+(rect.bottom()-4)*canvas.scale)
        canvas.selected_bars={0};one=canvas.context_menu(point);canvas.selected_bars={0,1};many=canvas.context_menu(point)
        self.assertEqual(labels(one),labels(many));self.assertFalse(find(one,'强制合并为一行').isEnabled());self.assertTrue(find(many,'强制合并为一行').isEnabled())
        self.assertFalse(find(many,'在本小节后换行').isEnabled());self.assertFalse(find(many,'在和弦钢琴卷帘中编辑').isEnabled())

class ScoreTests(unittest.TestCase):
    def test_key_and_meter_are_above_chords_and_melody_in_all_styles(self):
        p=Project();p.notes=[Note(4000,480,84)];p.chords=[Chord(3840,2880,53)];p.set_markers([1],53,'Dorian',3,4)
        for style in ('traditional','spatial','compact'):
            p.notation['style']=style;layout=ScoreLayout(p);positions=[];original=layout.text
            def text(painter,x,y,value,*args,**kwargs):
                if 'Dorian' in value:positions.append(painter.transform().map(QPointF(x,y)).y())
                return original(painter,x,y,value,*args,**kwargs)
            image=QImage(900,1273,QImage.Format.Format_RGB32);painter=QPainter(image)
            with patch.object(layout,'text',side_effect=text):layout.draw(painter,0)
            painter.end();self.assertEqual(len(positions),1)
            self.assertLess(positions[0],min(rect.top() for pg,rect,cid in layout.hit_chords));self.assertLess(max(rect.bottom() for pg,rect,cid in layout.hit_chords),min(rect.top() for pg,rect,nid in layout.hit_notes))

if __name__=='__main__':unittest.main()
