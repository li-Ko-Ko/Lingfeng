"""Requested engraving sizes remain editable, persistent and exportable."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Project,Note,Measure,Context,FONT_SIZE_MAX
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.score_view import ScoreCanvas
from lingfeng.ui.export_dialog import ExportDialog
from lingfeng.engraving.notation import ScoreLayout,export_pdf,PAPER_W,PAPER_H
from lingfeng.engraving.presentation import apply_forced_row
from lingfeng.audio.midi import export_midi

APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]


def song(size=40,count=4,step=120,legacy=False):
    project=Project();project.measures=[Measure() for _ in range(count)];project.contexts=[Context(0,project.end)]
    project.notes=[Note(t,step,60+(t//step)%5*2,80) for t in range(0,project.end,step)]
    project.notation.update(style='spatial',per_line=2,font_size=size,circles=False,lyrics=False)
    if not legacy:project.notation['font_layout_version']=45
    return project


def render(layout,page=0):
    image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);image.fill(Qt.GlobalColor.white)
    painter=QPainter(image);layout.draw(painter,page);painter.end();return image


class FontControlTests(unittest.TestCase):
    def setUp(self):
        self.preferences=patch.object(MainWindow,'save_preferences');self.preferences.start();self.addCleanup(self.preferences.stop)
        self.window=MainWindow(song());self.window.timer.stop();self.window.autosave.stop()
        self.window.change_language('zh',False);self.window.switch_workspace('score')
        self.addCleanup(self.close)

    def close(self):
        self.window.dirty=False;self.window.close();self.window.deleteLater();APP.processEvents()

    def assert_size(self,size):
        window=self.window;canvas=window.score_view.canvas
        self.assertEqual(window.project.notation['font_size'],size)
        self.assertEqual(window.note_font.value(),size)
        self.assertEqual(canvas.project.notation['font_size'],size)
        self.assertEqual(canvas.layout.font_size,size)
        self.assertAlmostEqual(canvas.layout.glyph_scale,size/15)

    def test_buttons_and_typing_exceed_advice_and_change_actual_glyphs(self):
        window=self.window;self.assertEqual(window.note_font.maximum(),FONT_SIZE_MAX)
        self.assertLess(window.score_view.canvas.layout.font_limit,40)
        window.note_font.setValue(40);window.note_font.stepUp();self.assert_size(41)
        editor=window.note_font.lineEdit();editor.selectAll();QTest.keyClicks(editor,'60');QTest.keyClick(editor,Qt.Key.Key_Return)
        self.assert_size(60);layout=window.score_view.canvas.layout;render(layout)
        self.assertTrue(layout.glyph_sizes);self.assertTrue(all(size==60 for _,size in layout.glyph_sizes))

    def test_sync_and_canvas_rebuild_do_not_rewrite_or_dirty_the_project(self):
        window=self.window;window.dirty=False;before=copy.deepcopy(window.project.to_dict())
        window.score_view.canvas.rebuild(window.project);window.sync_score_font()
        self.assert_size(40);self.assertEqual(window.project.to_dict(),before);self.assertFalse(window.dirty)

    def test_legacy_project_and_workspace_switches_preserve_requested_size(self):
        window=self.window;window.replace_project(song(48,legacy=True));self.assert_size(48)
        for _ in range(2):window.switch_workspace('compose');window.refresh();window.switch_workspace('score');self.assert_size(48)

    def test_layout_changes_recommend_traditional_size_and_restore_it_with_undo_redo(self):
        window=self.window
        for key,value in [('per_line',4),('row_gap',8),('style','traditional'),('style','compact')]:
            before=window.project.notation['font_size'];window.set_notation(key,value)
            expected=window.score_view.canvas.layout.recommended_font_size if value=='traditional' else before
            self.assert_size(expected);window.undo();self.assert_size(before);window.redo();self.assert_size(expected)

    def test_project_save_load_and_maximum_size_round_trip(self):
        window=self.window;window.note_font.setValue(FONT_SIZE_MAX);self.assert_size(FONT_SIZE_MAX)
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            path=Path(directory)/'large-font.lfs';window.project.save(path);restored=Project.load(path)
            self.assertEqual(restored.notation['font_size'],FONT_SIZE_MAX);window.replace_project(restored);self.assert_size(FONT_SIZE_MAX)

    def test_recommendation_is_explicit_and_undoable(self):
        window=self.window;expected=window.score_view.canvas.layout.recommended_font_size
        self.assertNotEqual(expected,40);window.recommend_score_font();self.assert_size(expected)
        window.undo();self.assert_size(40);window.redo();self.assert_size(expected)

    def test_language_rebuild_preserves_requested_value_and_advisory(self):
        window=self.window;layout=window.score_view.canvas.layout;window.change_language('en',False)
        self.assertIs(window.score_view.canvas.layout,layout);self.assert_size(40)
        self.assertIn(f'{layout.font_limit:g}',window.font_limit_label.text());self.assertNotIn('建议',window.font_limit_label.text())

    def test_forced_row_only_scales_the_merged_system(self):
        window=self.window;window.replace_project(song(40,count=8,step=480))
        window.mutate('merge test rows',lambda project:apply_forced_row(project,[0,1,2,3]),source='score')
        self.assert_size(40);layout=window.score_view.canvas.layout
        merged=next(system for system in layout.systems if system.bars==[0,1,2,3])
        ordinary=next(system for system in layout.systems if system.bars==[4,5])
        self.assertAlmostEqual(merged.symbol_scale,40/15/2);self.assertAlmostEqual(ordinary.symbol_scale,40/15)

    def test_full_score_pdf_uses_requested_size_and_frozen_music_snapshot(self):
        window=self.window;window.replace_project(song(40,count=12,step=480))
        original_pitch=window.score_view.canvas.project.notes[0].pitch
        window.mutate('music changed in editor',lambda project:setattr(project.notes[0],'pitch',original_pitch+1))
        self.assertNotEqual(window.project.notes[0].pitch,window.score_view.canvas.project.notes[0].pitch)
        before=copy.deepcopy(window.project.to_dict());midi=export_midi(window.project,None);dialog=ExportDialog(window,'pdf')
        try:
            self.assertEqual(dialog.project.notation['font_size'],40);self.assertEqual(dialog.project.notes[0].pitch,original_pitch)
            expected=ScoreLayout(dialog.project);self.assertGreater(expected.pages,1);seen=[];draw=ScoreLayout.draw
            def record(layout,painter,page,*args,**kwargs):
                result=draw(layout,painter,page,*args,**kwargs);seen.append((page,layout.font_size,layout.glyph_scale));return result
            with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
                path=Path(directory)/'requested-size.pdf'
                with patch.object(ScoreLayout,'draw',record):pages=export_pdf(dialog.project,path)
                self.assertEqual(pages,expected.pages);self.assertTrue(path.read_bytes().startswith(b'%PDF'))
            self.assertEqual([page for page,_,_ in seen],list(range(expected.pages)))
            self.assertTrue(all(size==40 and abs(scale-40/15)<1e-7 for _,size,scale in seen))
            self.assertEqual(window.project.to_dict(),before);self.assertEqual(export_midi(window.project,None),midi)
        finally:dialog.close();dialog.deleteLater()


if __name__=='__main__':unittest.main()
