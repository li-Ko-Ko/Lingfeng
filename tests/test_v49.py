"""Partial lyric entry, invisible skips, and notation-only rap over MIDI notes."""
import copy,os,tempfile,unittest
from pathlib import Path
from zipfile import ZipFile
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter
from lingfeng.music.model import Project, Note
from lingfeng.engraving.lyrics import tokenize, apply_range, plan_range, events, sections, matching_issues, delete_section, edit_lyric_track
from lingfeng.engraving.notation import ScoreLayout, PAPER_W, PAPER_H
from lingfeng.audio.midi import event_list, export_daw_bundle, export_midi
from lingfeng.ui.main_window import MainWindow
from tests.test_music import read_midi

APP=QApplication.instance() or QApplication([])

def song():
    p=Project();p.notes=[Note(i*480,480,60+i,70+i) for i in range(8)]
    p.notation.update(style='traditional',font_size=12,font_layout_version=45,circles=False)
    return p

def draw(p):
    layout=ScoreLayout(p);image=QImage(PAPER_W,PAPER_H,QImage.Format.Format_RGB32);image.fill(0xffffffff)
    painter=QPainter(image);layout.draw(painter,0);painter.end()
    return layout,image

class LyricRulesTests(unittest.TestCase):
    def test_abc_melisma_and_legacy_skips_consume_onsets(self):
        tokens=tokenize('我/s/s你 _ rapper')
        self.assertEqual([t.text for t in tokens],['我','','','你','','rapper'])
        self.assertEqual([t.skip for t in tokens],[False,True,True,False,True,False])
        self.assertEqual([t.melisma for t in tokens],[False,False,False,False,True,False])
        self.assertFalse(any(t.join_next for t in tokens))
        p=song();apply_range(p,'我/s/s你',0,1)
        self.assertEqual([e['tick'] for e in events(p)],[0,480,960,1440])

    def test_partial_ranges_and_unfilled_template_slots(self):
        p=song();self.assertFalse(plan_range(p,'春风',0,4).issues)
        self.assertFalse(plan_range(p,'春 | ',0,4).issues)
        apply_range(p,'春 & 风 & & & & &',0,1)
        self.assertEqual([(e['tick'],e['text']) for e in events(p)],[(0,'春'),(960,'风')])
        p.notes.append(Note(240,120,72));self.assertEqual(matching_issues(p),[])
        before=p.to_dict()
        for text in ('一二三四五六七八九','春 | 风','&'*9):
            with self.assertRaises(ValueError):apply_range(p,text,0,1)
            self.assertEqual(p.to_dict(),before)
        self.assertTrue(plan_range(p,'&&&&&&&&',0,1).issues)

    def test_rap_groups_mixed_with_singing_and_skips(self):
        p=song();before=event_list(p);notes=copy.deepcopy(p.notes)
        ident=apply_range(p,'唱/x{我是一个rapper}/s尾',0,1)
        self.assertEqual([e['kind'] for e in events(p)],['note']+['rap_note']*5+['skip','note'])
        self.assertEqual(event_list(p),before);self.assertEqual(p.notes,notes);p.validate()
        self.assertEqual(matching_issues(p),[])
        delete_section(p,ident);self.assertEqual(event_list(p),before)
        self.assertFalse(events(p))

    def test_invalid_rap_is_atomic_and_note_onsets_are_required(self):
        p=song();before=p.to_dict()
        for text in ('/x{我','/x{}','/x{/x{我}}','/x{我/4}','/x{一二三四五六七八九}'):
            with self.assertRaises(ValueError):apply_range(p,text,0,1)
            self.assertEqual(p.to_dict(),before)
        self.assertTrue(plan_range(Project(),'/x{我}',0,1).issues)

    def test_old_section_source_migrates_without_rebinding_existing_events(self):
        p=song();apply_range(p,'be fore/sdawn',0,1)
        section=p.notation['lyric_sections'][0];section.pop('syntax_version');section['text']='be-fore _ dawn'
        before=p.to_dict();loaded=sections(p)[0]
        self.assertEqual(loaded['text'],'be fore*dawn');self.assertEqual(p.to_dict(),before)
        apply_range(p,loaded['text'],0,1,section_id=loaded['id'])
        self.assertEqual([(e['tick'],e['text']) for e in events(p)],[(0,'be'),(480,'fore'),(960,''),(1440,'dawn')])
        self.assertEqual(sections(p)[0]['text'],'be fore*dawn')

    def test_save_load_retains_new_syntax_and_rap_midi(self):
        p=song();apply_range(p,'/x{我/s你}唱',0,1)
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            file=Path(folder)/'rap.lfs';p.save(file);q=Project.load(file)
        self.assertEqual(sections(q),sections(p));self.assertEqual(events(q),events(p));self.assertEqual(event_list(q),event_list(p))

    def test_midi_and_daw_omit_both_rap_lyric_kinds_but_keep_pitches(self):
        p=song();p.instrument_notes=[Note(0,480,72),Note(480,480,74)]
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            plain=Path(folder)/'plain.mid';rap=Path(folder)/'rap.mid';export_midi(p,plain)
            apply_range(p,r'唱 \x{Rap} Timed/8 尾',0,1)
            edit_lyric_track(p,1,lambda track:apply_range(track,r'\x{Speak} 器',0,1))
            export_midi(p,rap)
            before=read_midi(plain)[2];after=read_midi(rap)[2]
            self.assertEqual([[e for e in track if e[1]!=255] for track in after],
                             [[e for e in track if e[1]!=255] for track in before])
            def lyrics(track):return [(e[0],e[3].decode()) for e in track if e[1:3]==(255,5)]
            self.assertEqual([lyrics(track) for track in after],[[],[(0,'唱'),(1440,'尾')],[],[(480,'器')]])
            bundle=Path(folder)/'daw.zip';export_daw_bundle(p,bundle)
            with ZipFile(bundle) as archive:
                self.assertEqual(archive.read('00_Full.mid'),rap.read_bytes())
                for filename,expected in [('01_Melody.mid',[(0,'唱'),(1440,'尾')]),('03_Instrument.mid',[(480,'器')])]:
                    rap.write_bytes(archive.read(filename))
                    self.assertEqual(lyrics(read_midi(rap)[2][1]),expected)

