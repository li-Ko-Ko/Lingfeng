"""Global note labels, peer windows and localized product positioning."""
import os,json,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QRect,QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from lingfeng.ui.main_window import MainWindow
from lingfeng.music.model import Project, Note, Chord
from lingfeng.ui.help_dialog import HelpDialog
import lingfeng.ui.theme as theme

APP=QApplication.instance() or QApplication([])

class WindowDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='tmp');self.prefs=patch('lingfeng.ui.main_window.user_data_dir',return_value=Path(self.temp.name));self.prefs.start()
        p=Project();p.notes=[Note(0,1920,60),Note(2400,960,61)];p.chords=[Chord(0,3840,notes=[Note(0,1920,60),Note(2400,960,61)])]
        self.w=MainWindow(p);self.w.show();self.w.resize(1200,850);self.w.timer.stop();self.w.autosave.stop();self.w.open_harmony()
        self.w.melody_window.setFloating(True);self.w.harmony_window.setFloating(True);QTest.qWait(15)
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()
        self.prefs.stop();self.temp.cleanup();theme.set_note_degrees(True)
    def test_toggle_removes_note_digits_on_both_rolls_but_keeps_music_and_keyboard(self):
        w=self.w;before=w.project.to_dict();history=len(w.undo_history);images=[]
        for r in (w.roll,w.harmony_window.roll):
            r.selection=[];r.center_pitch(60);r.refresh();APP.processEvents();image=r.viewport().grab().toImage()
            ratio=image.devicePixelRatio();images.append((r,image.copy(QRect(round((r.x_at(0)+4)*ratio),round(r.y_at(60)*ratio),round(30*ratio),round(r.row_height*ratio))),image.copy(0,0,round(60*ratio),image.height())))
        w.note_degrees_action.setChecked(False);APP.processEvents()
        for r,note,keyboard in images:
            image=r.viewport().grab().toImage();ratio=image.devicePixelRatio()
            self.assertNotEqual(note,image.copy(QRect(round((r.x_at(0)+4)*ratio),round(r.y_at(60)*ratio),round(30*ratio),round(r.row_height*ratio))))
            self.assertEqual(keyboard,image.copy(0,0,round(60*ratio),image.height()))
        self.assertEqual(w.project.to_dict(),before);self.assertEqual(len(w.undo_history),history)
        w.note_degrees_action.setChecked(True);self.assertTrue(theme.SHOW_NOTE_DEGREES)
    def test_global_label_preference_survives_language_layout_and_restart(self):
        w=self.w;w.note_degrees_action.setChecked(False);w.change_language('en');w.switch_workspace('score');w.open_score_roll('chords',0);w.score_tools.setFloating(True)
        self.assertFalse(w.note_degrees_action.isChecked());self.assertFalse(theme.SHOW_NOTE_DEGREES)
        self.assertFalse(json.loads((Path(self.temp.name)/'preferences.json').read_text(encoding='utf-8'))['show_note_degrees'])
        w.dirty=False;w.close();other=MainWindow(Project())
        try:self.assertFalse(other.note_degrees_action.isChecked());self.assertFalse(theme.SHOW_NOTE_DEGREES)
        finally:other.dirty=False;other.close();other.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    def test_all_floating_editors_are_peer_windows_and_redock_cleanly(self):
        w=self.w
        for pane in (w.melody_window,w.harmony_window):
            self.assertIsNone(pane.parentWidget());self.assertIs(pane.owner,w);self.assertEqual(pane.windowType(),Qt.WindowType.Window)
            pane.setFloating(False);self.assertFalse(pane.isWindow());pane.setFloating(True);self.assertIsNone(pane.parentWidget())
        w.switch_workspace('score');w.edit_toggle.setChecked(True);w.toggle_editor();w.score_tools.setFloating(True)
        self.assertIsNone(w.score_tools.parentWidget());self.assertIs(w.score_tools.owner,w)
        w.score_tools.setFloating(False);self.assertFalse(w.score_tools.isWindow())
    def test_main_close_hides_every_peer_and_destruction_disposes_them(self):
        from shiboken6 import isValid
        w=self.w;panes=(w.melody_window,w.harmony_window,w.score_tools)
        w.dirty=False;w.close();self.assertTrue(all(not p.isVisible() for p in panes))
        w.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertTrue(all(not isValid(p) for p in panes))
        self.w=MainWindow(Project());self.w.timer.stop();self.w.autosave.stop()
    def test_about_positions_composition_and_names_inspiration_in_both_languages(self):
        for lang,words in [('zh',('专注','录音','混音','母带','Hooktheory','Cakewalk Next','独立实现','权利人')),('en',('composition','recording','mixing','mastering','Hooktheory','Cakewalk Next','independently','rights holders'))]:
            self.w.change_language(lang,False);d=HelpDialog(self.w,True);text=d.browser.toPlainText()
            for word in words:self.assertIn(word,text)
            d.deleteLater()

if __name__=='__main__':unittest.main()
