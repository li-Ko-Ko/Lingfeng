"""Native Windows gestures, live editing, local chord selection, keyboard focus."""
import os,sys,json
os.environ['QT_QPA_PLATFORM']='windows'
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox,QLineEdit
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Chord,Note
from popscore.keybindings import normalized

app=QApplication([]);app.setStyle('Fusion');errors=[];sys.excepthook=lambda typ,value,tb:errors.append(str(value))
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
p=Project();p.notes=[Note(960,480,60)];p.chords=[Chord(0,3840),Chord(3840,3840,55)]
w=MainWindow(p);w.keybindings=normalized({});w.show();w.resize(1100,800);w.open_harmony();w.harmony_window.setFloating(True);QTest.qWait(70);w.timer.stop();w.autosave.stop()
for mute in w.mute_buttons.values():mute.setChecked(True)
r=w.harmony_window.roll;lane=r.lane;w.chord_selection(set());w.chord_hover('');a=QPoint(round(lane.x_at(480)),25)
QTest.mouseClick(lane,Qt.MouseButton.LeftButton,pos=a);assert r.selected_chords and not w.roll.selected_chords and not w.roll.hovered_chord
w.seek(960);w.toggle_play();worker=w.transport.thread;clock=w.transport.start_time;anchor=w.play_anchor
box,c=lane.boxes[0];a=QPoint(round(box.right()-2),25);b=QPoint(round(lane.x_at(4800)),25)
QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=a);QTest.qWait(310);QTest.mouseMove(lane,b);QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=b)
assert w.project.chords[0].end==4800 and w.project.chords[1].start==4800
assert w.transport.thread is worker and w.transport.start_time==clock and w.play_anchor==anchor
w.harmony_window.activateWindow();lane.setFocus();app.processEvents();QTest.keyClick(lane,Qt.Key.Key_D)
assert w.project.chords[0].start==r.grid and w.transport.playing
QTest.keyClick(lane,Qt.Key.Key_E);assert r.tool=='draw';QTest.keyClick(lane,Qt.Key.Key_Q);assert r.tool=='smart'
w.stop();w.activateWindow();r=w.roll;r.selected_ids={w.project.notes[0].id};r.edit_target='notes';r.setFocus();app.processEvents();QTest.keyClick(r,Qt.Key.Key_W);assert w.project.notes[0].pitch==62
field=QLineEdit(w);field.show();field.setFocus();app.processEvents();QTest.keyClicks(field,'wasd qe');assert field.text()=='wasd qe' and w.project.notes[0].pitch==62
report=dict(status='passed',dpi_scale=w.devicePixelRatioF(),live_resize_preserves_worker=True,floating_selection_isolated=True,keyboard_gestures=True,qt_callback_errors=errors)
out=Path('output/native-v18');out.mkdir(parents=True,exist_ok=True);(out/'result.json').write_text(json.dumps(report,indent=2),'utf-8')
w.dirty=False;w.close();app.processEvents();assert not errors,errors;print(json.dumps(report))
