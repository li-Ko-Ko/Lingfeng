import os,copy,threading,time,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QLabel,QDialog
from PySide6.QtGui import QImage,QPainter
from PySide6.QtTest import QTest
from unittest.mock import patch
from lingfeng.music.model import Project, Note, Chord
from lingfeng.ui.main_window import MainWindow
from lingfeng.audio.transport import Transport
from lingfeng.engraving.lyrics import plan_range, apply_range, apply_section, events, matching_issues, sections
from lingfeng.engraving.notation import ScoreLayout
from lingfeng.ui.dialogs import NoteDialog
from lingfeng.platform.i18n import set_language

APP=QApplication.instance() or QApplication([])

class Synth:
    def __init__(self):self.events=[]
    def send(self,*args):self.events.append(args)
    def close(self):pass

def music():
    p=Project();p.notes=[Note(b*3840+t,240,60+i*2) for b in range(8) for i,t in enumerate((0,960,1920))]
    p.notes.append(Note(3840,480,72));return p

class LiveTests(unittest.TestCase):
    def test_edit_future_notes_and_sustains_without_restarting_worker_or_clock(self):
        p=Project();p.bpm=300;p.notes=[Note(0,3840,60)];t=Transport();t.synth=Synth();t.play(p)
        try:
            time.sleep(0.025);worker=t.thread;clock=t.start_time;t.synth.events.clear();tick=t.position()
            p.notes.append(Note(960,120,64,80));t.revise(p);time.sleep(0.02)
            self.assertIs(t.thread,worker);self.assertEqual(t.start_time,clock);self.assertTrue(t.playing);self.assertGreater(t.position(),tick)
            self.assertFalse(any(e[0] in (0x80,0xB0) for e in t.synth.events))
            p.notes=p.notes[1:];t.revise(p);time.sleep(0.025);self.assertIn((0x80,60),t.synth.events)
            time.sleep(0.21);self.assertIn((0x90,64,80),t.synth.events);self.assertTrue(t.playing)
        finally:t.close()

    def test_tempo_change_keeps_position_monotonic_and_worker(self):
        p=Project();p.notes=[Note(0,3840,60)];t=Transport();t.synth=Synth();t.play(p)
        try:
            time.sleep(0.035);before=t.position();worker=t.thread;p.bpm=200;t.revise(p);time.sleep(0.02)
            self.assertIs(t.thread,worker);self.assertGreaterEqual(t.position(),before);self.assertLess(t.position()-before,160);self.assertAlmostEqual(t.seconds_per_tick,60/200/960)
        finally:t.close()

    def test_loop_replacement_uses_edited_notes_and_no_stuck_old_notes(self):
        p=Project();p.bpm=300;p.notes=[Note(0,480,60)];t=Transport();t.synth=Synth();t.play(p,0,480,True)
        try:
            time.sleep(0.02);p.notes=[Note(0,480,67,80)];t.revise(p);time.sleep(0.14)
            self.assertIn((0x80,60),t.synth.events);self.assertGreaterEqual(t.synth.events.count((0x90,67,80)),2);self.assertTrue(t.playing)
        finally:t.close()

class RangeTests(unittest.TestCase):
    def setUp(self):set_language('zh')
    def test_range_unique_onsets_template_and_exact_coverage(self):
        p=music();plan=plan_range(p,'&&& | &&&',1,2)
        self.assertEqual(len(plan.events),6);self.assertTrue(plan.issues)
        good=plan_range(p,'风 _ 来 | be fore dawn',1,2)
        self.assertFalse(good.issues);self.assertEqual([e['tick'] for e in good.events],[3840,4800,5760,7680,8640,9600])

    def test_overflow_and_excess_bar_count_cannot_save(self):
        p=music();before=p.to_dict()
        for text in ('风雨来又去来去','风 雨 来 | 风 雨 来 | 风'):
            with self.assertRaises(ValueError):apply_range(p,text,1,2)
            self.assertEqual(before,p.to_dict())

    def test_bar_separators_prevent_syllables_spilling_into_next_bar(self):
        p=music();plan=plan_range(p,'一二三四 | 五六',1,2)
        self.assertTrue(plan.issues);self.assertEqual([e['text'] for e in plan.events if e['tick']==7680],['五'])

    def test_empty_bars_rap_bounds_and_missing_overlapped_melody_onsets(self):
        p=Project();good=plan_range(p,'我/64.爱/64你/64 | ',2,2);self.assertFalse(good.issues)
        self.assertEqual([e['duration'] for e in good.events],[90,60,60])
        self.assertTrue(plan_range(p,'我/1. | ',2,2).issues)
        p.notes=[Note(2*3840+60,240,60)];self.assertFalse(plan_range(p,'我/64.爱/64你/64',2,1).issues)

    def test_range_metadata_and_new_onsets_after_confirmation(self):
        p=music();apply_range(p,'一二三 | 四五六',1,2);self.assertFalse(matching_issues(p))
        self.assertEqual((sections(p)[0]['start'],sections(p)[0]['end']),(3840,11520))
        p.insert_measure(0);self.assertEqual((sections(p)[0]['start'],sections(p)[0]['end']),(7680,15360))
        p.notes.append(Note(7680+480,120,80));self.assertFalse(matching_issues(p))

    def test_mixed_meter_uses_actual_bar_boundaries(self):
        p=Project();p.change_meter(1,6,8);p.notes=[Note(p.starts[1]+t,120,60) for t in (0,320,960)]
        self.assertFalse(plan_range(p,'我爱你',1,1).issues);self.assertEqual(plan_range(p,'我爱你',1,1).end,p.starts[2])

