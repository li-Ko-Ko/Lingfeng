"""Joined chord notes, floating controls, linked following and legato input."""
import copy,os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord,Measure
from popscore.rhythm import analyze
from popscore.keybindings import load_bindings
from popscore import theme

APP=QApplication.instance() or QApplication([])

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.save=patch.object(MainWindow,'save_preferences');self.save.start()
        p=Project();p.measures=[Measure() for _ in range(16)];p.contexts[0].end=p.end
        p.notes=[Note(0,7680,60)];p.chords=[Chord(0,3840,notes=[Note(960,2880,60,event_id="held")]),Chord(3840,3840,notes=[Note(0,3840,60,event_id="held")])]
        self.w=MainWindow(p);self.w.change_language('zh',False);self.w.show();self.w.resize(1260,900);self.w.timer.stop();self.w.autosave.stop()
        for b in self.w.mute_buttons.values():b.setChecked(True)
        self.w.open_harmony();QTest.qWait(20)
    def tearDown(self):
        self.w.transport.playing=False;self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.save.stop()

    def test_chord_notes_join_across_structural_boundaries_without_changing_midi(self):
        w=self.w;r=w.harmony_window.roll;r.center_pitch(60);r.selection=[];before=w.project.to_dict()
        for selected in (False,True):
            r.selected_ids={n.id for n in r.notes} if selected else set();r.refresh();APP.processEvents()
            image=r.viewport().grab().toImage();ratio=image.devicePixelRatio();x=round(r.x_at(3840));y=round(r.y_at(60)+r.row_height/2)
            expected=theme.roll_color(r.category(60,3840),'note').name()
            for xx in range(x-3,x+4):self.assertEqual(image.pixelColor(round(xx*ratio),round(y*ratio)).name(),expected)
        self.assertEqual(w.project.to_dict(),before)
        self.assertEqual([(n.start,n.end) for n in r.notes],[(960,7680)])

    def test_linked_follow_copies_main_propagates_both_ways_and_unbinds(self):
        w=self.w;w.melody_window.setFloating(True);w.harmony_window.setFloating(True);APP.processEvents()
        w.follow_playhead.setChecked(False);w.melody_sync.setChecked(True);w.harmony_window.sync.setChecked(True)
        self.assertFalse(w.melody_transport.follow.isChecked());self.assertFalse(w.harmony_window.transport_controls.follow.isChecked())
        w.melody_transport.follow.setChecked(True);self.assertTrue(w.follow_playhead.isChecked());self.assertTrue(w.harmony_window.transport_controls.follow.isChecked())
        w.follow_views(25000)
        self.assertGreater(w.main_roll.horizontalScrollBar().value(),0)
        self.assertEqual(w.roll.horizontalScrollBar().value(),w.main_roll.horizontalScrollBar().value())
        self.assertEqual(w.harmony_window.roll.horizontalScrollBar().value(),w.main_roll.horizontalScrollBar().value())
        w.melody_sync.setChecked(False);w.follow_playhead.setChecked(False)
        self.assertTrue(w.melody_transport.follow.isChecked());self.assertFalse(w.harmony_window.transport_controls.follow.isChecked())
        w.melody_transport.follow.setChecked(False);w.melody_transport.follow.setChecked(True);self.assertFalse(w.follow_playhead.isChecked())

    def test_velocity_lane_changes_actual_midi_and_undo_without_moving_chords(self):
        w=self.w;lane=w.harmony_window.roll.lane;lane.velocity_action.setChecked(True);APP.processEvents()
        self.assertEqual(lane.height(),120);self.assertEqual(lane.card_height(),62)
        before=w.project.to_dict();ids={c.id for c in w.project.chords};lane.selection_event(ids)
        QTest.mouseClick(lane.velocity_lane,Qt.MouseButton.LeftButton,pos=QPoint(round(lane.x_at(1200)),24));APP.processEvents()
        self.assertTrue(all(c.velocity==79 for c in w.project.chords if c.notes!=[]));self.assertTrue(all(n.velocity==79 for n in w.project.harmony_notes()))
        w.undo();self.assertEqual(w.project.to_dict(),before)
        w.chord_lane.velocity_action.setChecked(True);self.assertEqual(w.chord_lane.height(),120)
        w.change_language('en',False);self.assertTrue(w.chord_lane.velocity_visible);self.assertTrue(w.harmony_window.roll.lane.velocity_visible)

    def test_q_toggle_and_e_focus_reveal_and_activate_float_and_score_tabs(self):
        w=self.w;w.roll.setFocus();w.tool.setCurrentIndex(w.tool.findData('smart'));APP.processEvents()
        QTest.keyClick(w.roll,Qt.Key.Key_Q);self.assertEqual(w.roll.tool,'draw')
        QTest.keyClick(w.roll,Qt.Key.Key_Q);self.assertEqual(w.roll.tool,'smart')
        w.visibility_actions['harmony'].setChecked(False);w.editor_key_command('switch_input');APP.processEvents()
        self.assertTrue(w.visibility_actions['harmony'].isChecked());self.assertIs(w.active_roll(),w.harmony_window.roll);self.assertEqual(w.midi_input.target,'chords')
        w.melody_window.setFloating(True);APP.processEvents();w.activateWindow();w.harmony_window.roll.setFocus();APP.processEvents()
        w.editor_key_command('switch_input');APP.processEvents();self.assertIs(w.active_roll(),w.roll);self.assertEqual(w.midi_input.target,'melody')
        w.switch_workspace('score');w.open_score_roll('melody',0);w.editor_key_command('switch_input');self.assertEqual(w.score_tabs.currentIndex(),1)
        w.editor_key_command('switch_input');self.assertEqual(w.score_tabs.currentIndex(),0)

    def test_legato_input_keeps_distinct_quantized_onsets_and_sustain_does_not_stack(self):
        w=self.w;c=w.midi_input;c.enabled=True;c.target='chords';w.project.chords=[Chord(0,3840,notes=[])];w.refresh();w.playhead=0
        c.receive(0x90,60,90,10);c.receive(0xB0,64,127,10.1)
        c.receive(0x90,64,80,10.3);c.receive(0x80,60,0,10.32)
        c.receive(0x90,67,70,10.6);c.receive(0x80,64,0,10.62);c.receive(0x80,67,0,10.9);c.receive(0xB0,64,0,11)
        notes=w.project.harmony_notes();self.assertEqual([n.start for n in notes],[0,480,960]);self.assertTrue(all(n.start%240==0 and n.duration%240==0 for n in notes))
        rhythm=analyze(w.project.chords[0],w.project);self.assertTrue(rhythm is None or rhythm.pattern!='block')

    def test_midi_chord_onset_and_repeated_pitch_are_preserved(self):
        w=self.w;c=w.midi_input;c.enabled=True;w.project.notes=[];w.refresh();w.playhead=0
        c.receive(0x90,60,90,10);c.receive(0x90,64,80,10.04);c.receive(0x80,60,0,10.3);c.receive(0x80,64,0,10.3)
        self.assertEqual({n.start for n in w.project.notes},{0})
        w.playhead=480;c.receive(0x90,60,50,11);c.receive(0x80,60,0,11.3)
        self.assertEqual([(n.start,n.end,n.velocity) for n in w.project.notes if n.pitch==60],[(0,480,90),(480,960,50)])

