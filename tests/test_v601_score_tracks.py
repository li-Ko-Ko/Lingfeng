"""Traditional notation checks only the melodies included in the score."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from lingfeng.audio.midi import export_midi
from lingfeng.engraving.notation import export_pdf
from lingfeng.music.model import Chord, Note, Project
from lingfeng.platform import i18n
from lingfeng.ui.export_dialog import ExportDialog
from lingfeng.ui.main_window import MainWindow

APP=QApplication.instance() or QApplication([])


def project():
    p=Project(notes=[Note(0,960,60),Note(960,960,62)],
              instrument_notes=[Note(0,960,48),Note(0,960,55)],
              chords=[Chord(0,3840,notes=[Note(0,3840,p) for p in (48,52,55)])])
    p.fill_chord_gaps()
    return p


class TraditionalTrackTests(unittest.TestCase):
    def setUp(self):
        temporary=self.enterContext(tempfile.TemporaryDirectory(dir='tmp'))
        self.folder=Path(temporary)
        self.enterContext(patch.dict(os.environ,{'LINGFENG_USER_DATA':str(self.folder/'user'),
                                                'LINGFENG_SYNTH_CACHE':str(self.folder/'synth-index.json')}))
        self.enterContext(patch.object(MainWindow,'save_preferences'))
        self.report=self.enterContext(patch('lingfeng.ui.score_compatibility_dialog.show_traditional_compatibility'))
        self.addCleanup(i18n.set_language,i18n.LANGUAGE)
        self.windows=[];self.addCleanup(self.close_windows)

    def close_windows(self):
        for window in self.windows:
            window.dirty=False;window.close();window.deleteLater()
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()

    def window(self,p=None):
        window=MainWindow(p or project());window.timer.stop();window.autosave.stop()
        self.windows.append(window);window.show();APP.processEvents()
        return window

    def traditional_option(self,w):
        return w.score_style.model().item(w.score_style.findData('traditional'))

    def test_hidden_polyphonic_instrument_switches_and_exports_vocal_chords_only(self):
        w=self.window();before=copy.deepcopy(w.project.instrument_notes);midi=export_midi(w.project,None)
        w.set_notation('show_instrument',False)
        w.switch_workspace('score')
        w.set_notation('style','traditional')
        self.assertEqual(w.project.notation['style'],'traditional')
        self.assertFalse(w.score_tracks['show_instrument'].isEnabled())
        self.assertFalse(w.score_tracks['show_instrument'].isChecked())
        self.assertTrue(w.score_tracks['show_melody'].isEnabled())
        self.assertTrue(w.score_tracks['show_chords'].isEnabled())
        self.assertTrue(self.traditional_option(w).isEnabled())
        self.report.assert_not_called()
        self.assertEqual(w.project.instrument_notes,before)
        self.assertEqual(export_midi(w.project,None),midi)
        self.assertTrue(all(1 not in system.tracks for system in w.score_view.canvas.layout.systems))
        dialog=ExportDialog(w,'pdf');self.addCleanup(dialog.close)
        self.assertNotIn('instrument',dialog.tracks.roles())
        self.assertTrue(dialog.export_button.isEnabled())
        self.assertEqual(export_pdf(dialog.project,self.folder/'vocal-chords.pdf',pages=[0]),1)

    def test_enabled_polyphonic_track_reports_and_reverts_combobox_without_history(self):
        w=self.window();w.switch_workspace('score')
        before=copy.deepcopy(w.project.to_dict());history=list(w.undo_history)
        w.score_style.setCurrentIndex(w.score_style.findData('traditional'))
        self.report.assert_called_once_with(w,w.project)
        self.assertEqual(w.project.to_dict(),before)
        self.assertEqual(w.undo_history,history)
        self.assertEqual(w.score_style.currentData(),'spatial')
        self.assertTrue(self.traditional_option(w).isEnabled())

    def test_disallowed_checkbox_cannot_be_enabled_programmatically(self):
        w=self.window();w.set_notation('show_instrument',False)
        w.set_notation('style','traditional');before=copy.deepcopy(w.project.to_dict())
        history=list(w.undo_history);check=w.score_tracks['show_instrument']
        self.assertFalse(check.isEnabled())
        check.setChecked(True)
        self.assertFalse(check.isChecked())
        self.assertFalse(w.project.notation['show_instrument'])
        self.assertEqual(w.project.to_dict(),before);self.assertEqual(w.undo_history,history)
        self.report.assert_not_called()

    def test_repair_unlocks_hidden_track_and_replaces_incompatible_music_snapshot(self):
        w=self.window();w.set_notation('show_instrument',False)
        w.switch_workspace('score');w.set_notation('style','traditional')
        self.assertEqual(len(w.score_view.canvas.project.instrument_notes),2)
        w.mutate('repair instrument',lambda p:p.instrument_notes.pop(),source='melody')
        self.assertTrue(w.score_tracks['show_instrument'].isEnabled())
        self.assertEqual(len(w.score_view.canvas.project.instrument_notes),2)
        w.score_tracks['show_instrument'].setChecked(True)
        self.assertTrue(w.project.notation['show_instrument'])
        self.assertEqual(w.project.notation['style'],'traditional')
        self.assertEqual(w.score_view.canvas.project.instrument_notes,w.project.instrument_notes)
        self.assertEqual(len(w.score_view.canvas.project.instrument_notes),1)
        self.report.assert_not_called()

    def test_leaving_traditional_unlocks_polyphonic_instrument(self):
        w=self.window();w.set_notation('show_instrument',False)
        w.set_notation('style','traditional')
        self.assertFalse(w.score_tracks['show_instrument'].isEnabled())
        w.set_notation('style','compact')
        self.assertTrue(w.score_tracks['show_instrument'].isEnabled())
        w.score_tracks['show_instrument'].setChecked(True)
        self.assertTrue(w.project.notation['show_instrument'])
        w.set_notation('style','traditional')
        self.report.assert_called_once_with(w,w.project)
        self.assertEqual(w.project.notation['style'],'compact')

    def test_hidden_polyphonic_vocal_is_ignored_and_locked_symmetrically(self):
        p=project();p.notes,p.instrument_notes=p.instrument_notes,p.notes
        w=self.window(p);w.set_notation('show_melody',False)
        w.switch_workspace('score');w.set_notation('style','traditional')
        self.assertEqual(w.project.notation['style'],'traditional')
        self.assertFalse(w.score_tracks['show_melody'].isEnabled())
        self.assertTrue(w.score_tracks['show_instrument'].isEnabled())
        self.assertTrue(all(0 not in system.tracks for system in w.score_view.canvas.layout.systems))
        self.report.assert_not_called()

    def test_saved_traditional_with_hidden_polyphonic_track_reopens_without_fallback(self):
        p=project();p.notation.update(style='traditional',show_instrument=False,font_layout_version=45)
        path=self.folder/'hidden-instrument.lfs';p.save(path)
        w=self.window(Project.load(path));before=copy.deepcopy(w.project.instrument_notes)
        self.assertEqual(w.project.notation['style'],'traditional');self.assertFalse(w.dirty)
        self.assertTrue(w.switch_workspace('score'))
        self.assertEqual(w.project.notation['style'],'traditional')
        self.assertEqual(w.project.instrument_notes,before)
        self.assertFalse(w.score_tracks['show_instrument'].isEnabled())
        self.report.assert_not_called()


if __name__=='__main__':unittest.main()
