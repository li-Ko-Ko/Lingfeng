"""Regression coverage for the docked workspace, chord gestures and score logic."""
import os,copy,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QPoint,Qt
from PySide6.QtGui import QImage,QPainter
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord,Measure,PPQ
from popscore.chordops import blank_chord,change_chords
from popscore.presentation import pair_candidate,add_compression,lyric_verses
from popscore.notation import ScoreLayout,PAPER_W,PAPER_H
from popscore.midi import export_midi
from popscore.dialogs import ChordDialog

APP=QApplication.instance() or QApplication([])

def repeated():
    p=Project()
    p.notes=[Note(i*3840+480,960,60+(i%2)*4,90,'风' if i<4 else '云') for i in range(8)]
    p.chords=[Chord(i*3840,3840,48 if i%2==0 else 53) for i in range(8)]
    return p


class ChordRegionTests(unittest.TestCase):
    def test_blank_stops_at_nearest_gap_or_measure_boundary(self):
        p=Project();p.chords=[Chord(1920,960)]
        self.assertEqual((blank_chord(p,720).start,blank_chord(p,720).end),(720,1920))
        self.assertIsNotNone(blank_chord(p,1920));self.assertIsNotNone(blank_chord(p,2879))
        self.assertEqual(blank_chord(p,2880).end,3840)
        self.assertEqual(blank_chord(p,3840).end,7680)
        self.assertIsNone(blank_chord(p,p.end))
    def test_empty_region_dialog_produces_selected_voicing(self):
        p=Project();c=blank_chord(p,480);self.assertEqual(c.render_notes(),[])
        d=ChordDialog(c,p);value=d.value();self.assertTrue(value.recognized);self.assertTrue(value.render_notes());d.deleteLater()
    def test_quality_keeps_rhythm_pattern_replaces_custom_edits(self):
        p=Project();c=Chord(480,3840,notes=[Note(120,360,60),Note(720,480,64),Note(960,720,67)]);p.chords=[c]
        change_chords(p,{c.id},'quality:m');self.assertEqual([(n.start,n.duration,n.pitch) for n in c.notes],[(120,360,60),(720,480,63),(960,720,67)])
        change_chords(p,{c.id},'pattern:up')
        from tests.music_reference import bar_events
        self.assertEqual(sorted((n.start,n.duration,n.pitch,n.velocity) for n in c.render_notes()),bar_events(c,p,c.start,c.end));p.validate()
    def test_batch_transpose_and_bounds_are_atomic(self):
        p=Project();p.chords=[Chord(0,3840),Chord(3840,3840,notes=[Note(0,960,108)])]
        before=p.to_dict()
        with self.assertRaises(ValueError):change_chords(p,{c.id for c in p.chords},'transpose:1')
        self.assertEqual(before,p.to_dict())
        notes=[n.pitch for n in p.harmony_notes()];change_chords(p,{c.id for c in p.chords},'transpose:-1')
        self.assertEqual([n.pitch for n in p.harmony_notes()],[x-1 for x in notes]);p.validate()