class LyricRenderingTests(unittest.TestCase):
    def test_skip_never_draws_text_or_melisma_lines_in_any_style(self):
        for style in ('traditional','spatial','compact'):
            p=song();p.notation['style']=style;apply_range(p,'风 /s *',0,1)
            layout,image=draw(p);q=copy.deepcopy(p)
            q.notation['lyric_events']=[e for e in events(q) if not e.get('skip')]
            plain,without_skips=draw(q)
            self.assertEqual(len(layout.lyric_positions),1);self.assertEqual(image,without_skips)
            p.notes[3].lyric='_';self.assertEqual(len(draw(p)[0].lyric_positions),1)

    def test_rap_replaces_digits_once_per_onset_and_shares_zero_center(self):
        for style in ('traditional','spatial','compact'):
            p=song();p.notation['style']=style;p.notes.append(Note(480,240,84))
            before=event_list(p);apply_range(p,'唱/x{我是一个rapper}',0,1);layout,_=draw(p)
            fragments=layout.systems[0].fragments[0]
            for tick in range(480,2880,480):
                here=[f for f in fragments if f.start==tick]
                self.assertEqual(len(here),1);self.assertTrue(here[0].ghost);self.assertIsNone(here[0].pitch)
            xs=[(t,y) for t,kind,x,y in layout.unpitched_positions if kind=='x']
            zeros=[y for t,kind,x,y in layout.unpitched_positions if kind=='0']
            self.assertEqual(len(xs),5);self.assertTrue(zeros)
            self.assertTrue(all(y==zeros[0] for t,y in xs));self.assertEqual(event_list(p),before)
            self.assertTrue({n.id for n in p.notes if n.start==480}<={ident for page,rect,ident in layout.hit_notes})

    def test_rap_across_barline_keeps_duration_and_delete_restores_digits(self):
        p=Project();p.notes=[Note(3600,960,72)];p.notation['style']='traditional'
        ident=apply_range(p,'/x{嘿}',0,1);layout,_=draw(p)
        self.assertTrue(all(f.ghost for s in layout.systems for fs in s.fragments.values() for f in fs if 3600<=f.start<4560))
        delete_section(p,ident);self.assertFalse(any(f.ghost for s in ScoreLayout(p).systems for fs in s.fragments.values() for f in fs))

    def test_panel_commit_undo_and_redo_refresh_rap_without_switching_modes(self):
        w=MainWindow(song());w.timer.stop();w.autosave.stop();w.show();w.switch_workspace('score');w.show_score_panel('lyrics')
        try:
            panel=w.lyric_panel;panel.count.setValue(1);panel.text.setPlainText('/x{我}/s唱');self.assertTrue(panel.check());panel.commit()
            self.assertTrue(w.score_view.canvas.layout.systems[0].fragments[0][0].ghost)
            w.undo();self.assertFalse(w.score_view.canvas.layout.systems[0].fragments[0][0].ghost)
            w.redo();self.assertTrue(w.score_view.canvas.layout.systems[0].fragments[0][0].ghost)
            panel.section.setCurrentIndex(1);panel.text.setPlainText('我/s唱');panel.commit();self.assertFalse(w.score_view.canvas.layout.systems[0].fragments[0][0].ghost)
        finally:w.dirty=False;w.close();w.deleteLater();APP.processEvents()

if __name__=='__main__':unittest.main()
