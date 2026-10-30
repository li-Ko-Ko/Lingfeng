"""Behavior regressions for independent rolls and symbol-first score editing."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtWidgets import QApplication,QToolTip,QMenuBar
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord
from popscore.chordops import chord_details
from popscore.structure import draft_candidate,apply_draft,KINDS
from popscore.presentation import visible_bars,compression_valid
from popscore.midi import export_midi
from popscore.i18n import set_language,EN

APP=QApplication.instance() or QApplication([])

def music():
    p=Project()
    p.notes=[Note(i*3840+480,720,60+(i%2)*2,90,'风' if i<4 else '云') for i in range(8)]
    p.chords=[Chord(i*3840,3840,48) for i in range(8)]
    return p

def draft(kind,*regions):
    return dict(id='test',kind=kind,regions=[dict(bars=list(b),ranges=[[min(b)*3840,(max(b)+1)*3840]]) for b in regions])

class DraftTests(unittest.TestCase):
    def setUp(self):set_language('zh')
    def test_explicit_coda_sections_and_music_validation(self):
        p=music();d=draft('jump_coda',[0,1],[2,3],[4,5],[6,7])
        result,_=draft_candidate(p,d);self.assertIsNotNone(result);self.assertTrue(compression_valid(p,result[1]))
        apply_draft(p,d);self.assertEqual(visible_bars(p),[0,1,2,3,6,7])
        p.notes[4].pitch+=1;self.assertEqual(visible_bars(p),list(range(8)))
    def test_reject_missing_disjoint_overlapping_or_different_regions(self):
        p=music()
        for d in [dict(kind='repeat',regions=[None,None]),draft('repeat',[0,1],[4,5]),draft('repeat',[0,1],[1,2]),draft('repeat',[0,1],[2,3,4])]:
            self.assertIsNone(draft_candidate(p,d)[0])
        d=draft('repeat',[0,1],[2,3]);p.chords[2].root=49;self.assertIsNone(draft_candidate(p,d)[0])
    def test_multiple_structures_roundtrip_and_midi_identity(self):
        p=music()
        with tempfile.TemporaryDirectory(dir='tmp') as path:
            path=Path(path);export_midi(p,path/'before.mid')
            apply_draft(p,draft('repeat',[0,1],[2,3]));apply_draft(p,draft('repeat',[4,5],[6,7]))
            self.assertIsNone(draft_candidate(p,draft('repeat',[0,1],[2,3]))[0]);self.assertEqual(visible_bars(p),[0,1,4,5])
            export_midi(p,path/'after.mid');self.assertEqual((path/'before.mid').read_bytes(),(path/'after.mid').read_bytes())
            p.save(path/'two.lfs');self.assertEqual(Project.load(path/'two.lfs').to_dict(),p.to_dict())
    def test_annotation_legality_and_actual_bass_tooltip(self):
        p=music();self.assertIsNone(draft_candidate(p,draft('fine',[0]))[0]);self.assertIsNotNone(draft_candidate(p,draft('fine',[7]))[0])
        c=Chord(0,3840,48,notes=[Note(0,960,52),Note(480,480,60),Note(960,480,67)])
        text=chord_details(p,c);self.assertIn('3 = E3',text);self.assertIn('1 = C4',text);self.assertIn('实际低音：3 = E3',text)
        self.assertIn('尚无音符',chord_details(p,Chord(0,960,notes=[])))
    def test_all_dynamic_kind_labels_have_english(self):
        for kind,label in KINDS:
            if any('\u4e00'<=c<='\u9fff' for c in label):self.assertIn(label,EN)

class UIRegressionTests(unittest.TestCase):
    def setUp(self):
        self.w=MainWindow(music());self.w.change_language('zh',False);self.w.show();self.w.resize(1280,900);QTest.qWait(45);self.w.timer.stop()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();QToolTip.hideText();APP.processEvents()
    def test_menu_order_and_resize_exclusions(self):
        w=self.w;menu=w.findChild(QMenuBar)
        self.assertEqual([a.text() for a in menu.actions()],['伶风','文件','编辑','视图','设置','帮助'])
        for child in [*w.title_bar.window_buttons,w.chord_lane,w.shared_scroll,menu]:
            self.assertEqual(w.resize_hit(child.mapTo(w,child.rect().center())),0)
        self.assertEqual(w.resize_hit(QPoint(0,w.height()//2)),10)
        self.assertFalse(w.statusBar().isSizeGripEnabled())
        QTest.mouseClick(w.title_bar.window_buttons[0],Qt.MouseButton.LeftButton);self.assertTrue(w.isMinimized());w.showNormal()
    def test_single_scrollbar_shared_keys_tools_and_independent_float(self):
        w=self.w;w.open_harmony();QTest.qWait(40);r,h=w.roll,w.harmony_window.roll
        self.assertTrue(w.shared_scroll.isVisible());self.assertFalse(r.horizontalScrollBar().isVisible());self.assertFalse(h.horizontalScrollBar().isVisible())
        w.shared_scroll.setValue(300);self.assertEqual(r.horizontalScrollBar().value(),h.horizontalScrollBar().value());self.assertEqual(r.horizontalScrollBar().value(),300)
        w.view_controls.range.setCurrentIndex(1);self.assertEqual(r.pitches,h.pitches);self.assertIn(48,r.pitches);self.assertIn(60,r.pitches)
        w.view_controls.height.setValue(25);self.assertEqual(h.row_height,25)
        w.tool.setCurrentIndex(w.tool.findData('draw'));w.grid.set_triplet(True);self.assertEqual((r.tool,r.grid,r.duration),(h.tool,h.grid,h.duration))
        self.assertFalse(w.harmony_window.toolbar.isVisible());self.assertFalse(hasattr(w.harmony_window,'pattern'))
        w.harmony_window.setFloating(True);QTest.qWait(40);self.assertFalse(w.rolls_linked());self.assertTrue(w.harmony_window.toolbar.isVisible())
        before=r.horizontalScrollBar().value();h.horizontalScrollBar().setValue(650);self.assertEqual(r.horizontalScrollBar().value(),before)
        h.set_row_height(30);self.assertEqual(r.row_height,25);self.assertEqual(h.row_height,30)
        w.harmony_window.sync.setChecked(True);h.horizontalScrollBar().setValue(400);self.assertEqual(r.horizontalScrollBar().value(),h.horizontalScrollBar().value())
    def test_three_tabs_share_tools_and_language_preserves_drafts(self):
        w=self.w;w.switch_workspace('score');w.open_score_roll('chords',0);self.assertEqual(w.score_tabs.count(),4);self.assertEqual(w.score_tabs.currentIndex(),1)
        w.tool.setCurrentIndex(w.tool.findData('draw'));self.assertEqual(w.harmony_window.roll.tool,'draw')
        w.harmony_window.tool.setCurrentIndex(0);self.assertEqual(w.roll.tool,'smart')
        w.follow_playhead.setChecked(False);w.score_tabs.setCurrentIndex(2);w.logic_panel.create_draft();first=w.logic_panel.current()['id'];w.logic_panel.kind.setCurrentIndex(w.logic_panel.kind.findData('jump_coda'));w.logic_panel.create_draft()
        self.assertEqual(len(w.logic_panel.drafts),2);w.change_language('en',False);QTest.qWait(30)
        self.assertFalse(w.follow_playhead.isChecked());self.assertEqual(w.score_tabs.currentIndex(),2);self.assertEqual(w.logic_panel.drafts[0]['id'],first);self.assertEqual(len(w.logic_panel.drafts),2)
        self.assertEqual(w.score_tabs.tabText(0),'Melody roll');self.assertEqual(w.score_tabs.tabText(1),'Chord roll');self.assertEqual(w.tool.currentText(),'Smart')
        w.set_theme('dark');APP.processEvents();image=w.logic_panel.grab().toImage();self.assertLess(image.pixelColor(5,image.height()-8).lightness(),80)
    def test_shift_chord_range_and_ctrl_shift_extension(self):
        w=self.w;lane=w.chord_lane;r=w.roll;r.zoom=36;r.update_ranges();r.refresh();QTest.qWait(20)
        def click(bar,mod=Qt.KeyboardModifier.NoModifier):QTest.mouseClick(lane,Qt.MouseButton.LeftButton,mod,QPoint(round(lane.x_at(bar*3840)+30),25))
        click(1);click(4,Qt.KeyboardModifier.ShiftModifier);self.assertEqual(r.selected_chords,{c.id for c in w.project.chords[1:5]})
        click(6,Qt.KeyboardModifier.ControlModifier);click(7,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(r.selected_chords,{c.id for c in w.project.chords[1:5]+w.project.chords[6:8]})
    def test_shared_ruler_selection_when_only_chord_roll_visible(self):
        w=self.w;w.open_harmony();w.visibility_actions['melody'].setChecked(False);QTest.qWait(25)
        self.assertIs(w.timeline.roll,w.harmony_window.roll)
        pos=QPoint(round(w.timeline.x_at(4000)),12);QTest.mouseClick(w.timeline,Qt.MouseButton.LeftButton,pos=pos)
        self.assertEqual(w.roll.selection,w.harmony_window.roll.selection);self.assertGreaterEqual(w.roll.selection[0][0],3840)
    def test_highlight_changes_chord_pitch_rows_only(self):
        w=self.w;r=w.roll;w.set_theme('light');r.center_pitch(63);w.chord_hover('');w.chord_selection(set());APP.processEvents();before=r.viewport().grab().toImage()
        c=w.project.chords[0];w.chord_hover(c.id);APP.processEvents();after=r.viewport().grab().toImage()
        def pixel(img,tick,pitch):return img.pixelColor(round(r.x_at(tick)),round(r.y_at(pitch)+r.row_height*.55)).rgba()
        for p in [60,64,67]:self.assertNotEqual(pixel(before,2600,p),pixel(after,2600,p))
        for p in [61,62,65]:self.assertEqual(pixel(before,2600,p),pixel(after,2600,p))
        self.assertEqual(pixel(before,4400,64),pixel(after,4400,64))
    def test_replay_and_follow_playhead(self):
        w=self.w;w.open_harmony();QTest.qWait(35);real=w.transport;real.stop()
        class Fake:
            playing=True;tick=28000;starts=[]
            def stop(self):self.playing=False
            def play(self,p,start,end,loop,**kwargs):self.playing=True;self.tick=start;self.starts.append(start)
            def position(self):return self.tick
        fake=Fake();w.transport=fake
        try:
            w.transport_active=True;w.play_anchor=3840;QTest.mouseClick(w.replay_button,Qt.MouseButton.LeftButton)
            self.assertTrue(fake.playing);self.assertTrue(w.transport_active);self.assertEqual(fake.starts,[3840]);self.assertEqual(w.play_button.kind,'pause')
            w.shared_scroll.setValue(0);w.follow_playhead.setChecked(False);fake.tick=28000;w.playback_tick();self.assertEqual(w.shared_scroll.value(),0)
            w.follow_playhead.setChecked(True);w.playback_tick();self.assertGreater(w.shared_scroll.value(),0);self.assertEqual(w.roll.horizontalScrollBar().value(),w.harmony_window.roll.horizontalScrollBar().value())
            QTest.mouseClick(w.replay_button,Qt.MouseButton.LeftButton);self.assertEqual(w.playhead,0);self.assertFalse(fake.playing)
        finally:w.transport=real;w.stop()
    def test_score_tooltip_and_symbol_delete_undo_restore(self):
        w=self.w;w.switch_workspace('score');w.open_score_roll('melody',0);canvas=w.score_view.canvas;logic=w.logic_panel
        logic.create_draft();canvas.selected_bars={0,1};logic.capture(0);canvas.selected_bars={2,3};logic.capture(1);self.assertTrue(logic.apply.isEnabled());logic.commit();self.assertEqual(visible_bars(w.project),[0,1,4,5,6,7])
        w.project.notation['forced_rows']=[[0,6]];w.refresh();APP.processEvents();canvas.grab()
        pg,rect,key=next(h for h in canvas.layout.hit_symbols if h[2][0]=='compressions');x,y=canvas.page_origin(pg);point=QPointF(x+rect.center().x()*canvas.scale,y+rect.center().y()*canvas.scale)
        menu=canvas.context_menu(point);self.assertEqual(menu.actions()[0].text(),'删除此符号并还原谱面');menu.actions()[0].trigger();self.assertEqual(visible_bars(w.project),list(range(8)))
        w.undo();self.assertEqual(visible_bars(w.project),[0,1,4,5,6,7]);APP.processEvents();canvas.grab()
        pg,rect,cid=canvas.layout.hit_chords[0];x,y=canvas.page_origin(pg);pos=QPoint(round(x+rect.center().x()*canvas.scale),round(y+rect.center().y()*canvas.scale))
        QTest.mouseMove(canvas,pos);APP.processEvents();self.assertEqual(canvas.hovered_chord,cid);self.assertIn('实际低音',QToolTip.text());self.assertIn('C3',QToolTip.text())

if __name__=='__main__':unittest.main()
