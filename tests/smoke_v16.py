"""Current-release screenshots and view/transport interaction smoke checks."""
import os,json,time,sys
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtCore import QPoint,QPointF,Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import demo_project,PPQ
from popscore.editor import KEY_W

app=QApplication([]);app.setStyle('Fusion');errors=[]
sys.excepthook=lambda typ,value,tb:errors.append(str(value))
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
out=Path('output/screenshots');out.mkdir(exist_ok=True,parents=True)
p=demo_project();p.set_context([[0,3840]],tonic=53,mode='Dorian')
w=MainWindow(p);w.show();w.resize(1380,1080);w.change_language('zh',False);w.set_theme('light');w.open_harmony();QTest.qWait(50)
for mute in w.mute_buttons.values():mute.setChecked(True)
w.grab().save(str(out/'lingfeng-v16-compose.png'))
lane=w.chord_lane;menu=lane.context_menu(QPoint(round(lane.x_at(960)),20));root=menu.root_menu
assert root.actions()[5].text()=='1 · F' and root.actions()[0].text()=='5 · C'
root.popup(lane.mapToGlobal(QPoint(80,0)));QTest.qWait(30);root.grab().save(str(out/'lingfeng-v16-chord-roots.png'));root.close();menu.close()
w.timer.stop();w.seek(960);w.toggle_play();worker=w.transport.thread;clock=w.transport.start_time;anchor=w.play_anchor;head=w.playhead
w.follow_playhead.setChecked(True)
nav=w.navigator;QTest.mousePress(nav,Qt.MouseButton.LeftButton,pos=QPoint(nav.width()//3,18));QTest.mouseMove(nav,QPoint(nav.width()*2//3,18));QTest.mouseRelease(nav,Qt.MouseButton.LeftButton,pos=QPoint(nav.width()*2//3,18))
assert not w.follow_playhead.isChecked() and w.playhead==head and w.play_anchor==anchor and w.transport.start_time==clock and w.transport.thread is worker
time.sleep(.03);w.playback_tick();assert w.playhead>head;QTest.qWait(20);w.grab().save(str(out/'lingfeng-v16-browse-playing.png'));w.stop()
w.roll.horizontalScrollBar().setValue(300);x=350;r=w.timeline.roll;offset=w.timeline.offset();tick=(x-offset-KEY_W+r.horizontalScrollBar().value())/r.zoom*PPQ
event=QWheelEvent(QPointF(x,12),QPointF(x,12),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.ControlModifier,Qt.ScrollPhase.NoScrollPhase,False)
app.sendEvent(w.timeline,event);assert abs(w.timeline.x_at(tick)-x)<=1 and w.roll.zoom==w.harmony_window.roll.zoom
w.roll.zoom_at(2048/w.roll.zoom,x);w.roll.horizontalScrollBar().setValue(0);w.grid.setCurrentIndex(w.grid.findData(60));QTest.qWait(25);w.grab().save(str(out/'lingfeng-v16-timeline-zoom.png'))
w.roll.zoom_at(78/w.roll.zoom);w.roll.horizontalScrollBar().setValue(0);w.grid.setCurrentIndex(w.grid.findData(240));w.change_language('en',False);w.set_theme('dark');w.resize(720,1000);QTest.qWait(35);w.grab().save(str(out/'lingfeng-v16-narrow-en.png'))
w.harmony_window.setFloating(True);QTest.qWait(35);w.harmony_window.grab().save(str(out/'lingfeng-v16-floating-harmony.png'))
assert not errors,errors
report=dict(status='passed',navigation_browses_without_seek=True,playback_clock_preserved=True,timeline_zoom_anchored=True,both_rolls_synchronized=True,chord_degrees_at_start=True,english_narrow_width=w.width(),qt_callback_errors=errors)
Path('output/v16-ui-check.json').write_text(json.dumps(report,indent=2),'utf-8')
w.dirty=False;w.close();app.processEvents();assert not errors,errors;print(json.dumps(report))
