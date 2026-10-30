"""Compact per-bar lyric input, explicit skip syntax and first-open autofill."""
import copy,os,tempfile,unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Project, Measure, Context, Note, demo_project
from lingfeng.ui.main_window import MainWindow
from lingfeng.engraving.lyrics import apply_range, range_source, events, sections, tokenize, plan_range, matching_issues
from lingfeng.audio.midi import event_list
from lingfeng.engraving.notation import ScoreLayout

APP=QApplication.instance() or QApplication([])

def song():
    p=Project();p.measures=[Measure() for _ in range(4)];p.contexts=[Context(0,p.end)]
    p.notes=[Note(i*480,480,60+i%5) for i in range(32)]
    return p

class SyntaxTests(unittest.TestCase):
    def test_slash_skips_punctuation_and_english_word_boundaries(self):
        t=tokenize("我，爱。你,hello world!/s/s中—文。rock-and-roll")
        self.assertEqual([x.text for x in t],['我，','爱。','你,','hello','world!','','','中—','文。','rock-and-roll'])
        self.assertEqual([i for i,x in enumerate(t) if x.skip],[5,6])
        self.assertEqual([t.text for t in tokenize('，我/s，你。')],['，我，','','你。'])

    def test_newlines_anchor_partial_bars_and_preserve_empty_lines(self):
        p=song();plan=plan_range(p,'春风\n\nhello world',0,3)
        self.assertFalse(plan.issues);self.assertEqual([e['tick'] for e in plan.events],[0,480,7680,8160])
        self.assertTrue(plan_range(p,'一二三四五六七八九\n好',0,2).issues)
        self.assertFalse(plan_range(p,'好\n',0,1).issues)
        self.assertTrue(plan_range(p,'好\n多',0,1).issues)

    def test_compact_autofill_merges_rap_across_bars_and_keeps_internal_gaps(self):
        p=song();text='春风，/s/s唱出心声\n/x{我们一起跟着节奏\nLet us rap in English now/s/s}\n你&好。'
        apply_range(p,text,0,4);before=p.to_dict();loaded,valid=range_source(p,0,4)
        self.assertTrue(valid);self.assertEqual(loaded,text);self.assertEqual(loaded.count('/x{'),1);self.assertNotIn('|',loaded)
        self.assertEqual(before,p.to_dict());midi=event_list(p);saved=[(e['tick'],e['text'],e['kind'],e['skip']) for e in events(p)]
        apply_range(p,loaded,0,4,replace=True)
        self.assertEqual(saved,[(e['tick'],e['text'],e['kind'],e['skip']) for e in events(p)]);self.assertEqual(event_list(p),midi)
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            path=Path(folder)/'lyrics.lfs';p.save(path);q=Project.load(path)
        self.assertEqual(range_source(q,0,4),(text,True));self.assertEqual(matching_issues(q),[])

    def test_legacy_source_uses_saved_assignments_and_new_display_syntax(self):
        p=song();ident=apply_range(p,'be fore/sdawn\n/x{说唱}',0,2)
        raw=p.notation['lyric_sections'][0];raw.update(text='be-fore _ dawn | /x{说}/x{唱}',syntax_version=1)
        before=p.to_dict();loaded=sections(p)[0]
        self.assertEqual(loaded['text'],'be fore/sdawn\n/x{说唱}');self.assertEqual(before,p.to_dict())
        self.assertFalse(plan_range(p,loaded['text'],0,2,section_id=ident).issues)

    def test_unclosed_or_nested_multiline_rap_is_atomic(self):
        p=song();before=p.to_dict()
        for text in ('/x{我\n你','/x{我\n/x{你}}','/x{}\n你'):
            with self.assertRaises(ValueError):apply_range(p,text,0,2)
            self.assertEqual(p.to_dict(),before)

class OpeningTests(unittest.TestCase):
    def setUp(self):
        p=song();apply_range(p,'已有歌词\n第二小节',0,2)
        self.w=MainWindow(p);self.w.save_preferences=lambda:None;self.w.timer.stop();self.w.autosave.stop();self.w.show()
    def tearDown(self):self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents()
    def test_first_tab_click_autofills_without_mutating(self):
        w=self.w;w.switch_workspace('score');before=w.project.to_dict();w.score_tabs.setCurrentWidget(w.lyric_panel)
        self.assertTrue(w.lyric_panel.text.toPlainText().startswith('已有歌词\n第二小节'));self.assertEqual(w.project.to_dict(),before)
    def test_first_menu_and_floating_open_use_current_selection(self):
        w=self.w;w.switch_workspace('score');w.score_view.canvas.selected_bars={1};w.toggle_score_panel_floating('lyrics')
        self.assertEqual(w.lyric_panel.text.toPlainText(),'第二小节');self.assertEqual(w.lyric_panel.start.value(),2)
        w.lyric_panel.text.setPlainText('未提交草稿');w.show_score_panel('lyrics');self.assertEqual(w.lyric_panel.text.toPlainText(),'未提交草稿')
    def test_replacement_project_loads_visible_editor_and_explicit_new_stays_empty(self):
        w=self.w;w.batch_lyrics();p=song();apply_range(p,'新工程',0,1);w.replace_project(p)
        self.assertTrue(w.lyric_panel.text.toPlainText().startswith('新工程'))
        w.lyric_panel.new_section();w.show_score_panel('lyrics');self.assertEqual(w.lyric_panel.text.toPlainText(),'')

class ExampleTests(unittest.TestCase):
    def test_builtin_and_standalone_examples_have_valid_rap_with_real_midi(self):
        for p in (demo_project(),Project.load('examples/demo.lfs'),Project.load('examples/lingfeng-rap.lfs')):
            self.assertTrue(any(e.get('kind')=='rap_note' for e in events(p)));self.assertFalse(matching_issues(p));midi=event_list(p)
            layout=ScoreLayout(p);self.assertTrue(any(f.ghost for s in layout.systems for fs in s.fragments.values() for f in fs));self.assertEqual(event_list(p),midi)

if __name__=='__main__':unittest.main()
