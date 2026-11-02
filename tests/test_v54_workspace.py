"""Strict source-melody Score entry and retained, inactive structure interfaces."""
import copy
from dataclasses import FrozenInstanceError
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPointF,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from lingfeng.music.model import Chord,Context,Measure,Note,Project
from lingfeng.music.onsets import group_onsets,is_monophonic,overlap_conflicts
from lingfeng.audio.midi import export_midi
from lingfeng.engraving.presentation import add_annotation,add_compression,visible_bars
from lingfeng.ui.main_window import MainWindow

APP=QApplication.instance() or QApplication([])


def song(notes=None):
    p=Project();p.notes=notes if notes is not None else [Note(0,960,60),Note(960,960,62)]
    p.notation.update(font_size=15,circles=False,lyrics=False)
    return p


class OnsetTests(unittest.TestCase):
    def test_grouped_original_attacks_keep_every_id_and_span_immutable(self):
        notes=[Note(480,960,67),Note(0,481,60),Note(480,240,64)]
        before=copy.deepcopy(notes);groups=group_onsets(iter(notes))
        self.assertEqual([g.tick for g in groups],[0,480])
        self.assertEqual([(n.note_id,n.start,n.end,n.pitch) for n in groups[1].notes],
            [(notes[2].id,480,720,64),(notes[0].id,480,1440,67)])
        with self.assertRaises(FrozenInstanceError):groups[0].notes[0].start=1
        self.assertEqual(notes,before)

    def test_half_open_boundaries_pass_and_one_tick_overlap_fails(self):
        a=Note(0,960,60);b=Note(960,960,62)
        self.assertTrue(is_monophonic([b,a]));self.assertTrue(is_monophonic([]))
        a.duration+=1;conflicts=overlap_conflicts([b,a])
        self.assertEqual([(c.start,c.end) for c in conflicts],[(960,961)])
        self.assertEqual({n.note_id for n in conflicts[0].notes},{a.id,b.id})
        self.assertEqual((conflicts[0].notes[0].start,conflicts[0].notes[0].end),(0,961))

    def test_nested_polyphony_reports_all_active_source_spans(self):
        notes=[Note(0,100,60),Note(10,80,64),Note(20,10,67),Note(100,100,72)]
        conflicts=overlap_conflicts(notes)
        self.assertEqual([(c.start,c.end,len(c.notes)) for c in conflicts],[(10,20,2),(20,30,3),(30,90,2)])
        self.assertEqual({n.note_id for n in conflicts[1].notes},{n.id for n in notes[:3]})