class LayoutTests(unittest.TestCase):
    def test_numbers_rests_and_rap_share_per_bar_font(self):
        p=music();apply_section(p,'我/64.爱/64你/64',14400)
        for style in ('traditional','spatial','compact'):
            p.notation['style']=style;layout=ScoreLayout(p);image=QImage(900,1273,QImage.Format.Format_RGB32);paint=QPainter(image);layout.draw(paint,0);paint.end()
            self.assertTrue({'0','x','1','2','3'}.issubset({g for g,s in layout.glyph_sizes}));self.assertTrue(all(0<size<=p.notation['font_size'] for g,size in layout.glyph_sizes))
            for t,end,left,right,a,b in layout.symbol_boxes:self.assertGreaterEqual(left,a-1e-5);self.assertLessEqual(right,b+1e-5)

    def test_pitch_gap_is_exact_and_not_clamped_by_font_or_polyphony(self):
        p=music();p.notes.append(Note(0,960,72));p.notation['font_size']=26
        for style in ('spatial','compact'):
            p.notation['style']=style;heights=[]
            for gap in (4,8,12,20,32):
                p.notation['row_gap']=gap;layout=ScoreLayout(p);self.assertTrue(all(s.row_gap==gap for s in layout.systems));heights.append(layout.systems[0].height)
            self.assertEqual(heights,sorted(set(heights)))

class UITests(unittest.TestCase):
    def setUp(self):
        set_language('zh');self.w=MainWindow(music());self.w.change_language('zh',False);self.w.resize(1280,1000);self.w.show();self.w.autosave.stop();QTest.qWait(40)
    def tearDown(self):self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents()

    def test_edit_undo_redo_and_invalid_edit_keep_playing_and_anchor(self):
        w=self.w;w.transport.close();w.transport.synth=Synth();w.playhead=0;w.toggle_play();QTest.qWait(20);worker=w.transport.thread;anchor=w.play_anchor
        self.assertTrue(w.mutate('edit',lambda p:setattr(p.notes[-1],'pitch',70)));self.assertTrue(w.transport.playing);self.assertIs(w.transport.thread,worker)
        w.undo();w.redo();self.assertTrue(w.transport.playing);self.assertEqual(w.play_anchor,anchor)
        with patch('lingfeng.ui.main_window.QMessageBox.warning'):
            self.assertFalse(w.mutate('bad',lambda p:setattr(p.notes[0],'pitch',200)))
        self.assertTrue(w.transport.playing);w.set_notation('row_gap',10);self.assertTrue(w.transport.playing)
        w.switch_workspace('score');w.batch_lyrics();w.toggle_score_panel_floating('lyrics');w.lyric_panel.text.setFocus();QTest.keyClicks(w.lyric_panel.text,'hello world')
        self.assertEqual(w.lyric_panel.text.toPlainText(),'hello world');self.assertTrue(w.transport.playing)
        w.change_language('en',False);self.assertTrue(w.transport.playing)

    def test_composition_has_no_lyric_fields_or_status(self):
        w=self.w;self.assertFalse(w.lyrics_action.isVisible());w.project.notes[0].lyric='歌词内容';w.note_selected(w.project.notes[0].id)
        self.assertNotIn('歌词',w.statusBar().currentMessage());d=NoteDialog(w.project.notes[0],w.project,w)
        self.assertFalse(hasattr(d,'lyric'));self.assertFalse(any('歌词' in label.text() for label in d.findChildren(QLabel)));self.assertEqual(d.value().lyric,'歌词内容');d.close()

    def test_lyric_range_template_table_commit_and_undo(self):
        w=self.w;w.switch_workspace('score');self.assertTrue(w.lyrics_action.isVisible());panel=w.lyric_panel
        panel.start.setValue(2);panel.count.setValue(2);panel.template();self.assertEqual(panel.text.toPlainText().count('&'),6);self.assertFalse(panel.apply.isEnabled())
        self.assertEqual(panel.rhythm.topLevelItemCount(),2);panel.text.setPlainText('风 _ 来 | be fore dawn');self.assertTrue(panel.check());panel.commit()
        self.assertEqual(len(events(w.project)),6);w.undo();self.assertFalse(events(w.project));w.switch_workspace('compose');self.assertFalse(w.lyrics_action.isVisible())

    def test_score_fills_top_area_when_collapsed_docked_or_floating(self):
        w=self.w;w.switch_workspace('score');self.assertFalse(hasattr(w,'score_height'))
        for mode in ('collapsed','docked','floating'):
            for key in w.score_pages:
                w.set_score_panel_visible(key,mode!='collapsed')
                if mode=='floating':w.toggle_score_panel_floating(key)
            QTest.qWait(40)
            self.assertEqual(w.score_view.y(),0)
            if mode!='docked':self.assertGreaterEqual(w.score_view.height(),w.score_splitter.height()-4)
            else:self.assertGreater(w.score_tools.height(),100)

    def test_gap_control_changes_actual_layout_and_traditional_explains_scope(self):
        w=self.w;w.switch_workspace('score');w.rowgap.setValue(8);a=w.score_view.canvas.layout.systems[0];self.assertEqual(a.row_gap,8)
        w.rowgap.setValue(24);b=w.score_view.canvas.layout.systems[0];self.assertEqual(b.row_gap,24);self.assertGreater(b.height,a.height)
        w.set_notation('style','traditional');self.assertFalse(w.rowgap.isEnabled())

    def test_lyric_panel_and_rhythm_table_keep_dark_backgrounds(self):
        w=self.w;w.switch_workspace('score');w.batch_lyrics();w.set_theme('dark');APP.processEvents();panel=w.lyric_panel
        self.assertLess(panel.grab().toImage().pixelColor(3,3).lightness(),90)
        image=panel.rhythm.viewport().grab().toImage();self.assertLess(image.pixelColor(image.width()-5,image.height()-5).lightness(),90)

if __name__=='__main__':unittest.main()
