"""File and Tools menu workflows for bar insertion and section navigation."""

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from lingfeng.music.abc_export import write_abc
from lingfeng.music.model import Chord, Context, Measure, Note, Project
from lingfeng.platform.i18n import tr
from lingfeng.ui.abc_import_dialog import AbcImportDialog
from lingfeng.ui.abc_export_dialog import AbcExportDialog
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.section_progression_dialog import SectionProgressionDialog

APP=QApplication.instance() or QApplication([])


class ImportAndToolsTests(unittest.TestCase):
    def setUp(self):
        project=Project(title='Target',bpm=85,measures=[Measure(section='Verse'),Measure(section='Chorus')],
                        contexts=[Context(0,7680)],notes=[Note(3600,480,60)],
                        chords=[Chord(3600,480,48)])
        with patch.object(MainWindow,'save_preferences'):
            self.window=MainWindow(project)
        self.window.timer.stop();self.window.autosave.stop()
        self.window.show();APP.processEvents()

    def tearDown(self):
        self.window.dirty=False
        self.window.close();self.window.deleteLater();APP.processEvents()

    def action(self,menu,title):
        return next(action for action in menu.actions() if action.text()==tr(title))

    def test_yue2_preflight_lists_optional_rules_and_warns_only_for_link(self):
        project = self.window.project
        project.chords[0].quality = 'maj9'
        project.measures[0].section = 'link'
        dialog = AbcExportDialog(project, self.window)
        report = dialog.compatibility_report()
        self.assertIn(tr('必须修改')+'\n'+tr('无'), report)
        self.assertIn('link → interlude', report)
        self.assertIn('Cmaj9 → Cmaj7', report)
        dialog.convert_chords.setChecked(False)
        dialog.rewrite_links.setChecked(False)
        self.assertTrue(dialog.issues)
        self.assertIn(tr('可选处理')+'\n'+tr('无'), dialog.compatibility_report())
        dialog.rewrite_links.setChecked(True)
        with patch.object(QMessageBox, 'information', return_value=QMessageBox.StandardButton.Ok) as notice:
            with patch.object(dialog, 'confirm_replacements', return_value=True):
                dialog.accept()
            notice.assert_called_once()
            self.assertIn('link', notice.call_args.args[2])
        self.assertEqual(project.measures[0].section, 'link')

    def test_abc_insertion_from_file_menu_undo_and_redo_in_score(self):
        window=self.window
        window.switch_workspace('score')
        before=window.project.to_dict()
        window.dirty=True
        with TemporaryDirectory(dir='tmp') as temp:
            path=Path(temp)/'score.abc'
            source=Project(bpm=120,measures=[Measure(3,4,section='Link')],contexts=[Context(0,2880)],
                           notes=[Note(0,480,62)],instrument_notes=[Note(480,480,69)],chords=[Chord(0,2880,50)])
            write_abc(source,path)
            def accept(dialog):
                dialog.bar.setValue(2)
                return QDialog.DialogCode.Accepted
            file_action=self.action(window.title_bar.menu,'文件')
            file_menu=file_action.menu()
            import_action=self.action(file_menu,'导入')
            export_action=self.action(file_menu,'导出')
            self.assertLess(file_menu.actions().index(import_action),file_menu.actions().index(export_action))
            with (
                patch('lingfeng.ui.main_window.QFileDialog.getOpenFileName',return_value=(str(path),'')),
                patch.object(AbcImportDialog,'exec',accept),
                patch.object(window,'maybe_save',side_effect=AssertionError('Insertion must keep the current project')),
            ):
                self.action(import_action.menu(),'ABC…').trigger()
        after=window.project.to_dict()
        self.assertEqual(window.project.starts,[0,3840,6720,10560])
        self.assertEqual((window.project.title,window.project.bpm),('Target',85))
        self.assertEqual([(note.start,note.duration,note.pitch) for note in window.project.notes],
                         [(3600,240,60),(3840,480,62),(6720,240,60)])
        self.assertEqual([measure.section for measure in window.project.measures],['verse','link','chorus'])
        self.assertEqual(window.playhead,3840)
        self.assertEqual(window.score_view.canvas.project.starts,window.project.starts)
        window.undo()
        self.assertEqual(window.project.to_dict(),before)
        self.assertEqual(window.score_view.canvas.project.starts,window.project.starts)
        window.redo()
        self.assertEqual(window.project.to_dict(),after)

    def test_tools_jump_uses_selected_bar_in_current_workspace(self):
        window=self.window
        def jump(dialog):
            dialog.jump_to(1)
            return dialog.result()
        tools=self.action(window.title_bar.menu,'工具')
        with patch.object(SectionProgressionDialog,'exec',jump):
            self.action(tools.menu(),'和弦进行预览…').trigger()
        self.assertEqual(window.playhead,3840)
