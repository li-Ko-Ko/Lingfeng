"""Selection overlays, melody tab resources, and mixed-range paste."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Chord, Note, Project
from lingfeng.ui.main_window import MainWindow

APP=QApplication.instance() or QApplication([])


class RollSelectionTests(unittest.TestCase):
    def setUp(self):
        project=Project(notes=[Note(0,480,60)],instrument_notes=[Note(480,480,67)],
                        chords=[Chord(0,1920,48),Chord(1920,1920,55)])
        with patch.object(MainWindow,'save_preferences'):
            self.window=MainWindow(project)
        self.window.timer.stop();self.window.autosave.stop()
        self.window.show();APP.processEvents()

    def tearDown(self):
        self.window.dirty=False
        self.window.close();self.window.deleteLater();APP.processEvents()

    def test_note_selection_reuses_roll_and_navigator_pixels(self):
        w=self.window
        roll=w.roll
        roll.viewport().grab();w.navigator.grab()
        roll_renders=roll.cache_renders;navigator_renders=w.navigator.cache_renders
        w.select_section_contents(0,1,'all_notes')
        roll.viewport().grab();w.navigator.grab()
        self.assertEqual(roll.selected_ids,{w.project.notes[0].id})
        self.assertEqual(roll.cache_renders,roll_renders)
        self.assertEqual(w.navigator.cache_renders,navigator_renders)

    def test_switch_keeps_camera_index_and_other_views(self):
        w=self.window
        w.switch_melody_track(1)
        roll=w.roll;index=roll.note_index()
        view=(roll.horizontalScrollBar().value(),roll.verticalScrollBar().value(),roll.zoom)
        with (
            patch.object(Project,'harmony_notes',side_effect=AssertionError('must reuse harmony')),
            patch.object(w,'sync_views',side_effect=AssertionError('must preserve existing view geometry')),
        ):
            w.switch_melody_track(0)
            w.switch_melody_track(1)
            w.navigator.grab()
        self.assertEqual(view,(roll.horizontalScrollBar().value(),roll.verticalScrollBar().value(),roll.zoom))
        self.assertIs(roll.note_index(),index)

    def test_range_paste_selects_new_chords_and_both_melody_tracks(self):
        w=self.window
        w.roll.setFocus()
        w.selection_changed([[0,3840]])
        original_chords={chord.id for chord in w.project.chords}
        w.copy_selection()
        w.selection_changed([[3840,7680]])
        w.paste_selection()
        self.assertEqual([(n.start,n.pitch) for n in w.roll.selected_notes()],[(3840,60)])
        self.assertTrue(w.roll.selected_chords)
        self.assertFalse(w.roll.selected_chords & original_chords)
        w.switch_melody_track(1)
        self.assertEqual([(n.start,n.pitch) for n in w.roll.selected_notes()],[(4320,67)])
        self.assertTrue(w.roll.selected_chords)
