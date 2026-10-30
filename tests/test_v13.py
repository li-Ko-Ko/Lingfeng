import os,copy,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication,QDialog,QMenuBar
from PySide6.QtTest import QTest
from lingfeng.music.model import Project, Note, Chord, PPQ, QUALITIES
from lingfeng.engraving.lyrics import tokenize, bind, apply_section, events, matching_issues, sections, delete_section, put
from lingfeng.music.chord_operations import change_chords, quality_items, set_quality_order
from lingfeng.engraving.notation import ScoreLayout, fragments_for_bar
from lingfeng.audio.transport import Transport
from lingfeng.ui.main_window import MainWindow
from lingfeng.platform.i18n import set_language

APP=QApplication.instance() or QApplication([])

def draw(project):
    layout=ScoreLayout(project);image=QImage(900,1273,QImage.Format.Format_ARGB32);painter=QPainter(image);layout.draw(painter,0);painter.end();return layout,image


class LyricsTests(unittest.TestCase):
    def test_chinese_characters_english_hyphens_punctuation_and_single_skips(self):
        tokens=tokenize("我爱你，be-fore the _ street! 你好 world",syntax_version=2)
        self.assertEqual([t.text for t in tokens],['我','爱','你，','be','','fore','the','','street!','你','好','world'])
        self.assertFalse(tokens[3].join_next);self.assertTrue(tokens[4].skip);self.assertTrue(tokens[7].skip)
        self.assertEqual(len(tokenize('你 好我')),3)

    def test_rap_duration_parser_and_invalid_denominators(self):
        tokens=tokenize('我/64.爱/64你/64')
        self.assertEqual([(t.text,t.duration) for t in tokens],[('我',90),('爱',60),('你',60)])
        for text in ('我/0','我/3','我/256','_/64','我/abc','/64'):
            with self.assertRaises(ValueError):tokenize(text)

    def test_unique_onsets_only_ignore_durations_and_simultaneous_voices(self):
        p=Project();p.notes=[Note(0,1500,60),Note(0,480,64),Note(960,240,62),Note(1920,480,65)]
        result=bind(p,'你 _ 好',0)
        self.assertEqual([e['tick'] for e in result],[0,960,1920]);self.assertEqual([e['kind'] for e in result],['note','skip','note'])
        with self.assertRaisesRegex(ValueError,'第 4'):bind(p,'你我大家',0)
        self.assertEqual(bind(p,'好',240)[0]['tick'],960)

    def test_rap_creates_explicit_unpitched_onsets_without_pitched_midi(self):
        p=Project();apply_section(p,'我/64.爱/64你/64',0)
        self.assertEqual([(e['tick'],e['duration']) for e in events(p)],[(0,90),(90,60),(150,60)])
        self.assertEqual(p.notes,[]);self.assertEqual(matching_issues(p),[])
        for style in ('traditional','spatial','compact'):
            p.notation['style']=style;layout,_=draw(p)
            self.assertEqual([t for t,k,x,y in layout.unpitched_positions if k=='x'],[0,90,150])
        from lingfeng.audio.midi import event_list
        self.assertEqual(event_list(p),[])

    def test_missing_onset_detected_even_if_a_note_is_sustained(self):
        p=Project();p.notes=[Note(0,1920,60)];put(p,480,'错')
        self.assertTrue(matching_issues(p));self.assertFalse(any(f.ghost for f in fragments_for_bar(p,0,events(p))))

    def test_apply_is_atomic_and_does_not_touch_notes(self):
        p=Project();p.notes=[Note(0,480,60),Note(960,480,62)];original=copy.deepcopy(p.notes)
        ident=apply_section(p,'你 好',0);self.assertEqual(p.notes,original);before=p.to_dict()
        with self.assertRaises(ValueError):apply_section(p,'你 好 呀',0,section_id=ident)
        self.assertEqual(p.to_dict(),before)
        apply_section(p,'世 界',0,section_id=ident);self.assertEqual([e['text'] for e in events(p)],['世','界'])
        delete_section(p,ident);self.assertFalse(events(p))

    def test_sections_overlap_checked_and_stanzas_supported(self):
        p=Project();p.notes=[Note(0,480,60)];apply_section(p,'风',0)
        with self.assertRaises(ValueError):apply_section(p,'云',0)
        apply_section(p,'云',0,1);self.assertFalse(matching_issues(p));self.assertEqual(len(sections(p)),2)

    def test_save_load_and_midi_replacement_preserve_lyrics_then_flag_mismatch(self):
        p=Project();p.notes=[Note(0,480,60)];apply_section(p,'风',0)
        with tempfile.TemporaryDirectory(dir=Path('tmp').resolve()) as folder:
            file=Path(folder)/'lyric.lfs';p.save(file);q=Project.load(file);self.assertEqual(sections(q),sections(p))
        from lingfeng.audio.midi_import import MidiData, MidiTrack, apply_midi
        before=events(p);apply_midi(p,MidiData([MidiTrack('track',[Note(480,480,62)],1920)],[],[]),[0],'melody',0)
        self.assertEqual(events(p),before);self.assertTrue(matching_issues(p))

    def test_rap_and_section_positions_follow_inserted_bars_and_meter(self):
        p=Project();ident=apply_section(p,'风/4',3600);p.insert_measure(1)
        self.assertEqual([(e['tick'],e['duration'],e['text']) for e in events(p)],[(3600,240,'风'),(7680,720,'')])
        self.assertEqual(sections(p)[0]['start'],3600);self.assertFalse(matching_issues(p))
        q=Project();apply_section(q,'云/4',4000);q.insert_measure(0)
        self.assertEqual(sections(q)[0]['start'],7840);q.change_meter(0,3,4)
        self.assertEqual(sections(q)[0]['start'],6880);self.assertEqual(events(q)[0]['tick'],6880)
        with self.assertRaises(ValueError):p.change_meter(0,3,4)

    def test_lyric_metadata_validation_and_apostrophe(self):
        self.assertEqual([t.text for t in tokenize('don’t stop')],['don’t','stop'])
        p=Project();apply_section(p,'风/4',0);p.notation['lyric_sections'][0]['start']=-1
        with self.assertRaises(ValueError):p.validate()


