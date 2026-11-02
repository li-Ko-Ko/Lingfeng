"""Integer traditional advice does not round a manually requested font size."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QPushButton
from lingfeng.audio.midi import export_midi
from lingfeng.music.model import Context,Measure,Note,Project
from lingfeng.platform.i18n import tr
from lingfeng.ui.main_window import MainWindow

APP=QApplication.instance() or QApplication([])


def song():
    p=Project(measures=[Measure()for _ in range(6)])
    p.contexts=[Context(0,p.end)]
    p.notes=[Note(t,480,(60,62,64,65,67)[(t//480)%5])for t in range(0,p.end,480)]
    p.notation.update(style='traditional',per_line=4,font_size=7.5,font_layout_version=45)
    return p


class IntegerRecommendationControlsTests(unittest.TestCase):
    def setUp(self):
        self.preferences=patch.object(MainWindow,'save_preferences');self.preferences.start();self.addCleanup(self.preferences.stop)
        self.w=MainWindow(song());self.w.timer.stop();self.w.autosave.stop();self.w.change_language('zh',False)
        self.assertTrue(self.w.switch_workspace('score'));self.w.show();APP.processEvents();self.addCleanup(self.close)

    def close(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents()

    def assert_requested_size(self,value):
        w=self.w
        self.assertEqual(w.project.notation['font_size'],value)
        self.assertEqual(w.note_font.value(),value)
        self.assertEqual(w.score_view.canvas.project.notation['font_size'],value)
        self.assertEqual(w.score_view.canvas.layout.font_size,value)

    def assert_integer_advice(self):
        layout=self.w.score_view.canvas.layout
        self.assertIs(type(layout.recommended_font_size),int);self.assertIs(type(layout.font_limit),int)
        self.assertEqual(self.w.font_limit_label.text(),tr('建议上限 {0}',str(layout.font_limit)))
        self.assertIn(str(layout.recommended_font_size),self.w.note_font.toolTip())
        return layout.recommended_font_size

    def test_recommend_button_undo_and_save_reload_keep_an_integer(self):
        w=self.w;expected=self.assert_integer_advice();self.assert_requested_size(7.5)
        button=next(b for b in w.findChildren(QPushButton)if b.text()==tr('推荐字号'))
        QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        self.assert_requested_size(expected);self.assertIs(type(w.project.notation['font_size']),int)
        w.undo();self.assert_requested_size(7.5);w.redo();self.assert_requested_size(expected)
        with tempfile.TemporaryDirectory(dir='tmp')as folder:
            path=Path(folder)/'integer-advice.lfs';w.project.save(path);loaded=Project.load(path)
            self.assertIs(type(loaded.notation['font_size']),int);w.replace_project(loaded)
        self.assert_requested_size(expected);self.assert_integer_advice()

    def test_manual_fraction_survives_sync_language_and_save_without_editing_music(self):
        w=self.w;notes=copy.deepcopy(w.project.notes);midi=export_midi(w.project,None)
        w.recommend_score_font();w.note_font.setValue(7.5)
        w.refresh();w.sync_score_font();self.assert_requested_size(7.5);self.assert_integer_advice()
        w.change_language('en',False);self.assert_requested_size(7.5);self.assert_integer_advice()
        with tempfile.TemporaryDirectory(dir='tmp')as folder:
            path=Path(folder)/'manual-fraction.lfs';w.project.save(path);w.replace_project(Project.load(path))
        self.assert_requested_size(7.5);self.assert_integer_advice()
        self.assertEqual(w.project.notes,notes);self.assertEqual(export_midi(w.project,None),midi)


if __name__=='__main__':unittest.main()
