"""Inspect batch patterns, navigation help and editor shortcuts in both languages."""
import os,sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Chord,Note
from popscore.theme import apply_theme
from popscore.helpview import HelpDialog
from popscore.keybindings import KeyBindingsDialog,load_bindings

app=QApplication([]);out=Path(__file__).resolve().parents[1]/'output/screenshots';out.mkdir(exist_ok=True,parents=True)
p=Project(title='批量节奏型 · 框选与导航');p.chords=[Chord(0,3840),Chord(3840,3840,50,'m'),Chord(7680,3840,55,'7')]
p.notes=[Note(0,960,60),Note(960,1920,64),Note(3840,2880,65),Note(6720,3840,67)]
with patch.object(MainWindow,'save_preferences'):
    w=MainWindow(p);w.change_language('zh',False);w.show();w.resize(1280,900);w.timer.stop();w.autosave.stop()
    for b in w.mute_buttons.values():b.setChecked(True)
    w.open_harmony();w.roll.center_pitch(64);w.harmony_window.roll.center_pitch(53)
    w.chord_command('pattern:up',{c.id for c in p.chords},w.harmony_window.roll);w.grid.set_triplet(True)
    for dark in (True,False):
        apply_theme(dark);QTest.qWait(60);w.grab().save(str(out/f'lingfeng-v30-main-{"dark" if dark else "light"}.png'))
    for language in ('zh','en'):
        w.change_language(language,False);apply_theme(True);QTest.qWait(30);r=w.harmony_window.roll;lane=r.lane
        w.chord_selection({c.id for c in w.project.chords},r);menu=lane.context_menu(QPoint(round(lane.x_at(480)),25));menu.pattern_menu.show();QTest.qWait(20)
        menu.pattern_menu.grab().save(str(out/f'lingfeng-v30-patterns-{language}.png'));menu.pattern_menu.hide();menu.deleteLater()
        help=HelpDialog(w);help.list.setCurrentRow(len(help.pages)-2);help.show();QTest.qWait(20)
        help.grab().save(str(out/f'lingfeng-v30-help-{language}.png'));help.close();help.deleteLater()
        keys=KeyBindingsDialog(load_bindings({}),w);keys.show();QTest.qWait(20)
        keys.grab().save(str(out/f'lingfeng-v30-keys-{language}.png'));keys.close();keys.deleteLater()
    w.dirty=False;w.close();w.deleteLater();app.processEvents()
print('Saved 8 offscreen visual fixtures.')
