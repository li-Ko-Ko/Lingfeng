"""Regression checks through the application's actual Qt controls and Windows MIDI API."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox,QDialog
from PySide6.QtCore import Qt,QPoint,QTimer
from PySide6.QtTest import QTest
from popscore.app import MainWindow,STYLE
from popscore.model import Project,Note,demo_project
from popscore.audio import midi_devices
from popscore.dialogs import SoundSettingsDialog
from popscore.notation import export_pdf

app=QApplication.instance() or QApplication([]);app.setStyle('Fusion');app.setStyleSheet(STYLE)
def fail(*args):raise AssertionError(str(args[1:]))
QMessageBox.warning=fail
w=MainWindow(Project());w.show();app.processEvents();r=w.roll;r.center_pitch(64);app.processEvents()
w.mute_buttons['melody'].click();w.mute_buttons['chords'].click()
w.tool.setCurrentIndex(w.tool.findData('draw'))
for pitch in (60,64,67):
    a=QPoint(round(r.x_at(960)+8),round(r.y_at(pitch)+10));b=QPoint(round(r.x_at(1920)),a.y())
    QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=a);QTest.qWait(310);QTest.mouseMove(r.viewport(),b)
    QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=b);app.processEvents()
assert len(w.project.notes)==3 and {n.start for n in w.project.notes}=={960}
w.grid.setCurrentIndex(w.grid.findData(480));w.grid.triplet_action.trigger();assert r.grid==320 and r.duration==480;w.length.set_triplet(True);assert r.duration==320
w.tool.setCurrentIndex(0)
a=QPoint(round(w.timeline.x_at(400)),12);b=QPoint(round(w.timeline.x_at(1450)),12)
QTest.mousePress(w.timeline,Qt.MouseButton.LeftButton,pos=a);QTest.qWait(310);QTest.mouseMove(w.timeline,b)
QTest.mouseRelease(w.timeline,Qt.MouseButton.LeftButton,pos=b);app.processEvents()
assert r.selection==[[320,1600]]
pos=QPoint(round(r.x_at(2600)),round(r.y_at(72)+10))
QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,pos=pos);app.processEvents()
assert w.playhead==2560 and r.cursor_tick==2560 and r.play_tick is None, (w.playhead,r.cursor_tick,r.play_tick,pos,r.viewport().size())
# Uses the actual WinMM default device, with silent CC7 values for the automated run.
assert midi_devices(), 'This Windows audio integration check requires a MIDI output.'
w.toggle_play();QTest.qWait(100);assert w.transport.playing
w.toggle_play();paused=w.playhead;assert paused>2560 and not w.transport.playing
w.toggle_play();assert w.transport.start_tick==paused
w.mute_buttons['melody'].click();assert w.transport.volumes=={'melody':100,'chords':0}
w.mute_buttons['melody'].click();w.replay();assert w.transport.start_tick==2560
w.stop_to_anchor();assert w.playhead==2560 and r.cursor_tick==2560
w.rewind();assert w.playhead==0 and r.cursor_tick==0
w.loop.setChecked(True);w.roll.selection=[[0,3840]];w.seek(960);w.toggle_play();QTest.qWait(50);w.toggle_play();paused=w.playhead
w.toggle_play();assert w.transport.start_tick==paused;w.stop();w.loop.setChecked(False)
# Settings dialog writes the two independent devices/programs into the project.
def accept_sounds():
    dialog=app.activeModalWidget();assert isinstance(dialog,SoundSettingsDialog)
    dialog.fields['melody'][0].setCurrentIndex(dialog.fields['melody'][0].findData('default'));dialog.fields['chords'][0].setCurrentIndex(dialog.fields['chords'][0].findData('default'));dialog.fields['melody'][1].setCurrentIndex(16);dialog.fields['chords'][1].setCurrentIndex(11);dialog.accept()
QTimer.singleShot(30,accept_sounds);w.sound_settings()
assert w.project.audio['melody']['program']==16 and w.project.audio['chords']['program']==11
w.transport.open();assert w.transport.synth.routes[0] is w.transport.synth.routes[1]
def accept_marker():
    dialog=app.activeModalWidget();dialog.tonic.setCurrentIndex(dialog.tonic.findData(53));dialog.accept()
QTimer.singleShot(30,accept_marker);w.edit_context([[0,w.project.end]]);assert all(w.project.marker_value(i)[2]==53 for i in range(8))
QTimer.singleShot(30,lambda:app.activeModalWidget().accept());w.insert_measure(1)
assert len(w.project.measures)==9 and w.project.marks==[0,1,2]
w.undo();assert len(w.project.measures)==8
w.view_controls.range.setCurrentIndex(1);assert r.pitches==[67,64,60]
w.view_controls.height.setCurrentIndex(w.view_controls.height.findData(32));assert r.row_height==32
for key in ('chords','velocity','navigator','ruler'):w.view_controls.panel_actions[key].setChecked(False)
app.processEvents();assert r.viewport().height()>400
# Minimum supported window width still exposes all controls.
assert not hasattr(w,'context_panel');w.resize(1120,800);app.processEvents()
assert w.width()==1120 and w.view_controls.width()<600
w.dirty=False;w.replace_project(demo_project());w.resize(1420,940)
w.switch_workspace('score');w.perline.setCurrentIndex(w.perline.findData(8));app.processEvents()
assert [len(s.bars) for s in w.score_view.canvas.layout.systems]==[8,8]
w.score_style.setCurrentIndex(w.score_style.findData('compact'));w.edit_toggle.click();app.processEvents()
w.dock_height.setCurrentIndex(w.dock_height.findData(520));app.processEvents()
assert w.score_tools.height()>=500
Path('output/screenshots').mkdir(parents=True,exist_ok=True)
w.grab().save('output/screenshots/compact-eight-bars.png')
export_pdf(w.project,'output/pdf/compact-eight-bars.pdf')
w.perline.setCurrentIndex(w.perline.findData(4));w.project.save('examples/compact-demo.popscore')
w.grab().save('output/screenshots/compact-four-bars.png')
w.dirty=False;w.close();app.processEvents()
print('Revision UI passed: melody polyphony, triplets, snapped range, cursor, pause/replay, live mute, WinMM devices, settings, markers, insertion/undo, compact, height, folding, 8-bar score.')
