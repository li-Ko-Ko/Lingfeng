"""Independent melody editing, section selection and MIDI routing."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from lingfeng.audio.events import INSTRUMENT_CHANNEL
from lingfeng.audio.midi import event_list, export_midi
from lingfeng.music.bar_operations import delete_bars
from lingfeng.music.model import Chord, Note, Project
from lingfeng.platform.i18n import tr
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.keybindings import load_bindings

APP=QApplication.instance() or QApplication([])


class MelodyTrackTests(unittest.TestCase):
    def test_legacy_load_and_both_melodies_survive_bar_edits(self):
        legacy=Project().to_dict()
        legacy.pop('instrument_notes')
        p=Project.from_dict(legacy)
        p.add_note(Note(3840,480,60))
        p.add_note(Note(3840,480,60),track=1)
        p.insert_measure(1)
        self.assertEqual([p.melody_notes(track)[0].start for track in (0,1)],[7680,7680])
        delete_bars(p,[1])
        self.assertEqual([p.melody_notes(track)[0].start for track in (0,1)],[3840,3840])
        p.change_meter(0,3,4)
        self.assertEqual(Project.from_dict(p.to_dict()).instrument_notes[0].start,2880)

    def test_simultaneous_equal_pitches_have_independent_midi_channels(self):
        p=Project(notes=[Note(0,480,60)],instrument_notes=[Note(0,960,60)])
        events=event_list(p)
        self.assertEqual([(t,ch) for t,on,ch,_,_ in events if not on],[(480,0),(960,INSTRUMENT_CHANNEL)])
        midi=export_midi(p,None)
        self.assertEqual(int.from_bytes(midi[10:12],'big'),4)
        self.assertIn(b'Ins Melody',midi)


class MelodyEditorTests(unittest.TestCase):
    def setUp(self):
        project=Project(notes=[Note(3500,500,60),Note(9000,240,67)],
                        instrument_notes=[Note(3900,240,64)])
        project.measures[1].section='Verse'
        project.measures[2].section='Chorus'
        project.chords=[Chord(3000,1100,notes=[]),Chord(4100,480,notes=[Note(0,240,55)])]
        with patch.object(MainWindow,'save_preferences'):
            self.window=MainWindow(project)
        self.window.timer.stop();self.window.autosave.stop()
        self.window.show();APP.processEvents()

    def tearDown(self):
        self.window.dirty=False
        self.window.close();self.window.deleteLater();APP.processEvents()

    def test_tab_targets_and_undo_restore_the_edited_roll(self):
        w=self.window
        original=w.project.notes[0].id
        w.melody_tabs.setCurrentIndex(1)
        added=Note(4200,240,60)
        self.assertTrue(w.edit_notes(w.roll,[added],[]))
        self.assertEqual(w.project.notes[0].id,original)
        self.assertIn(added.id,{n.id for n in w.project.instrument_notes})
        w.melody_tabs.setCurrentIndex(0)
        w.undo()
        self.assertEqual(w.melody_tabs.currentIndex(),1)
        self.assertNotIn(added.id,{n.id for n in w.project.instrument_notes})
        w.redo()
        self.assertIn(added.id,{n.id for n in w.roll.notes})

    def test_section_selects_intersecting_notes_and_chords_by_onset(self):
        w=self.window
        r=w.roll
        menu=r.timeline_menu(QPoint(round(r.x_at(4000)),8))
        section=menu.section_selection_menu
        next(a for a in section.actions() if a.text()==tr('三个卷帘的音符')).trigger()
        self.assertEqual(r.selected_ids,{w.project.notes[0].id})
        self.assertEqual(len(w.harmony_window.roll.selected_ids),1)
        w.melody_tabs.setCurrentIndex(1)
        self.assertEqual(r.selected_ids,{w.project.instrument_notes[0].id})
        next(a for a in section.actions() if a.text()==tr('起点在段落内的和弦')).trigger()
        self.assertEqual(w.chord_lane.highlight_ids,{c.id for c in w.project.chords if 3840<=c.start<7680})
        menu.deleteLater()

    def test_compose_float_button_detaches_only_the_selected_melody(self):
        w=self.window
        w.melody_tabs.setCurrentIndex(1)
        w.melody_float.activated.emit()
        APP.processEvents()
        instrument=w.melody_floats[1]
        self.assertTrue(instrument.isWindow())
        self.assertTrue(instrument.isVisible())
        self.assertFalse(w.melody_tabs.isTabVisible(1))
        self.assertTrue(w.melody_window.isVisible())
        self.assertEqual(w.roll.melody_track,0)
        self.assertEqual(instrument.roll.melody_track,1)
        self.assertIs(w.active_roll(),instrument.roll)
        self.assertEqual(w.midi_input.target,'instrument')

        w.melody_float.activated.emit()
        APP.processEvents()
        vocal=w.melody_floats[0]
        self.assertTrue(vocal.isVisible() and instrument.isVisible())
        self.assertFalse(w.melody_window.isVisible())
        added=Note(4320,240,72)
        instrument.roll.noteAdded.emit(added)
        self.assertNotIn(added.id,{n.id for n in w.project.notes})
        self.assertIn(added.id,{n.id for n in w.project.instrument_notes})
        w.undo()
        self.assertNotIn(added.id,{n.id for n in instrument.roll.notes})
        w.redo()
        self.assertIn(added.id,{n.id for n in instrument.roll.notes})

        instrument.title_bar.dock.activated.emit()
        APP.processEvents()
        self.assertTrue(vocal.isFloating() and vocal.isVisible())
        self.assertFalse(instrument.isFloating())
        self.assertTrue(w.melody_tabs.isTabVisible(1))
        self.assertEqual(w.roll.melody_track,1)
        self.assertIn(added.id,{n.id for n in w.roll.notes})
        vocal.close()
        self.assertTrue(w.melody_tabs.isTabVisible(0))

    def test_floating_melodies_keep_local_view_across_workspace_and_language(self):
        w=self.window
        for track in (0,1):
            w.set_melody_floating(track,True,focus=False)
        APP.processEvents()
        vocal=w.melody_floats[0]
        instrument=w.melody_floats[1]
        vocal.roll.zoom_at(1.7);vocal.roll.horizontalScrollBar().setValue(500)
        instrument.grid.setCurrentIndex(3)
        zoom,scroll,grid=vocal.roll.zoom,vocal.roll.horizontalScrollBar().value(),instrument.roll.grid
        w.switch_workspace('score')
        self.assertFalse(vocal.isVisible() or instrument.isVisible())
        w.switch_workspace('compose')
        self.assertTrue(vocal.isVisible() and instrument.isVisible())
        self.assertEqual(vocal.roll.horizontalScrollBar().value(),scroll)

        w.change_language('en' if w.language=='zh' else 'zh',persist=False)
        APP.processEvents()
        vocal=w.melody_floats[0]
        instrument=w.melody_floats[1]
        self.assertTrue(vocal.isVisible() and instrument.isVisible())
        self.assertEqual((vocal.roll.zoom,vocal.roll.horizontalScrollBar().value(),instrument.roll.grid),
                         (zoom,scroll,grid))

    def test_close_and_view_toggle_each_melody_without_empty_tabs(self):
        w=self.window
        vocal,instrument=(w.melody_view_actions[track] for track in (0,1))
        actions=w.visibility_button.menu().actions()
        self.assertIn(vocal,actions)
        self.assertIn(instrument,actions)
        self.assertNotIn(w.visibility_actions['melody'],actions)
        self.assertEqual([vocal.text(),instrument.text()],[w.project.melody_name(track) for track in (0,1)])
        self.assertTrue(w.melody_title.isHidden())
        w.melody_tabs.setCurrentIndex(1)
        w.melody_hide.activated.emit()
        self.assertTrue(vocal.isChecked())
        self.assertFalse(instrument.isChecked())
        self.assertTrue(w.melody_window.isVisible())
        self.assertTrue(w.melody_tabs.isHidden())
        self.assertTrue(w.melody_title.isVisible())
        self.assertEqual(w.melody_title.text(),w.project.melody_name(0))
        self.assertEqual(w.roll.melody_track,0)
        self.assertEqual(w.roll.notes,w.project.notes)

        w.melody_hide.activated.emit()
        self.assertTrue(w.melody_window.isHidden())
        self.assertTrue(w.melody_title.isHidden())
        instrument.trigger()
        self.assertTrue(w.melody_window.isVisible())
        self.assertTrue(w.melody_tabs.isHidden())
        self.assertTrue(w.melody_title.isVisible())
        self.assertEqual(w.melody_title.text(),w.project.melody_name(1))
        self.assertEqual(w.roll.melody_track,1)
        self.assertEqual(w.roll.notes,w.project.instrument_notes)
        vocal.trigger()
        self.assertTrue(w.melody_tabs.isVisible())
        self.assertTrue(w.melody_title.isHidden())

    def test_single_melody_title_follows_track_name_and_replacement_project(self):
        w=self.window
        w.set_melody_floating(0,True,focus=False)
        self.assertTrue(w.melody_title.isVisible())
        self.assertEqual(w.melody_title.text(),w.project.melody_name(1))

        name='<奏鸣>'
        with patch('lingfeng.ui.workspace.QInputDialog.getText',return_value=(name,True)):
            w.rename_melody_track(1)
        self.assertEqual(w.melody_title.text(),name)

        project=Project(melody_names=['歌唱','弦乐'],instrument_notes=[Note(0,240,67)])
        w.replace_project(project)
        self.assertTrue(w.melody_title.isVisible())
        self.assertEqual(w.melody_title.text(),'弦乐')
        self.assertEqual(w.roll.notes,project.instrument_notes)

    def test_hidden_melody_float_reopens_in_place_across_layout_restore(self):
        w=self.window
        w.set_melody_floating(1,True,focus=False)
        float_roll=w.melody_floats[1]
        w.melody_view_actions[1].setChecked(False)
        self.assertTrue(float_roll.isFloating())
        self.assertTrue(float_roll.isHidden())
        self.assertTrue(w.melody_window.isVisible())
        w.switch_workspace('score')
        w.switch_workspace('compose')
        self.assertTrue(float_roll.isHidden())

        w.change_language('en' if w.language=='zh' else 'zh',persist=False)
        float_roll=w.melody_floats[1]
        self.assertTrue(float_roll.isHidden())
        self.assertFalse(w.melody_view_actions[1].isChecked())
        w.melody_view_actions[1].setChecked(True)
        APP.processEvents()
        self.assertTrue(float_roll.isFloating())
        self.assertTrue(float_roll.isVisible())
        self.assertTrue(w.melody_view_actions[0].isChecked())
        self.assertTrue(w.melody_window.isVisible())
        self.assertTrue(w.melody_tabs.isHidden())

    def test_cycle_shortcut_focuses_all_open_rolls_and_skips_hidden_float(self):
        w=self.window
        w.keybindings=load_bindings({})
        w.set_melody_floating(0,True,focus=False)
        w.set_melody_floating(1,True,focus=False)
        w.open_harmony()
        vocal=w.melody_floats[0].roll
        instrument=w.melody_floats[1].roll
        harmony=w.harmony_window.roll
        w.focus_input_roll(vocal);APP.processEvents()

        for target,role in ((instrument,'instrument'),(harmony,'chords'),(vocal,'melody')):
            QTest.keyClick(w.active_roll(),Qt.Key.Key_Tab,Qt.KeyboardModifier.ControlModifier)
            APP.processEvents()
            self.assertIs(w.active_roll(),target)
            self.assertEqual(w.midi_input.target,role)

        w.melody_view_actions[1].setChecked(False)
        QTest.keyClick(vocal,Qt.Key.Key_Tab,Qt.KeyboardModifier.ControlModifier);APP.processEvents()
        self.assertIs(w.active_roll(),harmony)
        self.assertFalse(w.melody_floats[1].isVisible())

    def test_cycle_shortcut_can_be_rebound_and_switches_docked_melody_tabs(self):
        w=self.window
        w.keybindings=load_bindings({'cycle_roll':'F8'})
        w.focus_input_roll(w.roll);APP.processEvents()
        QTest.keyClick(w.roll,Qt.Key.Key_F8)
        self.assertEqual(w.roll.melody_track,1)
        self.assertEqual(w.midi_input.target,'instrument')
        QTest.keyClick(w.roll,Qt.Key.Key_F8)
        self.assertEqual(w.roll.melody_track,0)
        self.assertFalse(w.visibility_actions['harmony'].isChecked())
        self.assertEqual(w.keybindings['switch_input'],'E')

    def test_cycle_shortcut_selects_open_score_panels_including_inactive_tabs(self):
        w=self.window
        w.keybindings=load_bindings({})
        w.switch_workspace('score')
        w.show_score_panel('harmony')
        w.show_score_panel('melody')
        w.switch_melody_track(0)
        w.focus_input_roll(w.roll);APP.processEvents()
        QTest.keyClick(w.roll,Qt.Key.Key_Tab,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w.roll.melody_track,1)
        QTest.keyClick(w.roll,Qt.Key.Key_Tab,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w.current_score_panel(),'harmony')
        self.assertEqual(w.midi_input.target,'chords')
        QTest.keyClick(w.harmony_window.roll,Qt.Key.Key_Tab,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w.current_score_panel(),'melody')
        self.assertEqual(w.roll.melody_track,0)
