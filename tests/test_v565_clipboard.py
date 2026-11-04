"""Chord pastes keep independent MIDI identities and explicit menu targets."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPoint, QEvent
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Chord, Note, Project
from lingfeng.music.chord_operations import ChordClipboard
from lingfeng.ui.main_window import MainWindow
from tests.menu_helpers import find_action, walk_actions

APP=QApplication.instance() or QApplication([])


def sustained_project():
    p=Project();p.chords=[Chord(0,960),Chord(960,960),Chord(1920,960)]
    p.set_harmony_notes([Note(0,1920,48,71),Note(0,480,60,89),Note(960,480,64,83)])
    for c in p.chords:
        c.recognition_disabled=True;c.marked=True;c.recognized=True
    return p


class ClipboardTests(unittest.TestCase):
    def test_recognizable_actual_voicing_and_velocities_copy_exactly_at_any_phase(self):
        p=Project()
        notes=[Note(0,3840,53,79),*[Note(t,960,pitch,85+i) for t in range(0,3840,960) for i,pitch in enumerate((57,60,64))]]
        chord=Chord(0,3840,root=53,quality='maj7',notes=notes)
        p.chords=[chord];before=copy.deepcopy(chord)
        from lingfeng.music.rhythm import analyze
        self.assertEqual(analyze(chord,p).pattern,'sustained_bass_beats')
        expected=sorted((n.start,n.duration,n.pitch,n.velocity) for n in chord.notes)
        clip=ChordClipboard.capture([chord],p)
        ids=clip.paste(p,4200);result=next(c for c in p.chords if c.id in ids)
        self.assertEqual(sorted((n.start,n.duration,n.pitch,n.velocity) for n in result.notes),expected)
        self.assertEqual(chord,before);p.validate()

    def test_paste_sustain_has_new_shared_identity_and_keeps_source_separate(self):
        p=sustained_project();source=p.chords[:2];before=copy.deepcopy(source)
        clip=ChordClipboard.capture(source,p)
        ids=clip.paste(p,1920)
        copied=[c for c in p.chords if c.id in ids]
        source_events={n.event_id for c in source for n in c.notes}
        copied_events={n.event_id for c in copied for n in c.notes}
        self.assertTrue(source_events.isdisjoint(copied_events))
        self.assertEqual(len({n.event_id for c in copied for n in c.notes if n.pitch==48}),1)
        self.assertEqual([(n.start,n.duration) for n in p.harmony_notes() if n.pitch==48],[(0,1920),(1920,1920)])
        self.assertEqual(source,before)
        more=clip.paste(p,3840)
        self.assertTrue(copied_events.isdisjoint({n.event_id for c in p.chords if c.id in more for n in c.notes}))
        self.assertEqual([(n.start,n.duration) for n in p.harmony_notes() if n.pitch==48],[(0,1920),(1920,1920),(3840,1920)])
        # A later harmony edit must still see three separate rearticulations.
        p.set_harmony_notes(p.harmony_notes());p.validate()
        self.assertEqual([(n.start,n.duration) for n in p.harmony_notes() if n.pitch==48],[(0,1920),(1920,1920),(3840,1920)])
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            path=Path(folder)/'copy.lfs';p.save(path)
            self.assertEqual(Project.load(path).to_dict(),p.to_dict())

    def test_copy_inside_source_does_not_join_neighboring_original(self):
        p=sustained_project();clip=ChordClipboard.capture([p.chords[1]],p)
        ids=clip.paste(p,960)
        self.assertEqual(len(ids),1)
        self.assertEqual([(n.start,n.duration) for n in p.harmony_notes() if n.pitch==48],[(0,960),(960,960)])
        p.validate()


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(dir='tmp');self.addCleanup(self.directory.cleanup)
        pref=patch('lingfeng.ui.main_window.user_data_dir',return_value=Path(self.directory.name))
        pref.start();self.addCleanup(pref.stop)
        self.w=MainWindow(Project());self.w.timer.stop();self.w.autosave.stop();self.w.change_language('zh',False)
        self.addCleanup(self.close_window)

    def close_window(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_each_lane_pastes_at_clicked_chord_start_and_retains_position_paste(self):
        for index in range(3):
            with self.subTest(lane=index):
                p=Project();p.chords=[Chord(0,960,notes=[Note(0,960,48)],recognition_disabled=True),Chord(1920,1920,root=55)]
                self.w.replace_project(p)
                r=(self.w.main_roll,self.w.roll,self.w.harmony_window.roll)[index]
                self.w.chord_command('copy',{p.chords[0].id},r)
                r.anchor_tick=4800;r.cursor_tick=5200
                menu=r.lane.context_menu(QPoint(round(r.lane.x_at(2800)),18));self.addCleanup(menu.close)
                here=find_action(menu,'在此和弦开头覆盖粘贴');marker=find_action(menu,'在定位线处粘贴和弦')
                self.assertIn(here,menu.actions());self.assertIn(marker,menu.actions())
                self.assertTrue(here.isEnabled());self.assertTrue(marker.isEnabled())
                before=self.w.project.to_dict();here.trigger()
                pasted=self.w.project.chord_at(1920)
                self.assertEqual((pasted.start,pasted.end),(1920,2880))
                self.assertEqual(pasted.render_notes()[0].pitch,48)
                self.assertEqual(self.w.project.chord_at(2880).end,3840)
                after=self.w.project.to_dict();self.w.undo();self.assertEqual(self.w.project.to_dict(),before)
                self.w.redo();self.assertEqual(self.w.project.to_dict(),after)
                marker.trigger();self.assertEqual(self.w.project.chord_at(4800).start,4800)

    def test_blank_space_retains_point_paste_even_with_a_chord_selected(self):
        p=Project();p.chords=[Chord(0,960)]
        self.w.replace_project(p);r=self.w.roll
        self.w.chord_command('copy',{p.chords[0].id},r)
        self.w.chord_selection({p.chords[0].id},r)
        menu=r.lane.context_menu(QPoint(round(r.lane.x_at(2400)),18),preserve=True);self.addCleanup(menu.close)
        self.assertNotIn('在此和弦开头覆盖粘贴',[a.text() for a in walk_actions(menu)])
        find_action(menu,'在此粘贴和弦').trigger()
        self.assertEqual(self.w.project.chord_at(2400).start,2400)


if __name__=='__main__':unittest.main()
