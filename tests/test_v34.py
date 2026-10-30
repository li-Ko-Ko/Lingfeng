"""Continuous harmony MIDI, progression and export contracts for 0.34."""
import copy,os,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPointF,Qt
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Project, Chord, Note, PPQ, Context, Measure
from lingfeng.music.chord_operations import merge_chords, split_at_position, change_chords
from lingfeng.audio.midi import export_midi, event_list
from lingfeng.audio.midi_import import read_midi, apply_midi, MidiData, MidiTrack
from lingfeng.audio.exporting import bounds, export_mp3, offline_pcm
from lingfeng.music.progressions import resolve, apply, capture, tokens
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.dialogs import ChordDialog
from lingfeng.ui.export_dialog import ExportDialog
from lingfeng.engraving.notation import ScoreLayout, export_pdf, PAPER_W, PAPER_H
from lingfeng.ui.fonts import ensure_fonts
import lingfeng.ui.theme as theme
APP=QApplication.instance() or QApplication([]);ensure_fonts()

def signature(notes):return [(n.start,n.duration,n.pitch,n.velocity) for n in notes]

class DataTests(unittest.TestCase):
    def test_continuous_note_crosses_boundaries_without_midi_rearticulation(self):
        p=Project();p.fill_chord_gaps();regions=[(c.start,c.end) for c in p.chords]
        n=Note(3000,6000,60,85);p.overwrite_harmony(n);p.validate()
        self.assertEqual(signature(p.harmony_notes()),signature([n]))
        self.assertEqual([(c.start,c.end) for c in p.chords],regions)
        self.assertEqual(len([e for e in event_list(p) if e[1] and e[2]==1]),1)
        self.assertEqual([c.pcs for c in p.chords[:3]],[{0},{0},{0}])
        q=Project.from_dict(p.to_dict());self.assertEqual(signature(q.harmony_notes()),signature([n]))
        p.edit_harmony(delete_id=n.id);self.assertFalse(p.harmony_notes())

    def test_region_merge_preserves_every_onset_and_velocity(self):
        p=Project();p.chords=[Chord(0,960,notes=[Note(0,800,60,41)]),Chord(960,960,notes=[Note(0,960,67,99)])]
        before=signature(p.harmony_notes());merge_chords(p,{c.id for c in p.chords})
        self.assertEqual(signature(p.harmony_notes()),before);self.assertEqual(p.chords[0].end,1920);p.validate()

    def test_explicit_split_and_chord_replacement_cut_sustain(self):
        p=Project();p.fill_chord_gaps();p.overwrite_harmony(Note(0,7000,60))
        split_at_position(p,960)
        self.assertEqual([n.duration for n in p.harmony_notes()],[960,6040])
        p.put_chord(Chord(3840,3840,55))
        self.assertTrue(all(n.end<=3840 or n.start>=3840 for n in p.harmony_notes()));p.validate()

    def test_midi_import_extends_regions_for_cross_bar_note(self):
        p=Project();notes=[Note(3000,2000,60),Note(0,960,64)]
        data=MidiData([MidiTrack('Chord',notes,7680)],[],[])
        apply_midi(p,data,[0],'chords',0)
        self.assertEqual(signature(p.harmony_notes()),signature(sorted(notes,key=lambda n:(n.start,n.pitch))))
        self.assertEqual(p.chords[0].duration,7680);self.assertEqual(p.chords[-1].end,p.end)

    def test_nc_after_insertion_and_removal_has_no_sound(self):
        p=Project();p.fill_chord_gaps();self.assertEqual(len(p.chords),8)
        self.assertTrue(all(c.name==c.roman(48)=='N.C.' for c in p.chords));self.assertFalse(event_list(p))
        p.insert_measure(3);self.assertEqual(len(p.chords),9);p.chords.pop(4);p.fill_chord_gaps();p.validate();self.assertEqual(len(p.chords),9)

    def test_sections_preserve_repeated_names_and_export_bounds(self):
        p=Project();p.measures[0].section='verse';p.measures[2].section='verse';p.measures[5].section='Outro'
        self.assertEqual(p.sections(),[('Verse',0,2),('Verse',2,5),('Outro',5,8)])
        self.assertEqual(bounds(p,'section',section=1),(7680,19200));self.assertEqual(bounds(p,'bars',2,4),(3840,15360))
        with self.assertRaises(ValueError):bounds(p,'loop')

    def test_midi_range_crops_notes_and_retains_initial_meter(self):
        p=Project();p.notes=[Note(0,4800,60)];p.fill_chord_gaps();p.overwrite_harmony(Note(2000,4000,67))
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            path=Path(tmp)/'range.mid';export_midi(p,path,'both',3840,5760);data=read_midi(path)
            notes=data.notes_for(range(len(data.tracks)));self.assertEqual(sorted((n.start,n.duration,n.pitch) for n in notes),[(0,960,60),(0,1920,67)])
            self.assertEqual(data.meters,[(0,4,4)]);self.assertEqual(max(t.end for t in data.tracks),1920)

    def test_progression_crosses_meter_with_one_starting_tonic(self):
        p=Project();p.change_meter(1,3,4);p.set_context([[3840,p.end]],tonic=53);p.fill_chord_gaps()
        ids=apply(p,p.chords[0].id,'I ii7 V7 Imaj7',False,'block',83)
        self.assertEqual([c.root%12 for c in p.chords[:4]],[0,2,7,0]);self.assertEqual([c.quality for c in p.chords[:4]],['','m7','7','maj7'])
        self.assertEqual(capture(p,set(ids)),'I ii7 V7 Imaj7');p.validate()

    def test_progression_truncates_and_rejects_incompatible_rhythm(self):
        p=Project();p.change_meter(1,3,8);p.fill_chord_gaps();before=p.to_dict()
        with self.assertRaises(ValueError):apply(p,p.chords[0].id,'I V',False,'quarters')
        self.assertEqual(p.to_dict(),before)
        self.assertEqual(len(apply(p,p.chords[-1].id,'I V vi IV')),1)
        self.assertEqual(resolve('V/vi',0).root%12,4);self.assertEqual(resolve('bVII',0).root%12,10)

    def test_mp3_is_encoded_and_cancel_does_not_replace_target(self):
        p=Project();p.notes=[Note(0,PPQ,60)]
        with tempfile.TemporaryDirectory(dir='tmp') as tmp:
            path=Path(tmp)/'test.mp3';export_mp3(p,path,end=PPQ)
            self.assertGreater(path.stat().st_size,10000);original=path.read_bytes();self.assertTrue(original[:2] in (b'\xff\xfb',b'\xff\xfa'))
            flag=threading.Event();flag.set()
            with self.assertRaises(InterruptedError):export_mp3(p,path,end=PPQ,cancel=flag)
            self.assertEqual(path.read_bytes(),original);self.assertFalse(path.with_name('test.mp3.part').exists())

    @unittest.skipUnless(os.name=='nt','WASAPI uses Windows COM')
    def test_every_realtime_worker_has_its_own_audio_apartment(self):
        import ctypes
        from lingfeng.audio.exporting import realtime_pcm
        checks=[];errors=[]
        def capture(*args):
            kind=ctypes.c_int();qualifier=ctypes.c_int()
            result=ctypes.WinDLL('ole32').CoGetApartmentType(ctypes.byref(kind),ctypes.byref(qualifier))
            checks.append(result);yield b'\0'*8
        def run():
            try:list(realtime_pcm(Project(),'both',0,240,threading.Event(),lambda value:None))
            except Exception as exc:errors.append(str(exc))
        with patch('lingfeng.audio.exporting._capture_pcm',capture):
            for _ in range(3):worker=threading.Thread(target=run);worker.start();worker.join()
        self.assertEqual(errors,[]);self.assertEqual(checks,[0,0,0])

    def test_quality_and_root_rebuild_and_quality_resets_bass(self):
        p=Project();c=Chord(0,1920,48,'',bass=4,pattern='quarters',velocity=81);p.chords=[c]
        change_chords(p,{c.id},'quality:maj7');self.assertIsNone(c.bass);self.assertEqual(c.pattern,'quarters');self.assertEqual(min(n.pitch for n in c.notes)%12,0)
        change_chords(p,{c.id},'root:7');self.assertEqual({n.pitch%12 for n in c.notes},{7,11,2,6});self.assertEqual(c.velocity,81)

    def test_progression_keep_and_fallback_preserve_regions(self):
        from lingfeng.music.rhythm import analyze
        p=Project();p.chords=[Chord(0,3840,pattern='up'),Chord(3840,3840,custom_rhythm=True,notes=[Note(35,777,60,40)])]
        before=[(c.start,c.duration,c.id) for c in p.chords]
        apply(p,p.chords[0].id,'IV V',True,'quarters',90)
        self.assertEqual([(c.start,c.duration,c.id) for c in p.chords],before)
        self.assertEqual([analyze(c,p).pattern for c in p.chords],['up','quarters'])
        self.assertTrue(all(n.velocity==90 for n in p.harmony_notes()))

    def test_all_quality_progression_capture_roundtrips(self):
        from lingfeng.music.model import QUALITIES
        p=Project()
        for quality in QUALITIES:
            p.chords=[Chord(0,960,48,quality)]
            self.assertEqual(resolve(capture(p,{p.chords[0].id}),48).quality,quality)

    def test_removed_container_suffix_is_rejected(self):
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            path=Path(folder)/'old.popscore'
            with self.assertRaises(ValueError):Project().save(path)
            with self.assertRaises(ValueError):Project.load(path)

