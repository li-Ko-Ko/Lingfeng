"""Chord copies crop at destination boundaries, without rewriting performed MIDI."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPoint, QEvent
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Project, Chord, Note, Measure, Context
from lingfeng.music.chord_operations import ChordClipboard
from lingfeng.ui.main_window import MainWindow
from tests.menu_helpers import find_action

APP=QApplication.instance() or QApplication([])


def mixed():
    p=Project();p.measures=[Measure(),Measure(3,4),Measure(),Measure()]
    p.contexts=[Context(0,p.end)];p.fill_chord_gaps();return p


def signature(notes):
    return sorted((n.start,n.duration,n.pitch,n.velocity) for n in notes)


class MusicTests(unittest.TestCase):
    def test_different_source_meter_crops_exact_voicing_and_dynamics(self):
        source=Project()
        chord=Chord(0,7680,root=53,quality='maj7',notes=[Note(0,7680,53,67),
            *[Note(t,960,pitch,80+i) for t in range(0,7680,960) for i,pitch in enumerate((57,60,64))]])
        source.chords=[chord];before=copy.deepcopy(chord)
        clip=ChordClipboard.capture([chord],source);p=mixed();length=p.end
        self.assertTrue(clip.can_paste(p,4200))
        with patch('lingfeng.music.rhythm.regenerate',side_effect=AssertionError('Pasting must preserve MIDI')):
            ids=clip.paste(p,4200)
        result=next(c for c in p.chords if c.id in ids)
        self.assertEqual((result.start,result.end),(4200,6720))
        expected=sorted((n.start,min(n.duration,2520-n.start),n.pitch,n.velocity) for n in chord.notes if n.start<2520)
        self.assertEqual(signature(result.notes),expected)
        self.assertNotIn(41,{n.pitch for n in result.notes})
        self.assertEqual(chord,before);self.assertEqual(p.end,length);p.validate()
        self.assertEqual(p.chord_at(6720).start,6720)

    def test_group_stops_at_boundary_and_preserves_sustain_identity(self):
        source=Project();source.chords=[Chord(t,720) for t in (0,720,1440)]
        source.set_harmony_notes([Note(0,2160,48,71),Note(0,720,60,87),Note(720,720,64,93),Note(1440,720,67,101)])
        for c in source.chords:c.recognition_disabled=True;c.marked=True;c.recognized=True
        selected=source.chords[:3];before=source.to_dict();clip=ChordClipboard.capture(selected,source)
        p=mixed();ids=clip.paste(p,2760)
        copied=sorted((c for c in p.chords if c.id in ids),key=lambda c:c.start)
        self.assertEqual([(c.start,c.duration) for c in copied],[(2760,720),(3480,360)])
        self.assertEqual([(n.start,n.duration) for n in p.harmony_notes() if n.pitch==48],[(2760,1080)])
        self.assertEqual({n.pitch for c in copied for n in c.notes},{48,60,64})
        self.assertTrue(all(c.marked and c.recognition_disabled for c in copied))
        source_events={n.event_id for c in selected for n in c.notes}
        copied_events={n.event_id for c in copied for n in c.notes}
        self.assertTrue(source_events.isdisjoint(copied_events))
        more=clip.paste(p,7320)
        self.assertTrue(copied_events.isdisjoint({n.event_id for c in p.chords if c.id in more for n in c.notes}))
        self.assertEqual(source.to_dict(),before);p.validate()
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            path=Path(folder)/'cropped.lfs';p.save(path)
            self.assertEqual(Project.load(path).to_dict(),p.to_dict())

    def test_project_tail_and_empty_or_invalid_destinations_are_safe(self):
        p=mixed();source=[Chord(0,960,notes=[Note(0,960,60,101)]),Chord(960,960)]
        clip=ChordClipboard.capture(source);length=p.end;ids=clip.paste(p,p.end-100)
        self.assertEqual(len(ids),1);last=next(c for c in p.chords if c.id in ids)
        self.assertEqual((last.start,last.end),(length-100,length))
        self.assertEqual(signature(last.notes),[(0,100,60,101)])
        self.assertEqual(p.end,length);p.validate();before=p.to_dict()
        self.assertTrue(clip.can_paste(p,p.end));self.assertEqual(clip.paste(p,p.end),set())
        for tick in (-1,p.end+1,None,1.5,True):
            self.assertFalse(clip.can_paste(p,tick));self.assertEqual(clip.paste(p,tick),set())
        self.assertFalse(ChordClipboard([]).can_paste(p,0));self.assertEqual(ChordClipboard([]).paste(p,0),set())
        self.assertEqual(p.to_dict(),before)


class MenuAndRangeTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(dir='tmp');self.addCleanup(self.directory.cleanup)
        pref=patch('lingfeng.ui.main_window.user_data_dir',return_value=Path(self.directory.name))
        pref.start();self.addCleanup(pref.stop)
        self.w=MainWindow(mixed());self.w.timer.stop();self.w.autosave.stop();self.w.change_language('zh',False)
        self.addCleanup(self.close_window)

    def close_window(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def clipboard(self):
        clip=ChordClipboard.capture([Chord(0,1920,notes=[Note(0,1920,60,109)])])
        self.w.chord_clipboard=clip;self.w.clipboard_kind='chords'
        for r in (self.w.main_roll,self.w.roll,self.w.harmony_window.roll):r.chord_clipboard=clip
        return clip

    def test_all_lanes_enable_boundary_and_other_meter_pastes_with_undo(self):
        for index in range(3):
            with self.subTest(lane=index):
                p=mixed();p.chords=[Chord(0,3000,notes=[]),Chord(3000,840,notes=[]),Chord(3840,2880,notes=[])]
                p.fill_chord_gaps();self.w.replace_project(p);self.clipboard()
                r=(self.w.main_roll,self.w.roll,self.w.harmony_window.roll)[index];r.anchor_tick=6000
                menu=r.lane.context_menu(QPoint(round(r.lane.x_at(3200)),18));self.addCleanup(menu.close)
                here=find_action(menu,'在此和弦开头覆盖粘贴');marker=find_action(menu,'在定位线处粘贴和弦')
                self.assertTrue(here.isEnabled());self.assertTrue(marker.isEnabled())
                before=self.w.project.to_dict();here.trigger()
                self.assertEqual(signature(self.w.project.chord_at(3000).render_notes()),[(3000,840,60,109)])
                after=self.w.project.to_dict();self.w.undo();self.assertEqual(self.w.project.to_dict(),before)
                self.w.redo();self.assertEqual(self.w.project.to_dict(),after)
                marker.trigger();self.assertEqual(signature(self.w.project.chord_at(6000).render_notes()),[(6000,720,60,109)])
                self.assertEqual(self.w.project.end,p.end);self.w.project.validate()

    def test_project_end_menu_enabled_but_command_does_not_record_empty_edit(self):
        self.clipboard();r=self.w.roll;r.anchor_tick=self.w.project.end
        menu=r.lane.context_menu(QPoint(round(r.lane.x_at(100)),18));self.addCleanup(menu.close)
        marker=find_action(menu,'在定位线处粘贴和弦');self.assertTrue(marker.isEnabled())
        before=self.w.project.to_dict();history=len(self.w.undo_history);marker.trigger()
        self.assertEqual(self.w.project.to_dict(),before);self.assertEqual(len(self.w.undo_history),history)

    def test_range_paste_truncates_at_project_end_and_keeps_relative_starts(self):
        p=mixed();self.w.replace_project(p);length=p.end
        self.w.clipboard_kind='range';self.w.clipboard=([Note(0,1920,70,86),Note(600,960,72,95)],
            [Chord(0,1920,notes=[Note(0,1920,53,77)]),Chord(1920,960)],2880)
        self.w.roll.selection=[[p.end-480,p.end]];before=self.w.project.to_dict()
        self.w.paste_selection()
        self.assertEqual(signature(self.w.project.notes),[(length-480,480,70,86)])
        self.assertEqual(signature(self.w.project.chord_at(length-480).render_notes()),[(length-480,480,53,77)])
        self.assertEqual(self.w.project.end,length);self.w.undo();self.assertEqual(self.w.project.to_dict(),before)
        self.w.clipboard=([],[Chord(0,480,notes=[Note(0,480,60)]),Chord(960,960,notes=[Note(0,960,64)])],1920)
        self.w.roll.selection=[[3000,3480]];self.w.paste_selection()
        self.assertEqual(signature([n for n in self.w.project.harmony_notes() if n.start>=3000]),[(3000,480,60,92)])
        self.assertEqual(self.w.project.chord_at(3840).notes,[])

    def test_range_copy_keeps_cross_chord_sustain_then_crops_adjacent_copy(self):
        p=mixed();p.chords=[Chord(t,720) for t in (0,720,1440)]
        p.set_harmony_notes([Note(0,2160,48,71),Note(0,720,60,87),Note(720,720,64,93),Note(1440,720,67,101)])
        for c in p.chords:
            if c.start<2160:c.recognition_disabled=True;c.marked=True;c.recognized=True
        self.w.replace_project(p);r=self.w.roll;r.edit_target='notes';r.selected_ids.clear()
        r.selection=[[0,2160]];before=self.w.project.to_dict()
        with patch.object(self.w,'active_roll',return_value=r):self.w.copy_selection()
        self.assertEqual(self.w.clipboard_kind,'range')
        clips=self.w.clipboard[1]
        bass_ids={n.event_id for c in clips for n in c.notes if n.pitch==48}
        self.assertEqual(len(bass_ids),1)
        source_ids={n.id for c in p.chords for n in c.notes}
        self.assertTrue(source_ids.isdisjoint({n.id for c in clips for n in c.notes}))
        self.assertEqual(self.w.project.to_dict(),before)
        r.selection=[[2160,2640]];self.w.paste_selection()
        self.assertEqual([(n.start,n.duration) for n in self.w.project.harmony_notes() if n.pitch==48],[(0,2160),(2160,1680)])
        self.assertEqual(signature([n for n in self.w.project.harmony_notes() if n.start>=2160]),
                         [(2160,720,60,87),(2160,1680,48,71),(2880,720,64,93),(3600,240,67,101)])
        copied=[c for c in self.w.project.chords if 2160<=c.start<3840]
        self.assertTrue(bass_ids.isdisjoint({n.event_id for c in copied for n in c.notes}))
        self.assertEqual(self.w.project.chord_at(3840).notes,[])
        after=self.w.project.to_dict();self.w.undo();self.assertEqual(self.w.project.to_dict(),before)
        self.w.redo();self.assertEqual(self.w.project.to_dict(),after);self.w.project.validate()


if __name__=='__main__':unittest.main()
