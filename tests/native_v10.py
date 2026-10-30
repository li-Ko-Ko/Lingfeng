"""Windows-only high-DPI hit testing and continuous WinMM replay."""
import os,ctypes,json
os.environ['QT_QPA_PLATFORM']='windows'
from ctypes import wintypes
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import demo_project
app=QApplication([]);app.setStyle('Fusion')
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
w=MainWindow(demo_project());w.show();w.open_harmony();QTest.qWait(100)
user=ctypes.windll.user32;hwnd=wintypes.HWND(int(w.winId()))
user.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM];user.SendMessageW.restype=wintypes.LPARAM
ratio=w.devicePixelRatioF()
def hit(local):
    pt=wintypes.POINT(round(local.x()*ratio),round(local.y()*ratio));user.ClientToScreen(hwnd,ctypes.byref(pt))
    return user.SendMessageW(hwnd,0x84,0,(pt.x&0xffff)|((pt.y&0xffff)<<16))
checks={}
for name,child in [('minimize',w.title_bar.window_buttons[0]),('maximize',w.title_bar.window_buttons[1]),('close',w.title_bar.window_buttons[2]),('chord_lane',w.chord_lane),('scrollbar',w.shared_scroll)]:
    checks[name]=hit(child.mapTo(w,child.rect().center()));assert checks[name]==1,(name,checks[name])
assert hit(QPoint(0,w.height()//2))==10
QTest.mouseClick(w.title_bar.window_buttons[0],Qt.MouseButton.LeftButton);QTest.qWait(50);assert w.isMinimized();w.showNormal();QTest.qWait(50)
for b in w.mute_buttons.values():b.setChecked(True)
w.play_anchor=3840;w.playhead=3840;w.toggle_play();QTest.qWait(80);assert w.transport.playing
QTest.mouseClick(w.replay_button,Qt.MouseButton.LeftButton);QTest.qWait(80);assert w.transport.playing and w.transport_active and w.play_button.kind=='pause'
assert 3840<=w.transport.position()<4400
QTest.mouseClick(w.replay_button,Qt.MouseButton.LeftButton);QTest.qWait(30);assert w.playhead==0 and not w.transport.playing
w.play_anchor=960;w.playhead=2000;w.replay();assert w.playhead==960 and not w.transport.playing and w.roll.anchor_tick is None
assert w.title_bar.brand.text() in ('伶风','Lingfeng')
folder=Path('output/native-v10');folder.mkdir(exist_ok=True)
(folder/'result.json').write_text(json.dumps(dict(status='passed',dpi_scale=ratio,hit_results=checks,edge_hit=10,real_winmm_replay=True,paused_replay=True),indent=2),'utf-8')
w.dirty=False;w.close();app.processEvents();print('Windows native frame and WinMM passed at scale',ratio)
