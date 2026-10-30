"""Overwrite note intersections and validate lyrics only at lyric entry."""
import os,sys,copy,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import QPoint,Qt
from PySide6.QtWidgets import QApplication,QMenu
from PySide6.QtTest import QTest
from lingfeng.music.model import Project, Note, Chord
from lingfeng.music.chord_operations import blank_chord
from lingfeng.music.note_operations import overwrite_note, NoteClipboard, repartition_chord, resize_chord
from lingfeng.music.rhythm import analyze, label, extend, _recognize, _recognize_bar
from tests.music_reference import bar_events
from lingfeng.ui.main_window import MainWindow
from lingfeng.engraving.lyrics import put, events, matching_issues
from tests.test_v14 import Synth

APP=QApplication.instance() or QApplication([])

def spans(notes):return sorted((n.start,n.end,n.pitch,n.velocity) for n in notes)

class OverwriteTests(unittest.TestCase):
    def test_right_resize_trims_neighbor_without_union_or_transitive_growth(self):
        p=Project();p.notes=[Note(0,480,60,100),Note(480,480,60,70),Note(960,480,60,80),Note(0,1440,64,90)]
        edited=copy.deepcopy(p.notes[0]);edited.duration=720;p.add_note(edited,overwrite=True);p.validate()
        self.assertEqual(spans(p.notes),[(0,720,60,100),(0,1440,64,90),(720,960,60,70),(960,1440,60,80)])
        self.assertEqual(p.notes[0].id,edited.id)
    def test_left_resize_keeps_previous_note_prefix(self):
        p=Project();left=Note(0,960,60,70);right=Note(960,480,60,100);p.notes=[left,right]
        edited=copy.deepcopy(right);edited.start=720;edited.duration=720;p.add_note(edited,overwrite=True)
        self.assertEqual(spans(p.notes),[(0,720,60,70),(720,1440,60,100)]);p.validate()
    def test_interior_overwrite_keeps_both_sides_and_unique_ids(self):
        old=Note(0,1920,60,71,flat=True);new=Note(480,480,60,110);other=Note(480,960,67,85)
        result=overwrite_note(new,[old,other]);self.assertEqual(spans(result),[(0,480,60,71),(480,960,60,110),(480,1440,67,85),(960,1920,60,71)])
        self.assertEqual(result[0].id,old.id);self.assertNotEqual(result[-1].id,old.id);self.assertTrue(result[-1].flat)
        self.assertEqual((old.start,old.duration),(0,1920));self.assertEqual(len({n.id for n in result}),4)
    def test_full_cover_and_exact_touch(self):
        notes=[Note(0,480,60),Note(480,480,60),Note(960,480,60)]
        middle=Note(480,480,60,100);result=overwrite_note(middle,notes)
        self.assertEqual([n.id for n in result],[notes[0].id,middle.id,notes[2].id])
        self.assertEqual([n.id for n in overwrite_note(Note(0,1440,60),notes)][1:],[])
    def test_harmony_keeps_local_times_and_remaining_velocities(self):
        p=Project();c=Chord(3840,3840,notes=[Note(0,960,60,80),Note(960,960,60,70),Note(0,3840,64)]);p.chords=[c]
        n=c.render_notes()[0];n.duration=1440;p.edit_harmony(n,overwrite=True);p.validate()
        self.assertEqual([(n.start,n.end,n.velocity) for n in c.render_notes() if n.pitch==60],[(3840,5280,80),(5280,5760,70)])
    def test_generated_pattern_materializes_before_overwrite(self):
        p=Project();c=Chord(0,3840,pattern='quarters');p.chords=[c];n=c.render_notes()[0];pitch=n.pitch;n.duration=2400;p.edit_harmony(n,overwrite=True);p.validate()
        self.assertEqual([(x.start,x.end) for x in c.render_notes() if x.pitch==pitch],[(0,2400),(2400,2784),(2880,3744)])
    def test_auto_and_explicit_durations_keep_occupied_insertion(self):
        p=Project();p.chords=[Chord(0,1920,notes=[],recognized=False),Chord(2400,1440)]
        for tick in (0,100,1919,2400,3839):
            self.assertIsNotNone(blank_chord(p,tick));self.assertIsNotNone(blank_chord(p,tick,'beats:1'))
        self.assertEqual((blank_chord(p,1920).start,blank_chord(p,1920).end),(1920,2400))

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.errors=[];self.hook=patch.object(sys,'excepthook',lambda typ,value,tb:self.errors.append(str(value)));self.hook.start()
        self.warning=patch('lingfeng.ui.main_window.QMessageBox.warning',side_effect=AssertionError('Unexpected warning'));self.warning.start()
        self.w=MainWindow(Project());self.w.change_language('zh',False);self.w.resize(1250,900);self.w.show();self.w.timer.stop();self.w.autosave.stop();self.w.transport.close();self.w.transport.synth=Synth();APP.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.hook.stop();self.warning.stop();self.assertFalse(self.errors)
    def set_music(self):
        w=self.w;w.project.notes=[Note(0,480,60,100),Note(480,960,60,70)];w.refresh();return w
    def test_resize_signal_and_properties_overwrite_with_undo_redo(self):
        w=self.set_music();before=w.project.to_dict();n=copy.deepcopy(w.project.notes[0]);n.duration=960;w.roll.notesResized.emit([n])
        self.assertEqual(spans(w.project.notes),[(0,960,60,100),(960,1440,60,70)]);after=w.project.to_dict()
        w.undo();self.assertEqual(w.project.to_dict(),before);w.redo();self.assertEqual(w.project.to_dict(),after)
        n=copy.deepcopy(w.project.notes[0]);n.duration=1200;w.move_note(n);self.assertEqual(spans(w.project.notes),[(0,1200,60,100),(1200,1440,60,70)])
    def test_harmony_resize_signal(self):
        w=self.w;w.project.chords=[Chord(0,3840,notes=[Note(0,480,60,100),Note(480,960,60,70)])];w.refresh()
        r=w.harmony_window.roll;n=copy.deepcopy(r.notes[0]);n.duration=960;r.notesResized.emit([n])
        self.assertEqual(spans(w.project.harmony_notes()),[(0,960,60,100),(960,1440,60,70)])
    def test_multivoice_paste_over_existing_notes_and_repeat(self):
        w=self.w;p=w.project;p.notes=[Note(0,480,60,100),Note(0,960,64,90),Note(1920,1920,60,70),Note(1920,1920,64,75)];w.refresh()
        w.roll.selected_ids={n.id for n in p.notes[:2]};w.note_command(w.roll,'copy:direct');menu=QMenu();w.roll.selection_menu(menu,2400)
        action=next(a for a in menu.actions() if a.text()=='在此粘贴音符');self.assertTrue(action.isEnabled());action.trigger()
        expected=[(0,480,60,100),(0,960,64,90),(1920,2400,60,70),(1920,2400,64,75),(2400,2880,60,100),(2400,3360,64,90),(2880,3840,60,70),(3360,3840,64,75)]
        self.assertEqual(spans(w.project.notes),expected)
        w.seek(2400);w.paste_selection();self.assertEqual(spans(w.project.notes),expected);w.project.validate()
    def test_harmony_multivoice_paste_at_position_marker(self):
        w=self.w;w.project.chords=[Chord(0,7680,notes=[Note(0,480,60,100),Note(0,480,64,90),Note(1920,1920,60,70),Note(1920,1920,64,75)])];w.refresh()
        r=w.harmony_window.roll;r.selected_ids={n.id for n in r.notes if n.start==0};w.note_command(r,'copy:direct');r.anchor_tick=2400;r.cursor_tick=4800
        menu=QMenu();r.selection_menu(menu,5000);next(a for a in menu.actions() if a.text()=='在定位线处粘贴音符').trigger()
        self.assertEqual([(n.start,n.end) for n in w.project.harmony_notes() if n.pitch==60],[(0,480),(1920,2400),(2400,2880),(2880,3840)])
    def test_range_clipboard_also_overwrites_and_keeps_legacy_lyrics(self):
        w=self.w;w.project.notes=[Note(0,480,60,100),Note(1920,1920,60,70,lyric='旧')];w.refresh();before=events(w.project)
        w.roll.selection=[[0,480]];w.copy_selection();w.roll.selection=[[2400,2880]];w.paste_selection()
        self.assertEqual([(n.start,n.end) for n in w.project.notes],[(0,480),(1920,2400),(2400,2880),(2880,3840)]);self.assertEqual(events(w.project),before)
    def test_occupied_auto_enabled_at_pointer_and_marker(self):
        w=self.w;w.project.chords=[Chord(0,1920,notes=[],recognized=False)];w.refresh();r=w.roll;r.anchor_tick=960
        menu=r.lane.context_menu(QPoint(round(r.x_at(480)),25))
        for action in menu.actions():
            if action.text() in ('插入空白和弦','在定位线处插入空白和弦'):
                actions=action.menu().actions();self.assertTrue(all(a.isEnabled() for a in actions))
        w.chord_command('insert',(960,'auto'),r);self.assertEqual(w.project.chord_at(960).start,960)
        parent=QMenu();sub=r.lane.insertion_menu(parent,'test',1920);self.assertTrue(sub.actions()[0].isEnabled())

    def test_harmony_paste_crosses_regions_and_gaps_without_losing_polyphony(self):
        w=self.w;w.project.chords=[Chord(0,960,notes=[Note(0,960,60,70)]),Chord(1920,1920,notes=[Note(0,1920,60,75),Note(0,1920,64,80)])];w.refresh()
        r=w.harmony_window.roll
        self.assertTrue(w.edit_notes(r,[Note(480,2400,60,100),Note(480,2400,67,90)],[],overwrite=True))
        self.assertEqual([(n.start,n.end,n.velocity) for n in w.project.harmony_notes() if n.pitch==60],[(0,480,70),(480,2880,100),(2880,3840,75)])
        self.assertEqual([(n.start,n.end) for n in w.project.harmony_notes() if n.pitch==64],[(1920,3840)])
        self.assertEqual(len(r.selected_ids),2);w.project.validate()

    def test_rhythm_cards_menu_inspector_and_dialog_update_without_expanding(self):
        from lingfeng.ui.dialogs import ChordDialog
        w=self.w;c=picture_chord();w.project.chords=[c];w.refresh();r=w.harmony_window.roll;w.chord_selection({c.id},r)
        self.assertIn('持续柱式',w.harmony_window.summary.toolTip());menu=r.lane.context_menu(QPoint(round(r.x_at(c.start+120)),25))
        self.assertTrue(menu.pattern_menu.actions()[0].isChecked());d=ChordDialog(c,w.project);self.assertEqual(d.pattern.currentData(),'block');d.close()
        before=w.project.to_dict();w.change_chord_structure(resize_chord(c,0,1920));new=w.project.chords[0]
        self.assertEqual(label(new),'持续柱式');self.assertIn('持续柱式',w.harmony_window.summary.toolTip())
        edited=copy.deepcopy(r.notes[0]);edited.duration=960;w.edit_notes(r,[edited],[])
        self.assertEqual(label(w.project.chords[0]),'未知节奏型');w.undo();self.assertEqual(label(w.project.chords[0]),'持续柱式')
        w.undo();self.assertEqual(w.project.to_dict(),before)

    def test_compose_edits_do_not_validate_lyric_panel(self):
        w=self.set_music();put(w.project,240,'旧')
        with patch.object(w.lyric_panel,'check',side_effect=AssertionError('Lyrics checked in Compose')):
            n=copy.deepcopy(w.project.notes[0]);n.duration=960;self.assertTrue(w.edit_notes(w.roll,[n],[]))
    def test_score_switch_and_pdf_skip_global_lyric_validation(self):
        w=self.w;put(w.project,240,'旧');w.refresh();before=events(w.project);self.assertTrue(matching_issues(w.project))
        with patch('lingfeng.engraving.lyrics.matching_issues',side_effect=AssertionError('Global lyric gate')):
            self.assertTrue(w.switch_workspace('score'));self.assertEqual(w.workspace,'score');self.assertEqual(events(w.project),before)
            with patch('lingfeng.ui.export_dialog.ExportDialog.exec',return_value=0) as show:w.save_pdf();show.assert_called_once()
    def test_score_lyric_entry_still_rejects_extra_syllables(self):
        w=self.w;w.project.notes=[Note(0,960,60)];w.refresh();w.switch_workspace('score');panel=w.lyric_panel
        panel.start.setValue(1);panel.count.setValue(1);panel.text.setPlainText('你好吗');self.assertFalse(panel.check());before=w.project.to_dict();panel.commit();self.assertEqual(w.project.to_dict(),before)
        panel.text.setPlainText('你');self.assertTrue(panel.check());panel.commit();self.assertEqual([e['text'] for e in events(w.project)],['你'])
    def test_live_resize_and_paste_do_not_restart_playback(self):
        w=self.set_music();w.toggle_play();thread=w.transport.thread;clock=w.transport.start_time;anchor=w.play_anchor
        n=copy.deepcopy(w.project.notes[0]);n.duration=960;w.roll.notesResized.emit([n]);w.roll.selected_ids={n.id};w.note_command(w.roll,'copy:direct');w.note_command(w.roll,'paste',480)
        self.assertTrue(w.transport.playing);self.assertIs(w.transport.thread,thread);self.assertEqual((w.transport.start_time,w.play_anchor),(clock,anchor));w.project.validate()

