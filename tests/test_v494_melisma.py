"""Lyric skips and display-only adjacent-onset slurs."""
import copy,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from lingfeng.music.model import Project, Measure, Context, Note
from lingfeng.engraving.lyrics import tokenize, format_tokens, apply_range, range_source, events, sections, melisma_links, delete_range, matching_issues
from lingfeng.audio.midi import export_midi
from lingfeng.engraving.notation import ScoreLayout, export_pdf
from tests import test_v494 as entry

def song():
    p=Project();p.measures=[Measure() for _ in range(4)];p.contexts=[Context(0,p.end)]
    p.notes=[Note(i*480,480,(60,62,64,65,67,65,64,62)[i%8]) for i in range(32)]
    p.notation.update(style='traditional',per_line=2,font_size=12)
    return p

class MelismaTests(unittest.TestCase):
    def test_skip_and_melisma_tokens_are_distinct_and_punctuation_takes_no_slot(self):
        text='我，/-/-/s/x{Hello world!/-}/s尾。'
        tokens=tokenize(text)
        self.assertEqual([t.melisma for t in tokens],[False,True,True,False,False,False,True,False,False])
        self.assertEqual(format_tokens(tokens),text)
        self.assertFalse(any(t.melisma for t in tokenize('我/-/-',syntax_version=3)))
        self.assertEqual(format_tokens(tokenize('我/-_-',syntax_version=2)),'我/s/s/s')

    def test_adjacent_123_get_two_slurs_and_no_extra_text_or_midi_changes(self):
        for style in ('traditional','spatial','compact'):
            p=song();p.notation['style']=style;apply_range(p,'我/s/s',0,1);midi=export_midi(p,None);notes=copy.deepcopy(p.notes)
            apply_range(p,'我/-/-',0,1,replace=True);before=p.to_dict();layout=entry.render(p)
            self.assertEqual([(a,b,k) for a,b,k,_ in layout.melisma_paths],[(0,480,'continuous'),(480,960,'continuous')])
            self.assertEqual([e['text'] for e in events(p)],['我','',''])
            self.assertEqual(len(layout.lyric_positions),1);self.assertEqual(p.to_dict(),before)
            self.assertEqual(p.notes,notes);self.assertEqual(export_midi(p,None),midi)
            self.assertEqual(range_source(p,0,1),('我/-/-',True))
            apply_range(p,'我/s/s',0,1,replace=True);self.assertFalse(entry.render(p).melisma_paths)

    def test_first_song_onset_has_no_predecessor_but_range_start_can_connect_back(self):
        p=song();before=p.to_dict()
        with self.assertRaises(ValueError):apply_range(p,'/-我',0,1)
        self.assertEqual(p.to_dict(),before)
        apply_range(p,'/-',1,1)
        self.assertEqual([(a,b) for a,b,_,_ in melisma_links(p)],[(3360,3840)])
        self.assertEqual(range_source(p,1,1),('/-',True))

    def test_legacy_saved_skip_sources_are_not_reinterpreted(self):
        p=song();apply_range(p,'我/s/s',0,1)
        p.notation['lyric_sections'][0].update(text='我/-/-',syntax_version=3)
        before=p.to_dict();self.assertEqual(sections(p)[0]['text'],'我/s/s');self.assertFalse(melisma_links(p))
        self.assertEqual(before,p.to_dict())

    def test_mixed_rap_newlines_roundtrip_and_old_sample_remain_valid(self):
        p=song();text='我/-/-/s\n/x{我们/-Let us rap!/-/s}\n/-唱'
        apply_range(p,text,0,3);before=export_midi(p,None)
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            path=Path(folder)/'melisma.lfs';p.save(path);p=Project.load(path)
        self.assertEqual(range_source(p,0,3),(text,True));self.assertFalse(matching_issues(p));self.assertEqual(export_midi(p,None),before)
        layout=entry.render(p);self.assertEqual(len(layout.melisma_paths),6)
        self.assertEqual({kind for _,_,kind,_ in layout.melisma_paths},{'continuous','outgoing','incoming'})

    def test_polyphonic_attacks_under_sustain_and_multiple_verses_draw_once(self):
        p=song();p.notes[0].duration=1920;p.notes.append(Note(480,480,72));p.notes.append(Note(960,480,76))
        apply_range(p,'我/-/-',0,1);apply_range(p,'你/-/-',0,1,verse=1)
        self.assertEqual(len(melisma_links(p)),2);self.assertEqual(len(entry.render(p).melisma_paths),2)

    def test_crossbar_crossrow_and_page_entries(self):
        p=song();apply_range(p,'/s/s/s/s/s/s/s我\n/-/s/s/s/s/s/s你\n/-',0,3)
        paths=entry.render(p).melisma_paths
        self.assertEqual([(a,b,k) for a,b,k,_ in paths],[(3360,3840,'continuous'),(7200,7680,'outgoing'),(7200,7680,'incoming')])
        entry.EntryTieTests().assertDescendingLine(paths[-1][3])
        p=Project();p.notation.update(per_line=2,row_gap=32)
        p.notes=[Note(i*3840,240,21 if i%2==0 else 108) for i in range(len(p.measures))]
        first=next(s for s in ScoreLayout(p).systems if s.page==1);bar=first.bars[0];tick=p.starts[bar]
        apply_range(p,'/-',bar,1)
        self.assertIn((tick-3840,tick,'outgoing'),[(a,b,k) for a,b,k,_ in entry.render(p,0).melisma_paths])
        paths=entry.render(p,1).melisma_paths;self.assertEqual([(a,b,k) for a,b,k,_ in paths],[(tick-3840,tick,'incoming')])
        entry.EntryTieTests().assertDescendingLine(paths[0][3])

    def test_range_delete_preserves_outside_and_verse_flags(self):
        p=song();apply_range(p,'我/-/-\n你/-/-',0,2);apply_range(p,'他/-/-',0,1,verse=1)
        delete_range(p,0,1);self.assertEqual(range_source(p,1,1),('你/-/-',True));self.assertEqual(range_source(p,0,1,1),('他/-/-',True))
        self.assertEqual(len(melisma_links(p)),4)

    def test_flag_validation_rejects_visible_or_timed_melisma(self):
        p=song();apply_range(p,'我/-',0,1)
        for changes in ({'melisma':1},{'text':'字'},{'skip':False},{'duration':240}):
            q=Project.from_dict(p.to_dict());q.notation['lyric_events'][1].update(changes)
            with self.assertRaises(ValueError):q.validate()

    def test_pdf_uses_melisma_paths_without_mutating_project(self):
        p=song();apply_range(p,'我/-/-',0,1);before=p.to_dict();seen=[];original=ScoreLayout.draw
        def record(layout,*args,**kwargs):
            original(layout,*args,**kwargs);seen.extend(layout.melisma_paths)
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            with patch.object(ScoreLayout,'draw',record):export_pdf(p,Path(folder)/'slurs.pdf')
        self.assertEqual(len(seen),2);self.assertEqual(p.to_dict(),before)

    def test_example_has_slurs_skips_and_rap(self):
        p=Project.load('examples/lingfeng-melisma.lfs')
        self.assertFalse(matching_issues(p));self.assertEqual(len(entry.render(p).melisma_paths),6)
        self.assertTrue(any(e.get('skip') and not e.get('melisma') for e in events(p)))
        self.assertTrue(any(e.get('kind')=='rap_note' for e in events(p)))
        self.assertEqual(export_midi(p,None),Path('examples/lingfeng-melisma.mid').read_bytes())

    def test_tiny_large_font_and_forced_row_paths_follow_scaled_notes(self):
        from lingfeng.engraving.presentation import apply_forced_row
        for style in ('traditional','spatial','compact'):
            for size in (.1,4,12,26):
                p=song();p.notation.update(style=style,font_size=size)
                apply_range(p,'我/-/-\n/s/s/s/s/s/s/s你\n/-',0,3)
                paths=entry.render(p).melisma_paths
                self.assertEqual(len(paths),4)
                entry.EntryTieTests().assertDescendingLine(paths[-1][3])
        p=song();apply_range(p,'/s/s/s/s/s/s/s我\n/-',0,2);apply_forced_row(p,[0])
        self.assertEqual([k for _,_,k,_ in entry.render(p).melisma_paths],['outgoing','incoming'])

    def test_editor_commit_undo_redo_and_delete_refresh_current_score(self):
        from lingfeng.ui.main_window import MainWindow
        w=MainWindow(song());w.save_preferences=lambda:None;w.timer.stop();w.autosave.stop()
        try:
            w.switch_workspace('score');w.batch_lyrics();panel=w.lyric_panel;panel.count.setValue(1)
            panel.text.setPlainText('我/s/s');panel.commit();before=export_midi(w.project,None)
            panel.text.setPlainText('我/-/-');self.assertTrue(panel.check());panel.commit()
            self.assertEqual(len(entry.render(w.score_view.canvas.project).melisma_paths),2)
            self.assertIn('/- /-',panel.rhythm.topLevelItem(0).text(2))
            w.undo();self.assertEqual(panel.text.toPlainText(),'我/s/s');self.assertFalse(entry.render(w.score_view.canvas.project).melisma_paths)
            w.redo();self.assertEqual(panel.text.toPlainText(),'我/-/-')
            self.assertEqual(len(entry.render(w.score_view.canvas.project).melisma_paths),2);self.assertEqual(export_midi(w.project,None),before)
            panel.delete();self.assertFalse(entry.render(w.score_view.canvas.project).melisma_paths)
        finally:w.dirty=False;w.close();w.deleteLater();entry.APP.processEvents()

if __name__=='__main__':unittest.main()
