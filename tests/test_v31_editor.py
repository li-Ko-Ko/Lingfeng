"""Selection clicks, release-only edits and two-dimensional drag feedback."""
import copy,os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from popscore.app import MainWindow
from popscore.model import Project,Chord,Note,PPQ

APP=QApplication.instance() or QApplication([])
LEFT=Qt.MouseButton.LeftButton
CTRL=Qt.KeyboardModifier.ControlModifier

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.save=patch.object(MainWindow,'save_preferences');self.save.start()
        p=Project();p.notes=[Note(480,960,60),Note(2400,960,64)]
        p.chords=[Chord(480,960),Chord(2400,960,50,'m')]
        self.w=MainWindow(p);self.w.change_language('zh',False);self.w.show();self.w.resize(1100,900)
        self.w.timer.stop();self.w.autosave.stop()
        for b in self.w.mute_buttons.values():b.setChecked(True)
        self.w.roll.tool='smart';self.w.roll.zoom=120;self.w.roll.update_ranges();self.w.roll.timeViewChanged.emit()
        self.w.roll.center_pitch(62);APP.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.save.stop()
    def chords(self,lane=None):
        lane=lane or self.w.chord_lane;lane.selection_event({c.id for c in self.w.project.chords});lane.update();APP.processEvents();return lane
    def notes(self,roll=None):
        r=roll or self.w.roll;self.w.select_element('notes',r);r.selected_ids={n.id for n in r.notes};r.selected_note='';r.refresh();APP.processEvents();return r
    def chord_point(self,lane,c=None):
        c=c or self.w.project.chords[0];return QPoint(round(lane.x_at(c.start+c.duration//2)),25)
    def note_point(self,r,n=None,edge=False):
        n=n or r.notes[0];return QPoint(round(r.x_at(n.end)-2 if edge else r.x_at(n.start+n.duration//2)),round(r.y_at(n.pitch)+r.row_height/2))

    def test_plain_chord_click_narrows_but_control_removes_only_clicked_member(self):
        lane=self.chords();c=self.w.project.chords[0];before=self.w.project.to_dict();pos=self.chord_point(lane,c)
        QTest.mouseClick(lane,LEFT,pos=pos)
        self.assertEqual(lane.editor.selected_chords,{c.id});self.assertEqual(self.w.project.to_dict(),before)
        self.chords();QTest.mousePress(lane,LEFT,CTRL,pos);self.assertIsNone(lane.drag)
        QTest.mouseMove(lane,pos+QPoint(60,0));QTest.mouseRelease(lane,LEFT,CTRL,pos+QPoint(60,0))
        self.assertEqual(lane.editor.selected_chords,{self.w.project.chords[1].id});self.assertEqual(self.w.project.to_dict(),before)

    def test_plain_note_click_narrows_and_control_toggles_without_edit(self):
        r=self.notes();n=r.notes[0];before=self.w.project.to_dict();pos=self.note_point(r,n)
        QTest.mouseClick(r.viewport(),LEFT,pos=pos);self.assertEqual(r.selected_ids,{n.id})
        self.notes();QTest.mouseClick(r.viewport(),LEFT,CTRL,pos);self.assertEqual(r.selected_ids,{self.w.project.notes[1].id})
        QTest.mouseClick(r.viewport(),LEFT,CTRL,pos);self.assertEqual(r.selected_ids,{n.id,self.w.project.notes[1].id})
        self.assertEqual(self.w.project.to_dict(),before)

    def test_drag_selected_chord_keeps_group_and_previews_all_without_editing(self):
        lane=self.chords();before=self.w.project.to_dict();old=copy.deepcopy(self.w.project.chords);pos=self.chord_point(lane)
        QTest.mousePress(lane,LEFT,pos=pos);QTest.mouseMove(lane,pos+QPoint(120,0));APP.processEvents()
        self.assertEqual(self.w.project.to_dict(),before);self.assertEqual(len(lane.drag_originals),2)
        self.assertEqual({c.start for c in lane.previews.values()},{c.start+PPQ for c in old})
        self.assertEqual(lane.editor.selected_chords,{c.id for c in old})
        QTest.mouseRelease(lane,LEFT,pos=pos+QPoint(120,0))
        self.assertEqual([c.start for c in self.w.project.chords if c.id in {x.id for x in old}],[c.start+PPQ for c in old]);self.assertFalse(lane.previews);self.assertFalse(lane.drag_originals)

    def test_drag_selected_note_keeps_group_and_escape_clears_preview(self):
        r=self.notes();before=self.w.project.to_dict();pos=self.note_point(r)
        QTest.mousePress(r.viewport(),LEFT,pos=pos);QTest.mouseMove(r.viewport(),pos+QPoint(120,0));APP.processEvents()
        self.assertEqual(self.w.project.to_dict(),before);self.assertEqual(len(r.previews),2)
        self.assertEqual(r.selected_ids,{n.id for n in r.notes})
        QTest.keyClick(r,Qt.Key.Key_Escape);QTest.mouseRelease(r.viewport(),LEFT,pos=pos+QPoint(120,0))
        self.assertEqual(self.w.project.to_dict(),before);self.assertFalse(r.previews)

    def test_note_resize_ignores_vertical_position_until_release(self):
        r=self.notes();n=r.notes[0];r.selected_ids={n.id};r.refresh();APP.processEvents();before=self.w.project.to_dict();pos=self.note_point(r,n,True)
        end=pos+QPoint(120,r.viewport().height())
        QTest.mousePress(r.viewport(),LEFT,pos=pos);QTest.mouseMove(r.viewport(),end)
        self.assertEqual(self.w.project.to_dict(),before);self.assertEqual(r.preview.pitch,n.pitch);self.assertEqual(r.preview.duration,1920)
        QTest.mouseRelease(r.viewport(),LEFT,pos=end)
        self.assertEqual((self.w.project.notes[0].pitch,self.w.project.notes[0].duration),(60,1920));self.assertFalse(r.edge_timer.isActive())

    def test_chord_resize_ignores_vertical_position_and_commits_once(self):
        lane=self.chords();c=self.w.project.chords[0];lane.selection_event({c.id});before=self.w.project.to_dict()
        pos=QPoint(round(lane.x_at(c.end)-3),25);end=pos+QPoint(60,150)
        QTest.mousePress(lane,LEFT,pos=pos);lane.begin_resize();QTest.mouseMove(lane,end)
        self.assertEqual(self.w.project.to_dict(),before);self.assertEqual((lane.preview.start,lane.preview.duration),(480,1440))
        QTest.mouseRelease(lane,LEFT,pos=end);self.assertEqual(next(x for x in self.w.project.chords if x.id==c.id).duration,1440)
        self.assertFalse(lane.previews);self.assertFalse(lane.edge_timer.isActive())

    def test_vertical_only_motion_is_not_resize_and_plain_click_still_narrows(self):
        r=self.notes();n=r.notes[0];pos=self.note_point(r,n,True);before=self.w.project.to_dict()
        QTest.mousePress(r.viewport(),LEFT,pos=pos);QTest.mouseMove(r.viewport(),pos+QPoint(0,100));QTest.mouseRelease(r.viewport(),LEFT,pos=pos+QPoint(0,100))
        self.assertEqual(self.w.project.to_dict(),before);self.assertEqual(r.selected_ids,{n.id})
        lane=self.chords();c=self.w.project.chords[0];pos=QPoint(round(lane.x_at(c.end)-3),25)
        QTest.mousePress(lane,LEFT,pos=pos);lane.begin_resize();QTest.mouseMove(lane,pos+QPoint(0,80));QTest.mouseRelease(lane,LEFT,pos=pos+QPoint(0,80))
        self.assertEqual(self.w.project.to_dict(),before);self.assertEqual(lane.editor.selected_chords,{c.id})

    def test_draw_click_deletes_clicked_note_only_without_audition(self):
        r=self.notes();r.tool='draw';n=r.notes[0];heard=[];r.audition.connect(heard.append)
        QTest.mouseClick(r.viewport(),LEFT,pos=self.note_point(r,n))
        self.assertEqual(len(self.w.project.notes),1);self.assertNotEqual(self.w.project.notes[0].id,n.id);self.assertFalse(heard)

    def test_floating_chord_roll_clicks_remain_local_and_joined_notes_select_together(self):
        w=self.w;w.project.chords=[Chord(0,3840,notes=[Note(0,3840,60,event_id="held-c"),Note(0,3840,64,event_id="held-e")]),Chord(3840,3840,notes=[Note(0,3840,60,event_id="held-c"),Note(0,3840,64,event_id="held-e")])]
        w.refresh();w.open_harmony();w.harmony_window.setFloating(True);APP.processEvents();r=w.harmony_window.roll;r.center_pitch(62)
        lane=self.chords(r.lane);main_ids=set(w.roll.selected_chords);QTest.mouseClick(lane,LEFT,pos=self.chord_point(lane))
        self.assertEqual(r.selected_chords,{w.project.chords[0].id});self.assertEqual(w.roll.selected_chords,main_ids)
        self.notes(r);n=next(n for n in r.notes if n.pitch==60);QTest.mouseClick(r.viewport(),LEFT,pos=self.note_point(r,n))
        self.assertEqual(r.selected_ids,{n.id for n in r.notes if n.pitch==60})

    def test_hiding_chord_lane_cancels_ghost_and_drag_without_mutating_music(self):
        lane=self.chords();before=self.w.project.to_dict();pos=self.chord_point(lane)
        QTest.mousePress(lane,LEFT,pos=pos);QTest.mouseMove(lane,pos+QPoint(100,0));lane.hide();APP.processEvents()
        self.assertIsNone(lane.drag);self.assertFalse(lane.previews);self.assertFalse(lane.drag_originals);self.assertEqual(self.w.project.to_dict(),before)
        QTest.mouseRelease(lane,LEFT,pos=pos+QPoint(100,0))

    def test_hiding_note_roll_cancels_ghost_and_pending_edit(self):
        r=self.notes();before=self.w.project.to_dict();pos=self.note_point(r)
        QTest.mousePress(r.viewport(),LEFT,pos=pos);QTest.mouseMove(r.viewport(),pos+QPoint(120,0));self.assertTrue(r.previews)
        r.hide();r.show();APP.processEvents()
        self.assertIsNone(r.drag);self.assertFalse(r.previews)
        QTest.mouseRelease(r.viewport(),LEFT,pos=pos+QPoint(120,0));self.assertEqual(self.w.project.to_dict(),before)

if __name__=='__main__':unittest.main()
