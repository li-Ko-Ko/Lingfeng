"""Beat grouping, viewport zoom/panning, and entry-time score snapshots."""
import os,copy,unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent,QRectF
from PySide6.QtGui import QWheelEvent,QMouseEvent
from PySide6.QtTest import QTest,QSignalSpy
from PySide6.QtWidgets import QApplication
from popscore.model import Project,Note,Measure,Context
from popscore.notation import ScoreLayout,TRADITIONAL_BEAT_GAP,PAPER_W,PAPER_H
from popscore.scoreview import ScoreView
from popscore.app import MainWindow
APP=QApplication.instance() or QApplication([])

def song(count=24):
    p=Project();p.measures=[Measure() for _ in range(count)];p.contexts=[Context(0,p.end)]
    p.notes=[Note(b*3840,960,60+b%5) for b in range(count)];return p

class BeatTests(unittest.TestCase):
    def test_intra_beat_spacing_and_inter_beat_padding_for_all_denominators(self):
        for denominator in (2,4,8,16):
            p=Project();p.measures=[Measure(4,denominator)];p.contexts=[Context(0,p.end)]
            step=960*4//denominator//2;p.notes=[Note(t,step,60) for t in range(0,p.end,step)]
            p.notation.update(style='traditional',per_line=1)
            layout=ScoreLayout(p);s=layout.systems[0];points,xs,*_=layout.bar_map(s,0,0,s.bar_widths[0])
            cells=[layout.traditional_cell(0,t,points,xs) for t in range(0,p.end,step)]
            width=cells[0][1]-cells[0][0];centers=[(a+b)/2 for a,b in cells]
            for a,b in cells:self.assertAlmostEqual(b-a,width)
            extra=(s.bar_widths[0]-(8+3*TRADITIONAL_BEAT_GAP)*width)/3
            for i,(a,b) in enumerate(zip(centers,centers[1:])):
                self.assertAlmostEqual(b-a,width*(1+TRADITIONAL_BEAT_GAP)+(extra) if i%2 else width)
            self.assertEqual([n.duration for n in p.notes],[step]*8)

    def test_syncopation_and_extension_dashes_do_not_create_fake_notes(self):
        p=Project();p.notation.update(style='traditional',per_line=1)
        p.notes=[Note(0,1440,60),Note(1440,480,62),Note(1920,1920,64)]
        original=copy.deepcopy(p.notes);layout=ScoreLayout(p);s=layout.systems[0]
        self.assertEqual(layout.engraving_slots(0,s.fragments[0]),[0,1440,1920,2880,3840])
        self.assertEqual(p.notes,original)
        units=layout.engraving_units(0)
        self.assertEqual(units,[0,1.75,3.5,5.25,6.25])

