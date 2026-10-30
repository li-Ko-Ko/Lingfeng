"""Windows tool ownership, narrow floating mixers and transport rendering."""
import os,sys,json,time,ctypes,statistics
os.environ['QT_QPA_PLATFORM']='windows'
from pathlib import Path
from unittest.mock import patch
from ctypes import wintypes
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord,Measure
from popscore import theme

app=QApplication([]);app.setStyle('Fusion');errors=[]
def error_hook(typ,value,tb):errors.append(str(value));sys.__excepthook__(typ,value,tb)
sys.excepthook=error_hook
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
MainWindow.save_preferences=lambda self:None
class Synth:
    def __init__(self):self.events=[]
    def send(self,*args):self.events.append(args)
    def stop(self):pass
    def close(self):pass

p=Project();p.title='连续长音与独立卷帘';p.measures=[Measure() for _ in range(64)];p.contexts[0].end=p.end
p.notes=[Note(b*3840+i*480,420,60+(i%4)*2) for b in range(64) for i in range(8)]
p.notes=[n for n in p.notes if n.start>=7680]+[Note(960,5760,60),Note(2400,2880,64)]
p.chords=[Chord(b*3840,3840,48 if b%2==0 else 55,pattern='up') for b in range(64)]
p.chords[0].notes=[Note(960,2880,60)];p.chords[1].notes=[Note(0,3840,60)]
w=MainWindow(p);w.change_language('zh',False);theme.set_roll_coloring({});w.set_theme('dark');w.show()
area=app.primaryScreen().availableGeometry();w.resize(min(1260,area.width()-40),area.height()-60);w.timer.stop();w.autosave.stop();w.open_harmony();w.roll.center_pitch(62)
w.transport.synth=Synth();w.follow_playhead.setChecked(False);w.roll.selection=[];w.roll.refresh();QTest.qWait(50)
shots=Path('output/screenshots');shots.mkdir(parents=True,exist_ok=True)
w.grab().save(str(shots/'lingfeng-v24-continuous-notes-zh.png'))
hr=w.harmony_window.roll;hr.center_pitch(60);hr.selection=[];hr.refresh();app.processEvents()
img=hr.viewport().grab().toImage();ratio=img.devicePixelRatio();x=hr.x_at(3840)
for y in (hr.y_at(60)+hr.row_height/2,hr.y_at(60)+4):
    expected={theme.roll_color(hr.category(60,t),'note').name() for t in (3839,3840)}
    assert all(img.pixelColor(round(xx*ratio),round(y*ratio)).name() in expected for xx in range(round(x)-3,round(x)+4))
hr.viewport().grab().save(str(shots/'lingfeng-v24-joined-chord-notes.png'))
print('native: draw and zoom',flush=True)
# A new long note starts in empty space but intersects an existing note later.
r=w.roll;r.tool='draw';r.duration=1920;r.center_pitch(64);app.processEvents()
point=QPoint(round(r.x_at(1440)+5),round(r.y_at(64)+r.row_height/2))
QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,pos=point);app.processEvents()
assert [(n.start,n.end) for n in w.project.notes if n.pitch==64 and n.start<7680]==[(1440,3360),(3360,5280)]
w.undo();w.roll.tool='smart'
lane=w.harmony_window.roll.lane;point=QPointF(300,20);before=lane.editor.zoom
app.sendEvent(lane,QWheelEvent(point,QPointF(lane.mapToGlobal(point.toPoint())),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.ShiftModifier,Qt.ScrollPhase.NoScrollPhase,False))
assert w.roll.zoom==w.main_roll.zoom==w.harmony_window.roll.zoom==before*1.2
print('native: transport benchmark',flush=True)
w.transport.play(w.project,0,volumes={'melody':0,'chords':0});w.play_anchor=0;w.transport_active=True
widgets=[w.roll,w.harmony_window.roll,w.timeline,w.navigator,w.harmony_window.roll.lane]
w.show_cursor(0);app.processEvents();counts=[x.cache_renders for x in widgets]
durations=[];positions=[];worker=w.transport.thread
for i in range(90):
    start=time.perf_counter();w.playback_tick();app.processEvents()
    durations.append((time.perf_counter()-start)*1000);positions.append(w.roll.cursor_tick)
    QTest.qWait(16)
