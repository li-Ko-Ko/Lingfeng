import os,copy,tempfile,time,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication,QMenu,QDialog
from PySide6.QtTest import QTest
from lingfeng.music.model import Project, Note, Chord, Measure, Context
from lingfeng.music.note_operations import can_split, split_notes, repartition_chord, resize_chord
from lingfeng.audio.transport import Transport
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.piano_roll import PianoRoll
from lingfeng.engraving.lyrics import events, put, detach
from lingfeng.music.quantization import quantize_notes
from lingfeng.audio.midi_import import MidiData, MidiTrack, apply_midi, read_midi
from lingfeng.audio.midi_input import WinMidiInput, commit_notes
from lingfeng.engraving.notation import ScoreLayout
from lingfeng.audio.midi import export_midi
from lingfeng.platform.i18n import set_language

APP=QApplication.instance() or QApplication([])


class MusicTests(unittest.TestCase):
    def test_halving_includes_64th_and_triplet_and_ignores_start_grid(self):
        for duration,expected in ((120,60),(80,40),(160,80),(240,120),(960,480)):
            notes=[Note(17,duration,60),Note(81,duration,64)]
            self.assertTrue(can_split(notes,960));halves=split_notes(notes,960)
            self.assertEqual([n.duration for n in halves],[expected]*4)
            self.assertEqual(halves[1].end,notes[0].end)
        for duration in (60,40,90,30):
            self.assertFalse(can_split([Note(0,duration,60)],20))
            with self.assertRaises(ValueError):split_notes([Note(0,duration,60)])

    def test_structural_expansion_replaces_covered_neighbor_with_custom_silence(self):
        p=Project();p.chords=[Chord(0,3840,notes=[Note(0,3840,60,91),Note(0,3840,64,85)]),Chord(3840,3840,notes=[Note(0,3840,67,73)])]
        before=p.harmony_notes();cid=p.chords[0].id
        repartition_chord(p,cid,0,4320)
        self.assertEqual({n.pitch for n in p.chords[0].notes},{60,64})
        # Incomplete MIDI is rescanned after a region edit; C/E alone does not
        # establish the formerly declared complete C triad.
        self.assertFalse(p.chords[0].recognized)
        after=p.harmony_notes()
        for t in list(range(0,3840,40))+list(range(4320,7680,40)):
            self.assertEqual(sorted((n.pitch,n.velocity) for n in before if n.start<=t<n.end),sorted((n.pitch,n.velocity) for n in after if n.start<=t<n.end))
        self.assertEqual([(n.start,n.end) for n in after if n.pitch==67],[(4320,7680)])

    def test_structure_resize_limits_audio_to_new_region(self):
        for a,b in ((480,2880),(4000,5000),(0,5000),(480,5000)):
            p=Project();p.chords=[Chord(960,2880,pattern='up')];notes=p.harmony_notes()
            repartition_chord(p,p.chords[0].id,a,b)
            self.assertEqual(len(p.chords),1)
            self.assertTrue(all(a<=n.start<n.end<=b for n in p.harmony_notes()))
            p.validate()

    def test_chord_lane_resize_retains_symbol(self):
        c=Chord(0,3840,48,'m',notes=[Note(0,960,60)])
        d=resize_chord(c,0,4800);self.assertEqual((d.root,d.quality),(48,'m'))

    def test_mixed_quantization_preserves_triplets_and_straight_jitter(self):
        notes=[Note(t,312,60+i) for i,t in enumerate((7,327,638))]
        q=quantize_notes(notes,240,True)
        self.assertEqual([(n.start,n.duration) for n in q],[(0,320),(320,320),(640,320)])
        notes=[Note(t,230,60+i) for i,t in enumerate((4,251,474,727))]
        self.assertEqual([n.start for n in quantize_notes(notes,240,True)],[0,240,480,720])
        # An isolated slightly late eighth note must not invent a triplet section.
        self.assertEqual(quantize_notes([Note(530,470,60)],240,True)[0].start,480)

    def test_explicit_triplet_and_no_quantization(self):
        source=[Note(319,321,60),Note(641,300,64)]
        self.assertEqual([(n.start,n.duration) for n in quantize_notes(source,320)],[(320,320),(640,320)])
        self.assertEqual(quantize_notes(source,0),source)
        self.assertEqual(source[0].start,319)

    def test_import_keeps_existing_lyrics_and_ignores_incoming_lyrics(self):
        p=Project();p.notes=[Note(0,960,60,lyric='原')];put(p,2400,'词');before=events(p)
        data=MidiData([MidiTrack('test',[Note(240,320,62,lyric='覆盖')],3840)],[],[])
        for target in ('melody','chords'):
            q=copy.deepcopy(p);apply_midi(q,data,[0],target,0,quantization=dict(grid=160))
            self.assertEqual(events(q),before);self.assertFalse(any(n.lyric for n in q.notes))
        self.assertEqual(data.tracks[0].notes[0].lyric,'覆盖')

    def test_explicit_rap_x_in_all_scores_does_not_create_midi_notes(self):
        from lingfeng.engraving.lyrics import apply_section
        p=Project();p.notes=[Note(0,960,60)];apply_section(p,'风',0);apply_section(p,'空/16',1440);apply_section(p,'梦/16',1440,1)
        for style in ('spatial','compact','traditional'):
            p.notation['style']=style;layout=ScoreLayout(p)
            ghosts=[f for s in layout.systems for frags in s.fragments.values() for f in frags if f.ghost]
            self.assertEqual([f.start for f in ghosts],[1440])
            image=QImage(900,1273,QImage.Format.Format_RGB32);painter=QPainter(image);layout.draw(painter,0);painter.end()
            self.assertEqual(len(layout.lyric_positions),3)
            self.assertFalse(any(nid.startswith('lyric:') for _,_,nid in layout.hit_notes))
            self.assertTrue(all(y>layout.systems[0].top+layout.systems[0].grid_bottom for _,_,_,y in layout.lyric_positions))
        with tempfile.TemporaryDirectory(dir=Path('tmp').resolve()) as folder:
            path=Path(folder)/'lyrics.lfs';p.save(path);self.assertEqual(events(Project.load(path)),events(p))
            midi=Path(folder)/'lyrics.mid';export_midi(p,midi);self.assertEqual(sum(len(t.notes) for t in read_midi(midi).tracks),1)

    def test_lyrics_follow_bar_insertion_and_meter_shift(self):
        p=Project();put(p,4000,'风');p.insert_measure(1);self.assertEqual(events(p)[0]['tick'],7840)
        p.change_meter(0,3,4);self.assertEqual(events(p)[0]['tick'],6880)

    def test_independent_repeat_lyrics_stack_without_note_matches(self):
        from lingfeng.engraving.presentation import add_compression
        p=Project();p.notes=[Note(0,960,60),Note(3840,960,60)];put(p,1440,'一');put(p,5280,'二')
        add_compression(p,[0,1],'repeat');layout=ScoreLayout(p)
        self.assertEqual([(e['tick'],e['verse']) for e in layout.lyrics],[(1440,0),(1440,1)])
        self.assertEqual(layout.systems[0].lyric_rows,2)

    def test_chord_keyboard_input_handles_gaps_boundaries_and_overlap(self):
        p=Project();p.chords=[Chord(960,960,notes=[Note(0,960,60)])];put(p,480,'保留');before=events(p)
        commit_notes(p,[Note(0,2880,64,87),Note(480,1440,64,91)],'chords');p.validate()
        self.assertEqual(events(p),before)
        for t in range(0,2880,80):self.assertEqual(sum(n.start<=t<n.end and n.pitch==64 for n in p.harmony_notes()),1)

    def test_driver_queue_decodes_notes_and_discards_stale_generation(self):
        source=WinMidiInput();source.generation=2;source.epoch=100
        source.queue.put((1,0x90|(60<<8)|(99<<16),80));source.queue.put((2,0x91|(64<<8)|(77<<16),100))
        self.assertEqual(list(source.drain()),[(0x91,64,77,100.1)]);source.close()


