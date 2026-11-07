"""Traditional-score checks follow the selected melodies and preserve music."""
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPlainTextEdit, QWidget

from lingfeng.engraving.compatibility import melody_overlap, traditional_conflicts
from lingfeng.music.model import Chord, Measure, Note, PPQ, Project
from lingfeng.platform.i18n import tr
from lingfeng.ui.score_compatibility_dialog import (
    show_traditional_compatibility, traditional_compatibility_report,
)


APP=QApplication.instance() or QApplication([])


class TraditionalCompatibilityTests(unittest.TestCase):
    def project(self):
        project=Project(notes=[Note(0,PPQ,60),Note(PPQ,PPQ,62)],
                        instrument_notes=[Note(0,PPQ,67),Note(PPQ-1,PPQ,69)],
                        chords=[Chord(0,4*PPQ,48)])
        project.notation.update(show_melody=True,show_instrument=True,show_chords=True)
        return project

    def test_hidden_instrument_is_not_checked_and_chord_polyphony_is_allowed(self):
        project=self.project();before=copy.deepcopy(project.to_dict())
        self.assertEqual(set(traditional_conflicts(project)),{1})
        self.assertFalse(melody_overlap(project,dict(project.notation,show_instrument=False)))
        self.assertEqual(project.to_dict(),before)

    def test_only_selected_melody_tracks_are_inspected(self):
        project=self.project()
        project.notes.append(Note(0,PPQ,64))
        self.assertEqual(set(traditional_conflicts(project)),{0,1})
        self.assertEqual(set(traditional_conflicts(project,{'show_melody':False})),{1})
        with patch.object(Project,'melody_notes',side_effect=AssertionError('hidden tracks must not be inspected')):
            self.assertFalse(melody_overlap(project,{'show_melody':False,'show_instrument':False}))

    def test_one_tick_overlap_is_a_conflict_and_adjacent_notes_are_legal(self):
        project=self.project()
        conflicts=traditional_conflicts(project)
        self.assertEqual([(c.start,c.end) for c in conflicts[1]],[(PPQ-1,PPQ)])
        project.instrument_notes[1].start=PPQ
        self.assertEqual(traditional_conflicts(project),{})

    def test_report_uses_track_names_and_first_bar_beat_in_mixed_meter(self):
        project=self.project();project.melody_names=['Lead','Piano']
        project.measures=[Measure(3,4),Measure(6,8)]
        project.instrument_notes=[Note(3*PPQ,PPQ,67),Note(3*PPQ+PPQ//2,PPQ,69)]
        report=traditional_compatibility_report(project)
        self.assertIn('Piano',report)
        self.assertNotIn('Lead',report)
        self.assertIn(tr('第 {0} 小节，第 {1} 拍',2,'2'),report)
        self.assertIn(tr('必须修改'),report)
        project.notation['show_instrument']=False
        report=traditional_compatibility_report(project)
        self.assertNotIn('Piano',report)
        self.assertNotIn(tr('必须修改'),report)

    def test_dialog_is_readonly_with_close_only_and_does_not_modify_project(self):
        project=self.project();before=copy.deepcopy(project.to_dict())
        parent=QWidget();self.addCleanup(parent.close)
        shown=[]
        def inspect(dialog):
            shown.append(dialog)
            self.assertIs(dialog.parentWidget(),parent)
            self.assertEqual(dialog.windowTitle(),tr('传统简谱兼容性检查'))
            field=dialog.findChild(QPlainTextEdit)
            self.assertTrue(field.isReadOnly())
            self.assertEqual(field.toPlainText(),traditional_compatibility_report(project))
            buttons=dialog.findChild(QDialogButtonBox)
            self.assertEqual(buttons.standardButtons(),QDialogButtonBox.StandardButton.Close)
            return 0
        with patch('lingfeng.ui.score_compatibility_dialog.QDialog.exec',inspect):
            self.assertIsNone(show_traditional_compatibility(parent,project))
        self.assertEqual(len(shown),1)
        self.assertEqual(project.to_dict(),before)


if __name__=='__main__':unittest.main()
