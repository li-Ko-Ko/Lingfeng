"""User-visible annotation commands and creation preferences through the editors."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from lingfeng.audio.midi import event_list
from lingfeng.music.model import Project, Chord, Note
from lingfeng.platform import chord_preferences as preferences
from lingfeng.ui.dialogs import ChordDialog, ChordMarkerDialog
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.piano_roll import PianoRoll

APP=QApplication.instance() or QApplication([])


class ChordUiTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(preferences.set_preferences, preferences.settings_dict())
        preferences.load_preferences({})

    def test_editor_always_uses_default_velocity_and_selected_quality_order(self):
        preferences.set_preferences(dict(default_velocities=dict(melody=45,harmony=101),quick_chord_qualities=['m7','7','']))
        p=Project();c=Chord(0,1920,velocity=36)
        first=ChordDialog(c,p,defaults=dict(quality='7',velocity=11));self.addCleanup(first.close)
        self.assertEqual(first.velocity.value(),101)
        self.assertEqual([first.quality.itemData(i) for i in range(first.quality.count())],['m7','7',''])
        first.velocity.setValue(65);saved=first.options();self.assertNotIn('velocity',saved)
        second=ChordDialog(c,p,defaults=saved);self.addCleanup(second.close)
        self.assertEqual(second.velocity.value(),101)
        p.chords=[c];roll=PianoRoll(p);self.addCleanup(roll.close)
        menu=roll.lane.context_menu(QPoint(round(roll.lane.x_at(100)),18));self.addCleanup(menu.close)
        self.assertEqual([a.data() for a in menu.quality_menu.actions()],['m7','7',''])
        c.notes=[Note(0,800,64,36)]
        preserved=ChordDialog(c,p);self.addCleanup(preserved.close)
        preserved.regenerate.setChecked(False)
        self.assertEqual(preserved.value().notes[0].velocity,36)

    def test_current_add9_edit_memory_retains_compound_quality(self):
        preferences.set_preferences(dict(quick_chord_qualities=['add9','']))
        p=Project();c=Chord(0,1920,quality='add9')
        first=ChordDialog(c,p,defaults=dict(quality='add9'));self.addCleanup(first.close)
        second=ChordDialog(c,p,defaults=first.options());self.addCleanup(second.close)
        self.assertEqual(second.quality.currentData(),'add9');self.assertIn(62,second.value().pitches)

    def test_editor_uses_pychord_names_for_lossless_choices(self):
        preferences.set_preferences(dict(quick_chord_qualities=['maj9','mM7','M7']))
        p=Project();dialog=ChordDialog(Chord(0,1920,quality='maj9'),p);self.addCleanup(dialog.close)
        self.assertEqual([dialog.quality.itemData(i) for i in range(dialog.quality.count())
                          if dialog.quality.model().item(i).isEnabled()],['mM7','M7'])
        index=dialog.quality.findData('mM7')
        self.assertTrue(dialog.quality.itemText(index).startswith('mM7'))
        dialog.quality.setCurrentIndex(index)
        self.assertIn('CmM7',dialog.preview.text())
        self.assertNotIn('m(maj7)',dialog.preview.text())

    def test_actual_draw_input_uses_each_roll_default(self):
        preferences.set_preferences(dict(default_velocities=dict(melody=41,instrument=59,harmony=109)))
        for role,track,expected in [('melody',0,41),('melody',1,59),('harmony',0,109)]:
            roll=PianoRoll(Project(),role=role);self.addCleanup(roll.close)
            roll.melody_track=track
            roll.resize(900,500);roll.show();roll.center_pitch(60);APP.processEvents();roll.tool='draw'
            received=[];roll.noteAdded.connect(received.append)
            point=QPoint(round(roll.x_at(120)),round(roll.y_at(60)+roll.row_height/2))
            QTest.mouseClick(roll.viewport(),Qt.MouseButton.LeftButton,pos=point)
            self.assertEqual(len(received),1,(role,point))
            self.assertEqual(received[0].velocity,expected)

    def test_harmony_creation_follows_each_current_region_and_blank_space_default(self):
        preferences.set_preferences(dict(default_velocities=dict(melody=41,harmony=109)))
        project=Project();project.chords=[Chord(0,1920,velocity=67),Chord(1920,1920,velocity=105)]
        roll=PianoRoll(project,role='harmony');self.addCleanup(roll.close)
        roll.resize(1000,640);roll.show();roll.center_pitch(72);APP.processEvents()
        received=[];roll.noteAdded.connect(received.append)
        def create(tick,tool):
            roll.tool=tool
            point=QPoint(round(roll.x_at(tick)+8),round(roll.y_at(72)+roll.row_height/2))
            if tool=='draw':QTest.mouseClick(roll.viewport(),Qt.MouseButton.LeftButton,pos=point)
            else:QTest.mouseDClick(roll.viewport(),Qt.MouseButton.LeftButton,pos=point)
        create(960,'draw');create(1920,'smart');create(3840,'draw')
        self.assertEqual([note.velocity for note in received],[67,105,109])
        project.chords[0].velocity=52
        create(480,'smart')
        self.assertEqual(received[-1].velocity,52)
        self.assertIsNone(project.chords[0].notes)

    def test_auto_filled_blank_harmony_regions_use_the_saved_default(self):
        preferences.set_preferences(dict(default_velocities=dict(melody=41,harmony=109)))
        project=Project();project.fill_chord_gaps()
        roll=PianoRoll(project,role='harmony');self.addCleanup(roll.close)
        roll.resize(1000,640);roll.show();roll.center_pitch(72);APP.processEvents()
        received=[];roll.noteAdded.connect(received.append);roll.tool='draw'
        point=QPoint(round(roll.x_at(960)+8),round(roll.y_at(72)+roll.row_height/2))
        QTest.mouseClick(roll.viewport(),Qt.MouseButton.LeftButton,pos=point)
        self.assertEqual([note.velocity for note in received],[109])

    def test_marker_menu_commands_preserve_midi_and_support_history(self):
        with tempfile.TemporaryDirectory(dir='tmp') as directory:
            with patch('lingfeng.ui.main_window.user_data_dir',return_value=Path(directory)):
                p=Project();p.chords=[Chord(0,1920)]
                window=MainWindow(p);self.addCleanup(lambda:(setattr(window,'dirty',False),window.close()))
                window.timer.stop();window.autosave.stop();window.transport.audition=lambda *a,**k:None
                chord=window.project.chords[0];cid=chord.id;before=event_list(window.project)
                original=copy.deepcopy(window.project.to_dict())
                def accept(dialog):
                    self.assertFalse(hasattr(dialog,'velocity'))
                    dialog.root.setCurrentIndex(dialog.root.findData(2));dialog.quality.setCurrentIndex(dialog.quality.findData('m7'))
                    dialog.bass.setCurrentIndex(dialog.bass.findData(5));self.assertIn('Dm7/F',dialog.preview.text())
                    return QDialog.DialogCode.Accepted
                with patch.object(ChordMarkerDialog,'exec',accept):window.chord_command('mark',cid,window.roll)
                marked=copy.deepcopy(window.project.to_dict());c=window.project.chords[0]
                self.assertTrue(c.marked and c.recognition_disabled);self.assertEqual(c.name,'Dm7/F')
                self.assertEqual(event_list(window.project),before)
                menu=window.roll.lane.context_menu(QPoint(round(window.roll.lane.x_at(100)),18));self.addCleanup(menu.close)
                self.assertTrue(menu.recognition_action.isChecked());self.assertTrue(menu.custom_rhythm_action.isChecked())
                self.assertFalse(menu.custom_rhythm_action.isEnabled());self.assertFalse(menu.quality_menu.isEnabled())
                window.undo();self.assertEqual(window.project.to_dict(),original)
                window.redo();self.assertEqual(window.project.to_dict(),marked)
                window.chord_command('recognition:0',{cid},window.roll)
                c=window.project.chords[0];self.assertFalse(c.marked or c.recognition_disabled)
                self.assertEqual(c.name,'C');self.assertEqual(event_list(window.project),before)
                window.undo();self.assertTrue(window.project.chords[0].marked)
                self.assertEqual(Project.from_dict(window.project.to_dict()).to_dict(),window.project.to_dict())

    def test_recognition_name_menu_keeps_performance_and_roundtrips_combined_choice(self):
        from lingfeng.music.chord_operations import contextual_chord_name, roman_label
        with tempfile.TemporaryDirectory(dir='tmp') as directory:
            with patch('lingfeng.ui.main_window.user_data_dir',return_value=Path(directory)):
                p=Project(chords=[Chord(0,1920,notes=[Note(0,900,pitch) for pitch in (48,64,67)],
                                        include_instrument_in_recognition=True)],
                          instrument_notes=[Note(0,960,69)])
                window=MainWindow(p);self.addCleanup(lambda:(setattr(window,'dirty',False),window.close()))
                window.timer.stop();window.autosave.stop()
                chord=window.project.chords[0];self.assertEqual(chord.name,'C6')
                before=event_list(window.project)
                menu=window.roll.lane.context_menu(QPoint(round(window.roll.lane.x_at(100)),18));self.addCleanup(menu.close)
                other=next(a for a in menu.recognition_names_menu.actions() if 'Am7/C' in a.text())
                self.assertIn('vi7/1',other.text())
                other.trigger()
                chord=window.project.chords[0]
                self.assertEqual(contextual_chord_name(window.project,chord),'Am7/C')
                self.assertEqual(roman_label(window.project,chord),'vi7/1')
                self.assertEqual(event_list(window.project),before)
                self.assertEqual(chord.quality,'')
                restored=Project.from_dict(json.loads(json.dumps(window.project.to_dict())))
                self.assertEqual(restored.chords[0].name,'Am7/C')
                window.undo();self.assertEqual(window.project.chords[0].name,'C6')
                window.redo();self.assertEqual(window.project.chords[0].name,'Am7/C')


if __name__=='__main__':unittest.main()
