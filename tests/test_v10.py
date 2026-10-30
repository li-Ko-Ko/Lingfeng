"""Playback anchors, continuous score timing, audition and pane combinations."""
import os,unittest,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QImage,QPainter,QColor
from PySide6.QtWidgets import QApplication,QMenuBar
from PySide6.QtTest import QTest
from lingfeng.ui.main_window import MainWindow
from lingfeng.audio.transport import Transport
from lingfeng.music.model import Project, Note, Chord
from lingfeng.engraving.notation import ScoreLayout, PAPER_W, PAPER_H, GRID_LINE, ANCHOR_LINE
from lingfeng.engraving.presentation import add_compression

APP=QApplication.instance() or QApplication([])
def song():
    p=Project();p.notes=[Note(i*3840,960,60+i%2*4) for i in range(8)];p.chords=[Chord(i*3840,3840,48,pattern='up') for i in range(8)];return p
def render(p):
    layout=ScoreLayout(p);image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_ARGB32);q=QPainter(image);layout.draw(q,0);q.end();return layout,image

class ScoreTimingTests(unittest.TestCase):
    def test_repeat_dots_clear_first_and_last_rest_without_cursor_gaps(self):
        p=Project.load('examples/lingfeng-symbols.lfs');p.notation['style']='traditional';layout,_=render(p)
        first=next(r for r in layout.rest_positions if r[0]==0)
        last=max((r for r in layout.rest_positions if r[0]<p.starts[4]),key=lambda r:r[0])
        left=next(x for kind,x,y in layout.symbol_marks if kind=='repeat_start')
        right=next(x for kind,x,y in layout.symbol_marks if kind=='repeat_end')
        first_box=next(box for box in layout.symbol_boxes if box[0]==first[0])
        last_box=next(box for box in layout.symbol_boxes if box[0]==last[0])
        self.assertGreater(first_box[2],left+12);self.assertLess(last_box[3],right-12)
        self.assertLess(abs(layout.time_position(3839)[1]-layout.time_position(3840)[1]),1)

    def test_bar_boundaries_are_continuous_and_notes_follow_onset(self):
        for style in ('traditional','spatial','compact'):
            p=song();p.notation['style']=style;layout,_=render(p)
            for bar in range(1,4):
                before=layout.time_position(bar*3840-1);after=layout.time_position(bar*3840)
                self.assertLess(abs(after[1]-before[1]),1)
            cursor=layout.time_position(0)[1];rect=layout.hit_notes[0][1];self.assertGreater(rect.center().x()-cursor,5)
            if style=='traditional':self.assertAlmostEqual(rect.center().x()-cursor,layout.traditional_cell_width(0)/2)
            else:self.assertLess(rect.center().x()-cursor,15)
    def test_forced_system_and_hidden_repeat_share_the_same_time_map(self):
        p=song();p.notation['forced_rows']=[[0,8]];layout,_=render(p)
        self.assertLess(abs(layout.time_position(3840)[1]-layout.time_position(3839)[1]),1)
        add_compression(p,list(range(8)),'repeat');layout,_=render(p)
        self.assertEqual(layout.time_position(480),layout.time_position(4*3840+480))
    def test_anchor_rows_have_stronger_background_contrast(self):
        self.assertLess(QColor(ANCHOR_LINE).lightness(),QColor(GRID_LINE).lightness())
        p=song();layout,image=render(p);s=layout.systems[0];baseline=s.top+60+s.extra_header+(len(s.pitches)-1)*s.row_gap
        # Inspect the grid at a note-free horizontal position.
        x=round(52+40+s.bar_widths[0]*.86);anchor=s.boundaries[-1];other=next(n for n in s.pitches if n not in s.boundaries)
        a=round(baseline-s.pitch_position(anchor)*s.row_gap);b=round(baseline-s.pitch_position(other)*s.row_gap)
        self.assertLess(image.pixelColor(x,a).lightness(),image.pixelColor(x,b).lightness())

