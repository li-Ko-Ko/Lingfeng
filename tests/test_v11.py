import os,unittest,tempfile,struct,copy
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QDialog,QMenuBar,QMenu
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from lingfeng.ui.main_window import MainWindow
from lingfeng.music.model import Project, Note, Chord, Measure, Context, PPQ
from lingfeng.audio.midi import export_midi, track_bytes, meta
from lingfeng.audio.midi_import import read_midi, apply_midi, MidiData, MidiTrack
from lingfeng.ui.import_dialog import MidiImportDialog
from lingfeng.music.timing import grid_points, grid_bucket, selected_measures
from lingfeng.platform.i18n import set_language

APP=QApplication.instance() or QApplication([])


def payload(notes,end=1920,meters=None,tempos=None):
    return MidiData([MidiTrack('Melody',notes,end)],tempos or [],meters or [])


class MidiTests(unittest.TestCase):
    def test_export_read_import_roundtrip_two_tracks_and_ppq(self):
        p=Project();p.notes=[Note(240,777,60,85,lyric='风'),Note(600,900,64,91)];p.chords=[Chord(0,7680,48)]
        with tempfile.TemporaryDirectory(dir=Path("tmp").resolve()) as folder:
            path=Path(folder)/'song.mid';export_midi(p,path);data=read_midi(path)
        self.assertEqual([(n.start,n.duration,n.pitch,n.velocity,n.lyric) for n in data.tracks[1].notes],[(240,777,60,85,'风'),(600,900,64,91,'')])
        q=Project();apply_midi(q,data,[1],'melody',0)
        self.assertEqual([(n.start,n.duration,n.pitch) for n in q.notes],[(240,777,60),(600,900,64)])
        apply_midi(q,data,[2],'chords',0)
        self.assertEqual([(n.start,n.duration,n.pitch) for n in q.harmony_notes()],[(n.start,n.duration,n.pitch) for n in p.harmony_notes()])

    def test_running_status_different_ppq_velocity_zero_and_lyrics(self):
        events=b'\x00\x90\x3c\x50\x81\x70\x40\x60\x81\x70\x3c\x00\x00\x40\x00\x00\xff\x2f\x00'
        raw=b'MThd'+struct.pack('>IHHH',6,0,1,480)+b'MTrk'+struct.pack('>I',len(events))+events
        with tempfile.TemporaryDirectory(dir=Path("tmp").resolve()) as folder:
            path=Path(folder)/'running.mid';path.write_bytes(raw);data=read_midi(path)
        self.assertEqual([(n.start,n.duration,n.pitch) for n in data.tracks[0].notes],[(0,960,60),(480,480,64)])

    def test_invalid_midi_fails_before_any_import(self):
        for raw in (b'bad',b'MThd'+struct.pack('>IHHH',6,1,1,480),b'MThd'+struct.pack('>IHHH',6,2,1,480)):
            with tempfile.TemporaryDirectory(dir=Path("tmp").resolve()) as folder:
                path=Path(folder)/'bad.mid';path.write_bytes(raw)
                with self.assertRaises(ValueError):read_midi(path)

    def test_partial_melody_replacement_preserves_both_outside_tails_and_chords(self):
        p=Project();p.notes=[Note(0,6000,60),Note(7000,200,62)];p.chords=[Chord(0,7680,48)];before=copy.deepcopy(p.chords)
        apply_midi(p,payload([Note(240,480,65)]),[0],'melody',1920)
        self.assertEqual([(n.start,n.end,n.pitch) for n in p.notes],[(0,1920,60),(2160,2640,65),(3840,6000,60),(7000,7200,62)])
        self.assertEqual(p.chords,before)

    def test_chord_replacement_keeps_note_across_barline_and_other_track(self):
        p=Project();p.notes=[Note(0,4000,72)];p.chords=[Chord(0,12000,48)];before=copy.deepcopy(p.notes)
        data=payload([Note(120,5000,60),Note(960,960,64),Note(960,960,67)],6000)
        apply_midi(p,data,[0],'chords',1920)
        imported=[n for n in p.harmony_notes() if 1920<=n.start<7920]
        self.assertEqual(sorted((n.start,n.duration,n.pitch) for n in imported),[(2040,5000,60),(2880,960,64),(2880,960,67)])
        self.assertEqual(p.notes,before);self.assertEqual(p.chords[0].end,1920);self.assertEqual([c for c in p.chords if c.notes!=[]][-1].start,7920)

    def test_meter_tempo_opt_in_and_absolute_note_positions(self):
        data=payload([Note(0,480,60)],5760,[(0,3,4)],[(0,132),(2880,100)])
        p=Project();p.notes=[Note(10000,480,70)];apply_midi(p,data,[0],'chords',0,True,True)
        self.assertEqual(p.bpm,132);self.assertEqual(p.measures[0].ticks,2880);self.assertEqual(p.notes[0].start,10000)
        q=Project();apply_midi(q,data,[0],'melody',0);self.assertEqual(q.bpm,100);self.assertEqual(q.measures[0].ticks,3840)
        with self.assertRaises(ValueError):apply_midi(Project(),data,[0],'melody',240,True)

    def test_import_rejects_out_of_range_and_preserves_repeated_note_attacks(self):
        with self.assertRaises(ValueError):apply_midi(Project(),payload([Note(0,480,10)]),[0],'melody',0)
        p=Project();apply_midi(p,payload([Note(0,480,60),Note(480,480,60)]),[0],'melody',0);self.assertEqual(len(p.notes),2)


