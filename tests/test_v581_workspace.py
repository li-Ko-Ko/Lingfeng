"""Melody titles and the overlaid overview in normal workspace entry points."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QToolButton
from lingfeng.music.abc_import import read_abc
from lingfeng.music.model import Note, Project
from lingfeng.platform.i18n import tr
from lingfeng.ui.main_window import MainWindow

APP=QApplication.instance() or QApplication([])


class Workspace581Tests(unittest.TestCase):
    def setUp(self):
        p=Project(notes=[Note(0,480,60),Note(960,480,64)],
                  instrument_notes=[Note(0,480,60),Note(480,480,62)])
        with patch.object(MainWindow,'save_preferences'):
            self.window=MainWindow(p)
        self.window.timer.stop();self.window.autosave.stop()
        self.window.show();APP.processEvents()

    def tearDown(self):
        self.window.dirty=False
        self.window.close();self.window.deleteLater();APP.processEvents()

    def test_file_actions_stay_in_file_menu_and_tabs_mount_in_titles(self):
        w=self.window
        header=w.header_layout.parentWidget()
        self.assertNotIn(tr('保存'),[button.text() for button in header.findChildren(QPushButton)])
        self.assertNotIn(tr('导出'),[button.text() for button in header.findChildren(QToolButton)])
        self.assertIs(w.melody_tabs.parentWidget(),w.melody_header)
        self.assertEqual([w.melody_tabs.tabText(i) for i in range(2)],[tr('人声旋律'),tr('乐器旋律')])
        w.melody_window.setFloating(True);APP.processEvents()
        self.assertIs(w.melody_tabs.parentWidget(),w.melody_window.title_bar)
        w.switch_workspace('score');w.show_score_panel('melody');APP.processEvents()
        self.assertIs(w.melody_tabs.parentWidget(),w.melody_header)
        w.toggle_score_panel_floating('melody');APP.processEvents()
        self.assertIs(w.melody_tabs.parentWidget(),w.score_floats['melody'].title_bar)

    def test_rename_is_saved_undoable_and_reaches_mixer(self):
        w=self.window
        with patch('lingfeng.ui.workspace.QInputDialog.getText',return_value=(' Lead synth ',True)):
            w.rename_melody_track(1)
        self.assertEqual(w.melody_tabs.tabText(1),'Lead synth')
        self.assertEqual(w.audio_footer.titles['instrument'].toolTip(),'Lead synth')
        self.assertEqual(Project.from_dict(w.project.to_dict()).melody_names[1],'Lead synth')
        w.undo()
        self.assertEqual(w.melody_tabs.tabText(1),tr('乐器旋律'))

    def test_melodies_share_overview_time_and_have_separate_pitch_bands(self):
        nav=self.window.navigator
        segments=nav.segments()
        vocal=[segment[1:] for segment in segments if segment[0]==0]
        instrument=[segment[1:] for segment in segments if segment[0]==2]
        self.assertEqual(vocal[0][::2],instrument[0][::2])
        self.assertLess(vocal[0][1],instrument[0][1])
        self.assertLess(vocal[1][1],instrument[1][1])
        self.assertNotEqual(nav.TRACK_COLORS[0],nav.TRACK_COLORS[2])

    def test_file_menu_exports_model_abc_with_both_melodies(self):
        w=self.window
        w.project.measures[0].section='interlude'
        file_action=next(action for action in w.title_bar.menu.actions() if action.text()==tr('文件'))
        file_menu=file_action.menu()
        export_action=next(action for action in file_menu.actions() if action.text()==tr('导出'))
        export=export_action.menu()
        action=next(action for action in export.actions() if action.text()==tr('ABC…'))
        with TemporaryDirectory(dir='tmp') as temp:
            path=Path(temp)/'score'
            with (
                patch('lingfeng.ui.abc_export_dialog.AbcExportDialog.exec',return_value=QDialog.DialogCode.Accepted),
                patch('lingfeng.ui.main_window.QFileDialog.getSaveFileName',return_value=(str(path),'')),
                patch.object(w,'save_preferences'),
            ):
                action.trigger()
            source=path.with_suffix('.abc')
            self.assertIn('% interlude',source.read_text('utf-8'))
            data=read_abc(source)
            self.assertEqual(data.defaults()['vocal'],'Vocal')
            self.assertEqual(data.defaults()['instrument'],'Ins')
