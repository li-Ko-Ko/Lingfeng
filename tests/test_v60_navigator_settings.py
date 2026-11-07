"""Navigator track and height preferences survive UI rebuilds and restarts."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from lingfeng.music.model import Chord, Note, Project
from lingfeng.platform import i18n
from lingfeng.platform.preferences import load_preferences, save_preferences
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.piano_roll import NAVIGATOR_MIN_HEIGHT, NAVIGATOR_MAX_HEIGHT


APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]


class NavigatorSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(dir=ROOT/'tmp')
        self.addCleanup(temporary.cleanup)
        self.folder=Path(temporary.name)/'user-data'
        environment=patch.dict(os.environ,{'LINGFENG_USER_DATA':str(self.folder),
                                         'LINGFENG_SYNTH_CACHE':str(Path(temporary.name)/'synth-index.json')})
        environment.start();self.addCleanup(environment.stop)
        self.addCleanup(i18n.set_language,i18n.LANGUAGE)
        self.windows=[];self.addCleanup(self.close_windows)

    def close_windows(self):
        for window in self.windows:
            window.dirty=False;window.close();window.deleteLater()
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def window(self):
        project=Project(notes=[Note(0,480,60)],instrument_notes=[Note(480,480,67)],
                        chords=[Chord(0,3840,48)])
        window=MainWindow(project);window.timer.stop();window.autosave.stop()
        self.windows.append(window);window.show();APP.processEvents()
        return window

    def test_defaults_and_checkboxes_persist_without_modifying_music(self):
        save_preferences(self.folder,{'unknown_future_option':{'keep':True}})
        w=self.window();before=copy.deepcopy(w.project.to_dict())
        self.assertEqual(w.navigator_tracks,['vocal','instrument'])
        self.assertIsNone(w.navigator_height)
        self.assertTrue(w.navigator_auto_height_action.isChecked())
        self.assertFalse(w.navigator_track_actions['chords'].isChecked())
        w.navigator_track_actions['chords'].trigger()
        w.navigator_track_actions['vocal'].trigger()
        self.assertEqual(w.navigator_tracks,['instrument','chords'])
        self.assertEqual(set(w.navigator.visible_tracks),{'instrument','chords'})
        for navigator in w._navigators:
            self.assertEqual(set(navigator.visible_tracks),{'instrument','chords'})
        saved=load_preferences(self.folder)
        self.assertEqual(saved['navigator_tracks'],['instrument','chords'])
        self.assertEqual(saved['unknown_future_option'],{'keep':True})
        self.assertEqual(w.project.to_dict(),before)
        self.assertFalse(w.dirty);self.assertEqual(w.undo_history,[])
        reopened=self.window()
        self.assertEqual(reopened.navigator_tracks,['instrument','chords'])

    def test_manual_drag_and_height_dialog_save_and_restore_automatic_mode(self):
        w=self.window();auto=w.navigator.height()
        w.navigator.navigatorHeightChanged.emit(95)
        self.assertEqual(w.navigator_height,95)
        self.assertFalse(w.navigator_auto_height_action.isChecked())
        self.assertEqual(w.navigator.height(),95)
        self.assertEqual(load_preferences(self.folder)['navigator_height'],95)
        reopened=self.window();self.assertEqual(reopened.navigator.height(),95)
        with patch('lingfeng.ui.main_window.QInputDialog.getInt',return_value=(113,True)) as dialog:
            reopened.choose_navigator_height()
        self.assertEqual(dialog.call_args.args[-2:],(NAVIGATOR_MIN_HEIGHT,NAVIGATOR_MAX_HEIGHT))
        self.assertEqual(reopened.navigator.height(),113)
        reopened.navigator_auto_height_action.trigger()
        self.assertIsNone(reopened.navigator_height)
        self.assertEqual(reopened.navigator.height(),auto)
        self.assertIsNone(load_preferences(self.folder)['navigator_height'])
        reopened.navigator_auto_height_action.trigger()
        self.assertEqual(reopened.navigator_height,auto)
        self.assertFalse(reopened.navigator_auto_height_action.isChecked())

    def test_automatic_height_tracks_visible_nonempty_lanes_and_language_rebuild(self):
        w=self.window();two=w.navigator.height()
        w.navigator_track_actions['instrument'].trigger()
        one=w.navigator.height();self.assertLess(one,two)
        w.navigator_track_actions['chords'].trigger()
        self.assertGreater(w.navigator.height(),one)
        w.set_navigator_height(86)
        w.change_language('en');APP.processEvents()
        self.assertEqual(w.navigator.height(),86)
        self.assertEqual(set(w.navigator.visible_tracks),{'vocal','chords'})
        self.assertFalse(w.navigator_auto_height_action.isChecked())
        self.assertTrue(w.navigator_track_actions['chords'].isChecked())
        w.set_navigator_height(None)
        self.assertGreater(w.navigator.height(),one)

    def test_malformed_saved_values_use_safe_defaults_and_limits(self):
        cases=[({'navigator_tracks':'vocal','navigator_height':True},['vocal','instrument'],None),
               ({'navigator_tracks':['vocal','vocal',None,'future'],'navigator_height':-3},['vocal'],NAVIGATOR_MIN_HEIGHT),
               ({'navigator_tracks':[],'navigator_height':999},[],NAVIGATOR_MAX_HEIGHT)]
        for saved,tracks,height in cases:
            with self.subTest(saved=saved):
                save_preferences(self.folder,saved)
                w=self.window()
                self.assertEqual(w.navigator_tracks,tracks)
                self.assertEqual(w.navigator_height,height)
                self.assertEqual(set(w.navigator.visible_tracks),set(tracks))


if __name__=='__main__':unittest.main()
