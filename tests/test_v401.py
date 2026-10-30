"""One shortcut registry for dispatch, menus and conflict-aware settings."""
import os,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QKeySequence,QAction
from PySide6.QtWidgets import QApplication,QDialog,QMessageBox,QMenu,QLineEdit
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord
from popscore.keybindings import (COMMANDS,ALIASES,STANDARD,FIXED_KEYS,normalized,load_bindings,
                                validate,KeyBindingsDialog,shortcut_sequences)

APP=QApplication.instance() or QApplication([])

def actions(menu):
    for a in menu.actions():
        yield a
        if a.menu():yield from actions(a.menu())

class BindingTests(unittest.TestCase):
    def dialog(self,mapping=None):
        d=KeyBindingsDialog(mapping or normalized({}));self.addCleanup(d.deleteLater);return d
    def test_catalog_covers_global_commands_alternatives_and_native_keys(self):
        d=self.dialog();validate(d.value());self.assertEqual(set(d.fields),set(COMMANDS))
        self.assertTrue(set(STANDARD.values())<=set(d.fields))
        self.assertTrue({'new','open','redo_alt','delete_alt','scale_up_alt','scale_down_alt','next_chord'}<=set(d.fields))
        self.assertEqual(d.value()['save'],'Ctrl+S');self.assertEqual(d.value()['octave_down'],'Ctrl+Down')
        self.assertEqual({f.text() for f in d.findChildren(QLineEdit) if f.isReadOnly()},set(FIXED_KEYS))
        catalog=json.loads((Path(__file__).resolve().parents[1]/'popscore/en.json').read_text('utf-8'))
        self.assertTrue(all(label in catalog for label,_ in COMMANDS.values()))
    def test_confirm_conflict_clears_previous_action_only(self):
        d=self.dialog();d.fields['up'].setKeySequence(QKeySequence('D'))
        with patch('popscore.keybindings.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes) as prompt:
            d.fields['up'].editingFinished.emit()
        self.assertIn('向右移动',prompt.call_args.args[2]);self.assertIn('清除',prompt.call_args.args[2])
        self.assertEqual(d.value()['up'],'D');self.assertEqual(d.value()['right'],'');self.assertEqual(d.value()['down'],'S')
        d.accept();self.assertEqual(d.result(),QDialog.DialogCode.Accepted);validate(d.value())
    def test_declining_conflict_restores_previous_choice(self):
        d=self.dialog();before=d.value();d.fields['up'].setKeySequence(QKeySequence('Ctrl+S'))
        with patch('popscore.keybindings.QMessageBox.question',return_value=QMessageBox.StandardButton.No):self.assertFalse(d.resolve_change('up'))
        self.assertEqual(d.value(),before)
    def test_conflict_with_save_is_reassignable_and_cancellable_as_a_draft(self):
        original=normalized({});d=self.dialog(original);d.fields['octave_down'].setKeySequence(QKeySequence('Ctrl+S'))
        with patch('popscore.keybindings.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes) as prompt:
            self.assertTrue(d.resolve_change('octave_down'))
        self.assertIn('保存',prompt.call_args.args[2]);self.assertEqual(d.value()['save'],'')
        d.reject();self.assertEqual(original,normalized({}))
    def test_alternate_conflict_reset_and_canonical_validation(self):
        d=self.dialog();d.fields['up'].setKeySequence(QKeySequence('Alt+Up'))
        with patch('popscore.keybindings.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):d.resolve_change('up')
        self.assertEqual(d.value()['scale_up_alt'],'');self.assertEqual(d.value()['scale_up'],'Alt+W')
        d.reset();self.assertEqual(d.value(),normalized({}));validate(d.value())
        with self.assertRaises(ValueError):validate({'save':'ctrl+s','up':'Ctrl+S'})
    def test_reserved_native_key_rejected_without_altering_binding(self):
        d=self.dialog();d.fields['save'].setKeySequence(QKeySequence('Esc'))
        self.assertFalse(d.resolve_change('save'));self.assertEqual(d.value()['save'],'Ctrl+S');self.assertTrue(d.error.text())
    def test_saved_customization_wins_over_new_default_and_stays_cleared(self):
        mapping=load_bindings({'octave_down':'Ctrl+S','up':'Alt+Up','copy_selection':''})
        self.assertEqual(mapping['save'],'');self.assertEqual(mapping['scale_up_alt'],'');self.assertEqual(mapping['copy_selection'],'')
        self.assertEqual(mapping,load_bindings(mapping));validate(mapping)

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='tmp');self.folder=Path(self.temp.name)
        self.paths=patch('popscore.app.user_data_dir',return_value=self.folder);self.paths.start()
        p=Project();p.notes=[Note(0,480,60),Note(960,480,62)];p.chords=[Chord(0,3840),Chord(3840,3840,55)]
        self.w=MainWindow(p);self.w.timer.stop();self.w.autosave.stop();self.w.change_language('zh',False);self.w.show()
        self.r=self.w.roll;self.focus(self.r)
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.paths.stop();self.temp.cleanup()
    def focus(self,r):
        r.edit_target='notes';r.selected_ids={r.notes[0].id};r.window().activateWindow();r.setFocus();APP.processEvents()
    def test_note_and_chord_menus_use_current_keys_and_alternatives(self):
        w=self.w;w.keybindings['up']='I';w.keybindings['delete']='';w.keybindings['copy_selection']='Ctrl+Alt+C'
        for r in (w.roll,w.harmony_window.roll):
            r.selected_ids={n.id for n in r.notes};menu=QMenu();r.selection_menu(menu,0)
            tagged={a.property('shortcutCommand'):a for a in actions(menu) if a.property('shortcutCommand')}
            self.assertTrue({'copy_selection','up','down','scale_up','scale_down','octave_up','octave_down','split','merge','delete','paste_selection'}<=set(tagged))
            for key,a in tagged.items():self.assertEqual(a.shortcuts(),shortcut_sequences(w.keybindings,key));self.assertTrue(a.isShortcutVisibleInContextMenu())
            self.assertEqual(tagged['delete'].shortcut().toString(),'Backspace');menu.deleteLater()
            menu=r.lane.context_menu(QPoint(round(r.lane.x_at(100)),20));tagged={a.property('shortcutCommand'):a for a in actions(menu) if a.property('shortcutCommand')}
            self.assertTrue({'edit_chord','copy_selection','paste_selection','delete','split','merge','up','down','left','right','scale_up','scale_down'}<=set(tagged))
            for key,a in tagged.items():self.assertEqual(a.shortcuts(),shortcut_sequences(w.keybindings,key))
            menu.deleteLater()
    def test_confirmed_setting_updates_file_menu_and_runtime_without_restart(self):
        w=self.w
        def accept(d):
            d.fields['octave_down'].setKeySequence(QKeySequence('Ctrl+S'))
            with patch('popscore.keybindings.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):d.accept()
            return d.result()
        with patch.object(KeyBindingsDialog,'exec',accept):w.keybinding_settings()
        save=next(a for a in w.findChildren(QAction) if a.property('shortcutCommand')=='save')
        self.assertTrue(save.shortcut().isEmpty());self.assertEqual(w.keybindings['save'],'')
        with patch.object(w,'save') as save_method:
            QTest.keyClick(self.r,Qt.Key.Key_S,Qt.KeyboardModifier.ControlModifier);save_method.assert_not_called()
        self.assertEqual(w.project.notes[0].pitch,48)
        stored=json.loads((self.folder/'preferences.json').read_text('utf-8'))['keybindings']
        self.assertEqual(load_bindings(stored),w.keybindings)
    def test_global_file_key_and_redo_alias_work_in_floating_window_once(self):
        w=self.w;r=w.harmony_window.roll;w.harmony_window.setFloating(True);w.harmony_window.show();self.focus(r)
        w.keybindings['save']='Ctrl+Alt+S';w.update_shortcuts()
        with patch.object(w,'save') as save:
            QTest.keyClick(r,Qt.Key.Key_S,Qt.KeyboardModifier.ControlModifier);save.assert_not_called()
            QTest.keyClick(r,Qt.Key.Key_S,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier);save.assert_called_once_with()
        with patch.object(w,'redo') as redo:
            QTest.keyClick(r,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier);redo.assert_called_once()
    def test_disabled_keys_do_not_fall_through_to_old_widget_handlers(self):
        w=self.w;before=w.project.to_dict()
        for key in ('delete','delete_alt','scale_up_alt','select_all'):w.keybindings[key]=''
        w.update_shortcuts();selected=set(self.r.selected_ids)
        for key,mods in [(Qt.Key.Key_Delete,Qt.KeyboardModifier.NoModifier),(Qt.Key.Key_Backspace,Qt.KeyboardModifier.NoModifier),
                         (Qt.Key.Key_Up,Qt.KeyboardModifier.AltModifier),(Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)]:QTest.keyClick(self.r,key,mods)
        self.assertEqual(w.project.to_dict(),before);self.assertEqual(self.r.selected_ids,selected)
    def test_floating_menu_and_language_rebuild_preserve_custom_keys(self):
        w=self.w;w.keybindings['copy_selection']='Ctrl+Alt+C';w.update_shortcuts()
        w.harmony_window.setFloating(True);w.harmony_window.show();w.change_language('en',False)
        r=w.harmony_window.roll;self.focus(r);menu=QMenu();r.selection_menu(menu,0)
        copy=next(a for a in actions(menu) if a.property('shortcutCommand')=='copy_selection')
        self.assertEqual(copy.shortcut().toString(),'Ctrl+Alt+C');self.assertEqual(copy.text(),'Copy original');menu.deleteLater()
    def test_text_controls_keep_native_shortcuts_and_do_not_edit_music(self):
        edit=QLineEdit(self.w);edit.setText('example');edit.show();edit.setFocus();APP.processEvents();before=self.w.project.to_dict()
        QTest.keyClick(edit,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier);self.assertEqual(edit.selectedText(),'example')
        QTest.keyClick(edit,Qt.Key.Key_Backspace);self.assertEqual(edit.text(),'');self.assertEqual(self.w.project.to_dict(),before);edit.deleteLater()
    def test_cancel_settings_does_not_apply_cleared_conflict(self):
        w=self.w;before=dict(w.keybindings)
        def reject(d):
            d.fields['up'].setKeySequence(QKeySequence('Ctrl+C'))
            with patch('popscore.keybindings.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):d.resolve_change('up')
            return QDialog.DialogCode.Rejected
        with patch.object(KeyBindingsDialog,'exec',reject):w.keybinding_settings()
        self.assertEqual(w.keybindings,before)
    def test_next_chord_binding_can_be_changed(self):
        w=self.w;r=self.r;r.edit_target='chords';r.selected_chords={w.project.chords[0].id};w.keybindings['next_chord']='F8'
        r.setFocus();APP.processEvents();QTest.keyClick(r,Qt.Key.Key_F8)
        self.assertEqual(r.selected_chords,{w.project.chords[1].id})

if __name__=='__main__':unittest.main()