def picture_chord(duration=3840):
    # C7/E with octave doublings, unlike the application's canonical voicing.
    return Chord(0,duration,48,'7',4,notes=[Note(0,duration,p,v) for p,v in [(40,70),(52,85),(55,90),(58,76),(60,88),(64,94)]])


class RhythmTests(unittest.TestCase):
    def test_recognition_is_read_only_with_custom_voicing_and_dynamics(self):
        p=Project();c=picture_chord();p.chords=[c];before=p.to_dict()
        self.assertEqual(label(c),'持续柱式');self.assertEqual(analyze(c).pitches,(40,52,55,58,60,64));self.assertEqual(p.to_dict(),before)

    def test_shrink_move_expand_and_roundtrip_keep_detected_state(self):
        p=Project();c=picture_chord();p.chords=[c]
        for a,b in ((0,1920),(0,960),(0,3840),(480,3360),(480,5760)):
            repartition_chord(p,c.id,a,b);c=p.chords[0]
            self.assertEqual(label(c),'持续柱式');self.assertEqual({n.pitch:n.velocity for n in c.render_notes()},{pitch:c.velocity for pitch in c.pitches})
            self.assertEqual(sorted((n.start,n.duration,n.pitch,n.velocity) for n in c.render_notes()),bar_events(c,p,a,b));p=Project.from_dict(p.to_dict());c=p.chords[0];self.assertEqual(label(c),'持续柱式')
        from lingfeng.music.chord_operations import move_chords
        move_chords(p,{c.id},960);self.assertEqual(label(p.chords[0]),'持续柱式')

    def test_patterns_recognize_edited_notes_and_preserve_each_hit_velocity(self):
        from lingfeng.music.model import PATTERNS
        for code in PATTERNS:
            with self.subTest(pattern=code):
                c=Chord(0,3840,pattern=code,gate=.73);c.materialize()
                for i,n in enumerate(c.notes):n.velocity=60+i%40
                self.assertEqual(analyze(c).pattern,code)
                result=extend(c,0,7680)
                old={(n.start,n.pitch):n.velocity for n in c.render_notes()}
                for n in result.render_notes():
                    if (n.start,n.pitch) in old:self.assertEqual(n.velocity,old[n.start,n.pitch])
                self.assertEqual(analyze(result).pattern,code)

    def test_cache_updates_on_timing_pitch_and_duration_changes(self):
        c=picture_chord();_recognize_bar.cache_clear();self.assertIsNotNone(analyze(c));first=_recognize_bar.cache_info()
        c.notes[0].velocity=60;self.assertIsNotNone(analyze(c));self.assertGreater(_recognize_bar.cache_info().hits,first.hits)
        c.start=1000;self.assertIsNotNone(analyze(c))
        c.notes[0].duration-=120;self.assertIsNone(analyze(c));c.notes[0].duration+=120;self.assertIsNotNone(analyze(c))
        c.notes[0].start+=120;c.notes[0].duration-=120;self.assertIsNone(analyze(c));c.notes[0].start-=120;c.notes[0].duration+=120
        c.notes[0].pitch=41;self.assertIn(41,analyze(c).pitches)

    def test_short_known_pattern_survives_empty_offbeat_region(self):
        c=Chord(0,240,pattern='offbeat');p=Project();p.chords=[c];repartition_chord(p,c.id,0,1920)
        self.assertEqual(analyze(p.chords[0]).pattern,'offbeat');self.assertTrue(p.harmony_notes())

if __name__=='__main__':unittest.main()
