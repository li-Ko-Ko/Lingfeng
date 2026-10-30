"""Editing shortcuts across windows, undo destinations and score typography."""
import copy,json,os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication,QLineEdit
from PySide6.QtTest import QTest
from lingfeng.ui.main_window import MainWindow
from lingfeng.music.model import Project, Note, Chord
from lingfeng.ui.help_dialog import HelpDialog, ABOUT_ZH, ABOUT_EN
from lingfeng.ui.history import HistoryState

APP=QApplication.instance() or QApplication([])
CTRL=Qt.KeyboardModifier.ControlModifier
SYSTEM_TEXT_CLIPBOARD_AVAILABLE=None

class EditorHistoryTests(unittest.TestCase):
    def setUp(self):
        self.save=patch.object(MainWindow,'save_preferences');self.save.start()
        p=Project();p.notes=[Note(0,480,60),Note(960,480,64)]
        p.chords=[Chord(0,3840,notes=[Note(0,960,48),Note(960,960,52)]),Chord(3840,3840,55)]
        self.w=MainWindow(p);self.w.change_language('zh',False);self.w.show();self.w.resize(1200,850)
        self.w.timer.stop();self.w.autosave.stop();self.w.open_harmony()
        for b in self.w.mute_buttons.values():b.setChecked(True)
        self.w.melody_window.setFloating(True);self.w.harmony_window.setFloating(True)
        QTest.qWait(20)
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.save.stop()
    def focus(self,role):
        pane=self.w.melody_window if role=='melody' else self.w.harmony_window
        roll=self.w.roll if role=='melody' else pane.roll
        pane.show();pane.raise_();pane.activateWindow();roll.setFocus();QTest.qWait(15)
        return roll
    def select(self,r):
        self.w.select_element('notes',r);r.selected_ids={r.notes[0].id};r.refresh()
    def key(self,r,key,mods=CTRL):QTest.keyClick(r,key,mods);APP.processEvents()
    def edit(self,role):
        r=self.focus(role);self.select(r);self.w.note_command(r,'chromatic:1');return r

    def test_copy_paste_cut_all_and_history_in_each_floating_roll(self):
        for role in ('melody','harmony'):
            with self.subTest(role=role):
                r=self.focus(role);self.select(r);original=copy.deepcopy(r.notes[0]);before=self.w.project.to_dict()
                self.key(r,Qt.Key.Key_C);self.assertEqual(self.w.clipboard_kind,'notes')
                self.assertEqual(self.w.note_clipboard.paste(self.w.project,1920)[0].pitch,original.pitch)
                r.cursor_tick=1920;r.anchor_tick=None;n=len(self.w.undo_history)
                self.key(r,Qt.Key.Key_V);self.assertEqual(len(self.w.undo_history),n+1)
                self.assertTrue(any(x.start==1920 and x.pitch==original.pitch for x in r.notes))
                pasted=self.w.project.to_dict();self.key(r,Qt.Key.Key_Z)
                self.assertEqual(self.w.project.to_dict(),before);self.assertEqual(len(self.w.undo_history),n)
                self.key(r,Qt.Key.Key_Y);self.assertEqual(self.w.project.to_dict(),pasted)
                self.key(r,Qt.Key.Key_Z);self.key(r,Qt.Key.Key_Z,CTRL|Qt.KeyboardModifier.ShiftModifier)
                self.assertEqual(self.w.project.to_dict(),pasted)
                self.select(r);self.key(r,Qt.Key.Key_X)
                self.assertFalse(any(x.id==original.id for x in r.notes));self.key(r,Qt.Key.Key_Z)
                self.assertTrue(any(x.id==original.id for x in r.notes))
                self.key(r,Qt.Key.Key_A);self.assertEqual(r.selected_ids,{x.id for x in r.notes})

    def test_marquee_then_copy_in_floating_melody(self):
        r=self.focus('melody');r.center_pitch(62);r.tool='smart';QTest.qWait(20)
        start=QPoint(round(r.x_at(0)+1),max(r.ruler_height+2,round(r.y_at(67)+2)))
        end=QPoint(round(r.x_at(1680)),round(r.y_at(58)+r.row_height-2))
        QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(r.viewport(),end,50);QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=end)
        APP.processEvents();self.assertEqual(r.selected_ids,{n.id for n in self.w.project.notes})
        self.key(r,Qt.Key.Key_C);self.assertEqual(len(self.w.note_clipboard.paste(self.w.project,0)),2)

    def test_toolbar_focus_retains_floating_edit_target(self):
        r=self.focus('harmony');self.select(r)
        button=self.w.harmony_window.transport_controls.play;button.setFocus();APP.processEvents()
        self.key(button,Qt.Key.Key_C);self.assertEqual(self.w.note_clipboard.paste(self.w.project,0)[0].pitch,48)
        with patch.object(self.w,'save') as save:
            self.key(button,Qt.Key.Key_S);save.assert_called_once_with()
            save.reset_mock();self.key(button,Qt.Key.Key_S,CTRL|Qt.KeyboardModifier.ShiftModifier);save.assert_called_once_with(True)

    def test_undo_and_redo_activate_operation_window(self):
        self.edit('melody');self.edit('harmony');r=self.focus('melody')
        self.key(r,Qt.Key.Key_Z);self.assertIs(APP.activeWindow(),self.w.harmony_window)
        self.assertEqual(self.w.project.harmony_notes()[0].pitch,48)
        self.key(self.w.harmony_window.roll,Qt.Key.Key_Z);self.assertIs(APP.activeWindow(),self.w.melody_window)
        self.assertEqual(self.w.project.notes[0].pitch,60)
        self.key(self.w.roll,Qt.Key.Key_Y);self.assertIs(APP.activeWindow(),self.w.melody_window)
        self.key(self.w.roll,Qt.Key.Key_Y);self.assertIs(APP.activeWindow(),self.w.harmony_window)

    def test_undo_reveals_hidden_editor_in_current_dock_location(self):
        self.edit('harmony');w=self.w;w.harmony_window.setFloating(False)
        w.visibility_actions['harmony'].setChecked(False);self.focus('melody');self.key(w.roll,Qt.Key.Key_Z)
        self.assertFalse(w.harmony_window.isFloating());self.assertTrue(w.visibility_actions['harmony'].isChecked())
        self.assertIs(APP.activeWindow(),w);self.assertIs(w.active_roll(),w.harmony_window.roll)

    def test_undo_switches_back_from_score_to_compose_window(self):
        self.edit('harmony');w=self.w;w.switch_workspace('score');w.activateWindow();w.score_view.canvas.setFocus();APP.processEvents()
        self.key(w.score_view.canvas,Qt.Key.Key_Z);self.assertEqual(w.workspace,'compose')
        self.assertIs(APP.activeWindow(),w.harmony_window)

    def test_score_editor_tab_and_floating_score_tools_history(self):
        w=self.w;w.switch_workspace('score');w.open_score_roll('chords',0);w.toggle_score_panel_floating('harmony')
        w.score_floats['harmony'].show();w.score_floats['harmony'].activateWindow();r=w.harmony_window.roll;r.setFocus();APP.processEvents()
        self.select(r);w.note_command(r,'chromatic:1');w.score_tabs.setCurrentIndex(0);w.roll.setFocus()
        self.key(w.roll,Qt.Key.Key_Z);self.assertTrue(w.score_floats['harmony'].isVisible());self.assertIs(APP.activeWindow(),w.score_floats['harmony'])
        self.key(r,Qt.Key.Key_C);self.assertEqual(w.note_clipboard.paste(w.project,0)[0].pitch,48)

    def test_text_input_keeps_native_clipboard_and_undo(self):
        class TextField(QLineEdit):
            copy_keys=0
            def keyPressEvent(self,event):
                if event.matches(QKeySequence.StandardKey.Copy):self.copy_keys+=1
                super().keyPressEvent(event)
        self.edit('melody');w=self.w;field=TextField(w.melody_window);w.melody_window.box.addWidget(field)
        field.show();APP.processEvents();field.setFocus();QTest.qWait(15);self.assertIs(APP.focusWidget(),field)
        QTest.keyClicks(field,'lyrics');field.selectAll();APP.processEvents();count=len(w.undo_history)
        # Some test hosts cannot access the Windows clipboard, even with direct
        # QLineEdit.copy(). Still verify that Qt receives the key, not our editor.
        global SYSTEM_TEXT_CLIPBOARD_AVAILABLE
        field.copy();APP.processEvents();SYSTEM_TEXT_CLIPBOARD_AVAILABLE=APP.clipboard().text()=='lyrics'
        self.key(field,Qt.Key.Key_C);self.assertEqual(field.copy_keys,1);self.assertIsNone(w.note_clipboard)
        if SYSTEM_TEXT_CLIPBOARD_AVAILABLE:self.assertEqual(APP.clipboard().text(),'lyrics')
        self.key(field,Qt.Key.Key_X);self.assertEqual(field.text(),'');self.key(field,Qt.Key.Key_Z)
        self.assertEqual(field.text(),'lyrics');self.assertEqual(len(w.undo_history),count)

    def test_chord_clipboard_and_undo_use_chord_window(self):
        w=self.w;r=self.focus('harmony');cid=w.project.chords[0].id;w.chord_selection({cid},r)
        r.lane.setFocus();APP.processEvents();self.key(r.lane,Qt.Key.Key_C);self.assertEqual(w.clipboard_kind,'chords')
        r.cursor_tick=7680;r.anchor_tick=None;before=w.project.to_dict();self.key(r.lane,Qt.Key.Key_V)
        self.assertTrue(any(c.start==7680 for c in w.project.chords));self.focus('melody');self.key(w.roll,Qt.Key.Key_Z)
        self.assertEqual(w.project.to_dict(),before);self.assertIs(APP.activeWindow(),w.harmony_window)

    def test_history_metadata_is_session_only_and_survives_language_rebuild(self):
        self.edit('harmony');w=self.w;s=w.undo_history[-1];self.assertIsInstance(s,HistoryState)
        self.assertNotIn('location',json.loads(json.dumps(s)));w.change_language('en',False);APP.processEvents()
        self.focus('melody');self.key(w.roll,Qt.Key.Key_Z);self.assertIs(APP.activeWindow(),w.harmony_window)
        self.assertEqual(w.project.harmony_notes()[0].pitch,48)

    def test_score_font_toolbar_changes_glyph_size_independently_and_undo_returns_to_score(self):
        w=self.w;w.switch_workspace('score');APP.processEvents()
        self.assertTrue(w.note_font.isVisible());gap=w.project.notation['row_gap'];old=w.project.notation['font_size']
        w.note_font.setValue(old+3);self.assertEqual(w.project.notation['font_size'],old+3)
        self.assertEqual(w.project.notation['row_gap'],gap);self.assertEqual(w.score_view.canvas.layout.glyph_scale,(old+3)/15)
        w.switch_workspace('compose');self.focus('melody');self.key(w.roll,Qt.Key.Key_Z)
        self.assertEqual(w.workspace,'score');self.assertEqual(w.note_font.value(),old)

    def test_about_has_matching_localized_computer_and_lightweight_information(self):
        for lang,words in [('zh',('轻量级','鼠标','离线','MIDI','名字的由来')),('en',('lightweight','mouse','offline','MIDI','Behind the name'))]:
            self.w.change_language(lang,False);dialog=HelpDialog(self.w,True);text=dialog.browser.toPlainText()
            for word in words:self.assertIn(word,text)
            self.assertEqual((ABOUT_ZH if lang=='zh' else ABOUT_EN).count('<li>'),3)
            if lang=='en':self.assertNotIn('轻量级',text)
            else:self.assertNotIn('free from mystique',text)
            dialog.deleteLater()

    def test_main_toolbar_retains_last_docked_harmony_target(self):
        w=self.w;w.melody_window.setFloating(False);w.harmony_window.setFloating(False)
        w.activateWindow();r=w.harmony_window.roll;r.setFocus();APP.processEvents();self.select(r)
        w.play_button.setFocus();APP.processEvents();self.key(w.play_button,Qt.Key.Key_C)
        self.assertEqual(w.note_clipboard.paste(w.project,0)[0].pitch,48)

    def test_undo_window_switch_keeps_playback_thread_and_position_anchor(self):
        class Synth:
            def send(self,*args):pass
            def stop(self):pass
            def close(self):pass
        w=self.w;w.transport.close();w.transport.synth=Synth();w.toggle_play();QTest.qWait(20)
        worker=w.transport.thread;anchor=w.play_anchor;self.edit('harmony');self.focus('melody')
        self.key(w.roll,Qt.Key.Key_Z);self.assertTrue(w.transport.playing);self.assertIs(w.transport.thread,worker)
        self.assertEqual(w.play_anchor,anchor);self.assertIs(APP.activeWindow(),w.harmony_window)
        self.key(w.harmony_window.roll,Qt.Key.Key_Y);self.assertTrue(w.transport.playing);self.assertIs(w.transport.thread,worker)
        w.stop()

    def test_score_select_all_respects_measure_or_beat_mode(self):
        w=self.w;w.switch_workspace('score');w.activateWindow();canvas=w.score_view.canvas;canvas.setFocus();APP.processEvents()
        for unit in ('measure','beat'):
            canvas.set_selection_unit(unit);self.key(canvas,Qt.Key.Key_A)
            self.assertEqual(canvas.selected_units(),{key for _,_,key in canvas.selection_rects()})

if __name__=='__main__':unittest.main()

