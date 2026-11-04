"""Actual QAction dispatch for disabling recognition and removing manual markers."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from lingfeng.audio.midi import event_list
from lingfeng.music.model import Chord, Note, Project
from lingfeng.music.recognition import set_marker
from lingfeng.platform import chord_preferences
from lingfeng.platform import context_menu_preferences
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.piano_roll import PianoRoll

APP=QApplication.instance() or QApplication([])


def performed(chord):
    return [(n.id,n.event_id,n.start,n.duration,n.pitch,n.velocity) for n in chord.render_notes()]


def marked_project(*,custom=False):
    project=Project()
    chord=Chord(0,3840,notes=[Note(0,3840,pitch,velocity) for pitch,velocity in
                             ((36,47),(48,81),(52,93),(55,102))],custom_rhythm=custom)
    project.chords=[chord];set_marker(chord,54,'aug',11)
    return project,chord.id


class RecognitionActionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(dir='tmp');self.addCleanup(self.directory.cleanup)
        self.folder=Path(self.directory.name)
        paths=patch('lingfeng.ui.main_window.user_data_dir',return_value=self.folder)
        paths.start();self.addCleanup(paths.stop)
        self.addCleanup(chord_preferences.set_preferences,chord_preferences.settings_dict())
        chord_preferences.load_preferences({})
        self.addCleanup(context_menu_preferences.set_preferences,context_menu_preferences.settings_dict())
        context_menu_preferences.load_preferences({})

    def window(self,project):
        window=MainWindow(project);window.timer.stop();window.autosave.stop()
        window.change_language('zh',False)
        def close():
            window.dirty=False;window.close();window.deleteLater()
            APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.addCleanup(close)
        return window

    def menu(self,lane,ids):
        lane.editor.selected_chords=set(ids)
        first=min(c.start for c in lane.editor.project.chords if c.id in ids)
        menu=lane.context_menu(QPoint(round(lane.x_at(first+100)),18),preserve=True)
        self.addCleanup(menu.close)
        return menu

    def chord(self,window,cid):
        return next(c for c in window.project.chords if c.id==cid)

    def test_checkable_qaction_emits_both_new_states_without_callback_type_error(self):
        project,cid=marked_project();roll=PianoRoll(project);self.addCleanup(roll.close)
        commands=[];roll.chordCommand.connect(lambda *args:commands.append(args))
        menu=self.menu(roll.lane,{cid})
        with patch('sys.excepthook') as errors:
            self.assertTrue(menu.recognition_action.isChecked())
            menu.recognition_action.trigger()
            menu.recognition_action.trigger()
        errors.assert_not_called()
        self.assertEqual(commands,[('recognition:0',{cid}),('recognition:1',{cid})])

    def test_marked_chord_can_be_unchecked_from_every_chord_lane(self):
        for surface in ('main','melody','harmony'):
            with self.subTest(surface=surface):
                project,cid=marked_project();window=self.window(project)
                lane={'main':window.chord_lane,'melody':window.roll.lane,
                      'harmony':window.harmony_window.top_lane}[surface]
                before=performed(self.chord(window,cid));midi=event_list(window.project)
                menu=self.menu(lane,{cid});menu.recognition_action.trigger()
                chord=self.chord(window,cid)
                self.assertFalse(chord.marked or chord.recognition_disabled)
                self.assertTrue(chord.recognized);self.assertEqual(chord.name,'C')
                self.assertEqual(performed(chord),before)
                self.assertEqual(event_list(window.project),midi)
                reopened=self.menu(lane,{cid})
                self.assertFalse(reopened.recognition_action.isChecked())
                self.assertTrue(reopened.custom_rhythm_action.isEnabled())

    def test_repeated_clicks_toggle_plain_recognition_after_discarding_marker(self):
        project,cid=marked_project();window=self.window(project)
        before=performed(self.chord(window,cid))
        menu=self.menu(window.chord_lane,{cid})
        menu.recognition_action.trigger()
        self.assertFalse(self.chord(window,cid).marked)
        menu.recognition_action.trigger()
        self.assertTrue(self.chord(window,cid).recognition_disabled)
        self.assertFalse(self.chord(window,cid).marked)
        self.assertFalse(self.chord(window,cid).recognized)
        menu=self.menu(window.chord_lane,{cid});menu.recognition_action.trigger()
        self.assertFalse(self.chord(window,cid).recognition_disabled)
        self.assertEqual(self.chord(window,cid).name,'C')
        self.assertEqual(performed(self.chord(window,cid)),before)

    def test_modal_mouse_activation_works_at_root_and_in_user_grouped_recognition(self):
        for grouped in (False,True):
            with self.subTest(grouped=grouped):
                project,cid=marked_project();window=self.window(project)
                layout=context_menu_preferences.default_layout()
                for block in layout['chord']:
                    if block['id']=='recognition':block['grouped']=grouped
                context_menu_preferences.set_preferences({'context_menu_layout':layout})
                menu=self.menu(window.chord_lane,{cid});action=menu.recognition_action
                if grouped:
                    self.assertNotIn(action,menu.actions())
                    container=next(group for group in menu.group_menus if action in group.actions())
                else:
                    self.assertIn(action,menu.actions());container=menu
                clicked=[]
                def click():
                    clicked.append(True)
                    QTest.mouseClick(container,Qt.MouseButton.LeftButton,pos=container.actionGeometry(action).center())
                QTimer.singleShot(0,container,click)
                QTimer.singleShot(1000,container,container.close)
                container.exec(QPoint(100,100))
                self.assertEqual(clicked,[True])
                self.assertFalse(self.chord(window,cid).marked or self.chord(window,cid).recognition_disabled)

    def test_unchecking_supports_undo_redo_and_native_save_restart(self):
        project,cid=marked_project(custom=True);window=self.window(project)
        before=copy.deepcopy(window.project.to_dict());notes=performed(self.chord(window,cid))
        menu=self.menu(window.chord_lane,{cid});menu.recognition_action.trigger()
        after=window.project.to_dict();self.assertNotEqual(after,before)
        self.assertTrue(self.chord(window,cid).custom_rhythm)
        window.undo();self.assertEqual(window.project.to_dict(),before)
        window.redo();self.assertEqual(window.project.to_dict(),after)
        window.path=self.folder/'resumed.lfs';self.assertTrue(window.save())
        restarted=self.window(Project.load(window.path))
        chord=self.chord(restarted,cid)
        self.assertFalse(chord.marked or chord.recognition_disabled)
        self.assertTrue(chord.custom_rhythm)
        self.assertEqual(performed(chord),notes)
        menu=self.menu(restarted.chord_lane,{cid})
        self.assertFalse(menu.recognition_action.isChecked())
        self.assertTrue(menu.custom_rhythm_action.isChecked())
        self.assertTrue(menu.custom_rhythm_action.isEnabled())

    def test_marked_project_loaded_from_disk_can_resume_through_context_action(self):
        project,cid=marked_project();path=self.folder/'marked.lfs';project.save(path)
        window=self.window(Project.load(path));before=performed(self.chord(window,cid))
        menu=self.menu(window.chord_lane,{cid});self.assertTrue(menu.recognition_action.isChecked())
        menu.recognition_action.trigger()
        self.assertFalse(self.chord(window,cid).marked or self.chord(window,cid).recognition_disabled)
        self.assertEqual(self.chord(window,cid).name,'C')
        self.assertEqual(performed(self.chord(window,cid)),before)

    def test_batch_unchecking_resumes_each_actual_chord_without_using_marked_templates(self):
        project,cid=marked_project()
        second=Chord(3840,3840,50,'m',pattern='up',velocity=97)
        project.chords.append(second);set_marker(second,59,'maj7',1)
        window=self.window(project);ids={cid,second.id}
        before={c.id:performed(c) for c in window.project.chords if c.id in ids}
        menu=self.menu(window.chord_lane,ids);self.assertTrue(menu.recognition_action.isChecked())
        menu.recognition_action.trigger()
        self.assertEqual([self.chord(window,ident).name for ident in (cid,second.id)],['C','Dm'])
        for ident in ids:
            chord=self.chord(window,ident)
            self.assertFalse(chord.marked or chord.recognition_disabled)
            self.assertEqual(performed(chord),before[ident])

    def test_mixed_selection_disables_then_resumes_without_restoring_removed_marker(self):
        project,cid=marked_project();second=Chord(3840,3840,50,'m');project.chords.append(second)
        window=self.window(project);ids={cid,second.id};before=event_list(window.project)
        menu=self.menu(window.chord_lane,ids);self.assertFalse(menu.recognition_action.isChecked())
        menu.recognition_action.trigger()
        self.assertTrue(all(self.chord(window,ident).recognition_disabled for ident in ids))
        menu.recognition_action.trigger()
        self.assertTrue(all(not self.chord(window,ident).recognition_disabled and not self.chord(window,ident).marked for ident in ids))
        self.assertEqual(event_list(window.project),before)

    def test_unknown_and_empty_midi_resume_without_generating_annotation_tones(self):
        for notes in ([],[Note(0,1920,60,43),Note(0,1920,61,98)]):
            with self.subTest(notes=notes):
                project=Project();chord=Chord(0,1920,notes=notes,recognized=False);project.chords=[chord]
                set_marker(chord,2,'m11',5);cid=chord.id
                window=self.window(project);before=performed(self.chord(window,cid))
                menu=self.menu(window.chord_lane,{cid});menu.recognition_action.trigger()
                chord=self.chord(window,cid)
                self.assertFalse(chord.marked or chord.recognition_disabled or chord.recognized)
                self.assertEqual(performed(chord),before)
                self.assertEqual(chord.name,'N.C.' if not notes else '未识别')


if __name__=='__main__':unittest.main()
