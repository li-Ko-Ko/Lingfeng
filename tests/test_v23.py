"""Uniform overwrite, view synchronization, continuous notes and cached playback."""
import copy,os,sys,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from lingfeng.ui.main_window import MainWindow
from lingfeng.music.model import Project, Chord, Note, PPQ, Measure
from lingfeng.ui.piano_roll import PianoRoll, KEY_W
import lingfeng.ui.theme as theme

APP=QApplication.instance() or QApplication([])

def wheel(widget,x,y=15,mod=Qt.KeyboardModifier.ShiftModifier):
    point=QPointF(x,y)
    event=QWheelEvent(point,QPointF(widget.mapToGlobal(point.toPoint())),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,mod,Qt.ScrollPhase.NoScrollPhase,False)
    APP.sendEvent(widget,event);APP.processEvents()

class CategoryTests(unittest.TestCase):
    def test_harmony_colors_follow_region_not_measure_and_include_sustains(self):
        p=Project();p.chords=[Chord(240,960),Chord(1200,6000)]
        p.notes=[Note(0,600,60),Note(960,120,61),Note(1200,100,64),Note(5000,120,67)]
        cache={}
        for tick in (240,700,1199):
            self.assertEqual(p.category(60,tick,'harmony',cache),'both')
            self.assertEqual(p.category(61,tick,'harmony',cache),'chord')
            self.assertEqual(p.category(64,tick,'harmony',cache),'scale')
        for tick in (1200,2000,5000,7199):
            self.assertEqual(p.category(67,tick,'harmony',cache),'both')
            self.assertEqual(p.category(61,tick,'harmony',cache),'other')
        self.assertEqual(p.category(60,200,'harmony',cache),'scale')

    def test_all_four_coloring_switches_are_independent(self):
        try:
            for scale in (True,False):
                for match in (True,False):
                    theme.set_roll_coloring({'melody':{'scale':scale,'match':match}})
                    self.assertEqual(theme.colored_category('both','melody'),'both' if scale and match else 'scale' if scale else 'chord' if match else 'other')
                    self.assertEqual(theme.colored_category('both','harmony'),'both')
        finally:theme.set_roll_coloring({})

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.errors=[];self.hook=patch.object(sys,'excepthook',lambda typ,value,tb:self.errors.append(str(value)));self.hook.start()
        self.warning=patch('lingfeng.ui.main_window.QMessageBox.warning',side_effect=AssertionError('Unexpected warning'));self.warning.start()
        self.save=patch.object(MainWindow,'save_preferences');self.save.start()
        p=Project();p.notes=[Note(0,3840,60,51),Note(4800,480,62,103)];p.chords=[Chord(0,1920),Chord(1920,5760,55)]
        self.w=MainWindow(p);self.w.change_language('zh',False);theme.set_roll_coloring({});self.w.show();self.w.resize(1260,900);self.w.timer.stop();self.w.autosave.stop()
        for mute in self.w.mute_buttons.values():mute.setChecked(True)
        self.w.roll.center_pitch(60);QTest.qWait(30)
    def tearDown(self):
        self.w.transport.playing=False;self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents()
        self.hook.stop();self.warning.stop();self.save.stop();theme.set_roll_coloring({});self.assertFalse(self.errors)

    def test_create_and_move_keep_both_sides_and_other_voices_with_undo(self):
        w=self.w;original=w.project.to_dict();incoming=Note(960,480,60,113)
        w.add_note(incoming)
        self.assertEqual([(n.start,n.duration,n.velocity) for n in w.project.notes if n.pitch==60],[(0,960,51),(960,480,113),(1440,2400,51)])
        w.undo();self.assertEqual(w.project.to_dict(),original)
        moving=copy.deepcopy(w.project.notes[1]);moving.start=1200;moving.pitch=60
        w.move_note(moving)
        self.assertEqual([(n.start,n.duration,n.velocity) for n in w.project.notes],[(0,1200,51),(1200,480,103),(1680,2160,51)])
        self.assertEqual(len({n.id for n in w.project.notes}),3);w.project.validate()

    def test_polyphonic_group_moves_overwrite_at_destination_and_remove_originals(self):
        w=self.w;w.project.notes=[Note(0,3840,60),Note(0,3840,64),Note(4800,480,60),Note(4800,480,64)];w.refresh()
        incoming=copy.deepcopy(w.project.notes[2:])
        for n in incoming:n.start=960
        self.assertTrue(w.edit_notes(w.roll,incoming,[]))
        for pitch in (60,64):self.assertEqual([(n.start,n.duration) for n in w.project.notes if n.pitch==pitch],[(0,960),(960,480),(1440,2400)])
        w.project.validate()

    def test_new_harmony_notes_and_cross_region_moves_use_overwrite(self):
        w=self.w;h=w.harmony_window.roll;w.project.chords=[Chord(0,1920,notes=[Note(0,1920,60,61)]),Chord(1920,1920,notes=[Note(0,1920,60,72),Note(500,240,62,99)])];w.refresh()
        w.harmony_window.change_note(Note(480,240,60,100))
        self.assertEqual([(n.start,n.duration,n.velocity) for n in w.project.chords[0].notes],[(0,480,61),(480,240,100),(720,1200,61)])
        moving=copy.deepcopy(next(n for n in h.notes if n.pitch==62));moving.start=1680;moving.duration=480;moving.pitch=60
        self.assertTrue(w.edit_notes(h,[moving],[]));w.project.validate()
        self.assertEqual([(n.start,n.duration,n.velocity) for n in h.notes if n.start>=1680],[(1680,480,99),(2160,1680,72)])

    def test_shift_wheel_on_all_three_surfaces_has_identical_anchor_and_sync(self):
        w=self.w;w.open_harmony();APP.processEvents()
        for surface in (w.roll.viewport(),w.timeline,w.chord_lane,w.harmony_window.roll.lane):
            r=w.roll if surface is w.roll.viewport() else surface.roll if surface is w.timeline else surface.editor
            r.horizontalScrollBar().setValue(360);w.sync_time_views(r)
            x=330;offset=0 if surface is w.roll.viewport() else surface.offset()
            before=(x-offset-KEY_W+r.horizontalScrollBar().value())/r.zoom;zoom=r.zoom
            wheel(surface,x,r.ruler_height+15 if surface is r.viewport() else 15)
            self.assertAlmostEqual(r.zoom,zoom*1.2)
            after=(x-offset-KEY_W+r.horizontalScrollBar().value())/r.zoom
            self.assertLess(abs(before-after),1/r.zoom)
            self.assertEqual(w.roll.zoom,w.main_roll.zoom);self.assertEqual(w.harmony_window.roll.zoom,w.main_roll.zoom)
            self.assertEqual(w.roll.horizontalScrollBar().value(),w.harmony_window.roll.horizontalScrollBar().value())

    def test_floating_windows_are_peer_windows_with_right_aligned_transport(self):
        w=self.w;w.open_harmony();w.melody_window.setFloating(True);w.harmony_window.setFloating(True);APP.processEvents()
        for pane,roll,sync,transport in w.view_panes():
            self.assertEqual(pane.windowType(),Qt.WindowType.Window);self.assertIsNone(pane.parentWidget());self.assertIs(pane.owner,w)
            pane.resize(1100,620);APP.processEvents()
            self.assertLess(transport.width()-transport.options.geometry().right(),8)
            self.assertGreater(transport.play.x(),250)
            self.assertLess(transport.y(),roll.y())
            pane.resize(620,580);APP.processEvents()
            self.assertGreaterEqual(transport.play.x(),0);self.assertLessEqual(transport.bpm.geometry().right(),transport.width())
        w.harmony_window.setFloating(False);self.assertEqual(w.harmony_window.windowType(),Qt.WindowType.Widget)

    def test_all_volume_and_mute_controls_sync_without_stopping_and_survive_language(self):
        w=self.w;w.open_harmony();w.melody_window.setFloating(True);w.harmony_window.setFloating(True)
        a,b=w.melody_volume,w.harmony_window.volume_controls
        a.sliders['melody'].setValue(42);self.assertEqual(w.project.volumes['melody'],42);self.assertEqual(b.sliders['melody'].value(),42)
        b.sliders['chords'].setValue(69);self.assertEqual(w.volume_sliders['chords'].value(),69);self.assertEqual(a.sliders['chords'].value(),69)
        a.mutes['chords'].click();self.assertFalse(w.mute_buttons['chords'].isChecked());self.assertFalse(b.mutes['chords'].isChecked())
        w.commit_volume();w.undo();self.assertEqual(a.sliders['melody'].value(),100);self.assertEqual(b.sliders['chords'].value(),90)
        w.change_language('en',False);APP.processEvents();self.assertFalse(w.melody_volume.mutes['chords'].isChecked())

    def test_melody_lane_option_independent_and_survives_mount_and_language(self):
        w=self.w;w.melody_window.setFloating(True);w.melody_chords_action.setChecked(False)
        self.assertFalse(w.roll.panels['chords']);self.assertIsNone(w.nearest_chord_lane())
        main=w.visibility_actions['chords'].isChecked();w.mount_panels();self.assertFalse(w.roll.panels['chords'])
        w.change_language('en',False);APP.processEvents();self.assertFalse(w.floating_melody_chords);self.assertFalse(w.roll.panels['chords'])
        self.assertEqual(w.visibility_actions['chords'].isChecked(),main)
        w.melody_chords_action.setChecked(True);self.assertTrue(w.roll.panels['chords']);self.assertIs(w.nearest_chord_lane(),w.roll.lane)

    def test_coloring_settings_change_drawing_without_touching_project(self):
        w=self.w;before=w.project.to_dict();r=w.roll;initial=r.category(60,0)
        w.coloring_actions['melody','match'].setChecked(False);self.assertEqual(r.category(60,0),'scale')
        w.coloring_actions['melody','scale'].setChecked(False);self.assertEqual(r.category(60,0),'other')
        self.assertEqual(w.project.to_dict(),before);self.assertEqual(initial,'both')
        self.assertTrue(theme.ROLL_COLORING['harmony']['match']);w.change_language('en',False)
        self.assertFalse(w.coloring_actions['melody','scale'].isChecked())

    def test_long_note_has_no_gap_at_color_and_bar_boundaries(self):
        w=self.w;r=w.roll;w.project.notes=[Note(960,5760,60)];w.refresh();r.center_pitch(60);r.selection=[];r.selected_note='';r.selected_ids.clear();r.refresh();APP.processEvents()
        image=r.viewport().grab().toImage();y=round(r.y_at(60)+r.row_height/2);ratio=image.devicePixelRatio()
        for tick in (1920,3840):
            x=round(r.x_at(tick))
            # Scan across the boundary at mid-height and near the top: no corners/gaps.
            for yy in (y,round(r.y_at(60)+4)):
                colors={image.pixelColor(round(xx*ratio),round(yy*ratio)).name() for xx in range(x-3,x+4)}
                expected={theme.roll_color(r.category(60,tick-1),'note').name(),theme.roll_color(r.category(60,tick),'note').name()}
                self.assertTrue(colors<=expected,(tick,colors,expected))

    def test_playback_frames_reuse_static_layers_and_move_cursor_every_frame(self):
        w=self.w;w.open_harmony();w.follow_playhead.setChecked(False);w.transport.playing=True;w.play_anchor=100
        widgets=[w.roll,w.harmony_window.roll,w.timeline,w.navigator,w.harmony_window.roll.lane]
        w.show_cursor(120);APP.processEvents();counts=[x.cache_renders for x in widgets]
        for tick in range(140,2000,20):w.show_cursor(tick);APP.processEvents()
        self.assertEqual([x.cache_renders for x in widgets],counts)
        self.assertEqual(w.roll.cursor_tick,1980);self.assertEqual(w.harmony_window.roll.play_tick,1980)
        self.assertEqual(w.main_roll.anchor_tick,100)
        w.roll.selected_ids={w.project.notes[0].id};w.roll.refresh();APP.processEvents();self.assertGreater(w.roll.cache_renders,counts[0])
        w.transport.playing=False;w.show_cursor(1980);APP.processEvents();self.assertIsNone(w.roll.play_tick);self.assertIsNone(w.roll.anchor_tick)

if __name__=='__main__':unittest.main()
