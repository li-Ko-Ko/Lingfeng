"""Windows peer activation, minimize/restore and taskbar eligibility probes."""
import os,sys,json,ctypes,unittest
from pathlib import Path
from ctypes import wintypes
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from tests.test_v26 import WindowDisplayTests,APP
from tests.test_v25 import EditorHistoryTests
from popscore.app import MainWindow
from popscore.model import demo_project
from popscore.helpview import HelpDialog
from popscore.windowing import APP_ID
from popscore import __version__

errors=[]
def hook(typ,value,tb):errors.append(str(value));sys.__excepthook__(typ,value,tb)
sys.excepthook=hook
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in (WindowDisplayTests,EditorHistoryTests)])
result=unittest.TestResult() if '--only-window-check' in sys.argv else unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful() or errors:raise SystemExit(1)

MainWindow.save_preferences=lambda self:None
APP.setStyle('Fusion');w=MainWindow(demo_project());w.change_language('zh',False);w.set_theme('dark');w.show();w.timer.stop();w.autosave.stop();w.open_harmony()
w.setWindowTitle('Lingfeng 0.26 · Window restoration check')
area=APP.primaryScreen().availableGeometry();w.resize(min(1080,area.width()-40),max(560,area.height()-50));w.move(area.x()+10,area.y()+10)
w.melody_window.setFloating(True);w.harmony_window.setFloating(True);panes=[w,w.melody_window,w.harmony_window]
for pane in panes[1:]:pane.resize(min(920,area.width()-50),min(560,area.height()-50));pane.move(area.x()+35,area.y()+25)
QTest.qWait(30)
user=ctypes.windll.user32
user.GetWindow.argtypes=[wintypes.HWND,ctypes.c_uint];user.GetWindow.restype=wintypes.HWND
user.GetTopWindow.argtypes=[wintypes.HWND];user.GetTopWindow.restype=wintypes.HWND
user.GetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int];user.GetWindowLongW.restype=wintypes.LONG
user.IsWindowVisible.argtypes=[wintypes.HWND];user.IsIconic.argtypes=[wintypes.HWND]
user.GetForegroundWindow.restype=wintypes.HWND
def check_peer(p):
    hwnd=int(p.winId());assert not user.GetWindow(hwnd,4)  # GW_OWNER
    assert not p.windowHandle().transientParent()
    if p is not w:assert user.GetWindowLongW(hwnd,-20)&0x40000 and not user.GetWindowLongW(hwnd,-20)&0x80
    return hwnd
def highest(handles):
    hwnd=user.GetTopWindow(None)
    while hwnd:
        if hwnd in handles and user.IsWindowVisible(hwnd) and not user.IsIconic(hwnd):return hwnd
        hwnd=user.GetWindow(hwnd,2)  # GW_HWNDNEXT; inspect handles only.
    raise AssertionError('No application window in native z-order')
handles={check_peer(p) for p in panes}
foreground_checks=0
if '--interactive-foreground' in sys.argv:
    print('READY: activate Lingfeng 0.26 Window restoration check',flush=True)
    for _ in range(900):
        if user.GetForegroundWindow() in handles:break
        QTest.qWait(50)
    assert user.GetForegroundWindow() in handles,'Test window was not activated'
    QTest.qWait(800)
def activate_and_check(pane):
    global foreground_checks
    may_activate=user.GetForegroundWindow() in handles
    pane.raise_();pane.activateWindow();QTest.qWait(100)
    assert highest(handles)==int(pane.winId()),(pane.windowTitle(),int(pane.winId()),highest(handles),user.GetForegroundWindow())
    # Windows rightly prevents a background test process from stealing focus
    # from another app. Check foreground only when this process already owns it.
    if may_activate:
        assert user.GetForegroundWindow()==int(pane.winId());foreground_checks+=1
for pane in [panes[1],panes[2],w,panes[2],w]:
    activate_and_check(pane)
# A main-window minimize must leave independent editors visible.
w.showMinimized();QTest.qWait(30)
assert all(user.IsWindowVisible(int(p.winId())) and not user.IsIconic(int(p.winId())) for p in panes[1:])
w.showNormal()
# Exercise the application's native minimized state, then restore each preview's
# target separately. Actual Explorer thumbnail clicks are a separate UI check.
for cycle in range(2):
    for pane in panes:pane.showMinimized()
    QTest.qWait(40);assert all(user.IsIconic(int(p.winId())) for p in panes)
    for pane in (panes[2],w,panes[1],w):
        pane.showNormal();activate_and_check(pane)
        assert user.IsWindowVisible(int(pane.winId())) and not user.IsIconic(int(pane.winId()))
        check_peer(pane)
w.melody_window.setFloating(False);w.melody_window.setFloating(True);check_peer(w.melody_window)
w.change_language('en',False);QTest.qWait(30);check_peer(w.melody_window);check_peer(w.harmony_window)
w.switch_workspace('score');w.edit_toggle.setChecked(True);w.toggle_editor();w.score_tools.setFloating(True);check_peer(w.score_tools)
w.score_tools.showMinimized();QTest.qWait(20);w.score_tools.showNormal();w.score_tools.activateWindow();QTest.qWait(20);check_peer(w.score_tools)
ptr=ctypes.c_wchar_p();shell=ctypes.windll.shell32;shell.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(ptr));assert ptr.value==APP_ID
ctypes.windll.ole32.CoTaskMemFree(ptr)

shots=Path('output/screenshots');shots.mkdir(exist_ok=True)
w.switch_workspace('compose');w.change_language('zh',False);w.melody_window.setFloating(False);w.harmony_window.setFloating(False)
for visible in (True,False):
    w.note_degrees_action.setChecked(visible);w.roll.center_pitch(60);w.harmony_window.roll.center_pitch(55);QTest.qWait(30)
    w.grab().save(str(shots/f'lingfeng-v26-note-degrees-{str(visible).lower()}.png'))
for lang in ('zh','en'):
    w.change_language(lang,False);d=HelpDialog(w,True);d.resize(min(900,area.width()-40),min(760,area.height()-40));d.show();QTest.qWait(25)
    d.grab().save(str(shots/f'lingfeng-v26-about-{lang}.png'));d.browser.verticalScrollBar().setValue(d.browser.verticalScrollBar().maximum());QTest.qWait(20)
    d.grab().save(str(shots/f'lingfeng-v26-about-details-{lang}.png'));d.close();d.deleteLater()
w.dirty=False;w.close();APP.processEvents();assert not any(p.isVisible() for p in (w.melody_window,w.harmony_window,w.score_tools))
folder=Path('output/native-v26');folder.mkdir(exist_ok=True)
(folder/'result.json').write_text(json.dumps(dict(status='passed',version=__version__,native_tests=result.testsRun,qt_callback_errors=errors,
    device_pixel_ratio=APP.primaryScreen().devicePixelRatio(),app_id=APP_ID,foreground_checks=foreground_checks,explorer_thumbnail_clicks_tested=False,show_desktop_shell_command_tested=False,
    checks=['peer HWNDs without native or Qt transient owners','same AppID and separate taskbar previews eligible','main and float native z-order','main minimize leaves floating editors available','two minimize-all / individual-restore cycles','redock and language rebuild ownership','floating score panel restore','number labels on and off screenshots','bilingual About screenshots']),ensure_ascii=False,indent=2),'utf-8')
