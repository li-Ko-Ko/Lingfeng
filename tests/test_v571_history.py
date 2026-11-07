"""Shared undo records retain JSON compatibility and independent live music."""
import copy
import gc
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import weakref

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Chord,Note,Project
from lingfeng.ui.history import HistoryState
from lingfeng.ui.main_window import MainWindow

APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]


def project():
    p=Project()
    p.notes=[Note(i*480,240,60+i%5,75+i%8) for i in range(12)]
    p.chords=[Chord(0,3840,notes=[Note(0,1920,pitch,76) for pitch in (36,48,52,55)])]
    p.fill_chord_gaps()
    p.notation['lyric_events']=[dict(id='lyric-'+str(i),tick=n.start,text=text,verse=0,voice=0,pitch=n.pitch)
                                for i,(n,text) in enumerate(zip(p.notes,('我','爱','你')))]
    return p


class SharedHistoryTests(unittest.TestCase):
    def test_inserts_and_changes_reuse_only_equal_stable_id_records(self):
        p=project();first=HistoryState(p.to_dict(),{'surface':'melody'})
        old=copy.deepcopy(first)
        p.notes[3].velocity=101
        p.notes.insert(0,Note(120,120,72))
        p.chords[0].notes[2].velocity=49
        p.notation['lyric_events'][1]['text']='LOVE'
        second=HistoryState(p.to_dict(),{'surface':'score'},first)
        self.assertIs(second['measures'],first['measures'])
        self.assertIs(second['audio'],first['audio'])
        self.assertIs(second['notes'][1],first['notes'][0])
        self.assertIs(second['notes'][3],first['notes'][2])
        self.assertIsNot(second['notes'][4],first['notes'][3])
        self.assertIs(second['chords'][0]['notes'][0],first['chords'][0]['notes'][0])
        self.assertIsNot(second['chords'][0]['notes'][2],first['chords'][0]['notes'][2])
        self.assertIs(second['notation']['lyric_events'][0],first['notation']['lyric_events'][0])
        self.assertIsNot(second['notation']['lyric_events'][1],first['notation']['lyric_events'][1])
        self.assertEqual(first,old)
        self.assertEqual(json.loads(json.dumps(second)),p.to_dict())
        self.assertNotIn('location',json.loads(json.dumps(second)))
        self.assertEqual(second.location,{'surface':'score'})

    def test_restoring_and_mutating_project_never_changes_shared_snapshots(self):
        p=project();first=HistoryState(p.to_dict(),None)
        p.bpm=112;second=HistoryState(p.to_dict(),None,first)
        self.assertIs(first['notes'],second['notes'])
        before=json.dumps([first,second],sort_keys=True)
        restored=Project.from_dict(second)
        restored.notes[0].pitch=79
        restored.chords[0].notes[0].velocity=19
        restored.notation['lyric_events'][0]['text']='changed'
        restored.audio['melody']['program']=99
        restored.volumes['melody']=15
        self.assertEqual(json.dumps([first,second],sort_keys=True),before)
        self.assertNotEqual(restored.to_dict(),second)
        duplicate=copy.deepcopy(second);duplicate['notes'][0]['pitch']=33
        self.assertEqual(json.dumps([first,second],sort_keys=True),before)

    def test_nested_numeric_types_are_preserved_and_removed_records_do_not_leak(self):
        data=project().to_dict();data['notation']['extra']={'values':[0,15]}
        first=HistoryState(data,None)
        newer=copy.deepcopy(data);newer['notation']['extra']['values']=[False,15.0]
        newer['notes'].pop(2)
        second=HistoryState(newer,None,first)
        self.assertIs(type(second['notation']['extra']['values'][0]),bool)
        self.assertIs(type(second['notation']['extra']['values'][1]),float)
        self.assertIs(second['notes'][2],first['notes'][3])
        self.assertEqual(json.dumps(second,sort_keys=True),json.dumps(newer,sort_keys=True))

    def test_new_snapshots_hold_no_reference_to_prior_state_objects(self):
        p=project();first=HistoryState(p.to_dict(),None);prior=weakref.ref(first)
        p.notes[0].velocity=91
        second=HistoryState(p.to_dict(),None,first)
        del first;gc.collect()
        self.assertIsNone(prior())
        self.assertEqual(len(second['notes']),12)


class HistoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'tmp').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.temp.cleanup)
        paths=patch('lingfeng.ui.main_window.user_data_dir',return_value=Path(self.temp.name));paths.start();self.addCleanup(paths.stop)
        saving=patch.object(MainWindow,'save_preferences');saving.start();self.addCleanup(saving.stop)
        self.window=MainWindow(project());self.window.timer.stop();self.window.autosave.stop()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.dirty=False;self.window.close();self.window.deleteLater()
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_undo_redo_and_new_branch_preserve_states_and_restore_independent_notes(self):
        w=self.window;expected=[w.project.to_dict()]
        w.mutate('velocity',lambda p:setattr(p.notes[0],'velocity',103));expected.append(w.project.to_dict())
        w.mutate('title',lambda p:setattr(p,'title','Shared history'));expected.append(w.project.to_dict())
        w.mutate('chord velocity',lambda p:setattr(p.chords[0].notes[0],'velocity',31));expected.append(w.project.to_dict())
        self.assertIs(w.undo_history[1]['notes'],w.undo_history[2]['notes'])
        old_history=json.dumps(w.undo_history,sort_keys=True)
        for target in (2,1,0):w.undo();self.assertEqual(w.project.to_dict(),expected[target])
        for target in (1,2,3):w.redo();self.assertEqual(w.project.to_dict(),expected[target])
        self.assertEqual(json.dumps(w.undo_history,sort_keys=True),old_history)
        w.undo();self.assertTrue(w.redo_history)
        w.mutate('new branch',lambda p:setattr(p.notes[1],'velocity',64))
        self.assertFalse(w.redo_history)
        before=w.project.to_dict();w.undo();self.assertEqual(w.project.to_dict(),expected[2])
        w.redo();self.assertEqual(w.project.to_dict(),before)

    def test_volume_grouping_shares_music_and_keeps_volume_undo_independent(self):
        w=self.window
        w.mutate('title',lambda p:setattr(p,'title','Volume history'))
        notes=w.undo_history[-1]['notes'];original=w.project.volumes.copy()
        w.change_volume('melody',42);w.change_volume('chords',67);w.change_volume('instrument',58)
        self.assertIs(w.volume_before['notes'],notes)
        pending=w.volume_before;w.commit_volume()
        self.assertIs(w.undo_history[-1],pending)
        self.assertIsNone(w.volume_before)
        self.assertEqual(w.project.volumes,{'melody':42,'chords':67,'instrument':58})
        w.undo();self.assertEqual(w.project.volumes,original)
        w.redo();self.assertEqual(w.project.volumes,{'melody':42,'chords':67,'instrument':58})
        w.undo();w.project.notes[0].velocity=24
        self.assertEqual(pending['notes'][0]['velocity'],75)


if __name__=='__main__':unittest.main()
