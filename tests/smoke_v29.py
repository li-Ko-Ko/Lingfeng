"""Offscreen visual fixtures for meter-aware editing and distinct pattern states."""
import os,sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Measure,Context,Chord,Note
from popscore.theme import apply_theme
from popscore.helpview import HelpDialog

app=QApplication([]);out=Path(__file__).resolve().parents[1]/'output/screenshots';out.mkdir(exist_ok=True,parents=True)
p=Project(title='拍号边界 · 和弦编排');p.measures=[Measure(),Measure(3,4),Measure(),Measure()];p.contexts=[Context(0,p.end)]
p.put_chord(Chord(0,3840,pattern='up'))
p.chords += [Chord(3840,2880,50,'m',notes=[Note(t,d,k) for t,d,k in ((0,700,50),(120,900,53),(250,1100,57))]),Chord(6720,3840,notes=[Note(0,3840,k) for k in (48,52,55)],custom_rhythm=True)]
p.notes=[Note(0,960,60),Note(960,1920,64),Note(3840,2880,65),Note(6720,3840,67)]
with patch.object(MainWindow,'save_preferences'):
    w=MainWindow(p);w.change_language('zh',False);w.show();w.resize(1340,930);w.timer.stop();w.autosave.stop()
    for b in w.mute_buttons.values():b.setChecked(True)
    w.open_harmony();w.roll.center_pitch(64);w.harmony_window.roll.center_pitch(53);r=w.harmony_window.roll
    for dark in (True,False):
        apply_theme(dark);QTest.qWait(80);w.grab().save(str(out/f'lingfeng-v29-main-{"dark" if dark else "light"}.png'))
    for language in ('zh','en'):
        w.change_language(language,False);apply_theme(True);QTest.qWait(35);r=w.harmony_window.roll;lane=r.lane
        w.chord_command('copy',{w.project.chords[0].id},r)
        menu=lane.context_menu(QPoint(round(lane.x_at(4320)),25));menu.show();QTest.qWait(25)
        menu.grab().save(str(out/f'lingfeng-v29-menu-{language}.png'));menu.close();menu.deleteLater()
        w.chord_selection({c.id for c in w.project.chords},r);menu=lane.context_menu(QPoint(round(lane.x_at(480)),25));menu.move_menu.show();QTest.qWait(25)
        menu.move_menu.grab().save(str(out/f'lingfeng-v29-move-{language}.png'));menu.move_menu.hide();menu.deleteLater()
        help=HelpDialog(w);help.list.setCurrentRow(len(help.pages)-2);help.show();QTest.qWait(25)
        help.grab().save(str(out/f'lingfeng-v29-help-{language}.png'));help.close();help.deleteLater()
    w.dirty=False;w.close();w.deleteLater();app.processEvents()
print('Saved 8 offscreen visual fixtures.')