assert all(a<=b for a,b in zip(positions,positions[1:]));assert positions[-1]>1800
after_counts=[x.cache_renders for x in widgets];assert after_counts==counts
w.melody_volume.sliders['melody'].setValue(49);assert w.transport.thread is worker and w.transport.playing
assert w.harmony_window.volume_controls.sliders['melody'].value()==49
w.stop();w.seek(0)
print('native: grouped windows and mixers',flush=True)
w.melody_window.setFloating(True);w.harmony_window.setFloating(True);app.processEvents()
user=ctypes.windll.user32;user.GetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int];user.GetWindowLongW.restype=wintypes.LONG
user.GetWindow.argtypes=[wintypes.HWND,ctypes.c_uint];user.GetWindow.restype=wintypes.HWND
styles=[]
for pane,roll,sync,transport in w.view_panes():
    pane.resize(min(1000,area.width()-60),min(640,area.height()-70));pane.move(area.x()+20,area.y()+20);pane.show();pane.raise_();app.processEvents()
    hwnd=wintypes.HWND(int(pane.winId()));style=user.GetWindowLongW(hwnd,-20);styles.append(style)
    assert style&0x40000 and not style&0x80  # WS_EX_APPWINDOW exposes a thumbnail under the common process AppID.
    assert user.GetWindow(hwnd,4)==int(w.winId())  # GW_OWNER

    # Native hit testing must leave title controls clickable at non-unit DPI.
    from popscore.windowing import resize_hit,APP_ID
    for button in pane.title_bar.buttons:
        assert resize_hit(pane,button.mapTo(pane,button.rect().center()))==0
    QTest.mouseClick(pane.title_bar.maximize_button,Qt.MouseButton.LeftButton);QTest.qWait(35);assert pane.isMaximized()
    QTest.mouseClick(pane.title_bar.maximize_button,Qt.MouseButton.LeftButton);QTest.qWait(35);assert not pane.isMaximized()
    QTest.mouseClick(pane.title_bar.minimize_button,Qt.MouseButton.LeftButton);QTest.qWait(35);assert pane.isMinimized()
    pane.showNormal();QTest.qWait(30)
    dark=ctypes.c_int();ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd,20,ctypes.byref(dark),ctypes.sizeof(dark));assert dark.value==1

    assert transport.options.geometry().right()<=transport.width() and transport.width()-transport.options.geometry().right()<8
    roll.center_pitch(60 if roll is w.roll else 52);QTest.qWait(20)
    pane.grab().save(str(shots/f'lingfeng-v24-{pane.key}-floating-zh.png'))
w.melody_chords_action.setChecked(False);assert not w.roll.panels['chords']
w.melody_volume.sliders['chords'].setValue(66);assert w.volume_sliders['chords'].value()==66==w.harmony_window.volume_controls.sliders['chords'].value()
w.melody_volume.mutes['melody'].click();assert w.harmony_window.volume_controls.mutes['melody'].isChecked()==w.mute_buttons['melody'].isChecked()
w.change_language('en',False);app.processEvents();assert not w.floating_melody_chords
for pane,roll,sync,transport in w.view_panes():
    pane.resize(620,580);pane.move(area.x()+20,area.y()+20);pane.raise_();QTest.qWait(30)
    assert transport.play.x()>=0 and transport.options.geometry().right()<=transport.width()
    volume=w.melody_volume if pane is w.melody_window else w.harmony_window.volume_controls
    assert volume.isVisible() and volume.sliders['chords'].value()==66
    pane.grab().save(str(shots/f'lingfeng-v24-{pane.key}-narrow-en.png'))
QTest.mouseClick(w.harmony_window.title_bar.close_button,Qt.MouseButton.LeftButton);QTest.qWait(50);assert not w.harmony_window.isFloating() and w.visibility_actions['harmony'].isChecked()
QTest.mouseClick(w.melody_window.title_bar.close_button,Qt.MouseButton.LeftButton);QTest.qWait(50);assert not w.visibility_actions['melody'].isChecked()
w.melody_window.setFloating(False);w.coloring_actions['melody','match'].setChecked(False);w.coloring_actions['harmony','scale'].setChecked(False)
assert not theme.ROLL_COLORING['melody']['match'] and not theme.ROLL_COLORING['harmony']['scale']
identity=ctypes.c_wchar_p();assert ctypes.windll.shell32.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(identity))==0
assert identity.value=='Lingfeng.ForPopMusic';ctypes.windll.ole32.CoTaskMemFree(identity)
w.set_theme('light');app.processEvents();w.grab().save(str(shots/'lingfeng-v24-light-zh.png'))
assert not errors,errors
report=dict(status='passed',dpi_scale=w.devicePixelRatioF(),native_draw_overwrite=True,chord_lane_shift_zoom=True,
    app_window_styles=styles,common_application_id=True,right_aligned_transport=True,narrow_english_windows=True,
    joined_chord_note_pixels=True,native_title_buttons=True,dark_dwm_frame=True,
    shared_volume_mute_controls=True,melody_lane_option_preserved=True,coloring_settings=True,
    playback_frames=len(positions),playback_static_rerenders=[x-y for x,y in zip(after_counts,counts)],
    playback_frame_ms_median=round(statistics.median(durations),3),playback_frame_ms_p95=round(sorted(durations)[int(len(durations)*.95)],3),
    playback_monotonic=True,benchmark_melody_notes=len(p.notes),benchmark_chord_notes=len(p.harmony_notes()),qt_callback_errors=errors)
out=Path('output/native-v24');out.mkdir(parents=True,exist_ok=True);(out/'result.json').write_text(json.dumps(report,indent=2),'utf-8')
w.dirty=False;w.close();app.processEvents();print(json.dumps(report))
