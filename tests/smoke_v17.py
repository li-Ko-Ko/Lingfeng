"""Visual checks for independent floating transports and centered key sizing."""
import os,sys,json
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import demo_project

app=QApplication([]);app.setStyle('Fusion');errors=[]
sys.excepthook=lambda typ,value,tb:errors.append(str(value))
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
w=MainWindow(demo_project());w.show();w.resize(1380,1000);w.change_language('zh',False);w.set_theme('light');w.open_harmony();QTest.qWait(60);w.timer.stop()
for mute in w.mute_buttons.values():mute.setChecked(True)
out=Path('output/screenshots');out.mkdir(exist_ok=True,parents=True)
w.grab().save(str(out/'lingfeng-v17-compose.png'))
w.melody_window.setFloating(True);w.harmony_window.setFloating(True);QTest.qWait(70)
assert w.timeline.roll is w.main_roll
w.shared_scroll.setValue(400);w.roll.horizontalScrollBar().setValue(100);w.harmony_window.roll.horizontalScrollBar().setValue(800);w.melody_transport.follow.setChecked(False)
w.grab().save(str(out/'lingfeng-v17-main-both-floating.png'))
w.melody_window.grab().save(str(out/'lingfeng-v17-melody-floating.png'));w.harmony_window.grab().save(str(out/'lingfeng-v17-harmony-floating.png'))
r=w.roll;r.center_pitch(64);w.view_controls.height.setValue(34);QTest.qWait(30)
assert abs(r.y_at(64)+17-(r.ruler_height+(r.viewport().height()-r.ruler_height)/2))<=1
w.melody_window.grab().save(str(out/'lingfeng-v17-centered-keys.png'))
w.change_language('en',False);w.set_theme('dark');w.melody_window.resize(700,650);w.harmony_window.resize(700,650);QTest.qWait(60)
w.melody_window.grab().save(str(out/'lingfeng-v17-melody-en-narrow.png'));w.harmony_window.grab().save(str(out/'lingfeng-v17-harmony-en-narrow.png'))
for pane,_,_,controls in w.view_panes():assert all(c.isVisible() and pane.rect().contains(c.mapTo(pane,c.rect().center())) for c in (controls.play,controls.replay,controls.loop,controls.follow,controls.bpm))
assert not errors,errors
report=dict(status='passed',main_without_rolls=True,complete_floating_transports=True,centered_pitch=True,english_700px_windows=True,qt_callback_errors=errors)
Path('output/v17-ui-check.json').write_text(json.dumps(report,indent=2),'utf-8');w.dirty=False;w.close();app.processEvents();assert not errors,errors;print(json.dumps(report))
