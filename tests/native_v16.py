"""Windows high-DPI pointer mapping and live WinMM loop cancellation."""
import os,time,json,sys
os.environ['QT_QPA_PLATFORM']='windows'
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord,PPQ
from popscore.editor import KEY_W

app=QApplication([]);app.setStyle('Fusion');errors=[]
sys.excepthook=lambda typ,value,tb:errors.append(str(value))
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
p=Project();p.bpm=300;p.notes=[Note(0,2880,60),Note(1200,240,67)];p.chords=[Chord(0,3840,48)]
w=MainWindow(p);w.resize(1200,850);w.show();w.open_harmony();QTest.qWait(60);w.timer.stop()
for mute in w.mute_buttons.values():mute.setChecked(True)
w.roll.selection=[[0,960]];w.seek(0);w.loop.setChecked(True);w.toggle_play();worker=w.transport.thread;clock=w.transport.start_time;anchor=w.play_anchor
w.loop.setChecked(False);deadline=time.perf_counter()+2
while w.transport.position()<=1300 and time.perf_counter()<deadline:time.sleep(.005)
assert w.transport.playing and w.transport.position()>1300 and not w.transport.loop and w.transport.end_tick==p.end
assert w.transport.thread is worker and w.transport.start_time==clock and w.play_anchor==anchor
nav=w.navigator;w.follow_playhead.setChecked(True);head=w.playhead
QTest.mousePress(nav,Qt.MouseButton.LeftButton,pos=QPoint(nav.width()//3,15));QTest.mouseMove(nav,QPoint(nav.width()*2//3,15));QTest.mouseRelease(nav,Qt.MouseButton.LeftButton,pos=QPoint(nav.width()*2//3,15))
assert not w.follow_playhead.isChecked() and w.playhead==head and w.transport.thread is worker and w.transport.start_time==clock
w.roll.horizontalScrollBar().setValue(0);w.roll.center_pitch(65);app.processEvents()
QTest.mouseClick(w.roll.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(round(w.roll.x_at(1440)+4),round(w.roll.y_at(65)+10)))
QTest.mouseClick(w.chord_lane,Qt.MouseButton.LeftButton,pos=QPoint(round(w.chord_lane.x_at(480)),20))
assert w.playhead==head and w.play_anchor==anchor and w.transport.thread is worker
QTest.mouseClick(w.timeline,Qt.MouseButton.LeftButton,pos=QPoint(round(w.timeline.x_at(1920)),12));assert w.transport.playing and w.play_anchor==1920
w.stop();QTest.mouseClick(w.timeline,Qt.MouseButton.LeftButton,pos=QPoint(round(w.timeline.x_at(960)),12));assert not w.transport.playing and w.playhead==960
w.roll.horizontalScrollBar().setValue(500);x=350;r=w.timeline.roll;tick=(x-w.timeline.offset()-KEY_W+r.horizontalScrollBar().value())/r.zoom*PPQ
event=QWheelEvent(QPointF(x,16),QPointF(x,16),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.ControlModifier,Qt.ScrollPhase.NoScrollPhase,False)
app.sendEvent(w.timeline,event);assert abs(w.timeline.x_at(tick)-x)<=1 and w.roll.zoom==w.harmony_window.roll.zoom
assert not errors,errors
out=Path('output/native-v16');out.mkdir(exist_ok=True,parents=True)
report=dict(status='passed',dpi_scale=w.devicePixelRatioF(),winmm_loop_cancel_continuous=True,navigation_no_seek=True,grid_and_chord_no_seek=True,timeline_seek_preserves_state=True,timeline_zoom_anchor=True,qt_callback_errors=errors)
(out/'result.json').write_text(json.dumps(report,indent=2),'utf-8');w.dirty=False;w.close();app.processEvents();assert not errors,errors;print(json.dumps(report))