class ViewTests(unittest.TestCase):
    def setUp(self):
        self.view=ScoreView(song());self.view.resize(850,640);self.view.show();QTest.qWait(30)
    def tearDown(self):self.view.close();self.view.deleteLater();APP.processEvents()
    def document_point(self,anchor):
        v=self.view;return v.canvas.page_point(QPointF(anchor)+QPointF(v.horizontalScrollBar().value(),v.verticalScrollBar().value()))
    def wheel(self,ctrl=True):
        v=self.view;anchor=QPoint(230,180);glob=v.viewport().mapToGlobal(anchor);local=v.canvas.mapFromGlobal(glob)
        e=QWheelEvent(QPointF(local),QPointF(glob),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,
                      Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
        QApplication.sendEvent(v.canvas,e);APP.processEvents()
    def test_ctrl_wheel_preserves_cursor_anchor_and_manual_scale_on_resize(self):
        v=self.view;v.set_zoom(1.8);v.horizontalScrollBar().setValue(180);v.verticalScrollBar().setValue(1200);APP.processEvents()
        page,a=self.document_point(QPoint(230,180));self.wheel();other,b=self.document_point(QPoint(230,180))
        self.assertEqual(page,other);self.assertLess((a-b).manhattanLength(),1.3)
        self.assertAlmostEqual(v.canvas.scale,1.8*1.15);self.assertEqual(v.zoom_mode,'manual')
        v.resize(700,500);QTest.qWait(20);self.assertAlmostEqual(v.canvas.scale,1.8*1.15)
    def test_fill_width_and_fit_page_follow_viewport(self):
        v=self.view;self.assertAlmostEqual(v.canvas.scale,(v.viewport().width()-48)/PAPER_W)
        self.assertEqual(v.horizontalScrollBar().maximum(),0)
        v.resize(1000,720);QTest.qWait(20);self.assertAlmostEqual(v.canvas.scale,(v.viewport().width()-48)/PAPER_W)
        v.fit_zoom('page');QTest.qWait(20)
        self.assertLessEqual(PAPER_W*v.canvas.scale,v.viewport().width())
        self.assertLessEqual(PAPER_H*v.canvas.scale+32,v.viewport().height())
        v.set_zoom(2);v.locate_bar(23);v.fit_zoom('page');v.resize(850,800);QTest.qWait(40)
        page,_=v.canvas.page_point(QPointF(v.horizontalScrollBar().value()+v.viewport().width()/2,v.verticalScrollBar().value()+v.viewport().height()/2))
        x,y=v.canvas.page_origin(page)
        visible=QRectF(v.horizontalScrollBar().value(),v.verticalScrollBar().value(),v.viewport().width(),v.viewport().height())
        self.assertTrue(visible.contains(QRectF(x,y,PAPER_W*v.canvas.scale,PAPER_H*v.canvas.scale)))
    def test_ordinary_wheel_scrolls_without_changing_zoom(self):
        v=self.view;v.verticalScrollBar().setValue(900);scale=v.canvas.scale;self.wheel(False)
        self.assertEqual(v.canvas.scale,scale);self.assertLess(v.verticalScrollBar().value(),900)
    def test_middle_drag_pans_both_axes_without_selection_or_music_edits(self):
        v=self.view;v.set_zoom(2);v.horizontalScrollBar().setValue(300);v.verticalScrollBar().setValue(700)
        before=v.canvas.project.to_dict();v.canvas.selected_bars={2};start=v.viewport().mapToGlobal(QPoint(300,250))
        def send(kind,glob,button,buttons):
            event=QMouseEvent(kind,QPointF(v.canvas.mapFromGlobal(glob)),QPointF(glob),button,buttons,Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(v.canvas,event)
        send(QEvent.Type.MouseButtonPress,start,Qt.MouseButton.MiddleButton,Qt.MouseButton.MiddleButton)
        end=start-QPoint(90,70);send(QEvent.Type.MouseMove,end,Qt.MouseButton.NoButton,Qt.MouseButton.MiddleButton)
        send(QEvent.Type.MouseButtonRelease,end,Qt.MouseButton.MiddleButton,Qt.MouseButton.NoButton)
        self.assertEqual((v.horizontalScrollBar().value(),v.verticalScrollBar().value()),(390,770))
        self.assertEqual(v.canvas.selected_bars,{2});self.assertIsNone(v.canvas.pan);self.assertEqual(before,v.canvas.project.to_dict())
    def test_target_bar_revealed_on_both_axes_without_forcing_center(self):
        v=self.view;v.set_zoom(2);v.horizontalScrollBar().setValue(0);v.verticalScrollBar().setValue(0)
        self.assertTrue(v.locate_bar(23));APP.processEvents();rect=v.bar_rect(23)
        visible=QRectF(v.horizontalScrollBar().value(),v.verticalScrollBar().value(),v.viewport().width(),v.viewport().height())
        self.assertTrue(visible.contains(rect));position=(v.horizontalScrollBar().value(),v.verticalScrollBar().value())
        v.locate_bar(23);self.assertEqual(position,(v.horizontalScrollBar().value(),v.verticalScrollBar().value()))
        self.assertFalse(v.locate_bar(100))
    def test_hidden_repeat_bar_locates_its_visible_source(self):
        from popscore.presentation import add_compression
        p=Project();p.notes=[Note(b*3840,960,60) for b in range(8)];add_compression(p,list(range(8)),'repeat')
        self.view.canvas.rebuild(p);self.view.set_zoom(2)
        self.assertEqual(self.view.bar_rect(5),self.view.bar_rect(1));self.assertTrue(self.view.locate_bar(5))
    def test_large_zoom_cache_is_bounded_to_viewport_and_reused_for_playback(self):
        v=self.view;v.set_zoom(4);v.locate_bar(2);APP.processEvents();v.viewport().repaint()
        self.assertTrue(v.canvas.page_cache);count=v.canvas.cache_renders;layout=v.canvas.layout
        for pixmap,crop in v.canvas.page_cache.values():
            self.assertLessEqual(crop.width(),v.viewport().width()+97);self.assertLessEqual(crop.height(),v.viewport().height()+97)
        for tick in (7680,8000,8200):v.canvas.play_tick=tick;v.canvas.update();APP.processEvents()
        self.assertEqual(count,v.canvas.cache_renders);self.assertIs(layout,v.canvas.layout)

class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.save=patch.object(MainWindow,'save_preferences');self.save.start()
        self.w=MainWindow(song());self.w.timer.stop();self.w.autosave.stop();self.w.resize(1300,950);self.w.show();QTest.qWait(20)
    def tearDown(self):self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.save.stop()
    def test_music_edits_only_rebuild_score_on_entry(self):
        w=self.w;c=w.score_view.canvas;self.assertIsNone(c.layout)
        with patch('popscore.scoreview.ScoreLayout',wraps=ScoreLayout) as build:
            for pitch in (61,62,63):w.mutate('edit',lambda p,v=pitch:setattr(p.notes[0],'pitch',v))
            self.assertEqual(build.call_count,0)
            w.switch_workspace('score');self.assertEqual(build.call_count,1);layout=c.layout
            w.mutate('edit',lambda p:setattr(p.notes[0],'pitch',67));w.refresh();w.show_cursor(960)
            self.assertIs(c.layout,layout);self.assertEqual(c.project.notes[0].pitch,63)
            w.note_font.setValue(5);self.assertEqual(c.project.notes[0].pitch,63);self.assertEqual(c.project.notation['font_size'],5)
            count=build.call_count;w.switch_workspace('compose');w.mutate('edit',lambda p:setattr(p.notes[0],'pitch',69));self.assertEqual(build.call_count,count)
            w.switch_workspace('score');self.assertEqual(build.call_count,count+1);self.assertEqual(c.project.notes[0].pitch,69)
            layout=c.layout;w.mutate('music spelling',lambda p:setattr(p.notes[0],'flat',True));self.assertIs(c.layout,layout)
            w.set_spelling(w.project.notes[0].id,False);self.assertFalse(c.project.notes[0].flat)
            w.undo();self.assertTrue(c.project.notes[0].flat)
    def test_language_rebuild_preserves_snapshot_and_zoom(self):
        w=self.w;w.switch_workspace('score');w.score_view.set_zoom(1.7);old=w.score_view.canvas.layout
        w.mutate('edit',lambda p:setattr(p.notes[0],'pitch',70));w.change_language('en' if w.language=='zh' else 'zh',False);QTest.qWait(20)
        self.assertIs(w.score_view.canvas.layout,old);self.assertEqual(w.score_view.canvas.project.notes[0].pitch,60)
        self.assertEqual(w.score_view.zoom_mode,'manual');self.assertAlmostEqual(w.score_view.canvas.scale,1.7)
    def test_double_bar_header_in_both_docked_rolls_locates_score_without_editing(self):
        w=self.w;w.switch_workspace('score');w.edit_toggle.setChecked(True);w.toggle_editor();w.score_view.set_zoom(1.5)
        before=w.project.to_dict()
        for tab,roll in enumerate((w.roll,w.harmony_window.roll)):
            w.score_tabs.setCurrentIndex(tab);QTest.qWait(20);roll.ensure_tick(w.project.starts[20]);APP.processEvents()
            w.score_view.verticalScrollBar().setValue(0);spy=QSignalSpy(roll.measureActivated)
            QTest.mouseDClick(roll.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(round(roll.x_at(w.project.starts[20])+8),10));APP.processEvents()
            self.assertEqual(spy.count(),1);self.assertEqual(spy.at(0),[20])
            rect=w.score_view.bar_rect(20);visible=QRectF(w.score_view.horizontalScrollBar().value(),w.score_view.verticalScrollBar().value(),w.score_view.viewport().width(),w.score_view.viewport().height())
            self.assertTrue(visible.intersects(rect));self.assertGreater(w.score_view.verticalScrollBar().value(),0)
        self.assertEqual(before,w.project.to_dict())
    def test_floating_roll_and_compose_do_not_move_score(self):
        w=self.w;w.switch_workspace('score');w.edit_toggle.setChecked(True);w.toggle_editor();w.toggle_score_panel_floating('melody');APP.processEvents()
        with patch.object(w.score_view,'locate_bar') as locate:w.roll.measureActivated.emit(20);locate.assert_not_called()
        w.switch_workspace('compose')
        with patch.object(w.score_view,'locate_bar') as locate:w.roll.measureActivated.emit(20);locate.assert_not_called()
    def test_pdf_uses_displayed_snapshot_midi_uses_latest_music(self):
        from popscore.exportdialog import ExportDialog
        w=self.w;w.switch_workspace('score');w.mutate('edit',lambda p:setattr(p.notes[0],'pitch',70))
        pdf=ExportDialog(w,'pdf');midi=ExportDialog(w,'midi')
        self.assertEqual(pdf.project.notes[0].pitch,60);self.assertEqual(midi.project.notes[0].pitch,70)
        pdf.deleteLater();midi.deleteLater();w.switch_workspace('compose')
        pdf=ExportDialog(w,'pdf');self.assertEqual(pdf.project.notes[0].pitch,70);pdf.deleteLater()
    def test_new_document_does_not_retain_old_score(self):
        w=self.w;w.switch_workspace('score');p=song(8);p.title='replacement';w.replace_project(p)
        self.assertEqual(w.score_view.canvas.project.title,'replacement')
        w.switch_workspace('compose');w.replace_project(song(16));self.assertIsNone(w.score_view.canvas.layout)
        w.switch_workspace('score');self.assertEqual(len(w.score_view.canvas.project.measures),16)

if __name__=='__main__':unittest.main()
