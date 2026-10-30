"""Meter-local editing, recoverable cropped selections and bar deletion."""
import copy,os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from lingfeng.music.model import Project, Measure, Context, Chord, Note, PPQ
from lingfeng.music.meter import moved_chord, region_at
from lingfeng.music.rhythm import analyze, label
from lingfeng.music.chord_operations import ChordClipboard, ChordMoveSession, move_chords, can_move_diatonic
from lingfeng.music.bar_operations import delete_bars, deletion_has_content
from lingfeng.ui.main_window import MainWindow

APP=QApplication.instance() or QApplication([])
def mixed():
    p=Project();p.measures=[Measure(),Measure(3,4),Measure(),Measure()];p.contexts=[Context(0,p.end)];return p
def events(notes):return sorted((n.start,n.duration,n.pitch,n.velocity,n.flat) for n in notes)

class ModelTests(unittest.TestCase):
    def test_paste_requires_exact_meter_and_whole_destination_range(self):
        p=mixed();c=Chord(3840,1920);p.chords=[c];clip=ChordClipboard.capture([c],p)
        self.assertFalse(clip.can_paste(p,0));self.assertTrue(clip.can_paste(p,3840));self.assertFalse(clip.can_paste(p,6000))
        before=p.to_dict()
        with self.assertRaises(ValueError):clip.paste(p,0)
        self.assertEqual(p.to_dict(),before)
        p.measures[0]=Measure(6,8);p.contexts=[Context(0,p.end)]
        self.assertFalse(clip.can_paste(p,0))

    def test_clipboard_meter_is_stable_after_source_edits(self):
        p=mixed();c=Chord(0,1920);clip=ChordClipboard.capture([c],p)
        p.change_meter(0,3,4,True);self.assertFalse(clip.can_paste(p,0))
        self.assertTrue(clip.can_paste(p,p.starts[2]));clip.paste(p,p.starts[2]);p.validate()

    def test_left_and_right_crops_use_full_bar_phase_for_known_patterns(self):
        p=mixed();p.put_chord(Chord(3840,1920,pattern='up'));c=p.chords[0]
        left=moved_chord(p,c,3360);self.assertEqual((left.start,left.end),(3840,5280));self.assertEqual(analyze(left,p).pattern,'up')
        right=moved_chord(p,c,6000);self.assertEqual((right.start,right.end),(6000,6720));self.assertEqual(analyze(right,p).pattern,'up')
        self.assertIsNone(moved_chord(p,c,1900));self.assertIsNone(moved_chord(p,c,6720))

    def test_custom_translation_then_crop_preserves_velocity_and_spelling(self):
        p=mixed();c=Chord(3840,1920,notes=[Note(0,1920,60,117,flat=True)],custom_rhythm=True)
        result=moved_chord(p,c,3360)
        self.assertEqual(events(result.notes),[(0,1440,60,117,True)]);self.assertIsNone(analyze(result,p));self.assertFalse(result.recognized);self.assertTrue(result.custom_rhythm);self.assertEqual(label(result,p),'未知节奏型')

    def test_unknown_rhythm_can_become_known_after_crop(self):
        p=Project();c=Chord(0,1920,notes=[Note(0,480,48),Note(480,1440,48),Note(480,1440,52),Note(480,1440,55)])
        self.assertIsNone(analyze(c,p));self.assertEqual(label(c,p),'未知节奏型')
        result=moved_chord(p,c,-480);self.assertTrue(result.recognized);self.assertEqual(analyze(result,p).pattern,'block')
        c.custom_rhythm=True;result=moved_chord(p,c,-480);self.assertIsNone(analyze(result,p))

    def test_same_signature_disjoint_regions_still_disable_batch_keyboard_move(self):
        p=mixed();p.chords=[Chord(0,960),Chord(6720,960)];before=p.to_dict()
        with self.assertRaises(ValueError):move_chords(p,{c.id for c in p.chords},480)
        self.assertEqual(before,p.to_dict())

    def test_session_recovers_whole_and_partial_crops_on_reversal(self):
        p=mixed();c=Chord(3840,960);p.chords=[c];s=ChordMoveSession.capture(p,{c.id})
        s.apply(p,-1920);s.delta-=1920;self.assertFalse(p.chords)
        s.apply(p,960);s.delta+=960;self.assertFalse(p.chords)
        s.apply(p,480);s.delta+=480;self.assertEqual((p.chords[0].start,p.chords[0].duration),(3840,480))
        s.apply(p,480);s.delta+=480;self.assertEqual((p.chords[0].start,p.chords[0].duration),(3840,960));p.validate()

    def test_mixed_diatonic_selection_cannot_move_scale(self):
        p=Project();p.chords=[Chord(0,960),Chord(960,960,49)]
        for direction in (-1,1):self.assertFalse(can_move_diatonic(p,p.chords,direction))

    def test_delete_bars_splits_crossing_events_and_shifts_contexts(self):
        p=mixed();p.notes=[Note(3000,5000,60),Note(9000,480,64)];p.chords=[Chord(0,p.end)]
        p.contexts=[Context(0,6720),Context(6720,p.end,53,'Dorian')]
        self.assertTrue(deletion_has_content(p,[1]));delete_bars(p,[1])
        self.assertEqual(events(p.notes),[(3000,840,60,92,False),(3840,1280,60,92,False),(6120,480,64,92,False)])
        self.assertEqual(len(p.chords),2);self.assertEqual(p.context_at(3840).tonic,53);p.validate()

    def test_delete_disjoint_bars_keeps_lyrics_and_valid_layout_metadata(self):
        p=Project();p.notes=[Note(i*3840,480,60,lyric=str(i)) for i in range(8)]
        p.notation['forced_rows']=[[0,4],[4,8]];p.notation['symbols']=[dict(kind='double_bar',start=0,end=3840)]
        p.notation['compressions']=[dict(kind='repeat',start=0,first_end=2,hidden_start=2,hidden_end=4,end=4)]
        delete_bars(p,[1,3,6]);self.assertEqual(len(p.measures),5);self.assertEqual(len(p.notes),5);self.assertFalse(p.notation['compressions'])
        from lingfeng.engraving.lyrics import events as lyrics
        self.assertEqual([e['text'] for e in lyrics(p)],['0','2','4','5','7']);p.validate()
        before=p.to_dict()
        with self.assertRaises(ValueError):delete_bars(p,list(range(5)))
        self.assertEqual(p.to_dict(),before)

    def test_deleting_bar_cuts_rap_and_random_note_ranges_without_merging(self):
        import random
        rng=random.Random(29)
        for _ in range(25):
            p=Project();p.measures=[Measure(*rng.choice(((4,4),(3,4),(6,8)))) for _ in range(8)];p.contexts=[Context(0,p.end)]
            p.notes=[Note(i*480,min(rng.randint(1,5)*120,p.end-i*480),48+i%12) for i in range(p.end//480)]
            p.notation['lyric_events']=[dict(id='rap',tick=0,duration=p.end,text='声',kind='rap')]
            bars=sorted(rng.sample(range(8),3));expected=sum(m.ticks for i,m in enumerate(p.measures) if i not in bars)
            delete_bars(p,bars);p.validate();self.assertEqual(p.end,expected)
            self.assertEqual(sum(e['duration'] for e in p.notation['lyric_events']),expected)

    def test_crop_rechecks_the_symbol_from_remaining_midi(self):
        p=mixed();c=Chord(0,7680,notes=[Note(0,3840,48),Note(0,3840,52),Note(0,3840,55),Note(3840,3840,50)])
        p.chords=[c];p.change_meter(0,3,4,True)
        self.assertTrue(p.chords[0].recognized)
        self.assertFalse(p.chords[-1].recognized)

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.save=patch.object(MainWindow,'save_preferences');self.save.start()
        p=mixed();p.chords=[Chord(0,1920),Chord(3840,1920,50,'m'),Chord(6720,1920)]
        self.w=MainWindow(p);self.w.change_language('zh',False);self.w.show();self.w.resize(1280,900);self.w.timer.stop();self.w.autosave.stop()
        for b in self.w.mute_buttons.values():b.setChecked(True)
        APP.processEvents()
    def tearDown(self):self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.save.stop()
    def select(self,ids):
        w=self.w;w.chord_selection(ids,w.roll);w.roll.edit_target='chords';w.chord_lane.setFocus();APP.processEvents()
    def test_hidden_chord_keeps_selection_until_deselected_and_undo_restores(self):
        w=self.w;c=w.project.chords[1];self.select({c.id});before=w.project.to_dict()
        w.chord_command('move:-2400',{c.id},w.roll);self.assertNotIn(c.id,{x.id for x in w.project.chords});self.assertIn(c.id,w.roll.selected_chords)
        w.editor_key_command('right');self.assertNotIn(c.id,{x.id for x in w.project.chords})
        w.chord_command('move:2160',{c.id},w.roll);self.assertEqual((next(x for x in w.project.chords if x.id==c.id).start,next(x for x in w.project.chords if x.id==c.id).duration),(3840,1920))
        w.chord_command('move:-2400',{c.id},w.roll);w.chord_selection(set(),w.roll);self.assertIsNone(w.chord_move_session)
        w.editor_key_command('right');self.assertNotIn(c.id,{x.id for x in w.project.chords});w.undo();self.assertIn(c.id,{x.id for x in w.project.chords})

    def test_keyboard_rejects_mixed_regions_and_alt_scale_mixed_chords(self):
        w=self.w;self.select({c.id for c in w.project.chords});before=w.project.to_dict();w.editor_key_command('left');self.assertEqual(before,w.project.to_dict())
        w.project.chords[1].root=49;w.refresh();self.select({c.id for c in w.project.chords});before=w.project.to_dict()
        for command in ('scale_up','scale_down'):w.editor_key_command(command);self.assertEqual(before,w.project.to_dict())
        menu=w.chord_lane.context_menu(QPoint(round(w.chord_lane.x_at(480)),25))
        self.assertFalse(menu.move_menu.actions()[0].isEnabled());self.assertFalse(menu.move_menu.actions()[1].isEnabled())

    def test_drag_preview_does_not_regenerate_then_wrong_meter_release_is_noop(self):
        w=self.w;lane=w.chord_lane;c=w.project.chords[0];before=w.project.to_dict();history=len(w.undo_history)
        press=QPoint(round(lane.x_at(480)),25);end=QPoint(round(lane.x_at(4320)),25)
        with patch('lingfeng.music.meter.moved_chord',side_effect=AssertionError('Must not scan during preview')):
            QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=press);QTest.mouseMove(lane,end)
            self.assertEqual(w.project.to_dict(),before)
            QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=end)
        self.assertEqual(w.project.to_dict(),before);self.assertEqual(len(w.undo_history),history)

    def test_drag_can_cross_other_meter_to_matching_region(self):
        w=self.w;lane=w.chord_lane;c=w.project.chords[0]
        QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=QPoint(round(lane.x_at(480)),25))
        end=QPoint(round(lane.x_at(7200)),25);QTest.mouseMove(lane,end);QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=end)
        result=next(x for x in w.project.chords if x.id==c.id);self.assertEqual((result.start,result.end),(6720,8640));w.project.validate()

    def test_resize_only_rebuilds_on_release(self):
        w=self.w;lane=w.chord_lane;APP.processEvents();c=w.project.chords[0];before=w.project.to_dict()
        start=QPoint(round(lane.x_at(c.end)-3),25);end=QPoint(round(lane.x_at(2880)),25)
        QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=start)
        with patch('lingfeng.ui.piano_roll.resize_chord',side_effect=AssertionError('No generation while dragging')):
            lane.begin_resize();QTest.mouseMove(lane,end);self.assertEqual(before,w.project.to_dict())
        QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=end);self.assertEqual(w.project.chords[0].end,2880)

    def test_paste_menu_disabled_for_wrong_meter_and_keyboard_does_not_modify(self):
        w=self.w;c=w.project.chords[1];self.select({c.id});w.copy_selection();before=w.project.to_dict()
        menu=w.chord_lane.context_menu(QPoint(round(w.chord_lane.x_at(480)),25))
        action=next(a for a in menu.actions() if a.text()=='在此粘贴和弦');self.assertFalse(action.isEnabled())
        w.chord_command('paste',0,w.roll);self.assertEqual(before,w.project.to_dict())

    def test_delete_confirmation_cancel_accept_and_one_undo(self):
        w=self.w;before=w.project.to_dict()
        with patch('lingfeng.ui.main_window.QMessageBox.question',return_value=QMessageBox.StandardButton.No) as question:w.delete_measures([0,2]);self.assertTrue(question.called)
        self.assertEqual(w.project.to_dict(),before)
        with patch('lingfeng.ui.main_window.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):w.delete_measures([0,2])
        self.assertEqual(len(w.project.measures),2);w.undo();self.assertEqual(w.project.to_dict(),before)
        w.project.chords=[];w.project.notes=[];w.refresh()
        with patch('lingfeng.ui.main_window.QMessageBox.question',side_effect=AssertionError('Empty bars need no confirmation')):w.delete_measures([3])

    def test_offscreen_trailing_note_and_chord_do_not_recenter(self):
        r=self.w.roll;r.center_pitch(60);r.horizontalScrollBar().setValue(500);before=(r.horizontalScrollBar().value(),r.verticalScrollBar().value())
        r.ensure_events_visible([Note(0,960,90),Note(14000,960,30)],dx=1,dy=-1)
        self.assertEqual(before,(r.horizontalScrollBar().value(),r.verticalScrollBar().value()))
        r.ensure_events_visible([Chord(0,960),Chord(14000,960)],dx=-1);self.assertEqual(before[0],r.horizontalScrollBar().value())

if __name__=='__main__':unittest.main()
