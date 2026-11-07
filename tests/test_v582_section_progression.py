"""Section progression previews capture the same chords they display."""
import os
import unittest
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication, QDialog, QPushButton
from lingfeng.music.model import Chord, Context, Note, Project
from lingfeng.music.progressions import capture
from lingfeng.ui.progression_dialogs import CaptureProgressionDialog
from lingfeng.ui.section_progression_dialog import SectionProgressionDialog, section_progressions

APP=QApplication.instance() or QApplication([])


def song():
    project=Project()
    project.measures[1].section='Verse'
    project.measures[3].section='Chorus'
    project.contexts=[Context(0,3840,48),Context(3840,project.end,55)]
    project.chords=[Chord(2880,1920,48),Chord(4800,1920,55,notes=[],marked=True),
                    Chord(6720,960,notes=[],recognized=False),
                    Chord(11520,960,notes=[Note(0,960,55)],recognized=False)]
    return project


class SectionProgressionTests(unittest.TestCase):
    def test_crossing_chord_and_symbolic_chord_use_same_preview_and_capture_anchor(self):
        p=song();before=p.to_dict();intro,verse,chorus=section_progressions(p)
        self.assertEqual((intro.first_bar,intro.end_bar,intro.names,intro.roman),(0,1,'C','I'))
        self.assertEqual((verse.first_bar,verse.end_bar,verse.context_tick),(1,3,3840))
        self.assertEqual(verse.chord_ids,{c.id for c in p.chords[:2]})
        self.assertEqual((verse.names,verse.roman),('C – G','IV – I'))
        self.assertEqual(capture(p,verse.chord_ids,context_tick=verse.context_tick),'IV I')
        dialog=CaptureProgressionDialog(p,verse.chord_ids,context_tick=verse.context_tick)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.value()['sequence'],'IV I')
        self.assertEqual(chorus.roman,'?');self.assertTrue(chorus.save_issue)
        self.assertEqual(p.to_dict(),before)

    def test_save_forwards_row_and_jump_closes_with_its_first_bar(self):
        save=Mock(return_value=True)
        dialog=SectionProgressionDialog(song(),save);self.addCleanup(dialog.close);dialog.show()
        adds=dialog.findChildren(QPushButton,'saveSectionProgression')
        jumps=dialog.findChildren(QPushButton,'jumpSectionProgression')
        self.assertEqual(len(adds),3);self.assertFalse(adds[2].isEnabled())
        adds[1].click()
        save.assert_called_once_with(dialog.rows[1].chord_ids,parent=dialog,context_tick=3840)
        self.assertTrue(dialog.isVisible());self.assertTrue(dialog.feedback.text())
        jumps[2].click()
        self.assertEqual(dialog.result(),QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.jump_bar,3);self.assertFalse(dialog.isVisible())

    def test_unmarked_project_has_one_non_saveable_row_when_empty(self):
        p=Project();rows=section_progressions(p)
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0].first_bar,rows[0].end_bar),(0,len(p.measures)))
        self.assertFalse(rows[0].chord_ids);self.assertTrue(rows[0].save_issue)


if __name__=='__main__':unittest.main()
