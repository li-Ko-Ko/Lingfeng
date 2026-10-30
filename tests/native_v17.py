"""Native Windows scrollbar gestures and independent follow during WinMM playback."""
import os,sys,time,json
os.environ['QT_QPA_PLATFORM']='windows'
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox,QStyle,QStyleOptionSlider
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import demo_project

app=QApplication([]);app.setStyle('Fusion');errors=[]
sys.excepthook=lambda typ,value,tb:errors.append(str(value))
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
w=MainWindow(demo_project());w.show();w.resize(1150,850);w.open_harmony();w.melody_window.setFloating(True);w.harmony_window.setFloating(True);QTest.qWait(80);w.timer.stop()
for mute in w.mute_buttons.values():mute.setChecked(True)
w.seek(960);w.toggle_play();worker=w.transport.thread;clock=w.transport.start_time;anchor=w.play_anchor
for bar,follow in ((w.shared_scroll,w.follow_playhead),(w.roll.horizontalScrollBar(),w.melody_transport.follow),(w.harmony_window.roll.horizontalScrollBar(),w.harmony_window.transport_controls.follow)):
    opt=QStyleOptionSlider();bar.initStyleOption(opt);pos=bar.style().subControlRect(QStyle.ComplexControl.CC_ScrollBar,opt,QStyle.SubControl.SC_ScrollBarSlider,bar).center()
    QTest.mousePress(bar,Qt.MouseButton.LeftButton,pos=pos);QTest.mouseMove(bar,pos+QPoint(50,0));QTest.mouseRelease(bar,Qt.MouseButton.LeftButton,pos=pos+QPoint(50,0))
    assert not follow.isChecked() and w.transport.thread is worker and w.transport.start_time==clock and w.play_anchor==anchor
w.melody_sync.setChecked(True);w.harmony_window.sync.setChecked(True);w.shared_scroll.setValue(0);w.sync_time_views(w.main_roll)
w.melody_transport.follow.setChecked(True);w.follow_views(25000)
assert w.roll.horizontalScrollBar().value()>0 and w.shared_scroll.value()==w.harmony_window.roll.horizontalScrollBar().value()==0
w.roll.center_pitch(64);w.view_controls.height.setValue(38)
middle=w.roll.ruler_height+(w.roll.viewport().height()-w.roll.ruler_height)/2
assert abs(w.roll.y_at(64)+19-middle)<=1
QTest.mouseClick(w.harmony_window.transport_controls.play,Qt.MouseButton.LeftButton);assert not w.transport.playing and w.melody_transport.play.kind=='play'
QTest.mouseClick(w.melody_transport.replay,Qt.MouseButton.LeftButton);assert not w.transport.playing
assert not errors,errors
out=Path('output/native-v17');out.mkdir(exist_ok=True,parents=True);report=dict(status='passed',dpi_scale=w.devicePixelRatioF(),real_winmm_worker_preserved=True,scrollbar_gestures=True,independent_follow=True,centered_pitch=True,qt_callback_errors=errors)
(out/'result.json').write_text(json.dumps(report,indent=2),'utf-8');w.dirty=False;w.close();app.processEvents();assert not errors,errors;print(json.dumps(report))
