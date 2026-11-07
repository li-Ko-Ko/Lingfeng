"""Chord cuts preserve source N.C. regions and the clipboard's performed rhythm."""
import copy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtWidgets import QApplication

from lingfeng.music.model import Chord, Note, Project
from lingfeng.ui.main_window import MainWindow
from tests.menu_helpers import find_action


APP=QApplication.instance() or QApplication([])


def rhythm(chord):
    return chord.start,chord.duration,chord.pattern,chord.gate,chord.custom_rhythm,chord.bar_aligned


def performed(chord):
    return [(n.start-chord.start,n.duration,n.pitch,n.velocity) for n in chord.render_notes()]


class ChordCutTests(unittest.TestCase):
    def setUp(self):
        folder=self.enterContext(TemporaryDirectory(dir='tmp'))
        self.folder=Path(folder)
        self.enterContext(patch('lingfeng.ui.main_window.user_data_dir',return_value=self.folder))
        self.enterContext(patch.object(MainWindow,'save_preferences'))
        # Non-bar-aligned adjacent blocks expose accidental gap refilling.
        project=Project(notes=[Note(0,480,72)],instrument_notes=[Note(0,1200,p) for p in (48,52,58)],
                        chords=[Chord(240,1200,48,pattern='offbeat',gate=.65),
                                Chord(1440,1440,53,pattern='up',gate=.8),
                                Chord(2880,1440,55,pattern='block',gate=.5,custom_rhythm=True,
                                      bar_aligned=True,notes=[Note(120,720,43,81),Note(840,360,62,93)])])
        project.fill_chord_gaps()
        self.window=MainWindow(project)
        self.window.timer.stop();self.window.autosave.stop()
        self.window.show();APP.processEvents()

    def tearDown(self):
        self.window.dirty=False;self.window.close();self.window.deleteLater()
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()

    def selected(self):
        return [c for c in self.window.project.chords if c.start in (240,2880)]

    def test_cut_keeps_source_geometry_rhythm_and_neighbors_and_captures_originals(self):
        w=self.window;selected=self.selected();ids={c.id for c in selected}
        before={c.id:copy.deepcopy(c) for c in w.project.chords}
        w.chord_command('cut',ids,w.roll)
        self.assertEqual({c.id for c in w.project.chords},set(before))
        for chord in w.project.chords:
            if chord.id in ids:
                self.assertEqual(rhythm(chord),rhythm(before[chord.id]))
                self.assertEqual(chord.notes,[])
                self.assertEqual(chord.name,'N.C.')
                self.assertEqual(chord.render_notes(),[])
                self.assertFalse(chord.marked)
            else:self.assertEqual(chord,before[chord.id])
        self.assertEqual(w.clipboard_kind,'chords')
        self.assertEqual(w.chord_clipboard.chords,selected)
        self.assertEqual([performed(c) for c in w.chord_clipboard.chords],[performed(c) for c in selected])
        for roll in w.editing_rolls():
            self.assertTrue(roll.has_chord_clipboard)
            self.assertIs(roll.chord_clipboard,w.chord_clipboard)

    def test_context_cut_pastes_original_events_and_undo_redo_restores_source(self):
        w=self.window;chord=self.selected()[0];r=w.roll
        before=w.project.to_dict();events=performed(chord);duration=chord.duration
        w.chord_selection({chord.id},r)
        menu=r.lane.context_menu(QPoint(round(r.lane.x_at(chord.start+100)),18),preserve=True)
        cut=find_action(menu,'剪切所选和弦');copy_action=find_action(menu,'复制所选和弦')
        self.assertLess(menu.actions().index(copy_action),menu.actions().index(cut))
        self.assertTrue(cut.isEnabled());cut.trigger()
        after=w.project.to_dict()
        self.assertEqual(w.project.chord_at(chord.start).name,'N.C.')
        self.assertEqual(len(w.undo_history),1)
        w.undo();self.assertEqual(w.project.to_dict(),before)
        w.redo();self.assertEqual(w.project.to_dict(),after)
        w.chord_command('paste',6000,r)
        pasted=w.project.chord_at(6000)
        self.assertEqual(pasted.duration,duration)
        self.assertEqual(performed(pasted),events)
        self.assertEqual(w.project.chord_at(chord.start).name,'N.C.')

    def test_cut_stays_nc_with_instrument_recognition_and_reload(self):
        w=self.window;chord=self.selected()[0]
        chord.include_instrument_in_recognition=True
        w.project.rescan_instrument_recognition()
        self.assertIsNotNone(chord.instrument_analysis)
        w.chord_command('cut',{chord.id},w.roll)
        result=next(c for c in w.project.chords if c.id==chord.id)
        self.assertEqual(result.name,'N.C.')
        self.assertIsNone(result.instrument_analysis)
        self.assertFalse(result.include_instrument_in_recognition)
        w.project.rescan_instrument_recognition()
        self.assertEqual(result.name,'N.C.')
        path=self.folder/'cut.lfs';w.project.save(path)
        reopened=Project.load(path);reopened.rescan_instrument_recognition()
        self.assertEqual(next(c for c in reopened.chords if c.id==chord.id).name,'N.C.')

    def test_cut_manual_mark_leaves_nc_and_copies_the_original_mark(self):
        from lingfeng.music.recognition import set_marker
        w=self.window;chord=self.selected()[0]
        set_marker(chord,root=53,quality='m7',bass=0)
        before=copy.deepcopy(chord)
        w.chord_command('cut',{chord.id},w.roll)
        result=next(c for c in w.project.chords if c.id==chord.id)
        self.assertEqual(result.name,'N.C.')
        self.assertFalse(result.marked)
        self.assertEqual(rhythm(result),rhythm(before))
        self.assertEqual(w.chord_clipboard.chords,[before])

    def test_keyboard_cut_uses_same_nc_behavior(self):
        w=self.window;chord=self.selected()[0]
        w.chord_selection({chord.id},w.roll)
        with patch.object(w,'active_roll',return_value=w.roll):w.cut_selection()
        result=next(c for c in w.project.chords if c.id==chord.id)
        self.assertEqual(result.name,'N.C.')
        self.assertEqual(rhythm(result),rhythm(chord))
        self.assertEqual(w.chord_clipboard.chords,[chord])

    def test_cut_middle_of_shared_sustain_leaves_neighbors_and_silences_gap(self):
        w=self.window
        project=Project(chords=[Chord(start,960) for start in (0,960,1920)])
        project.set_harmony_notes([Note(0,2880,pitch,77) for pitch in (48,52,55)])
        w.replace_project(project)
        middle=w.project.chord_at(960);before=w.project.to_dict()
        neighbors={c.id:copy.deepcopy(c) for c in w.project.chords if c.id!=middle.id}
        w.chord_command('cut',{middle.id},w.roll)
        self.assertEqual(w.project.chord_at(960).name,'N.C.')
        self.assertEqual(w.project.chord_at(960).render_notes(),[])
        for chord in w.project.chords:
            if chord.id in neighbors:self.assertEqual(chord,neighbors[chord.id])
        audible=w.project.harmony_notes()
        self.assertFalse(any(note.start<1920 and note.end>960 for note in audible))
        self.assertEqual([(n.start,n.duration) for n in audible if n.pitch==48],[(0,960),(1920,960)])
        self.assertEqual(performed(w.chord_clipboard.chords[0]),performed(middle))
        w.undo();self.assertEqual(w.project.to_dict(),before)
        self.assertEqual([(n.start,n.duration) for n in w.project.harmony_notes() if n.pitch==48],[(0,2880)])

    def test_empty_or_failed_cut_keeps_clipboard_and_history(self):
        w=self.window;chord=self.selected()[0]
        w.chord_command('copy',{chord.id},w.roll)
        clipboard=w.chord_clipboard;before=w.project.to_dict()
        w.chord_command('cut',set(),w.roll)
        w.chord_command('cut',{'no-longer-present'},w.roll)
        with patch.object(w,'mutate',return_value=False):w.chord_command('cut',{chord.id},w.roll)
        self.assertIs(w.chord_clipboard,clipboard)
        self.assertEqual(w.clipboard_kind,'chords')
        self.assertEqual(w.project.to_dict(),before)
        self.assertFalse(w.undo_history)


if __name__=='__main__':unittest.main()
