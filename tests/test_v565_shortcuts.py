"""Movement keys remain fixed across old preferences, dialogs and editor surfaces."""
import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication,QLineEdit,QMenu
from PySide6.QtTest import QTest
from lingfeng.music.model import Project,Note,Chord
from lingfeng.ui.keybindings import FIXED_COMMANDS,KeyBindingsDialog,load_bindings,normalized,validate,shortcut_sequences
from lingfeng.ui.main_window import MainWindow

APP=QApplication.instance() or QApplication([])


class BindingTests(unittest.TestCase):
    def test_old_custom_movement_and_camera_bindings_cannot_take_direction_keys(self):
        old={'up':'W','down':'S','left':'A','right':'D','scale_up':'Alt+W','scale_down':'Alt+S',
            'scale_up_alt':'Alt+Up','scale_down_alt':'Alt+Down','octave_up':'F2','octave_down':'',
            'view_left':'Left','view_right':'Right','play':'Up','toggle_tool':'F3','switch_input':''}
        for mapping in (old,dict(reversed(list(old.items())))):
            result=load_bindings(mapping);validate(result)
            for key,value in FIXED_COMMANDS.items():self.assertEqual(result[key],value,key)
            self.assertEqual(result['play'],'');self.assertEqual(result['toggle_tool'],'F3');self.assertEqual(result['switch_input'],'')
            self.assertEqual(load_bindings(result),result)

    def test_dialog_cannot_clear_or_replace_fixed_keys_or_claim_them_elsewhere(self):
        d=KeyBindingsDialog({'up':'I','view_left':'F8'});self.addCleanup(d.deleteLater)
        for key,value in FIXED_COMMANDS.items():
            self.assertFalse(d.fields[key].isEnabled(),key);self.assertEqual(d.value()[key],value)
            d.fields[key].setKeySequence(QKeySequence('F12'))
            self.assertFalse(d.resolve_change(key));self.assertEqual(d.fields[key].keySequence().toString(),value)
        before=d.value();d.fields['play'].setKeySequence(QKeySequence('Right'))
        with patch('lingfeng.ui.keybindings.QMessageBox.question') as prompt:
            self.assertFalse(d.resolve_change('play'));prompt.assert_not_called()
        self.assertEqual(d.value(),before)
        d.reset();self.assertEqual(d.value(),normalized({}));validate(d.value())

    def test_menu_registry_uses_fixed_keys_even_if_in_memory_mapping_is_stale(self):
        for key,value in FIXED_COMMANDS.items():
            self.assertEqual([s.toString() for s in shortcut_sequences({key:'F12'},key)],[value] if value else [])
        self.assertEqual(shortcut_sequences({'play':'Left'},'play'),[])
        with self.assertRaises(ValueError):validate({'play':'Alt+Up'})


class SurfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='tmp');self.paths=patch('lingfeng.ui.main_window.user_data_dir',return_value=Path(self.temp.name));self.paths.start()
        p=Project();p.notes=[Note(960,480,60)];p.chords=[Chord(0,3840)]
        self.w=MainWindow(p);self.w.change_language('zh',False);self.w.timer.stop();self.w.autosave.stop();self.w.resize(1100,850);self.w.show()
        self.w.keybindings.update(up='I',right='D',view_right='F9',toggle_tool='Right')
        for button in self.w.mute_buttons.values():button.setChecked(True)

    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.paths.stop();self.temp.cleanup()

    def focus(self,widget):
        widget.window().activateWindow();widget.setFocus();APP.processEvents()

    def test_note_arrows_ignore_stale_bindings_and_leave_position_unchanged(self):
        w=self.w;r=w.roll;r.edit_target='notes';r.selected_ids={w.project.notes[0].id};self.focus(r)
        anchor=r.position_tick();tool=r.tool
        for key in (Qt.Key.Key_W,Qt.Key.Key_I,Qt.Key.Key_D,Qt.Key.Key_F9):QTest.keyClick(r,key)
        self.assertEqual((w.project.notes[0].pitch,w.project.notes[0].start),(60,960))
        QTest.keyClick(r,Qt.Key.Key_Up);QTest.keyClick(r,Qt.Key.Key_Right)
        self.assertEqual((w.project.notes[0].pitch,w.project.notes[0].start),(61,960+r.grid))
        self.assertEqual(r.tool,tool);self.assertEqual(r.position_tick(),anchor)
        QTest.keyClick(r,Qt.Key.Key_Down);QTest.keyClick(r,Qt.Key.Key_Left)
        self.assertEqual((w.project.notes[0].pitch,w.project.notes[0].start),(60,960))
        menu=QMenu();r.selection_menu(menu,0)
        up=next(a for a in menu.findChildren(type(menu.actions()[0])) if a.property('shortcutCommand')=='up')
        self.assertEqual(up.shortcut().toString(),'Up');menu.deleteLater()

    def test_chord_arrows_work_in_floating_surface_and_camera_has_no_key(self):
        w=self.w;w.open_harmony();w.harmony_window.setFloating(True);w.harmony_window.sync.setChecked(False);w.harmony_window.show()
        r=w.harmony_window.roll;r.edit_target='chords';r.lane.selection_event({w.project.chords[0].id});self.focus(r.lane)
        anchor=r.position_tick();QTest.keyClick(r.lane,Qt.Key.Key_Up);QTest.keyClick(r.lane,Qt.Key.Key_Right)
        c=next(c for c in w.project.chords if c.id in r.selected_chords);self.assertEqual((c.root%12,c.start),(1,r.grid));self.assertEqual(r.position_tick(),anchor)
        r.selected_chords=set();r.horizontalScrollBar().setValue(0);before=w.project.to_dict()
        QTest.keyClick(r.lane,Qt.Key.Key_Right);QTest.keyClick(r.lane,Qt.Key.Key_F9)
        self.assertEqual(r.horizontalScrollBar().value(),0);self.assertEqual(w.project.to_dict(),before)

    def test_text_entry_receives_arrows_without_editing_notes(self):
        before=self.w.project.to_dict();field=QLineEdit(self.w);field.setText('abc');field.show();self.focus(field);field.setCursorPosition(1)
        QTest.keyClick(field,Qt.Key.Key_Right);self.assertEqual(field.cursorPosition(),2)
        for key,mods in ((Qt.Key.Key_Up,Qt.KeyboardModifier.NoModifier),(Qt.Key.Key_Down,Qt.KeyboardModifier.AltModifier),
                         (Qt.Key.Key_Up,Qt.KeyboardModifier.ControlModifier)):QTest.keyClick(field,key,mods)
        self.assertEqual(self.w.project.to_dict(),before);field.deleteLater()


if __name__=='__main__':unittest.main()
