"""Performed harmony, explicit regeneration, and per-window time geometry."""
import copy,os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import QPoint,QRectF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from lingfeng.ui.main_window import MainWindow
from lingfeng.music.model import Project, Chord, Note, PPQ
from lingfeng.ui.dialogs import ChordDialog
from lingfeng.music.rhythm import analyze, analyze_performed
from lingfeng.music.chord_operations import change_chords, chord_details
from lingfeng.engraving.notation import is_chord_tone
from lingfeng.ui.piano_roll import KEY_W
from lingfeng.ui.theme import color
from lingfeng.platform.i18n import set_language

APP=QApplication.instance() or QApplication([])

def bass_fragment():
    return Chord(0,PPQ,58,pattern='bass_chord',notes=[Note(0,864,46,73)])

def events(c):return [(n.start,n.duration,n.pitch,n.velocity) for n in c.render_notes()]


class RegenerationTests(unittest.TestCase):
    def test_performed_recognition_does_not_change_region_edit_semantics(self):
        p=Project();c=bass_fragment();before=copy.deepcopy(c)
        self.assertEqual(analyze(c,p).pattern,'bass_chord')
        self.assertEqual(analyze_performed(c,p).pattern,'quarters');self.assertEqual(c,before)

    def test_circles_and_hover_agree_with_actual_midi(self):
        p=Project();c=bass_fragment();p.chords=[c]
        self.assertTrue(is_chord_tone(p,58,0));self.assertFalse(is_chord_tone(p,62,320))
        details=chord_details(p,c);self.assertIn('A#2',details);self.assertNotIn('D4',details);self.assertNotIn('F4',details)

    def test_dialog_defaults_to_fragment_pattern_and_fills_all_voices(self):
        p=Project();c=bass_fragment();before=copy.deepcopy(c);d=ChordDialog(c,p)
        try:
            self.assertTrue(d.regenerate.isChecked());self.assertEqual(d.pattern.currentData(),'quarters')
            result=d.value();p.put_chord(result);result=p.chords[0]
            self.assertEqual({n.pitch%12 for n in result.render_notes()},{0,4,7})
            self.assertEqual(analyze(result,p).pattern,'quarters');self.assertEqual({n.duration for n in result.render_notes()},{864})
            self.assertTrue(is_chord_tone(p,64,320));self.assertEqual(c,before)
        finally:d.deleteLater()

    def test_dialog_can_keep_midi_and_cancelling_never_edits_source(self):
        p=Project();c=bass_fragment();before=events(c);d=ChordDialog(c,p)
        try:
            d.root.setCurrentIndex(d.root.findData(c.root%12));d.regenerate.setChecked(False)
            result=d.value();self.assertEqual(events(result),before);self.assertEqual(result.pattern,c.pattern)
            d.reject();self.assertEqual(events(c),before)
        finally:d.deleteLater()

    def test_root_and_quality_quick_edits_rebuild_incomplete_chords(self):
        for action,pcs,pitches in [('quality:m',{10,1,5},{46,58,61,65}),('root:0',{0,4,7},{36,48,52,55})]:
            with self.subTest(action=action):
                p=Project();c=bass_fragment();p.chords=[c];change_chords(p,{c.id},action)
                self.assertEqual(c.pattern,'quarters');self.assertEqual(analyze(c,p).pattern,'quarters')
                self.assertEqual({n.pitch%12 for n in c.notes},pcs);self.assertEqual({n.pitch for n in c.notes},pitches)
                self.assertEqual({(n.start,n.duration,n.velocity) for n in c.notes},{(0,864,c.velocity)});p.validate()

    def test_bass_and_inversion_do_not_fill_missing_voices(self):
        for action in ('bass:2','inversion:1'):
            with self.subTest(action=action):
                p=Project();c=bass_fragment();p.chords=[c];before=[(n.start,n.duration,n.velocity,n.id) for n in c.notes]
                change_chords(p,{c.id},action)
                self.assertEqual([(n.start,n.duration,n.velocity,n.id) for n in c.notes],before)
                self.assertEqual(c.pattern,'bass_chord');self.assertEqual(c.notes[0].pitch%12,2)

    def test_explicit_custom_lock_disables_automatic_fragment_recognition(self):
        p=Project();c=bass_fragment();c.custom_rhythm=True
        self.assertIsNone(analyze_performed(c,p));d=ChordDialog(c,p)
        try:
            d.regenerate.setChecked(False);self.assertTrue(d.value().custom_rhythm)
            d.regenerate.setChecked(True);self.assertFalse(d.value().custom_rhythm)
        finally:d.deleteLater()


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prefs=patch.object(MainWindow,'save_preferences');cls.prefs.start()
        cls.w=MainWindow(Project());cls.w.change_language('zh',False);cls.w.show();cls.w.timer.stop();cls.w.autosave.stop()
    @classmethod
    def tearDownClass(cls):
        cls.w.dirty=False;cls.w.close();cls.w.deleteLater();APP.processEvents();cls.prefs.stop();set_language('zh')
    def setUp(self):
        w=self.w;w.switch_workspace('compose');w.melody_window.setFloating(False);w.harmony_window.setFloating(False)
        w.replace_project(Project());w.resize(1100,860);w.open_harmony();w.change_language('zh',False)
        w.visibility_actions['melody'].setChecked(True);w.visibility_actions['chords'].setChecked(True)
        w.set_theme('dark');w.grid.setCurrentIndex(4);w.grid.set_triplet(False);w.change_chord_ruler(1)
        w.roll.zoom=120;w.roll.update_ranges();w.roll.timeViewChanged.emit();w.roll.horizontalScrollBar().setValue(0);w.seek(960)
        w.mount_panels();APP.processEvents()

    def test_each_docked_roll_controls_page_grid_and_triplets(self):
        w=self.w;w.harmony_window.grid.setCurrentIndex(6);w.harmony_window.grid.set_triplet(True)
        for r in (w.main_roll,w.roll,w.harmony_window.roll):self.assertEqual((r.grid,r.grid_bars),(40,0))
        self.assertEqual(w.grid.currentData(),40);self.assertEqual(w.timeline.roll.grid,40)
        w.grid.setCurrentIndex(9)
        for r in (w.main_roll,w.roll,w.harmony_window.roll):self.assertEqual(r.grid_bars,4)
        self.assertEqual(w.harmony_window.grid.bars,4)

    def test_floating_grids_are_local_and_redocking_inherits_destination(self):
        w=self.w;w.harmony_window.setFloating(True);w.set_timeline_sync(False,w.harmony_window.roll)
        w.harmony_window.grid.setCurrentIndex(7);self.assertEqual(w.harmony_window.roll.grid,30);self.assertEqual(w.main_roll.grid,240)
        w.grid.setCurrentIndex(3);w.grid.set_triplet(True);self.assertEqual(w.main_roll.grid,320);self.assertEqual(w.harmony_window.roll.grid,30)
        w.harmony_window.setFloating(False);APP.processEvents()
        self.assertEqual(w.harmony_window.roll.grid,320);self.assertEqual(w.harmony_window.grid.currentData(),320)

    def test_main_timeline_retains_scale_when_both_rolls_float(self):
        w=self.w;w.grid.setCurrentIndex(3);w.roll.zoom=190;w.roll.update_ranges();w.roll.timeViewChanged.emit()
        w.melody_window.setFloating(True);w.harmony_window.setFloating(True)
        w.set_timeline_sync(False,w.roll);w.set_timeline_sync(False,w.harmony_window.roll)
        w.grid.setCurrentIndex(6);w.roll.zoom=300;w.roll.update_ranges();w.roll.timeViewChanged.emit()
        self.assertEqual(w.main_roll.grid,480);self.assertEqual(w.main_roll.zoom,190)
        w.melody_window.setFloating(False);APP.processEvents()
        self.assertEqual(w.roll.grid,480);self.assertEqual(w.grid.currentData(),480);self.assertEqual(w.roll.zoom,190)

    def test_revealed_roll_and_language_rebuild_keep_page_scale(self):
        w=self.w;w.visibility_actions['harmony'].setChecked(False);w.grid.setCurrentIndex(5);w.grid.set_triplet(True)
        w.open_harmony();self.assertEqual(w.harmony_window.roll.grid,80)
        w.change_language('en',False)
        self.assertEqual(w.timeline.roll.grid,80);self.assertEqual(w.grid.currentData(),80);self.assertEqual(w.harmony_window.grid.currentData(),80)

    def assert_alignment(self,roll,lane):
        for tick in (0,240,960,2640,6000):
            actual=roll.viewport().mapToGlobal(QPoint()).x()+roll.x_at(tick)
            self.assertEqual(actual,lane.mapToGlobal(QPoint()).x()+lane.x_at(tick))
            self.assertEqual(lane.tick_at(lane.x_at(tick)),tick)

    def test_all_position_lines_align_in_narrow_floating_and_restored_windows(self):
        w=self.w
        for theme in ('light','dark'):
            w.set_theme(theme)
            for pane,roll,lane in ((w.melody_window,w.roll,w.roll.lane),(w.harmony_window,w.harmony_window.roll,w.harmony_window.top_lane)):
                pane.setFloating(True);APP.processEvents();w.set_timeline_sync(False,roll)
                for width in (700,1100):
                    pane.resize(width,620);APP.processEvents();roll.horizontalScrollBar().setValue(130);self.assert_alignment(roll,lane)
                pane.showMaximized();APP.processEvents();self.assert_alignment(roll,lane)
                pane.showNormal();lane.set_velocity_visible(True);APP.processEvents();self.assert_alignment(roll,lane)
                lane.set_velocity_visible(False);pane.setFloating(False)
            APP.processEvents();roll=w.timeline.roll
            self.assertEqual(w.timeline.mapToGlobal(QPoint()).x()+w.timeline.x_at(960),roll.viewport().mapToGlobal(QPoint()).x()+roll.x_at(960))
            self.assert_alignment(roll,w.chord_lane)

    def test_auxiliary_ruler_scale_uses_meter_beats_without_changing_snap(self):
        w=self.w;p=Project();p.set_markers([0],48,'Ionian',6,8);w.replace_project(p);w.roll.zoom=120;w.roll.update_ranges();w.roll.timeViewChanged.emit()
        lane=w.chord_lane;grid=w.roll.grid;before=p.to_dict();w.change_chord_ruler(1)
        xs=[x for x,_,label in lane.ruler_ticks() if label.startswith('1.')]
        self.assertGreater(len(xs),2);self.assertEqual(xs[1]-xs[0],60)
        w.change_chord_ruler(.5);xs=[x for x,_,label in lane.ruler_ticks() if label.startswith('1.')];self.assertEqual(xs[1]-xs[0],30)
        for target in (w.chord_lane,w.roll.lane,w.harmony_window.top_lane):self.assertEqual(target.aux_ruler_scale,.5)
        self.assertEqual(w.roll.grid,grid);self.assertEqual(p.to_dict(),before)
        w.change_chord_ruler(0);self.assertEqual(list(lane.ruler_ticks()),[])

    def test_cursor_pixels_align_in_the_composited_window(self):
        w=self.w;w.seek(1440);APP.processEvents()
        for mode in ('light','dark'):
            w.set_theme(mode);image=w.grab().toImage();ratio=image.devicePixelRatio()
            for widget,x,y in ((w.timeline,w.timeline.x_at(1440),15),
                               (w.roll.viewport(),w.roll.x_at(1440),w.roll.ruler_height+20),
                               (w.chord_lane,w.chord_lane.x_at(1440),25)):
                point=widget.mapTo(w,QPoint(round(x),y))
                self.assertEqual(image.pixelColor(round(point.x()*ratio),round(point.y()*ratio)),color('#D15F49'))

    def test_auxiliary_ticks_are_covered_by_cards_then_appear_on_drag_overlay(self):
        w=self.w;c=Chord(0,4*PPQ);w.project.chords=[c];w.refresh();lane=w.chord_lane;APP.processEvents()
        def render():
            img=QImage(lane.size(),QImage.Format.Format_ARGB32);p=QPainter(img)
            try:lane.paint_content(p)
            finally:p.end()
            return img
        w.change_chord_ruler(0);plain=render();w.change_chord_ruler(1);normal=render()
        x=round(lane.x_at(PPQ));self.assertEqual(plain.pixelColor(x,8),normal.pixelColor(x,8))
        lane.preview=copy.deepcopy(c);lane.preview.duration+=PPQ;moving=render()
        self.assertNotEqual(moving.pixelColor(x,8),normal.pixelColor(x,8));self.assertEqual(lane.chord_hit(QPoint(x,8))[1].id,c.id)
        lane.preview=None

    def test_loop_has_only_vertical_borders_and_shared_fill(self):
        w=self.w;w.set_loop_range((960,2880));r=w.roll;width=800;h=r.bar_ruler_height+30
        image=QImage(width,h,QImage.Format.Format_ARGB32);painter=QPainter(image)
        try:r.paint_ruler(painter,width,h,r.x_at)
        finally:painter.end()
        x=round(r.x_at(1600));y=r.bar_ruler_height
        self.assertEqual(image.pixelColor(x,y+2),image.pixelColor(x,y+6))
        self.assertNotEqual(image.pixelColor(round(r.x_at(960)),y+6),image.pixelColor(x,y+6))


if __name__=='__main__':unittest.main()
