"""Note undo restores music and editor focus without navigating its piano roll."""
import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Project,Chord,Note
from lingfeng.ui.main_window import MainWindow

APP=QApplication.instance() or QApplication([])
CTRL=Qt.KeyboardModifier.ControlModifier


class UndoViewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='tmp');self.windows=[]
        self.paths=patch('lingfeng.ui.main_window.user_data_dir',return_value=Path(self.temp.name));self.paths.start()
        self.prefs=patch.object(MainWindow,'save_preferences');self.prefs.start()

    def tearDown(self):
        for w in self.windows:w.dirty=False;w.close();w.deleteLater()
        APP.processEvents();self.prefs.stop();self.paths.stop();self.temp.cleanup()

    def window(self,mode='compose-dock',pitches=(48,52)):
        p=Project();p.notes=[Note(0,480,60)]
        p.chords=[Chord(0,3840,notes=[Note(0,960,pitch) for pitch in pitches],recognition_disabled=True)]
        w=MainWindow(p);self.windows.append(w);w.timer.stop();w.autosave.stop();w.resize(1200,850);w.show();w.open_harmony()
        for b in w.mute_buttons.values():b.setChecked(True)
        if mode.startswith('score'):w.switch_workspace('score');w.show_score_panel('harmony')
        if mode.endswith('float'):
            if mode.startswith('score'):w.toggle_score_panel_floating('harmony')
            else:w.harmony_window.setFloating(True);w.harmony_window.show()
            w.harmony_window.sync.setChecked(False)
        QTest.qWait(60);r=w.harmony_window.roll;self.focus(r)
        return w,r

    def focus(self,r):
        r.window().activateWindow();r.setFocus();APP.processEvents()

    def select(self,w,r,pitch=None):
        w.select_element('notes',r)
        note=next(n for n in r.notes if pitch is None or n.pitch==pitch)
        r.selected_ids={note.id};r.refresh();return note.id

    def view(self,r):return (r.horizontalScrollBar().value(),r.verticalScrollBar().value())

    def browse(self,r,x=2200,y=710):
        r.horizontalScrollBar().setValue(x);r.verticalScrollBar().setValue(y);APP.processEvents()
        return self.view(r)

    def test_gui_delete_undo_redo_preserves_current_scroll_in_all_four_modes(self):
        for mode in ('compose-dock','compose-float','score-dock','score-float'):
            with self.subTest(mode=mode):
                w,r=self.window(mode);nid=self.select(w,r);before=w.project.to_dict()
                self.browse(r,1000,1000);QTest.keyClick(r,Qt.Key.Key_Delete);APP.processEvents()
                deleted=w.project.to_dict();self.assertNotIn(nid,{n.id for n in r.notes})
                view=self.browse(r);QTest.keyClick(r,Qt.Key.Key_Z,CTRL)
                self.assertEqual(w.project.to_dict(),before);self.assertEqual(self.view(r),view)
                self.assertIn(nid,r.selected_ids);QTest.qWait(70);self.assertEqual(self.view(r),view)
                view=self.browse(r,1800,680);QTest.keyClick(r,Qt.Key.Key_Y,CTRL)
                self.assertEqual(w.project.to_dict(),deleted);self.assertEqual(self.view(r),view)
                QTest.qWait(70);self.assertEqual(self.view(r),view)
                self.assertEqual(w.workspace,'score' if mode.startswith('score') else 'compose')

    def test_compact_keyboard_keeps_existing_pitches_stationary_when_undo_adds_a_top_row(self):
        for mode in ('compose-dock','compose-float'):
            with self.subTest(mode=mode):
                w,r=self.window(mode,tuple(range(37,104,2)));r.set_compact(True);self.select(w,r,103)
                QTest.keyClick(r,Qt.Key.Key_Delete);APP.processEvents();self.assertNotIn(103,r.pitches)
                self.browse(r,1700,r.pitches.index(77)*r.row_height-70);before_y=r.y_at(77)
                QTest.keyClick(r,Qt.Key.Key_Z,CTRL);self.assertIn(103,r.pitches)
                self.assertEqual(r.y_at(77),before_y);self.assertEqual(r.horizontalScrollBar().value(),1700)
                QTest.keyClick(r,Qt.Key.Key_Y,CTRL);self.assertNotIn(103,r.pitches)
                self.assertEqual(r.y_at(77),before_y);self.assertEqual(r.horizontalScrollBar().value(),1700)
                QTest.qWait(70);self.assertEqual(r.y_at(77),before_y)

    def test_current_custom_range_row_height_and_zoom_are_not_history_data(self):
        w,r=self.window('compose-float');self.select(w,r);QTest.keyClick(r,Qt.Key.Key_Delete)
        r.set_pitch_range(45,81);r.set_row_height(24);r.zoom_at(1.3);view=self.browse(r,1900,300);zoom=r.zoom
        QTest.keyClick(r,Qt.Key.Key_Z,CTRL);QTest.qWait(70)
        self.assertEqual((r.pitch_range,r.manual_pitch_range,r.row_height,r.zoom),((45,81),(45,81),24,zoom))
        self.assertEqual(self.view(r),view)
        self.assertNotIn('location',json.loads(json.dumps(w.redo_history[-1])))

    def test_pending_layout_center_cannot_move_the_roll_after_undo(self):
        w,r=self.window('compose-float');self.select(w,r);QTest.keyClick(r,Qt.Key.Key_Delete);view=self.browse(r)
        w.harmony_window.schedule_center(30);QTest.keyClick(r,Qt.Key.Key_Z,CTRL);QTest.qWait(80)
        self.assertEqual(self.view(r),view)

    def test_history_still_returns_to_hidden_operation_window_and_restores_selection(self):
        w,r=self.window('compose-float');nid=self.select(w,r);before=w.project.to_dict();QTest.keyClick(r,Qt.Key.Key_Delete)
        w.switch_workspace('score');w.activateWindow();w.score_view.canvas.setFocus();QTest.qWait(50)
        r.horizontalScrollBar().setValue(2100);r.verticalScrollBar().setValue(700)
        pitch=r.pitch_at(r.ruler_height+(r.viewport().height()-r.ruler_height)/2)
        QTest.keyClick(w.score_view.canvas,Qt.Key.Key_Z,CTRL);QTest.qWait(80)
        self.assertEqual(w.project.to_dict(),before);self.assertEqual(w.workspace,'compose')
        self.assertIs(APP.activeWindow(),w.harmony_window);self.assertIn(nid,r.selected_ids)
        self.assertEqual(r.horizontalScrollBar().value(),2100)
        self.assertAlmostEqual(r.pitch_at(r.ruler_height+(r.viewport().height()-r.ruler_height)/2),pitch,delta=1)


if __name__=='__main__':unittest.main()