class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prefs=patch.object(MainWindow,'save_preferences');cls.prefs.start();cls.w=MainWindow(Project());cls.w.change_language('zh',False);cls.w.show();cls.w.timer.stop();cls.w.autosave.stop()
    @classmethod
    def tearDownClass(cls):
        cls.w.dirty=False;cls.w.close();cls.w.deleteLater();APP.processEvents();cls.prefs.stop()
    def setUp(self):
        w=self.w;w.replace_project(Project());w.switch_workspace('compose');w.melody_window.setFloating(False);w.harmony_window.setFloating(False);w.visibility_actions['melody'].setChecked(True);w.visibility_actions['chords'].setChecked(True);APP.processEvents()

    def test_nc_coverage_after_ui_note_changes_and_undo(self):
        w=self.w;r=w.harmony_window.roll
        self.assertTrue(w.edit_notes(r,[Note(3000,2000,60)],[]));self.assertEqual(len(w.project.harmony_notes()),1)
        w.undo();self.assertFalse(w.project.harmony_notes());self.assertEqual(len(w.project.chords),8)

    def test_font_size_changes_height_without_changing_pitch_spacing(self):
        w=self.w;p=Project();p.notes=[Note(i*240,240,60) for i in range(16)];w.replace_project(p);w.switch_workspace('score');gap=w.project.notation['row_gap']
        w.note_font.setValue(10);small=w.score_view.canvas.layout.glyph_scale
        w.note_font.setValue(22);large=w.score_view.canvas.layout.glyph_scale
        self.assertGreater(large,small);self.assertLessEqual(large*15,w.score_view.canvas.layout.max_font_size);self.assertEqual(w.project.notation['row_gap'],gap)
        layout=w.score_view.canvas.layout;image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_ARGB32);painter=QPainter(image);layout.draw(painter,0);painter.end()
        for _,_,a,b,left,right in layout.symbol_boxes:self.assertGreaterEqual(a,left-.01);self.assertLessEqual(b,right+.01)

    def test_chord_dialog_has_degrees_quality_codes_and_root_bass_default(self):
        c=Chord(0,1920,48,'',bass=4);d=ChordDialog(c,self.w.project)
        try:
            self.assertIn('3',d.bass.itemText(d.bass.findData(4)));self.assertIn('M7',d.quality.itemText(d.quality.findData('maj7')))
            d.quality.setCurrentIndex(d.quality.findData('maj7'));self.assertEqual(d.bass.currentData(),d.root.currentData())
            self.assertIsNone(d.value().bass)
        finally:d.deleteLater()

    def test_format_specific_export_dialogs(self):
        w=self.w;w.project.measures[0].section='Intro'
        for format in ('pdf','midi','mp3'):
            d=ExportDialog(w,format)
            try:
                if format=='pdf':self.assertFalse(hasattr(d,'range'));self.assertEqual(list(d.options()['pages']),[0])
                else:self.assertGreaterEqual(d.range.findData('section'),0);self.assertEqual(d.options()['end'],w.project.end)
                if format=='mp3':self.assertEqual(d.mode.count(),2)
            finally:d.deleteLater()

    def test_off_grid_note_drag_and_keyboard_snap_absolute_onset(self):
        w=self.w;p=Project();p.notes=[Note(130,240,60)];w.replace_project(p);r=w.roll;r.grid=240;r.selected_ids={p.notes[0].id};r.gesture_notes=copy.deepcopy(r.notes)
        r.drag=('move',r.notes[0],180,60);r.move_gesture(QPointF(r.x_at(290),r.y_at(60)+r.row_height/2))
        self.assertEqual(r.preview.start,240);r.drag=None;r.preview=None;r.previews={}
        r.edit_target='notes';r.setFocus();w.last_main_surface='melody';APP.processEvents()
        w.editor_key_command('right');self.assertEqual(w.project.notes[0].start,240)

    def test_preference_does_not_change_midi_and_grid_gaps_are_bounded(self):
        w=self.w;r=w.roll;before=w.project.to_dict();w.change_accidentals('flat')
        self.assertEqual(theme.roll_pitch_name(61),'Db4');self.assertEqual(r.note_degree_label(61,0,960),'♭2');self.assertEqual(w.project.to_dict(),before)
        w.change_accidentals('sharp');r.zoom=512;r.grid=240;r.update_ranges();r.center_pitch(60)
        self.assertTrue(r.grid_gap(QPointF(r.x_at(960)+7,r.y_at(60)+10)))
        r.zoom=32;r.update_ranges();self.assertFalse(r.grid_gap(QPointF(r.x_at(960)+3,r.y_at(60)+10)))

    def test_only_chord_lane_stays_at_top_and_visual_clock_is_fresh(self):
        w=self.w;w.visibility_actions['melody'].setChecked(False);w.visibility_actions['harmony'].setChecked(False);APP.processEvents()
        self.assertLess(w.timeline.mapTo(w.compose,w.timeline.rect().topLeft()).y(),100)
        self.assertLess(w.chord_lane.mapTo(w.compose,w.chord_lane.rect().topLeft()).y(),180)
        r=w.roll;r.play_tick=5;r.cursor_tick=5;r.playback_clock=lambda:970
        self.assertEqual(r.visual_tick(),970);r.playback_clock=w.transport.position;r.play_tick=None

    def test_root_edit_regenerates_even_after_unchecking_when_fully_recognized(self):
        c=Chord(0,1920,48,pattern='quarters');c.materialize();d=ChordDialog(c,self.w.project)
        try:
            d.root.setCurrentIndex(d.root.findData(7));d.regenerate.setChecked(False)
            value=d.value();self.assertEqual(value.root%12,7);self.assertIsNone(value.notes);self.assertEqual(value.pattern,'quarters')
        finally:d.deleteLater()

    def test_replay_and_edit_shortcuts_and_single_move_audition(self):
        from lingfeng.ui.keybindings import normalized
        w=self.w;r=w.roll;w.keybindings=normalized({});self.assertEqual(w.keybindings['replay'],'R');self.assertEqual(w.keybindings['edit_chord'],'C')
        r.edit_target='chords';r.selected_chords={w.project.chords[0].id};r.setFocus();w.last_main_surface='melody';APP.processEvents()
        with patch.object(w,'edit_chord') as edit:w.editor_key_command('edit_chord');edit.assert_called_once()
        with patch.object(w,'replay') as replay:w.editor_key_command('replay');replay.assert_called_once()
        w.project.notes=[Note(130,240,60)];w.refresh();r.edit_target='notes';r.selected_ids={w.project.notes[0].id};heard=[];r.audition.connect(heard.append)
        try:w.editor_key_command('right');self.assertEqual(heard,[ [60] ])
        finally:r.audition.disconnect(heard.append)

    def test_open_save_remember_directory_and_export_pauses(self):
        w=self.w
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            path=Path(folder).resolve()/'saved.lfs'
            with patch('lingfeng.ui.main_window.QFileDialog.getSaveFileName',return_value=(str(path),'')):self.assertTrue(w.save())
            self.assertEqual(w.last_project_dir,str(path.parent));w.replace_project(Project())
            with patch('lingfeng.ui.main_window.QFileDialog.getOpenFileName',return_value=(str(path),'')) as choose:w.open();self.assertEqual(Path(choose.call_args.args[2]),path.parent)
            self.assertEqual(w.path,path)
        with patch.object(w,'stop') as stop,patch('lingfeng.ui.export_dialog.ExportDialog.exec',return_value=0):w.open_export('mp3');stop.assert_called_once()

    def test_sections_menu_and_ruler_end_are_grid_aligned(self):
        from lingfeng.ui.timeline import TimelineGesture
        from types import SimpleNamespace
        from PySide6.QtCore import QPoint
        w=self.w;r=w.main_roll;r.grid=240
        w.set_section([0,2],'verse');self.assertEqual(w.project.sections(),[('Verse',0,2),('Verse',2,8)])
        menu=r.timeline_menu(QPoint(round(r.x_at(960)),10))
        section=next(a.menu() for a in menu.actions() if a.text()=='段落标识');self.assertIn('Prechorus',[a.text() for a in section.actions()]);menu.deleteLater()
        heard=[];r.playheadChanged.connect(heard.append);gesture=TimelineGesture(w.timeline,lambda:r)
        gesture.state=dict(upper=False,moved=False,button=Qt.MouseButton.LeftButton)
        event=SimpleNamespace(button=lambda:Qt.MouseButton.LeftButton,position=lambda:QPointF(r.x_at(w.project.end-1),r.bar_ruler_height+12))
        try:gesture.release(event);self.assertEqual(heard[-1],w.project.end-240)
        finally:r.playheadChanged.disconnect(heard.append);gesture.deleteLater()

if __name__=='__main__':unittest.main()
