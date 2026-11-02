"""True font sizing from visible symbol budgets, without whole-row transforms."""
import copy
import math
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from lingfeng.audio.midi import event_list,export_midi
from lingfeng.engraving.notation import ScoreLayout,export_pdf,PAPER_W,MARGIN
from lingfeng.engraving.presentation import apply_forced_row
from lingfeng.music.model import Chord,Note
from tests.test_v542_layout import STYLES,paint,song


def density_song(dense=6,normal=4,size=10):
    p=song(bars=dense+normal,size=size,per_line=4)
    for bar in range(dense+normal):
        step=120 if bar<dense else 480
        p.notes.extend(Note(bar*3840+t,step,48)for t in range(0,3840,step))
    return p


def expected_recommendation(units):
    return max(1,min(72,math.floor(15*(PAPER_W-2*MARGIN)/(20.95*units)+1e-7)))


class VisibleBudgetTests(unittest.TestCase):
    def assert_gap_budget(self,layout):
        for s in layout.systems:
            self.assertEqual(s.layout_scale,1)
            self.assertEqual(s.unit_count,s.symbol_count+s.gap_units)
            self.assertEqual(s.gap_units,2*len(s.beat_cells))
            expected=max(s.cell_width,(PAPER_W-2*MARGIN-s.symbol_count*s.cell_width)/s.gap_units)
            self.assertAlmostEqual(s.bar_side_gap,expected);self.assertAlmostEqual(s.beat_gap,2*expected)

    def test_split_fragments_and_extension_dashes_each_count_as_visible_symbols(self):
        p=song([Note(0,1440,48),Note(1440,480,50),Note(1920,1920,52)])
        before=copy.deepcopy(p.to_dict());layout=ScoreLayout(p);s=layout.systems[0]
        self.assertEqual([f.start for f in s.fragments[0]if f.note],[0,960,1440,1920])
        self.assertIn((0,2880),s.traditional_cells)  # sustain dash, not a new note
        self.assertEqual((s.symbol_count,s.gap_units,s.unit_count),(5,8,13))
        self.assertEqual(layout.reference_unit_count,13)
        self.assertEqual(layout.recommended_font_size,expected_recommendation(13))
        self.assertEqual(p.to_dict(),before);self.assert_gap_budget(layout)

    def test_nonforced_rows_set_global_advice_and_forced_ratio_uses_full_budget(self):
        p=density_song();apply_forced_row(p,list(range(6)));layout=ScoreLayout(p)
        forced,normal=layout.systems
        self.assertEqual(layout.reference_source,'nonforced');self.assertEqual(layout.reference_rows,((6,7,8,9),))
        self.assertEqual(layout.reference_unit_count,64);self.assertEqual(layout.recommended_font_size,expected_recommendation(64))
        self.assertEqual((forced.symbol_count,forced.gap_units,forced.unit_count),(192,48,240))
        self.assertEqual((normal.symbol_count,normal.gap_units,normal.unit_count),(32,32,64))
        self.assertTrue(forced.is_forced);self.assertFalse(normal.is_forced)
        self.assertAlmostEqual(forced.font_ratio,64/240);self.assertAlmostEqual(forced.forced_font_ratio,64/240)
        self.assertEqual(normal.font_ratio,1);self.assertNotAlmostEqual(forced.font_ratio,4/6)
        self.assert_gap_budget(layout)

    def test_all_forced_fallback_uses_current_automatic_rows_and_visible_density(self):
        p=density_song(4,4);apply_forced_row(p,list(range(8)));layout=ScoreLayout(p)
        self.assertEqual(layout.reference_source,'baseline');self.assertEqual(layout.reference_rows,((0,1,2,3),(4,5,6,7)))
        self.assertEqual(layout.reference_unit_count,160);self.assertEqual(layout.systems[0].unit_count,224)
        self.assertAlmostEqual(layout.systems[0].font_ratio,160/224)
        self.assertEqual(layout.recommended_font_size,expected_recommendation(160))
        p.notation['per_line']=2;changed=ScoreLayout(p)
        self.assertEqual(changed.reference_rows,((0,1),(2,3),(4,5),(6,7)))
        self.assertEqual(changed.reference_unit_count,80);self.assertAlmostEqual(changed.systems[0].font_ratio,80/224)
        self.assertEqual(changed.recommended_font_size,expected_recommendation(80));self.assert_gap_budget(changed)

    def test_per_line_and_content_changes_recompute_advice_ratio_and_gap(self):
        p=density_song();apply_forced_row(p,list(range(6)));first=ScoreLayout(p)
        p.notation['font_size']=first.recommended_font_size;first=ScoreLayout(p)
        p.notation['per_line']=2;probe=ScoreLayout(p);p.notation['font_size']=probe.recommended_font_size;second=ScoreLayout(p)
        self.assertEqual((first.reference_unit_count,second.reference_unit_count),(64,32))
        self.assertGreater(second.font_size,first.font_size)
        self.assertNotEqual(second.systems[0].cell_width,first.systems[0].cell_width)
        self.assertNotEqual(second.systems[0].bar_side_gap,first.systems[0].bar_side_gap)
        self.assert_gap_budget(second)
        # More ink in the forced part changes its own ratio, not normal advice.
        p.notes=[n for n in p.notes if n.start>=6*3840]+[Note(t,60,48)for t in range(0,6*3840,60)]
        forced_dense=ScoreLayout(p)
        self.assertEqual(forced_dense.reference_unit_count,32)
        self.assertEqual(forced_dense.recommended_font_size,second.recommended_font_size)
        self.assertEqual(forced_dense.systems[0].unit_count,432)
        self.assertAlmostEqual(forced_dense.systems[0].font_ratio,32/432)
        # More ink in the normal part changes the global recommendation too.
        p.notes=[n for n in p.notes if n.start<6*3840]+[Note(t,120,48)for t in range(6*3840,p.end,120)]
        normal_dense=ScoreLayout(p)
        self.assertEqual(normal_dense.reference_unit_count,80)
        self.assertLess(normal_dense.recommended_font_size,forced_dense.recommended_font_size)
        self.assert_gap_budget(normal_dense)

    def test_forced_font_and_real_circle_width_follow_the_global_requested_font(self):
        p=density_song(size=8);p.chords=[Chord(0,p.end,48)];p.notation['circles']=True;apply_forced_row(p,list(range(6)))
        measured=[]
        for size in (8,16):
            p.notation['font_size']=size;layout=ScoreLayout(p);pages=paint(layout)
            self.assertEqual(layout.font_size,size)
            widths=[]
            for data in pages:
                for row in data['rows']:
                    s=row['system'];self.assertEqual(s.layout_scale,1)
                    self.assertAlmostEqual(s.symbol_scale,size/15*s.font_ratio)
                    self.assertAlmostEqual(s.cell_width,20.95*size/15*s.font_ratio)
                    circles=[i for i in row['ink']if i['kind']=='ellipse'and i['rx']!=i['ry']]
                    self.assertTrue(circles)
                    for circle in circles:self.assertAlmostEqual(circle['path'].boundingRect().width(),s.cell_width)
                    widths.append(circles[0]['path'].boundingRect().width())
            measured.append(widths)
        for a,b in zip(*measured):self.assertAlmostEqual(b/a,2)

    def test_manual_oversize_is_never_hidden_by_a_whole_row_transform_in_any_style(self):
        for style in STYLES:
            p=density_song(size=72);p.notation['style']=style;apply_forced_row(p,list(range(6)))
            before=copy.deepcopy(p.to_dict());layout=ScoreLayout(p);paint(layout)
            self.assertTrue(all(s.layout_scale==1 for s in layout.systems));self.assertEqual(layout.font_size,72)
            self.assertEqual(p.to_dict(),before)

    def test_recommended_render_and_pdf_preserve_source_ids_timing_and_midi(self):
        p=density_song();apply_forced_row(p,list(range(6)));p.notation['font_size']=ScoreLayout(p).recommended_font_size
        before=copy.deepcopy(p.to_dict());events=event_list(p);midi=export_midi(p,None)
        layout=ScoreLayout(p);pages=paint(layout);self.assert_gap_budget(layout)
        for s in layout.systems:self.assertAlmostEqual(sum(s.bar_widths),PAPER_W-2*MARGIN)
        self.assertTrue(pages)
        with tempfile.TemporaryDirectory(dir='tmp')as folder:
            path=Path(folder)/'budget-fonts.pdf';self.assertGreater(export_pdf(p,path),0)
            self.assertTrue(path.read_bytes().startswith(b'%PDF'))
        self.assertEqual(p.to_dict(),before);self.assertEqual(event_list(p),events);self.assertEqual(export_midi(p,None),midi)


if __name__=='__main__':unittest.main()
