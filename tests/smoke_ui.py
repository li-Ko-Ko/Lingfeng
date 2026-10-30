"""Exercise the app's own Qt widgets, without controlling other applications."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint,QTimer
from PySide6.QtTest import QTest
from popscore.app import MainWindow,STYLE
from popscore.model import Project,Note,PPQ,demo_project
from popscore.notation import export_pdf,ScoreLayout
from popscore.midi import export_midi

app=QApplication.instance() or QApplication([]);app.setStyle('Fusion');app.setStyleSheet(STYLE)
w=MainWindow(Project());w.show();app.processEvents();w.roll.center_pitch(60);app.processEvents()
# Double click adds a real note using the actual viewport hit mapping.
x=round(w.roll.x_at(960)+3);y=round(w.roll.y_at(60)+11)
QTest.mouseDClick(w.roll.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(x,y));app.processEvents()
assert len(w.project.notes)==1 and w.project.notes[0].pitch==60
assert w.project.notes[0].start==960
# Drag and resize use the viewport's real press/move/release handlers.
QTest.mousePress(w.roll.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(x+10,y))
QTest.mouseMove(w.roll.viewport(),QPoint(x+10+78,y-w.roll.row_height));QTest.mouseRelease(w.roll.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(x+10+78,y-w.roll.row_height));app.processEvents()
assert (w.project.notes[0].start,w.project.notes[0].pitch)==(1920,61)
w.undo();assert (w.project.notes[0].start,w.project.notes[0].pitch)==(960,60)
w.undo();assert not w.project.notes
w.redo();assert len(w.project.notes)==1
# Context changes don't change sound; paper spelling doesn't change the roll.
QTimer.singleShot(20,lambda:(app.activeModalWidget().mode.setCurrentText('Aeolian'),app.activeModalWidget().accept()));w.edit_context(w.roll.selection);assert w.project.context_at(0).mode=='Aeolian'
assert w.project.notes[0].pitch==60
nid=w.project.notes[0].id;w.set_spelling(nid,True);assert w.project.notes[0].flat
w.switch_workspace('score');app.processEvents();assert not w.editor.isVisible()
w.edit_toggle.click();app.processEvents();assert w.editor.isVisible()
assert not hasattr(w,'range_up') and not w.roll.panels['velocity']
w.score_bar_clicked(2);assert w.roll.selection==[[7680,11520]]
w.switch_workspace('compose');app.processEvents();assert w.editor.isVisible()
assert w.view_controls.isVisible()
# Generate a reference session and screenshots from real Qt rendering.
w.dirty=False;w.replace_project(demo_project());w.roll.center_pitch(58);app.processEvents()
Path('output/screenshots').mkdir(parents=True,exist_ok=True)
w.grab().save('output/screenshots/compose.png')
w.switch_workspace('score');app.processEvents();w.grab().save('output/screenshots/score.png')
w.edit_toggle.click();app.processEvents();w.grab().save('output/screenshots/score-edit.png')
Path('output/pdf').mkdir(parents=True,exist_ok=True);Path('examples').mkdir(exist_ok=True)
w.project.save('examples/demo.popscore');export_midi(w.project,'examples/demo.mid')
pages=export_pdf(w.project,'output/pdf/demo-score.pdf')
print('UI smoke passed; demo PDF pages:',pages)
w.dirty=False;w.close();app.processEvents()
