"""Row edits apply the count recommendation in the same undoable operation."""
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from lingfeng.audio.midi import export_midi
from lingfeng.engraving.notation import ScoreLayout,PAPER_W,MARGIN
from lingfeng.engraving.presentation import apply_forced_row
from lingfeng.music.model import Context,Measure,Note,Project
from lingfeng.ui.main_window import MainWindow

APP=QApplication.instance() or QApplication([])

def song(size=7.5):
    p=Project(measures=[Measure() for _ in range(8)]);p.contexts=[Context(0,p.end)];p.chords=[]
    p.notes=[Note(t,480,48) for t in range(0,p.end,480)]
    p.notation.update(style='traditional',per_line=2,font_size=size,font_layout_version=45,circles=True,lyrics=False)
    return p

class CountFontControlTests(unittest.TestCase):
    def setUp(self):
        self.preferences=patch.object(MainWindow,'save_preferences');self.preferences.start();self.addCleanup(self.preferences.stop)
        self.w=MainWindow(song());self.w.timer.stop();self.w.autosave.stop();self.w.change_language('zh',False)
        self.assertTrue(self.w.switch_workspace('score'));self.addCleanup(self.close)

    def close(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents()

    def assert_font(self,value):
        w=self.w;layout=w.score_view.canvas.layout
        self.assertEqual(w.project.notation['font_size'],value);self.assertEqual(w.note_font.value(),value)
        self.assertEqual(w.score_view.canvas.project.notation['font_size'],value);self.assertEqual(layout.font_size,value)
        self.assertTrue(all(row.layout_scale==1 for row in layout.systems))

    def assert_recommended(self):
        layout=self.w.score_view.canvas.layout;self.assert_font(layout.recommended_font_size)
        self.assertIs(type(layout.recommended_font_size),int)
        self.assertTrue(all(abs(sum(row.bar_widths)-(PAPER_W-2*MARGIN))<1e-6 for row in layout.systems))

    def test_first_score_entry_reduces_oversized_font_using_recommendation(self):
        self.w.switch_workspace('compose');self.w.replace_project(song(40))
        self.assertTrue(self.w.switch_workspace('score'));self.assert_recommended()
        self.assertLess(self.w.project.notation['font_size'],40)

    def test_per_line_recommends_in_the_same_undo_step_and_preserves_music(self):
        w=self.w;before=copy.deepcopy(w.project.to_dict());midi=export_midi(w.project,None);history=len(w.undo_history)
        w.set_notation('per_line',4);self.assert_recommended();self.assertEqual(len(w.undo_history),history+1)
        self.assertEqual(export_midi(w.project,None),midi)
        w.undo();self.assert_font(7.5);self.assertEqual(w.project.notation['per_line'],2)
        self.assertEqual(w.project.to_dict(),before)
        w.redo();self.assert_recommended();self.assertEqual(w.project.notation['per_line'],4)

    def test_force_and_restore_rows_apply_the_new_reference_and_undo_together(self):
        w=self.w;before=copy.deepcopy(w.project.to_dict());midi=export_midi(w.project,None)
        payload=dict(bars=[0,1,2],ranges=[[0,w.project.starts[3]]])
        w.score_command('force_row',payload);self.assert_recommended()
        layout=w.score_view.canvas.layout;row=layout.systems[0]
        self.assertEqual(row.bars,[0,1,2]);self.assertTrue(row.is_forced)
        self.assertAlmostEqual(row.font_ratio,layout.reference_unit_count/row.unit_count)
        self.assertEqual(export_midi(w.project,None),midi)
        w.undo();self.assertEqual(w.project.to_dict(),before);self.assert_font(7.5)
        w.redo();self.assert_recommended()
        w.score_command('auto_rows',payload);self.assert_recommended()
        self.assertFalse(any(row.is_forced for row in w.score_view.canvas.layout.systems))

    def test_forced_glyph_font_tracks_manual_global_font_without_scaling_headers(self):
        w=self.w;w.score_command('force_row',dict(bars=[0,1,2],ranges=[[0,w.project.starts[3]]]))
        ratio=w.score_view.canvas.layout.systems[0].font_ratio
        for value in (8,12.5):
            w.set_notation('font_size',value);self.assert_font(value)
            row=w.score_view.canvas.layout.systems[0]
            self.assertAlmostEqual(row.font_ratio,ratio);self.assertAlmostEqual(row.symbol_scale,value/15*ratio)
            self.assertAlmostEqual(row.cell_width,20.95*value/15*ratio)

    def test_new_music_budget_is_recommended_when_returning_to_score(self):
        w=self.w;w.switch_workspace('compose')
        w.project.notes=[Note(t,120,48) for t in range(0,w.project.end,120)];w.refresh()
        midi=export_midi(w.project,None);self.assertTrue(w.switch_workspace('score'));self.assert_recommended()
        self.assertEqual(export_midi(w.project,None),midi)

    def test_recommendation_uses_frozen_music_and_current_force_metadata(self):
        w=self.w;original=list(w.score_view.canvas.project.notes)
        w.project.notes=[Note(t,120,48) for t in range(0,w.project.end,120)]
        candidate=copy.deepcopy(w.project);apply_forced_row(candidate,[0,1,2])
        snapshot=w.score_font_project(candidate)
        self.assertEqual(snapshot.notes,original);self.assertEqual(snapshot.notation['forced_rows'],[[0,3]])
        self.assertEqual(ScoreLayout(snapshot).systems[0].bars,[0,1,2])

if __name__=='__main__':unittest.main()