class KeyMigrationTests(unittest.TestCase):
    def test_imported_legato_chord_rearticulations_are_not_merged_to_block(self):
        from popscore.midi_import import MidiData,MidiTrack,apply_midi
        notes=[Note(t,min(980,3840-t),pitch,80+i) for i,t in enumerate(range(0,3840,960)) for pitch in (48,52,55)]
        data=MidiData([MidiTrack('Legato',notes,3840)],[],[]);p=Project()
        apply_midi(p,data,[0],'chords',0)
        self.assertEqual(sorted({n.start for n in p.harmony_notes()}),[0,960,1920,2880])
        self.assertNotEqual(analyze(p.chords[0],p).pattern,'block')
        self.assertEqual([n.velocity for n in p.chords[0].notes if n.pitch==48],[80,81,82,83])

    def test_old_defaults_migrate_but_custom_direct_shortcuts_survive(self):
        migrated=load_bindings({'smart':'Q','draw':'E'});self.assertEqual((migrated['toggle_tool'],migrated['switch_input']),('Q','E'));self.assertEqual(migrated['smart'],'')
        custom=load_bindings({'smart':'F2','draw':'Q'});self.assertEqual(custom['smart'],'F2');self.assertEqual(custom['draw'],'Q');self.assertEqual(custom['toggle_tool'],'')

if __name__=='__main__':unittest.main()
