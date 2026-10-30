"""Full-window checks for context commands, score picking, themes and transport icons."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt,QPoint,QTimer
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import demo_project
from popscore.notation import export_pdf

app=QApplication.instance() or QApplication([])
def fail(*args):raise AssertionError(str(args[1:]))
QMessageBox.warning=fail
w=MainWindow(demo_project());w.show();app.processEvents();w.set_theme('light')
assert not hasattr(w,'context_panel') and not hasattr(w,'granularity')
assert w.play_button.text()=='' and w.replay_button.text()=='' and w.play_button.kind=='play'
assert w.view_controls.options.parentWidget() is w.editor
# Context menu actions open the real dialogs and broadcast whole measures from a beat-level selection.
w.roll.selection=[[480,1440]];menu=w.roll.timeline_menu(QPoint(round(w.roll.x_at(960)),12))
def accept_context():
    dialog=app.activeModalWidget();dialog.mode.setCurrentText('Aeolian');dialog.accept()
QTimer.singleShot(20,accept_context);next(a for a in menu.actions() if a.text()=='设置所选小节拍号与调性…').trigger()
assert w.project.context_at(480).mode=='Aeolian' and w.project.context_at(3839).mode=='Aeolian' and w.project.context_at(3840).mode=='Ionian'
QTimer.singleShot(20,lambda:app.activeModalWidget().accept());next(a for a in menu.actions() if a.text()=='在此小节后插入…').trigger()
assert len(w.project.measures)==17;w.undo();w.undo()
# Returning to the beginning by double click works even while looping a later selection.
w.mute_buttons['melody'].click();w.mute_buttons['chords'].click();w.seek(1920)
QTest.mouseClick(w.play_button,Qt.MouseButton.LeftButton);QTest.qWait(60)
assert w.play_button.kind=='pause' and w.transport.playing
QTest.mouseClick(w.play_button,Qt.MouseButton.LeftButton);assert w.play_button.kind=='play' and not w.transport.playing
w.roll.selection=[[3840,7680]];w.loop.setChecked(True)
QTest.mouseClick(w.replay_button,Qt.MouseButton.LeftButton);QTest.qWait(30);QTest.mouseClick(w.replay_button,Qt.MouseButton.LeftButton)
QTest.qWait(app.doubleClickInterval()+30);assert w.playhead==0 and not w.transport.playing;w.loop.setChecked(False)
w.mute_buttons['melody'].click();w.mute_buttons['chords'].click()
Path('output/screenshots').mkdir(parents=True,exist_ok=True)
w.roll.center_pitch(58);app.processEvents();w.grab().save('output/screenshots/light-v5.png')
w.set_theme('dark');app.processEvents();w.grab().save('output/screenshots/dark-v5.png')
w.open_harmony(w.project.chords[0].id);app.processEvents();w.harmony_window.grab().save('output/screenshots/dark-harmony-v5.png')
w.harmony_window.hide();w.switch_workspace('score');w.edit_toggle.click();app.processEvents()
w.rowgap.setValue(8);w.system_gap.setValue(0);w.resize_score();app.processEvents()
assert w.score_view.height()>=400 and w.score_view.canvas.layout.systems[0].row_gap==8,(w.score_view.height(),w.score_splitter.sizes(),w.editor.minimumSizeHint(),w.score_view.canvas.layout.systems[0].row_gap)
systems=w.score_view.canvas.layout.systems;assert systems[1].top==systems[0].top+systems[0].height
# A click exactly on a bar edge in the score positions the playhead without editing notes.
canvas=w.score_view.canvas;w.score_view.verticalScrollBar().setValue(0);app.processEvents()
page,rect,bar,points,positions=next(item for item in canvas.layout.hit_times if item[2]==1)
ox,oy=canvas.page_origin(page);pos=QPoint(round(ox+(rect.x()+.5)*canvas.scale),round(oy+(rect.y()+55)*canvas.scale))
count=len(w.project.notes);QTest.mouseClick(canvas,Qt.MouseButton.LeftButton,pos=pos);app.processEvents()
assert w.playhead==3840 and len(w.project.notes)==count
w.grab().save('output/screenshots/dark-score-v5.png')
w.view_controls.panel_actions['chords'].setChecked(False);w.view_controls.range.setCurrentIndex(1)
app.processEvents();w.grab().save('output/screenshots/dark-compact-v5.png')
Path('output/pdf').mkdir(parents=True,exist_ok=True);export_pdf(w.project,'output/pdf/compact-v5.pdf')
# The menu stays valid across theme changes, and the smallest supported window remains usable.
w.set_theme('light');w.resize(1120,800);app.processEvents();assert w.width()==1120
w.visibility_actions['navigator'].setChecked(False);w.switch_workspace('compose');w.visibility_actions['navigator'].trigger();assert w.navigator.isVisible()
w.dirty=False;w.harmony_window.close();w.close();app.processEvents()
print('v0.5 UI passed: context-only controls, single/double transport, score edge picking, spacing/height, both themes, floating editor, options.')