class ScoreTests(unittest.TestCase):
    def test_traditional_rests_fill_every_beat_including_leading_and_full_bar(self):
        p=Project();p.notes=[Note(1920,960,60)];p.notation['style']='traditional';layout,_=draw(p)
        self.assertEqual([t for t,pitch,x,y in layout.rest_positions if t<3840],[0,960,2880])
        self.assertEqual([t for t,pitch,x,y in layout.rest_positions if 3840<=t<7680],[3840,4800,5760,6720])
        self.assertTrue(all(f.duration<=960 for f in fragments_for_bar(p,1)))

    def test_zero_and_x_share_center_in_spatial_and_compact(self):
        p=Project();p.notes=[Note(1920,480,72),Note(2880,480,48)];apply_section(p,'说/4',0)
        for style in ('spatial','compact'):
            p.notation['style']=style;layout,_=draw(p);s=layout.systems[0]
            rows=[(kind,y) for t,kind,x,y in layout.unpitched_positions if t<3840]
            self.assertTrue(any(k=='x' for k,y in rows));self.assertTrue(any(k=='0' for k,y in rows))
            self.assertEqual(len({round(y,5) for k,y in rows}),1)

    def test_anchor_lines_default_and_optional_scale_lines(self):
        p=Project();p.notes=[Note(0,480,60),Note(960,480,67)]
        a,image=draw(p);p.notation['show_scale_lines']=True;b,other=draw(p)
        self.assertNotEqual(image,other);self.assertEqual(a.systems[0].pitches,b.systems[0].pitches)

    def test_digits_accidentals_and_dots_fit_dense_beat_and_bar_slots(self):
        p=Project();p.notation.update(style='traditional',font_size=26,per_line=8)
        p.notes=[Note(i*3840+3570,270,61) for i in range(8)]+[Note(i*3840+90,90,66) for i in range(8)]
        layout,_=draw(p)
        self.assertTrue(layout.symbol_boxes)
        for start,end,left,right,a,b in layout.symbol_boxes:
            self.assertGreaterEqual(left,a-1e-6);self.assertLessEqual(right,b+1e-6)


class ChordTests(unittest.TestCase):
    def test_root_preserves_pattern_and_transposes_custom_notes(self):
        p=Project();c=Chord(0,3840,48,pattern='up');p.chords=[c];change_chords(p,{c.id},'root:2')
        self.assertEqual((c.root,c.pattern),(50,'up'));c.materialize();before=[n.pitch for n in c.notes]
        change_chords(p,{c.id},'root:3');self.assertEqual([n.pitch for n in c.notes],[n+1 for n in before])

    def test_inversions_change_bass_keep_root_and_custom_onsets(self):
        for custom in (False,True):
            p=Project();c=Chord(0,3840,48,'7');p.chords=[c]
            if custom:c.materialize()
            times={n.start for n in c.render_notes()}
            change_chords(p,{c.id},'inversion:1');self.assertEqual(c.root,48);self.assertEqual(min(n.pitch for n in c.render_notes())%12,4)
            self.assertEqual({n.start for n in c.render_notes()},times);p.validate()

    def test_extended_quality_and_user_order(self):
        p=Project();c=Chord(0,3840,notes=[Note(0,960,48),Note(0,960,52),Note(0,960,55)]);p.chords=[c]
        change_chords(p,{c.id},'quality:maj9');self.assertEqual(c.pcs,{0,2,4,7,11});p.validate()
        set_quality_order(['m9','7','m9','bad']);self.assertEqual([q for q,label in quality_items()][:2],['m9','7']);self.assertEqual(len(quality_items()),len(QUALITIES));set_quality_order([])


