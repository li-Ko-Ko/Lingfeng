"""Show actual overlapping card previews in the main and floating chord lanes."""
import os,sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Chord,Note,Context,PPQ
from popscore.theme import apply_theme

app=QApplication([]);out=Path(__file__).resolve().parents[1]/'output/screenshots';out.mkdir(exist_ok=True,parents=True)
p=Project(title='和弦预览层级');p.contexts=[Context(0,p.end,53,'Ionian')]
p.chords=[Chord(0,1920,53,pattern='quarters'),Chord(1920,1920,48,bass=4,pattern='quarters'),Chord(3840,1920,50,'m7',pattern='quarters')]
p.notes=[Note(t,240,pitch) for t,pitch in [(0,65),(480,67),(960,69),(1920,67),(2880,69),(3840,67),(4320,65),(4800,69)]]
with patch.object(MainWindow,'save_preferences'):
    w=MainWindow(p);w.change_language('zh',False);w.show();w.resize(1120,780);w.timer.stop();w.autosave.stop()
    for button in w.mute_buttons.values():button.setChecked(True)
    r=w.roll;r.zoom=120;r.update_ranges();r.timeViewChanged.emit();r.center_pitch(65);QTest.qWait(40)
    lane=w.chord_lane;c=p.chords[1]
    for dark in (True,False):
        apply_theme(dark);lane.selection_event({c.id});start=QPoint(round(lane.x_at(c.end)-3),25);end=QPoint(round(lane.x_at(5280)),25)
        QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=start);lane.begin_resize();QTest.mouseMove(lane,end);app.processEvents()
        w.grab().save(str(out/f'lingfeng-v31-layers-resize-{"dark" if dark else "light"}.png'))
        QTest.keyClick(lane,Qt.Key.Key_Escape);QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=end);app.processEvents()
    apply_theme(True);w.open_harmony();w.harmony_window.setFloating(True);QTest.qWait(40)
    r=w.harmony_window.roll;lane=r.lane;r.zoom=120;r.update_ranges();r.center_pitch(55);lane.selection_event({c.id});app.processEvents()
    start=QPoint(round(lane.x_at(c.start+960)),25);end=start+QPoint(120,0)
    QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(lane,end);app.processEvents()
    w.harmony_window.grab().save(str(out/'lingfeng-v31-layers-floating-move.png'))
    QTest.keyClick(lane,Qt.Key.Key_Escape);QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=end)
    w.dirty=False;w.close();w.deleteLater();app.processEvents()
print('Saved 3 overlap-preview fixtures.')