class AuditionTests(unittest.TestCase):
    def test_chord_audition_during_playback_uses_separate_channel(self):
        class Synth:
            def __init__(self):self.events=[]
            def send(self,*event):self.events.append(event)
        t=Transport();t.synth=Synth();t.playing=True;t.audition([48,52,55],True,allow_during_playback=True)
        self.assertTrue(t.playing);self.assertEqual([e for e in t.synth.events if e[0]==0x93],[(0x93,48,80),(0x93,52,80),(0x93,55,80)])
        QTest.qWait(220);t.audition([48,55],True,allow_during_playback=True);count=len(t.synth.events);QTest.qWait(140)
        self.assertEqual(len(t.synth.events),count) # The first timer cannot stop the new chord.
        QTest.qWait(550);self.assertEqual(t.synth.events[-2:],[(0x83,48),(0x83,55)]);t.synth=None;t.deleteLater()

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.w=MainWindow(song());self.w.change_language('zh',False);self.w.show();self.w.resize(1280,920);QTest.qWait(45);self.w.timer.stop();self.heard=[]
        self.w.transport.begin_audition=lambda pitches,harmony=False,**kw:self.heard.append((list(pitches),harmony,kw))
        self.w.transport.begin_chord_audition=lambda chord,bpm:self.heard.append((chord.render_notes(),True,dict(bpm=bpm)))
    def tearDown(self):self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents()
    def test_chord_press_always_auditions_block_including_deselect(self):
        w=self.w;lane=w.chord_lane;pos=QPoint(round(lane.x_at(480)),25)
        QTest.mouseClick(lane,Qt.MouseButton.LeftButton,pos=pos)
        self.assertEqual(self.heard[0][0],w.project.chords[0].pitches)
        self.assertTrue(self.heard[0][1])
        QTest.mouseClick(lane,Qt.MouseButton.LeftButton,pos=pos);self.assertEqual(len(self.heard),2)
        QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=pos);end=pos+QPoint(24,0);QTest.mouseMove(lane,end);QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=end);self.assertEqual(len(self.heard),3)
    def test_overview_contains_both_tracks_and_sits_above_controls(self):
        w=self.w;segments=w.navigator.segments();self.assertEqual(sum(s[0]==0 for s in segments),len(w.project.notes));self.assertEqual(sum(s[0]==1 for s in segments),len(w.project.harmony_notes()))
        self.assertGreater(w.navigator.mapTo(w,QPoint()).y(),w.play_button.mapTo(w,QPoint()).y()+w.play_button.height())
        self.assertLess(w.navigator.mapTo(w,QPoint()).y(),w.tool.mapTo(w,QPoint()).y())
        menu=w.title_bar.menu;self.assertLess(menu.actionGeometry(w.title_bar.brand).x(),menu.actionGeometry(menu.actions()[1]).x());self.assertEqual(w.title_bar.brand.text(),'伶风')
        w.change_language('en',False);self.assertEqual(w.title_bar.brand.text(),'Lingfeng');self.assertNotIn('伶风',w.windowTitle())
    def test_each_floating_combination_keeps_controls_and_right_dock_icons(self):
        w=self.w;w.open_harmony()
        for melody,harmony in ((False,False),(True,False),(False,True),(True,True)):
            w.melody_window.setFloating(melody);w.harmony_window.setFloating(harmony);QTest.qWait(35)
            self.assertTrue(w.melody_toolbar.isVisible());self.assertEqual(w.harmony_window.toolbar.isVisible(),melody or harmony)
            self.assertEqual(w.melody_float.kind,'dock' if melody else 'float');self.assertEqual(w.harmony_window.float_button.kind,'dock' if harmony else 'float')
            self.assertTrue(w.harmony_window.top_lane.isVisible());self.assertIn(w.melody_sync,w.melody_options.menu().actions())
            for pane,icon,hide in ((w.melody_window,w.melody_float,w.melody_hide),(w.harmony_window,w.harmony_window.float_button,w.harmony_window.hide_button)):
                if pane.isFloating():self.assertTrue(pane.title_bar.dock.isVisible())
                else:
                    position=icon.mapTo(pane,QPoint());close=hide.mapTo(pane,QPoint())
                    self.assertGreater(close.x(),pane.width()-80);self.assertLessEqual(position.x()+icon.width(),close.x());self.assertEqual(position.y(),close.y())
        w.switch_workspace('score');w.open_score_roll('melody',0);self.assertTrue(w.melody_toolbar.isVisible());w.open_score_roll('chords',0);self.assertTrue(w.melody_toolbar.isVisible())
        w.score_float.click();self.assertTrue(w.score_floats['harmony'].isFloating());self.assertFalse(w.score_floats['melody'].isFloating())
    def test_melody_floating_timeline_sync_controls_main_chord_axis(self):
        w=self.w;w.open_harmony();w.melody_window.setFloating(True);QTest.qWait(40)
        w.melody_sync.setChecked(True);w.roll.horizontalScrollBar().setValue(450)
        self.assertEqual(w.harmony_window.roll.horizontalScrollBar().value(),450);self.assertEqual(w.shared_scroll.value(),450)
        self.assertFalse(w.harmony_window.sync.isChecked());self.assertIs(w.timeline.roll,w.harmony_window.roll)
        w.melody_sync.setChecked(False);w.roll.horizontalScrollBar().setValue(700);self.assertEqual(w.harmony_window.roll.horizontalScrollBar().value(),450)
    def test_paused_replay_and_playing_reference_lines(self):
        w=self.w;w.switch_workspace('score');w.switch_workspace('compose');real=w.transport;real.stop()
        class Fake:
            playing=False;starts=[]
            def play(self,p,start,end,loop,**kw):self.starts.append(start);self.playing=True
            def stop(self):self.playing=False
            def position(self):return self.starts[-1] if self.starts else 0
        f=Fake();w.transport=f
        try:
            w.play_anchor=960;w.playhead=2000;w.replay();self.assertEqual(w.playhead,960);self.assertFalse(f.starts);self.assertIsNone(w.roll.anchor_tick)
            f.playing=True;w.replay();self.assertEqual(f.starts,[960]);self.assertEqual(w.roll.anchor_tick,960);self.assertIsNone(w.score_view.canvas.anchor_tick)
            w.switch_workspace('score');self.assertEqual(w.score_view.canvas.anchor_tick,960)
            w.stop();self.assertIsNone(w.harmony_window.roll.anchor_tick);self.assertIsNone(w.score_view.canvas.anchor_tick)
        finally:w.transport=real
    def test_delayed_layout_cannot_override_explicit_pitch_view(self):
        w=self.w;w.open_harmony();w.harmony_window.setFloating(True);r=w.harmony_window.roll;r.center_pitch(64);APP.processEvents();r.center_pitch(64);before=r.verticalScrollBar().value()
        QTest.qWait(60);self.assertEqual(r.verticalScrollBar().value(),before)
        w.chord_selection(set(),r);r.lane.repaint();pos=QPoint(round(r.x_at(480)),25)
        QTest.mouseClick(r.lane,Qt.MouseButton.LeftButton,pos=pos);self.assertTrue(self.heard)
    def test_score_playback_caches_static_pages_and_invalidates_on_theme_or_edit(self):
        w=self.w;w.switch_workspace('score');c=w.score_view.canvas;APP.processEvents();c.grab();count=c.cache_renders
        for tick in range(100,3000,200):c.play_tick=tick;c.update();APP.processEvents()
        self.assertEqual(c.cache_renders,count);hits=len(c.layout.hit_times)
        w.set_theme('dark');c.grab();self.assertGreater(c.cache_renders,count);self.assertEqual(len(c.layout.hit_times),hits)
        count=c.cache_renders;w.project.notes[0].pitch=67;w.refresh();c.grab();self.assertEqual(c.cache_renders,count)
        w.switch_workspace('compose');w.switch_workspace('score');c.grab();self.assertGreater(c.cache_renders,count)

if __name__=='__main__':unittest.main()
