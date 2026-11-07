"""Section note selection reveals the selected time and pitch in its roll."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from lingfeng.music.model import Chord, Note, Project
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.piano_roll import KEY_W


APP=QApplication.instance() or QApplication([])


class SectionFocusTests(unittest.TestCase):
    def setUp(self):
        self.folder=self.enterContext(TemporaryDirectory(dir='tmp'))
        self.enterContext(patch('lingfeng.ui.main_window.user_data_dir',return_value=Path(self.folder)))
        self.enterContext(patch.object(MainWindow,'save_preferences'))
        self.project=Project(notes=[Note(0,480,60),Note(6*3840,960,96)],
                             instrument_notes=[Note(5*3840,960,30)],
                             chords=[Chord(4*3840,3840,notes=[Note(0,960,42)])])
        self.window=MainWindow(self.project)
        self.window.timer.stop();self.window.autosave.stop()
        self.window.resize(1100,760);self.window.show();APP.processEvents()

    def tearDown(self):
        self.window.dirty=False;self.window.close();self.window.deleteLater()
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()

    def assert_note_visible(self,roll,note,start=None):
        start=note.start if start is None else start
        self.assertGreater(roll.x_at(note.end),KEY_W)
        self.assertLess(roll.x_at(start),roll.viewport().width())
        self.assertGreaterEqual(roll.y_at(note.pitch),roll.ruler_height)
        self.assertLessEqual(roll.y_at(note.pitch)+roll.row_height,roll.viewport().height())
        self.assertTrue(roll.isVisible())

    def test_offscreen_selection_reveals_time_and_pitch_without_editing(self):
        w=self.window;r=w.roll;note=self.project.notes[1]
        r.horizontalScrollBar().setValue(0);r.center_pitch(48)
        before=self.project.to_dict();zoom=r.zoom;playhead=w.playhead
        self.assertFalse(r.tick_visible(note.start))
        w.select_section_contents(6,7,'melody');APP.processEvents()
        self.assertEqual(r.selected_ids,{note.id})
        self.assert_note_visible(r,note)
        self.assertEqual((r.zoom,w.playhead),(zoom,playhead))
        self.assertEqual(self.project.to_dict(),before)
        self.assertFalse(w.undo_history)

    def test_visible_selection_preserves_camera(self):
        w=self.window;r=w.roll
        r.horizontalScrollBar().setValue(0);r.center_pitch(60)
        before=(r.horizontalScrollBar().value(),r.verticalScrollBar().value(),r.zoom)
        self.assert_note_visible(r,self.project.notes[0])
        w.select_section_contents(0,1,'melody');APP.processEvents()
        self.assertEqual((r.horizontalScrollBar().value(),r.verticalScrollBar().value(),r.zoom),before)

    def test_instrument_selection_opens_hidden_tab_and_reveals_its_notes(self):
        w=self.window
        w.melody_view_actions[1].setChecked(False)
        w.select_section_contents(5,6,'instrument');APP.processEvents()
        self.assertEqual(w.roll.melody_track,1)
        self.assertEqual(w.roll.selected_ids,{self.project.instrument_notes[0].id})
        self.assert_note_visible(w.roll,self.project.instrument_notes[0])

    def test_harmony_selection_opens_roll_and_reveals_its_notes(self):
        w=self.window
        self.assertFalse(w.harmony_window.isVisible())
        w.select_section_contents(4,5,'harmony');APP.processEvents()
        r=w.harmony_window.roll;note=r.selected_notes()[0]
        self.assert_note_visible(r,note)

    def test_all_notes_opens_populated_track_in_score_workspace(self):
        w=self.window
        w.switch_workspace('score');APP.processEvents()
        self.assertEqual(w.roll.melody_track,0)
        w.select_section_contents(5,6,'all_notes');APP.processEvents()
        self.assertEqual(w.current_score_panel(),'melody')
        self.assertEqual(w.roll.melody_track,1)
        self.assert_note_visible(w.roll,self.project.instrument_notes[0])

    def test_sustained_note_reveals_selected_section_instead_of_early_onset(self):
        w=self.window;r=w.roll
        note=self.project.notes[0];note.duration=7*3840
        r.refresh()
        w.select_section_contents(6,7,'melody');APP.processEvents()
        self.assert_note_visible(r,note,6*3840)
        self.assertTrue(r.tick_visible(6*3840))
        self.assertFalse(r.tick_visible(note.start))

    def test_floating_target_uses_local_camera(self):
        w=self.window
        w.set_melody_floating(1,True,focus=False);APP.processEvents()
        pane=w.melody_floats[1];pane.sync.setChecked(False)
        before=(w.roll.horizontalScrollBar().value(),w.roll.verticalScrollBar().value())
        w.select_section_contents(5,6,'instrument');APP.processEvents()
        self.assert_note_visible(pane.roll,self.project.instrument_notes[0])
        self.assertEqual((w.roll.horizontalScrollBar().value(),w.roll.verticalScrollBar().value()),before)

    def test_all_notes_keeps_active_float_when_docked_vocal_also_has_notes(self):
        w=self.window
        self.project.notes[1].start=5*3840;w.refresh()
        w.set_melody_floating(1,True,focus=True);APP.processEvents()
        pane=w.melody_floats[1];pane.sync.setChecked(False)
        pane.roll.horizontalScrollBar().setValue(0);pane.roll.setFocus();APP.processEvents()
        self.assertIs(w.active_roll(),pane.roll)
        before=(w.roll.horizontalScrollBar().value(),w.roll.verticalScrollBar().value())
        w.select_section_contents(5,6,'all_notes');APP.processEvents()
        self.assert_note_visible(pane.roll,self.project.instrument_notes[0])
        self.assertEqual((w.roll.horizontalScrollBar().value(),w.roll.verticalScrollBar().value()),before)


if __name__=='__main__':unittest.main()
