"""Velocity editing, cross-region joins and compact, complete editor menus."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPoint, QEvent
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Project, Chord, Note
from lingfeng.audio.midi import event_list
from lingfeng.ui.main_window import MainWindow
from lingfeng.platform import chord_preferences

APP=QApplication.instance() or QApplication([])

def actions(menu):
    for action in menu.actions():
        yield action
        if action.menu():yield from actions(action.menu())

class EditorTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(dir='tmp');self.addCleanup(self.directory.cleanup)
        self.path=patch('lingfeng.ui.main_window.user_data_dir',return_value=Path(self.directory.name));self.path.start();self.addCleanup(self.path.stop)
        self.w=MainWindow(Project());self.w.timer.stop();self.w.autosave.stop()
        self.addCleanup(self.close_window)
        self.w.change_language('zh',False)
        chord_preferences.set_preferences(dict(default_velocities=dict(melody=49,harmony=83)))
        self.addCleanup(chord_preferences.load_preferences,{})
    def close_window(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_cross_chord_join_one_sustained_event_undo_save(self):
        p=Project();p.chords=[Chord(0,960,notes=[Note(0,960,60,83)]),Chord(960,960,notes=[Note(0,960,60,71)])]
        self.w.replace_project(p);r=self.w.harmony_window.roll;r.selected_ids={n.id for n in r.notes}
        before=copy.deepcopy(p.to_dict());menu=r.note_menu(QPoint(round(r.x_at(120)),r.ruler_height+10),preserve=True)
        self.addCleanup(menu.close)
        join=next(a for a in actions(menu) if a.text()=='合并相邻音符');self.assertTrue(join.isEnabled());join.trigger()
        performed=self.w.project.harmony_notes();self.assertEqual([(n.start,n.duration,n.pitch) for n in performed],[(0,1920,60)])
        self.assertEqual(len([e for e in event_list(self.w.project) if e[1]==1 and e[2]==1]),1)
        after=self.w.project.to_dict();self.w.undo();self.assertEqual(self.w.project.to_dict(),before)
        self.w.redo();self.assertEqual(self.w.project.to_dict(),after)
        file=Path(self.directory.name)/'joined.lfs';self.w.project.save(file)
        self.assertEqual(event_list(Project.load(file)),event_list(self.w.project))

    def test_roll_velocity_menu_defaults_and_batch_notes_for_both_roles(self):
        for role,default in [('melody',49),('harmony',83)]:
            p=Project();notes=[Note(0,240,60,11),Note(480,240,64,22)]
            if role=='melody':p.notes=notes
            else:p.chords=[Chord(0,1920,notes=notes)]
            self.w.replace_project(p);r=self.w.roll if role=='melody' else self.w.harmony_window.roll
            r.selected_ids={n.id for n in r.notes};before=copy.deepcopy(self.w.project.to_dict())
            menu=r.note_menu(QPoint(round(r.x_at(120)),r.ruler_height+10),preserve=True);self.addCleanup(menu.close)
            self.assertLessEqual(len([a for a in menu.actions() if not a.isSeparator()]),14)
            for text in ('复制所选音符','在此粘贴音符','在定位线处粘贴音符','合并相邻音符','二等分音符'):
                self.assertIn(text,[a.text().split('\t')[0] for a in menu.actions()])
            pitch_menu=next(a.menu() for a in menu.actions() if a.text()=='音高变换')
            self.assertEqual(len(pitch_menu.actions()),6)
            self.assertEqual(menu.velocity_menu.actions()[0].text(),f'使用默认力度（{default}）')
            with patch('lingfeng.ui.velocity_menu.QInputDialog.getInt',return_value=(101,True)) as prompt:
                menu.velocity_menu.custom_action.trigger();self.assertEqual(prompt.call_args.args[3],default)
            actual=self.w.project.notes if role=='melody' else self.w.project.harmony_notes()
            self.assertEqual([n.velocity for n in actual],[101,101])
            self.assertEqual([(n.start,n.duration,n.pitch) for n in actual],[(0,240,60),(480,240,64)])
            self.w.undo();self.assertEqual(self.w.project.to_dict(),before)

    def test_velocity_axis_numeric_input_and_cancel(self):
        p=Project();p.notes=[Note(0,240,60,13)];self.w.replace_project(p);r=self.w.roll
        point=QPoint(round(r.x_at(0))+4,20)
        def event():return QContextMenuEvent(QContextMenuEvent.Reason.Mouse,point,point)
        with patch('lingfeng.ui.velocity_menu.QInputDialog.getInt',return_value=(89,True)) as prompt:
            r.velocity_lane.contextMenuEvent(event());self.assertEqual(prompt.call_args.args[3],49)
        self.assertEqual(self.w.project.notes[0].velocity,89);before=self.w.project.to_dict()
        with patch('lingfeng.ui.velocity_menu.QInputDialog.getInt',return_value=(20,False)):
            r.velocity_lane.contextMenuEvent(event())
        self.assertEqual(self.w.project.to_dict(),before)
        p=Project();p.chords=[Chord(0,1920)];self.w.replace_project(p);r=self.w.roll;lane=r.lane
        with patch('lingfeng.ui.velocity_menu.QInputDialog.getInt',return_value=(94,True)) as prompt:
            lane.velocity_lane.contextMenuEvent(event());self.assertEqual(prompt.call_args.args[3],83)
        self.assertEqual({n.velocity for n in self.w.project.harmony_notes()},{94})

    def test_chord_menus_offer_one_common_batch_velocity(self):
        p=Project();p.chords=[Chord(0,1920),Chord(1920,1920,root=55)]
        self.w.replace_project(p);r=self.w.roll;r.selected_chords={c.id for c in self.w.project.chords}
        menu=r.lane.context_menu(QPoint(round(r.lane.x_at(120)),18),preserve=True);self.addCleanup(menu.close)
        self.assertLessEqual(len([a for a in menu.actions() if not a.isSeparator()]),24)
        for title in ('修改力度','和弦属性','设置和弦标记…','禁用和弦识别','和弦进行','插入','和弦轨力度窗格'):
            self.assertIn(title,[a.text() for a in menu.actions()])
        self.assertFalse(hasattr(menu,'bass_velocity_menu'))
        self.assertNotIn('修改低音力度',[a.text() for a in actions(menu)])
        before=event_list(self.w.project);menu.velocity_menu.default_action.trigger()
        for c in self.w.project.chords:
            if not c.render_notes():continue
            self.assertEqual({n.velocity for n in c.render_notes()},{83})
            self.assertEqual(c.velocity,83)
        self.assertEqual([(e[0],e[1],e[2],e[3]) for e in event_list(self.w.project)],[(e[0],e[1],e[2],e[3]) for e in before])
        self.w.undo();self.assertEqual(event_list(self.w.project),before)
        self.w.chord_command('recognition:1',{self.w.project.chords[0].id},r)
        r.selected_chords={c.id for c in self.w.project.chords}
        menu=r.lane.context_menu(QPoint(round(r.lane.x_at(120)),18),preserve=True);self.addCleanup(menu.close)
        self.assertTrue(menu.velocity_menu.isEnabled())
        self.assertNotIn('修改低音力度',[a.text() for a in actions(menu)])

if __name__=='__main__':unittest.main()