class ScoreEntryTests(unittest.TestCase):
    def setUp(self):
        self.save=patch.object(MainWindow,'save_preferences');self.save.start();self.addCleanup(self.save.stop)
        self.dialogs=[]
        def show(box):
            self.dialogs.append(dict(title=box.windowTitle(),text=box.text(),
                informative=box.informativeText(),details=box.detailedText()))
            return QMessageBox.StandardButton.Ok
        self.messages=patch.object(QMessageBox,'exec',show);self.messages.start();self.addCleanup(self.messages.stop)
        self.w=MainWindow(song());self.w.timer.stop();self.w.autosave.stop();self.w.change_language('zh',False)
        self.w.show();APP.processEvents();self.addCleanup(self.close)

    def close(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents()

    def test_adjacent_melody_and_polyphonic_harmony_are_allowed_without_music_changes(self):
        w=self.w;w.project.chords=[Chord(0,3840,notes=[Note(0,960,p)for p in (48,52,55)])]
        before=copy.deepcopy(w.project.to_dict());midi=export_midi(w.project,None)
        self.assertTrue(w.switch_workspace('score'));self.assertEqual(w.workspace,'score');self.assertFalse(self.dialogs)
        before['notation']['font_layout_version']=45
        self.assertEqual(w.project.to_dict(),before);self.assertEqual(export_midi(w.project,None),midi)

    def test_any_positive_original_overlap_blocks_all_styles_without_state_changes(self):
        w=self.w;w.project.notes[0].duration=961
        w.roll.selected_ids={w.project.notes[0].id};w.roll.selection=[[480,1440]];w.roll.setFocus();APP.processEvents()
        history=object();w.undo_history.append(history);w.dirty=True
        for style in ('traditional','spatial','compact'):
            with self.subTest(style=style):
                w.project.notation['style']=style;before=copy.deepcopy(w.project.to_dict());focus=APP.focusWidget()
                self.assertFalse(w.switch_workspace('score'));self.assertEqual(w.workspace,'compose')
                self.assertEqual(w.project.to_dict(),before);self.assertEqual(w.undo_history,[history]);self.assertTrue(w.dirty)
                self.assertEqual(w.roll.selected_ids,{w.project.notes[0].id});self.assertEqual(w.roll.selection,[[480,1440]])
                self.assertIs(APP.focusWidget(),focus);self.assertIsNone(w.score_view.canvas.layout)
                self.assertTrue(w.compose_button.isChecked());self.assertFalse(w.score_button.isChecked())
        self.assertEqual(len(self.dialogs),3)
        text=self.dialogs[-1]['informative']
        self.assertIn('第 1 小节',text);self.assertIn('第 2 拍',text);self.assertIn('960–961',text)
        for note in w.project.notes:self.assertIn(note.id,text);self.assertIn(str(note.pitch),text)

    def test_simultaneous_attacks_and_humanized_legato_are_not_tolerated(self):
        for notes in ([Note(0,320,60),Note(240,720,57)],
                      [Note(0,480,60),Note(0,480,64)],
                      [Note(0,480,60),Note(479,480,64)]):
            with self.subTest(notes=[(n.start,n.duration)for n in notes]):
                self.w.project.notes=notes
                self.assertFalse(self.w.switch_workspace('score'))
        self.assertEqual(len(self.dialogs),3)

    def test_score_button_and_lyrics_entry_each_show_one_diagnostic_without_losing_focus(self):
        w=self.w;w.project.notes[0].duration=961;w.roll.setFocus();APP.processEvents()
        focus=APP.focusWidget();QTest.mouseClick(w.score_button,Qt.MouseButton.LeftButton)
        self.assertEqual(w.workspace,'compose');self.assertIs(APP.focusWidget(),focus);self.assertEqual(len(self.dialogs),1)
        w.batch_lyrics();self.assertEqual(len(self.dialogs),2);self.assertEqual(w.workspace,'compose')

    def test_each_reentry_checks_live_music_instead_of_deferred_valid_snapshot(self):
        w=self.w;self.assertTrue(w.switch_workspace('score'));snapshot=w.score_view.canvas.project
        w.switch_workspace('compose');w.mutate('overlap',lambda p:setattr(p.notes[0],'duration',961))
        before=copy.deepcopy(w.project.to_dict());history=list(w.undo_history)
        self.assertFalse(w.switch_workspace('score'));self.assertIs(w.score_view.canvas.project,snapshot)
        self.assertEqual(w.project.to_dict(),before);self.assertEqual(w.undo_history,history);self.assertEqual(len(self.dialogs),1)
        w.mutate('fix',lambda p:setattr(p.notes[0],'duration',960))
        self.assertTrue(w.switch_workspace('score'));self.assertEqual(w.score_view.canvas.project.notes[0].duration,960)

    def test_replacement_from_score_loads_conflicting_file_in_compose_once(self):
        w=self.w;w.switch_workspace('score');p=song([Note(0,961,60),Note(960,480,64)])
        notes=copy.deepcopy(p.notes);w.replace_project(p)
        self.assertIs(w.project,p);self.assertEqual(w.project.notes,notes);self.assertEqual(w.workspace,'compose')
        self.assertIsNone(w.score_view.canvas.layout);self.assertEqual(len(self.dialogs),1)
        self.assertFalse(w.undo_history);self.assertFalse(w.dirty)

    def test_startup_and_mono_replacement_have_no_implicit_score_bypass(self):
        w=self.w;p=song([Note(0,481,60),Note(480,480,64)])
        w.replace_project(p);self.assertEqual(w.workspace,'compose');self.assertFalse(self.dialogs)
        self.assertFalse(w.switch_workspace('score'));self.assertEqual(len(self.dialogs),1)
        w.replace_project(song());self.assertTrue(w.switch_workspace('score'))
        w.replace_project(song([Note(0,1920,65)]));self.assertEqual(w.workspace,'score')
        self.assertEqual(w.score_view.canvas.project.notes[0].pitch,65);self.assertEqual(len(self.dialogs),1)

    def test_conflicting_startup_project_remains_in_compose_until_fixed(self):
        p=song([Note(0,961,60),Note(960,480,64)]);before=copy.deepcopy(p.notes)
        window=MainWindow(p);window.timer.stop();window.autosave.stop()
        try:
            self.assertEqual(window.workspace,'compose');self.assertIsNone(window.score_view.canvas.layout);self.assertFalse(self.dialogs)
            self.assertFalse(window.switch_workspace('score'));self.assertEqual(window.project.notes,before)
            self.assertEqual(len(self.dialogs),1)
        finally:window.dirty=False;window.close();window.deleteLater();APP.processEvents()

    def test_language_reentry_checks_original_music_once(self):
        w=self.w;w.switch_workspace('score');w.mutate('overlap',lambda p:setattr(p.notes[0],'duration',961))
        before=copy.deepcopy(w.project.to_dict());w.change_language('en',False)
        self.assertEqual(w.workspace,'compose');self.assertEqual(w.project.to_dict(),before);self.assertEqual(len(self.dialogs),1)

    def test_all_overlap_details_remain_available_without_an_override(self):
        w=self.w;w.project.notes=[Note(t,961,60+i)for i,t in enumerate(range(0,4800,960))]
        self.assertFalse(w.switch_workspace('score'));self.assertEqual(len(self.dialogs),1)
        self.assertIn('4',self.dialogs[0]['text']);self.assertIn('3840–3841',self.dialogs[0]['details'])
        for n in w.project.notes:self.assertIn(n.id,self.dialogs[0]['details'])

    def test_structure_entry_points_stay_hidden_after_language_and_stale_panel_state(self):
        w=self.w;w.switch_workspace('score')
        self.assertEqual(set(w.score_pages),{'melody','harmony','lyrics'});self.assertEqual(w.score_tabs.count(),3)
        self.assertFalse(w.logic_panel.isVisible());self.assertFalse(w.logic_panel.isEnabled())
        self.assertIsNone(w.show_score_panel('logic'));w.toggle_score_panel_floating('logic');w.set_score_panel_visible('logic',True)
        w.score_panel_state['logic']=dict(visible=True,floating=True);w.change_language('en',False)
        self.assertNotIn('logic',w.score_panel_state);self.assertNotIn('logic',w.score_view_actions)
        self.assertEqual(w.score_tabs.count(),3);self.assertFalse(w.logic_panel.isVisible())

    def test_structure_commands_are_inactive_but_existing_data_and_normal_rows_survive(self):
        w=self.w;p=w.project
        p.notes=[Note(i*3840,960,60)for i in range(8)];p.chords=[Chord(i*3840,3840)for i in range(8)]
        add_compression(p,list(range(8)),'repeat');add_annotation(p,'fine',7*3840,p.end)
        before=copy.deepcopy(p.to_dict());midi=export_midi(p,None);self.assertTrue(w.switch_workspace('score'))
        canvas=w.score_view.canvas;canvas.grab();self.assertEqual(visible_bars(w.project),list(range(4)))
        payload=dict(bars=[0,1],ranges=[[0,7680]],key=('compressions',0))
        for command in ('compress:repeat','symbol:segno','expand','clear_symbols','remove_structure'):w.score_command(command,payload)
        w.logic_panel.create_draft();w.logic_panel.commit();self.assertFalse(w.logic_panel.drafts)
        before['notation']['font_layout_version']=45;self.assertEqual(w.project.to_dict(),before);self.assertFalse(w.undo_history)
        self.assertEqual(export_midi(w.project,None),midi)
        page,rect,_=canvas.layout.hit_bars[0];x,y=canvas.page_origin(page)
        menu=canvas.context_menu(QPointF(x+rect.center().x()*canvas.scale,y+rect.center().y()*canvas.scale))
        labels={a.text()for a in menu.actions()}
        self.assertTrue({'强制合并为一行','恢复选区自动分行'}<=labels)
        self.assertFalse({'反复与跳转压缩','展开选区反复段落','添加谱面符号','清除选区符号','删除此符号并还原谱面'}&labels)


if __name__=='__main__':unittest.main()
