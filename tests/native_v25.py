"""Run real Windows keyboard/focus checks, then capture both localized interfaces."""
import os,sys,json,unittest
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from tests.test_v25 import EditorHistoryTests,APP
from tests import test_v25
from popscore.app import MainWindow
from popscore.model import demo_project
from popscore.helpview import HelpDialog
from popscore import __version__

errors=[]
def hook(typ,value,tb):errors.append(str(value));sys.__excepthook__(typ,value,tb)
sys.excepthook=hook
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
suite=unittest.defaultTestLoader.loadTestsFromTestCase(EditorHistoryTests)
result=unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful() or errors:raise SystemExit(1)

MainWindow.save_preferences=lambda self:None
APP.setStyle('Fusion');w=MainWindow(demo_project());w.show();w.timer.stop();w.autosave.stop()
area=APP.primaryScreen().availableGeometry();out=Path('output/screenshots');out.mkdir(parents=True,exist_ok=True)
for lang in ('zh','en'):
    w.change_language(lang,False);w.set_theme('dark' if lang=='zh' else 'light')
    w.switch_workspace('score');w.edit_toggle.setChecked(False);w.toggle_editor()
    w.resize(min(1080,area.width()-40),max(560,area.height()-50));w.move(area.x()+20,area.y()+20);w.activateWindow()
    w.note_font.setValue(19);QTest.qWait(35)
    assert w.note_font.isVisible() and w.project.notation['font_size']==19 and 0<w.score_view.canvas.layout.glyph_scale<=19/15
    w.grab().save(str(out/f'lingfeng-v25-score-font-{lang}.png'))
    w.resize(620,w.height());QTest.qWait(35)
    assert w.note_font.isVisible() and w.note_font.parentWidget().rect().contains(w.note_font.geometry())
    w.grab().save(str(out/f'lingfeng-v25-score-narrow-{lang}.png'))
    dialog=HelpDialog(w,True);dialog.resize(min(880,area.width()-40),min(760,area.height()-40));dialog.move(area.x()+20,area.y()+20);dialog.show();QTest.qWait(35)
    dialog.grab().save(str(out/f'lingfeng-v25-about-{lang}.png'));dialog.close();dialog.deleteLater()

w.switch_workspace('compose');w.open_harmony();w.harmony_window.setFloating(True)
pane=w.harmony_window;pane.resize(min(980,area.width()-40),min(620,area.height()-40));pane.move(area.x()+20,area.y()+20)
pane.show();pane.activateWindow();r=pane.roll;r.setFocus();w.select_element('notes',r);r.selected_ids={n.id for n in r.notes[:3]};r.center_pitch(55);r.refresh();QTest.qWait(35)
QTest.keyClick(r,Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier);APP.processEvents();assert w.clipboard_kind=='notes'
pane.grab().save(str(out/'lingfeng-v25-floating-shortcuts-en.png'))
w.dirty=False;w.close();APP.processEvents()
folder=Path('output/native-v25');folder.mkdir(exist_ok=True)
(folder/'result.json').write_text(json.dumps(dict(status='passed',version=__version__,native_tests=result.testsRun,qt_callback_errors=errors,
    device_pixel_ratio=APP.primaryScreen().devicePixelRatio(),system_text_clipboard_available=test_v25.SYSTEM_TEXT_CLIPBOARD_AVAILABLE,
    checks=['floating copy/cut/paste/select all/save','marquee copy','undo and redo focus editor window','dock relocation and workspace restore','score floating tab restore','text key routing and local undo isolation','language rebuild preserves history','playback worker and anchor preserved','visible score font control at 620px','bilingual About screenshots']),ensure_ascii=False,indent=2),'utf-8')