class AuditionTests(unittest.TestCase):
    def test_hold_release_floor_generation_and_playback_channel_isolation(self):
        class Synth:
            def __init__(self):self.events=[]
            def send(self,*args):self.events.append(args)
        t=Transport();t.synth=Synth();callbacks=[]
        with patch('lingfeng.audio.transport.time.monotonic',return_value=10),patch('lingfeng.audio.transport.QTimer.singleShot',side_effect=lambda ms,owner,fn:callbacks.append((ms,fn))):
            t.begin_audition([60]);t.end_audition();self.assertEqual(callbacks[-1][0],650)
            t.begin_audition([62]);callbacks[0][1]();self.assertNotIn((0x82,62),t.synth.events)
            t.extend_audition(False,2.4);t.end_audition();self.assertEqual(callbacks[-1][0],2400)
            t.stop(preserve_auditions=True);self.assertNotIn((0xB2,123,0),t.synth.events)
        with patch('lingfeng.audio.transport.time.monotonic',return_value=14):t.end_audition()
        self.assertIn((0x82,62),t.synth.events)
        t.stop();self.assertIn((0xB4,123,0),t.synth.events);t.synth=None

    def test_draw_delete_is_silent_and_creation_is_held(self):
        p=Project();p.notes=[Note(960,960,60)];r=PianoRoll(p);r.resize(1000,640);r.show();r.center_pitch(60);APP.processEvents();r.tool='draw'
        heard=[];released=[];r.audition.connect(heard.append);r.auditionReleased.connect(lambda:released.append(True))
        pos=QPoint(round(r.x_at(1200)),round(r.y_at(60)+10));QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,pos=pos);self.assertEqual(heard,[])
        pos=QPoint(round(r.x_at(2400)+8),round(r.y_at(64)+10));QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=pos)
        self.assertEqual(heard,[[64]]);count=len(released);QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=pos);self.assertEqual(len(released),count+1);r.close()