class BroadcastTests(unittest.TestCase):
    def test_disjoint_broadcast_only_selected_bars_and_no_duplicate_markers(self):
        p=Project();p.set_markers([1,3],53,'Dorian',3,4)
        self.assertEqual([p.marker_value(i) for i in range(5)],[(4,4,48,'Ionian'),(3,4,53,'Dorian'),(4,4,48,'Ionian'),(3,4,53,'Dorian'),(4,4,48,'Ionian')])
        p.set_markers([1,2,3],53,'Dorian',3,4);self.assertFalse(p.marker_visible(2));self.assertFalse(p.marker_visible(3));self.assertTrue(p.marker_visible(4));p.validate()

    def test_mixed_meter_grid_resets_at_each_bar_and_supports_bar_groups(self):
        p=Project();p.set_markers([0],48,'Ionian',3,8)
        points=grid_points(p,960);self.assertEqual(points[:5],[0,960,1440,2400,3360]);self.assertEqual(grid_bucket(p,1500,960),[1440,2400])
        self.assertEqual(grid_points(p,3840,2)[1],p.starts[2])


class EditingTests(unittest.TestCase):
    def setUp(self):
        set_language('zh');p=Project();p.notes=[Note(275,480,60),Note(900,480,64)];self.w=MainWindow(p);self.w.show();QTest.qWait(30)
        for b in self.w.mute_buttons.values():b.setChecked(True)
    def tearDown(self):self.w.dirty=False;self.w.close();APP.processEvents();set_language('zh')

    def test_duration_and_snap_are_independent_with_exclusive_modifiers(self):
        w=self.w;w.length.setCurrentIndex(w.length.findData(480));w.length.set_triplet(True);self.assertEqual(w.roll.duration,320);self.assertEqual(w.roll.grid,240)
        w.dotted.setChecked(True);self.assertFalse(w.length.triplet);self.assertEqual(w.roll.duration,720)
        w.grid.set_triplet(True);self.assertEqual(w.roll.grid,160);self.assertEqual(w.roll.duration,720)
        w.length.setCurrentIndex(w.length.findData(0));self.assertEqual(w.roll.note_duration(0),160)
        w.roll.previous_duration=777;w.length.setCurrentIndex(w.length.findData(-1));self.assertEqual(w.roll.note_duration(1000),777)
        w.open_harmony();self.assertEqual(w.harmony_window.length.currentData(),-1)

    def test_quantize_only_note_selection_and_undo(self):
        w=self.w;r=w.roll;self.assertFalse(hasattr(w,'quantize_button'));before=w.project.to_dict();w.quantize(r);self.assertEqual(w.project.to_dict(),before)
        r.selected_ids={r.notes[0].id};r.refresh();APP.processEvents();menu=QMenu();r.selection_menu(menu,0);self.assertIn('按当前格点量化',[a.text() for a in menu.actions()]);w.quantize(r)
        self.assertEqual(w.project.notes[0].start,240);self.assertEqual(w.project.notes[1].start,900);w.undo();self.assertEqual(w.project.to_dict(),before)
        r.selected_ids.clear();r.refresh();self.assertFalse(hasattr(w,'quantize_button'))

    def test_ctrl_toggle_shift_range_and_grid_selection_on_both_rulers(self):
        w=self.w;r=w.roll
        def click(bar,mod=Qt.KeyboardModifier.NoModifier):QTest.mouseClick(w.timeline,Qt.MouseButton.LeftButton,mod,QPoint(round(w.timeline.x_at(w.project.starts[bar]+500)),12));APP.processEvents()
        click(0);self.assertEqual(r.selection,[[0,3840]])
        click(2,Qt.KeyboardModifier.ControlModifier);self.assertEqual(selected_measures(w.project,r.selection),[0,2])
        click(0,Qt.KeyboardModifier.ControlModifier);self.assertEqual(selected_measures(w.project,r.selection),[2])
        click(3,Qt.KeyboardModifier.ShiftModifier);self.assertEqual(selected_measures(w.project,r.selection),[0,1,2,3])
        w.melody_window.setFloating(True);QTest.qWait(20)
        a=QPoint(round(r.x_at(500)),12);b=QPoint(round(r.x_at(1400)),12)
        QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=a);QTest.mouseMove(r.viewport(),b);QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=b);self.assertEqual(r.selection,[[0,3840]])

    def test_marker_dialog_broadcast_is_undoable_and_cancel_is_inert(self):
        w=self.w;w.open_harmony();w.harmony_window.setFloating(True);before=w.project.to_dict();fake=type('Dialog',(),{'exec':lambda s:QDialog.DialogCode.Accepted,'value':lambda s:dict(tonic=53,mode='Dorian',numerator=3,denominator=4)})
        with patch('lingfeng.ui.main_window.MarkerDialog',return_value=fake()):w.edit_context([[100,300],[8000,8300]])
        self.assertEqual(w.project.marker_value(0)[2:],(53,'Dorian'));self.assertEqual(w.project.marker_value(1)[2:],(48,'Ionian'));self.assertEqual(w.project.marker_value(2)[2:],(53,'Dorian'))
        self.assertEqual(w.harmony_window.roll.selection,[w.project.starts[i:i+2] for i in (0,2)])
        w.undo();self.assertEqual(w.project.to_dict(),before)

    def test_import_dialog_defaults_and_real_menu_import_undo(self):
        w=self.w;data=payload([Note(0,240,70)])
        dialog=MidiImportDialog(w.project,data,'melody',0,w);self.assertFalse(dialog.meter.isChecked());self.assertFalse(dialog.tempo.isChecked());self.assertEqual(dialog.indices(),[0]);dialog.close()
        with tempfile.TemporaryDirectory(dir=Path("tmp").resolve()) as folder:
            source=Project();source.notes=[Note(0,240,70)];path=Path(folder)/'input.mid';export_midi(source,path);before=w.project.to_dict()
            with patch('lingfeng.ui.main_window.QFileDialog.getOpenFileName',return_value=(str(path),'')),patch.object(MidiImportDialog,'exec',return_value=QDialog.DialogCode.Accepted):w.import_midi('melody')
            self.assertEqual(w.project.notes[0].pitch,70);w.undo();self.assertEqual(w.project.to_dict(),before)
            with patch('lingfeng.ui.main_window.QFileDialog.getOpenFileName',return_value=(str(path),'')),patch.object(MidiImportDialog,'exec',return_value=QDialog.DialogCode.Rejected):w.import_midi('melody')
            self.assertEqual(w.project.to_dict(),before)

    def test_brand_aligns_menu_and_grid_is_at_right_in_both_languages(self):
        w=self.w
        for language in ('zh','en'):
            if w.language!=language:w.change_language(language,False)
            APP.processEvents();menu=w.title_bar.menu
            self.assertEqual(menu.actionGeometry(w.title_bar.brand).center().y(),menu.actionGeometry(menu.actions()[1]).center().y());self.assertEqual(w.title_bar.brand.font().pixelSize(),menu.font().pixelSize())
            self.assertGreater(w.grid.mapTo(w,QPoint()).x(),w.length.mapTo(w,QPoint()).x())


if __name__=='__main__':unittest.main()