class StructureTests(unittest.TestCase):
    def test_two_regions_require_adjacency_equal_length_and_actual_music(self):
        p=repeated();self.assertIsNotNone(pair_candidate(p,[0,1,2,3],[4,5,6,7]))
        for a,b in [([0,1],[4,5]),([0,2],[3,4]),([0,1,2],[3,4]),([4,5],[2,3])]:self.assertIsNone(pair_candidate(p,a,b))
        p.notes[4].pitch+=1;self.assertIsNone(pair_candidate(p,[0,1,2,3],[4,5,6,7]))
    def test_different_lyrics_stack_below_grid_all_styles_and_midi_unchanged(self):
        p=repeated()
        with tempfile.TemporaryDirectory(dir='tmp') as d:
            before=Path(d)/'a.mid';after=Path(d)/'b.mid';export_midi(p,before);add_compression(p,list(range(8)),'repeat');export_midi(p,after);self.assertEqual(before.read_bytes(),after.read_bytes())
        for style in ('traditional','spatial','compact'):
            p.notation['style']=style;layout=ScoreLayout(p);s=layout.systems[0]
            image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_ARGB32);painter=QPainter(image);layout.draw(painter,0);painter.end()
            self.assertEqual(layout.verses[p.notes[0].id],['风','云']);self.assertEqual(len(layout.lyric_positions),8)
            self.assertTrue(all(y>s.top+s.grid_bottom for _,_,_,y in layout.lyric_positions))
            ys=[y for nid,_,_,y in layout.lyric_positions if nid in (p.notes[0].id,p.notes[4].id)];self.assertEqual(ys[1]-ys[0],17 if style=='traditional' else 22)
    def test_lower_directions_do_not_overlap_lyrics(self):
        from popscore.presentation import add_annotation
        p=repeated();add_annotation(p,'rit',7*3840,p.end);add_annotation(p,'fine',7*3840,p.end)
        layout=ScoreLayout(p);image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_ARGB32);q=QPainter(image);layout.draw(q,0);q.end()
        s=layout.systems[-1];lyrics=[y for nid,_,_,y in layout.lyric_positions if nid==p.notes[-1].id]
        self.assertTrue(all(y>max(lyrics) for kind,_,y in layout.symbol_marks if kind in ('rit','fine')))


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.w=MainWindow(repeated());self.w.show();QTest.qWait(40)
    def tearDown(self):self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents()
    def test_order_default_visibility_and_two_floating_rolls(self):
        w=self.w;self.assertFalse(w.harmony_window.isVisible());self.assertFalse(w.roll.panels['velocity']);self.assertFalse(w.harmony_window.roll.panels['velocity'])
        self.assertLess(w.navigator.mapTo(w,QPoint()).y(),w.timeline.mapTo(w,QPoint()).y());self.assertEqual([w.tracks.widget(i) for i in range(w.tracks.count())],[w.melody_window,w.chord_lane,w.harmony_window])
        w.open_harmony();w.melody_window.setFloating(True);w.harmony_window.setFloating(True);QTest.qWait(30)
        self.assertTrue(w.roll.lane.isVisible());self.assertTrue(w.harmony_window.top_lane.isVisible())
        self.assertEqual(w.harmony_window.top_lane.y(),w.harmony_window.roll.timeline_height)
        w.melody_window.setFloating(False);w.harmony_window.setFloating(False);self.assertFalse(w.roll.panels['chords'])
    def test_chord_click_toggle_hover_marquee_and_batch_menu(self):
        w=self.w;lane=w.chord_lane;QTest.qWait(20);c=w.project.chords[0];a=QPoint(round(lane.x_at(c.start)+30),25)
        QTest.mouseMove(lane,a);QTest.qWait(10);self.assertEqual(w.roll.hovered_chord,c.id)
        QTest.mouseClick(lane,Qt.MouseButton.LeftButton,pos=a);self.assertEqual(w.roll.selected_chords,{c.id})
        QTest.mouseClick(lane,Qt.MouseButton.LeftButton,pos=a);self.assertFalse(w.roll.selected_chords)
        start=QPoint(round(lane.x_at(0)+10),1);end=QPoint(round(lane.x_at(7680)-10),40)
        QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(lane,end);QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=end)
        self.assertEqual(w.roll.selected_chords,{c.id for c in w.project.chords[:2]})
        menu=lane.context_menu(a);labels={a.text().split('\t')[0] for a in menu.actions()};self.assertTrue({'删除所选和弦','复制所选和弦','二等分和弦','合并相邻和弦'}<=labels)
        self.assertIn('和弦根音',labels);self.assertFalse(menu.root_menu.isEnabled())
    def test_occupied_insert_enabled_and_empty_insert_undo(self):
        w=self.w;lane=w.chord_lane;menu=lane.context_menu(QPoint(round(lane.x_at(480)),25));self.assertTrue(menu.actions()[0].isEnabled())
        w.project.chords=[];w.refresh();w.chord_command('insert',480);self.assertEqual((w.project.chord_at(480).start,w.project.chord_at(480).end),(480,3840));self.assertFalse(w.project.harmony_notes());w.undo();self.assertFalse(w.project.chords)
    def test_shared_score_tab_and_logic_capture(self):
        w=self.w;w.switch_workspace('score');w.open_score_roll('chords',0);QTest.qWait(20)
        self.assertEqual(w.score_tabs.currentWidget(),w.score_harmony_page);w.open_score_roll('melody',0);self.assertEqual(w.score_tabs.currentWidget(),w.score_melody_page)
        logic=w.logic_panel;logic.create_draft();w.score_view.canvas.selected_bars={0,1,2,3};logic.capture(0);w.score_view.canvas.selected_bars={4,5,6,7};logic.capture(1);self.assertTrue(logic.apply.isEnabled());logic.commit();self.assertEqual(len(w.project.notation['compressions']),1)
        w.toggle_score_panel_floating('melody');self.assertTrue(w.score_floats['melody'].isFloating());w.toggle_score_panel_floating('melody');self.assertEqual(w.score_splitter.widget(1),w.score_tools)
    def test_half_screen_minimum_and_size_buttons(self):
        w=self.w;w.resize(680,900);QTest.qWait(30);self.assertEqual(w.width(),680)
        spin=w.view_controls.height;value=spin.value();QTest.mouseClick(spin,Qt.MouseButton.LeftButton,pos=QPoint(spin.width()-8,8));self.assertEqual(spin.value(),value+1)
        self.assertEqual(w.roll.row_height,value+1)
        w.perline.setValue(5);self.assertEqual(w.project.notation['per_line'],5)
        self.assertIsNone(w.score_view.canvas.layout);w.switch_workspace('score')
        self.assertEqual(len(w.score_view.canvas.layout.systems[0].bars),5)
        w.undo();self.assertEqual(w.project.notation['per_line'],4)

    def test_layout_settle_cannot_shift_a_keyboard_during_drawing(self):
        w=self.w;w.open_harmony();w.harmony_window.setFloating(True);QTest.qWait(40)
        roll=w.harmony_window.roll;roll.center_pitch(85);before=roll.verticalScrollBar().value();roll.drag=('draw',)
        w.harmony_window.center_after_layout();self.assertEqual(roll.verticalScrollBar().value(),before);roll.drag=None

if __name__=='__main__':unittest.main()