class InputTests(unittest.TestCase):
    def setUp(self):
        set_language('zh');self.w=MainWindow(Project());self.w.timer.stop();self.w.autosave.stop();self.w.transport.monitor=lambda *args:None
        self.c=self.w.midi_input;self.c.enabled=True;self.c.timer.stop()
    def tearDown(self):self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents()

    def test_step_polyphony_strict_triplet_grid_velocity_and_undo(self):
        w=self.w;c=self.c;w.grid.set_triplet(True);self.assertEqual(w.roll.grid,160);put(w.project,0,'词')
        before=events(w.project)
        c.receive(0x90,60,77,10);c.receive(0x90,64,93,10.04);c.receive(0x80,60,0,10.21)
        self.assertFalse(w.project.notes);c.receive(0x90,64,0,10.3)
        self.assertEqual([(n.start,n.duration,n.velocity) for n in w.project.notes],[(0,320,77),(0,480,93)])
        self.assertEqual(w.playhead,480);self.assertEqual(events(w.project),before);w.undo();self.assertFalse(w.project.notes)

    def test_keyboard_end_snaps_at_mixed_meter_bar_boundary(self):
        w=self.w;c=self.c;w.project.set_markers([0],48,'Ionian',3,8);w.refresh();w.grid.setCurrentIndex(w.grid.findData(960));w.playhead=960
        c.receive(0x90,60,85,10);c.receive(0x80,60,0,10.3)
        self.assertEqual([(n.start,n.end) for n in w.project.notes],[(960,1440)])

    def test_sustain_and_cancel_do_not_leave_stuck_notes(self):
        c=self.c;c.receive(0x90,60,80,10);c.receive(0xB0,64,127,10.1);c.receive(0x80,60,0,10.2)
        self.assertTrue(c.held);c.receive(0xB0,64,0,10.4);self.assertFalse(c.held);self.assertTrue(self.w.project.notes)
        c.receive(0x90,67,80,11);c.reset();self.assertFalse(c.held);self.assertFalse(c.pending)

    def test_live_input_uses_driver_timestamp_not_ui_poll_delay(self):
        w=self.w;c=self.c;t=w.transport;t.playing=True;t.start_tick=0;t.start_time=10;t.end_tick=w.project.end;t.seconds_per_tick=60/(100*960)
        c.receive(0x90,60,85,10.308);c.receive(0x80,60,0,10.606)
        self.assertEqual([(n.start,n.duration) for n in w.project.notes],[(480,480)]);self.assertTrue(t.playing);self.assertTrue(any(e[0]==480 and e[1]==1 and e[3]==60 for e in t.loop_events))

    def test_explicit_rap_input_without_pitched_notes(self):
        self.w.batch_lyrics();panel=self.w.lyric_panel;panel.text.setPlainText('伶/16风/16');panel.commit()
        self.assertEqual([e['tick'] for e in events(self.w.project)],[0,240]);self.assertEqual(self.w.project.notes,[])
        self.assertEqual(sum(f.ghost for s in ScoreLayout(self.w.project).systems for fragments in s.fragments.values() for f in fragments),2)

    def test_quantize_only_in_selected_note_context_menu(self):
        r=self.w.roll;self.assertFalse(hasattr(self.w,'quantize_button'))
        menu=QMenu();r.selection_menu(menu,0);self.assertFalse(next(a for a in menu.actions() if a.text()=='按当前格点量化').isEnabled())
        n=Note(277,480,60);self.w.project.notes=[n];self.w.refresh();r.selected_ids={n.id}
        menu=QMenu();r.selection_menu(menu,0);next(a for a in menu.actions() if a.text()=='按当前格点量化').trigger();self.assertEqual(self.w.project.notes[0].start,240)


if __name__=='__main__':unittest.main()