class AudioTests(unittest.TestCase):
    def test_new_audition_interrupts_prior_preview_without_waiting(self):
        class Synth:
            def __init__(self):self.events=[]
            def send(self,*args):self.events.append(args)
        t=Transport();t.synth=Synth();callbacks=[]
        with patch('lingfeng.audio.transport.QTimer.singleShot',side_effect=lambda ms,obj,fn:callbacks.append((ms,fn))):
            t.audition([60]);t.begin_audition([64],True);last=len(t.synth.events)
            self.assertIn((0x82,60),t.synth.events);self.assertEqual(t.synth.events[-1],(0x93,64,80));callbacks[0][1]();self.assertEqual(len(t.synth.events),last)
        t.synth=None

    def test_chord_audition_preserves_offsets_durations_velocity_and_cancels_timers(self):
        class Synth:
            def __init__(self):self.events=[]
            def send(self,*args):self.events.append(args)
        t=Transport();t.synth=Synth();callbacks=[];c=Chord(1920,1920,notes=[Note(0,240,60,45),Note(480,320,64,99)])
        with patch('lingfeng.audio.transport.QTimer.singleShot',side_effect=lambda ms,obj,fn:callbacks.append((ms,fn))):t.begin_chord_audition(c,120)
        self.assertEqual(t.synth.events,[(0x93,60,45)]);self.assertEqual([ms for ms,fn in callbacks],[125,250,417])
        callbacks[0][1]();callbacks[1][1]();self.assertEqual(t.synth.events[-2:],[(0x83,60),(0x93,64,99)])
        t.begin_audition([67]);count=len(t.synth.events);callbacks[2][1]();self.assertEqual(len(t.synth.events),count);t.synth=None


class WindowTests(unittest.TestCase):
    def setUp(self):
        set_language('zh');self.w=MainWindow(Project());self.w.show();self.w.timer.stop();self.w.autosave.stop();QTest.qWait(25)
    def tearDown(self):self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();set_language('zh')

    def test_brand_and_commands_share_font_baseline_in_both_languages(self):
        w=self.w
        for language in ('zh','en'):
            w.change_language(language,False);APP.processEvents();menu=w.title_bar.menu;actions=menu.actions()
            self.assertIs(actions[0],w.title_bar.brand);self.assertTrue(menu.font().bold())
            rects=[menu.actionGeometry(a) for a in actions];self.assertEqual(len({(r.y(),r.height()) for r in rects}),1)

    def test_seek_preserves_playing_or_paused_state_and_updates_anchor(self):
        w=self.w
        class Fake:
            playing=False
            def play(self,project,start,end,loop,**kw):self.playing=True;self.start=start
            def stop(self,**kw):self.playing=False
            def close(self):pass
        w.transport.close();w.transport=Fake();w.seek(960);self.assertFalse(w.transport.playing)
        w.transport.playing=True;w.seek(1920);self.assertTrue(w.transport.playing);self.assertEqual(w.transport.start,1920);self.assertEqual(w.roll.anchor_tick,1920)
        w.return_to_start();self.assertFalse(w.transport.playing);self.assertEqual(w.playhead,0)

    def test_score_switch_does_not_gate_unmatched_lyrics(self):
        w=self.w;put(w.project,240,'错');w.refresh()
        with patch('lingfeng.ui.lyric_panel.LyricsGateDialog.exec') as gate:
            self.assertTrue(w.switch_workspace('score'));gate.assert_not_called()
        self.assertEqual(w.workspace,'score');self.assertTrue(matching_issues(w.project))
        self.assertEqual(w.score_tabs.count(),4)

    def test_lyrics_tab_commit_unique_onsets_undo_and_rap_only_input(self):
        w=self.w;w.switch_workspace('score');w.batch_lyrics();self.assertIs(w.score_tabs.currentWidget(),w.lyric_panel)
        panel=w.lyric_panel;panel.text.setPlainText('你/64.好/64');self.assertTrue(panel.check());panel.commit()
        self.assertEqual([e['tick'] for e in events(w.project)],[0,90]);self.assertFalse(w.project.notes);w.undo();self.assertFalse(events(w.project))

    def test_root_quality_inversion_menus_and_preference_controls(self):
        w=self.w;c=Chord(0,3840);w.project.chords=[c];w.refresh();menu=w.chord_lane.context_menu(QPoint(round(w.chord_lane.x_at(240)),20))
        menus={a.text():a.menu() for a in menu.actions() if a.menu()}
        self.assertEqual(len(menus['和弦根音'].actions()),12);self.assertEqual(len(menus['和弦性质'].actions()),len(QUALITIES));self.assertEqual(len(menus['替换低音'].actions()),12)
        from lingfeng.ui.dialogs import ChordPreferenceDialog
        d=ChordPreferenceDialog(w);d.list.setCurrentRow(1);d.move_item(-1);self.assertEqual(d.value()[0],'m');d.close()

    def test_lyric_draft_survives_language_but_not_project_replacement(self):
        w=self.w;w.switch_workspace('score');w.lyric_panel.start.setValue(2);w.lyric_panel.text.setPlainText('风/64.云/64')
        w.change_language('en',False);self.assertEqual(w.lyric_panel.text.toPlainText(),'风/64.云/64');self.assertEqual(w.lyric_panel.start.value(),2);self.assertTrue(w.lyric_panel.dirty)
        w.replace_project(Project());self.assertEqual(w.lyric_panel.text.toPlainText(),'');self.assertFalse(w.lyric_panel.dirty)


if __name__=='__main__':unittest.main()
