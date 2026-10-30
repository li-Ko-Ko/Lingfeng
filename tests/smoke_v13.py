"""Real Qt/WinMM walkthrough and all-page PDF fixtures for v0.13."""
import os,json,copy
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord
from popscore.lyrics import apply_section,matching_issues,put
from popscore.notation import export_pdf
from popscore.midi import export_midi
from popscore.lyricpanel import LyricsGateDialog
from popscore.dialogs import ChordPreferenceDialog

app=QApplication([]);app.setStyle('Fusion')
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
out=Path('output/screenshots');out.mkdir(exist_ok=True,parents=True)
p=Project();p.title='伶风 · 风中的节奏';p.author='原创示例 · 歌词起点与说唱'
p.notes=[Note(960,720,60),Note(1680,240,62),Note(1920,480,64),Note(2400,960,67),
         Note(3840,960,67),Note(3840,960,60),Note(4800,480,60),Note(5280,720,62),Note(6000,240,64),Note(6720,960,65)]
p.notes.extend(Note(14400+i*60,60 if i%3 else 90,60+i%7) for i in range(12))
p.notes.extend(Note(t,480,60+(i%5)*2) for i,t in enumerate(range(15360,30720,960)))
p.chords=[Chord(i*3840,3840,48 if i%2==0 else 53,'maj7' if i%2 else '',pattern='up' if i==0 else 'offbeat' if i==1 else 'block') for i in range(8)]
apply_section(p,'我/64.爱/64你/64',0);apply_section(p,'风 _ 轻 唱',960);apply_section(p,'be-fore the _ dawn',3840)
apply_section(p,'夜/16里/16星/16光/16',7680);p.validate();assert not matching_issues(p)
p.save('examples/lingfeng-lyrics.lfs')
w=MainWindow(p);w.show();w.resize(1380,1000);w.change_language('zh',False);w.set_theme('light')
for mute in w.mute_buttons.values():mute.setChecked(True)
w.open_harmony();QTest.qWait(70);w.title_bar.grab().save(str(out/'lingfeng-v13-title-zh.png'))
w.grab().save(str(out/'lingfeng-v13-compose.png'))
w.playhead=960;w.toggle_play();QTest.qWait(40);w.seek(4800);QTest.qWait(40)
assert w.transport.playing and w.play_anchor==4800 and w.roll.anchor_tick==4800
w.stop();w.seek(1920);assert not w.transport.playing
menu=w.chord_lane.context_menu(QPoint(round(w.chord_lane.x_at(480)),20));menu.popup(w.chord_lane.mapToGlobal(QPoint(90,20)));QTest.qWait(30);menu.grab().save(str(out/'lingfeng-v13-chord-menu.png'))
for name in ('root_menu','quality_menu','inversion_menu'):
    sub=getattr(menu,name);sub.popup(menu.pos()+QPoint(menu.width(),0));QTest.qWait(30);sub.grab().save(str(out/f'lingfeng-v13-{name}.png'));sub.hide()
menu.hide();pref=ChordPreferenceDialog(w);pref.show();QTest.qWait(30);pref.grab().save(str(out/'lingfeng-v13-chord-preferences.png'));pref.close()
assert w.switch_workspace('score');w.batch_lyrics();w.lyric_panel.section.setCurrentIndex(1);QTest.qWait(60)
w.grab().save(str(out/'lingfeng-v13-lyrics-tab.png'))
w.edit_toggle.setChecked(False);w.toggle_editor();w.seek(0);export_midi(w.project,'tmp/v13-before.mid')
pages={}
for style in ('spatial','compact','traditional'):
    w.project.notation['style']=style;w.refresh();QTest.qWait(40)
    pages[style]=export_pdf(w.project,f'output/pdf/lingfeng-v13-{style}.pdf')
    w.grab().save(str(out/f'lingfeng-v13-{style}.png'))
w.project.notation['style']='spatial';w.project.notation['show_scale_lines']=True;w.project.notation['font_size']=26;w.refresh()
pages['all-lines']=export_pdf(w.project,'output/pdf/lingfeng-v13-all-lines.pdf')
w.grab().save(str(out/'lingfeng-v13-all-lines-large-font.png'))
export_midi(w.project,'tmp/v13-after.mid');assert Path('tmp/v13-before.mid').read_bytes()==Path('tmp/v13-after.mid').read_bytes()
w.project.notation['show_scale_lines']=False;w.project.notation['font_size']=15;w.refresh()
put(w.project,100,'错',1);w.refresh();gate=LyricsGateDialog(w);gate.show();QTest.qWait(40);assert not gate.enter.isEnabled();gate.grab().save(str(out/'lingfeng-v13-lyric-validation.png'));gate.close()
w.project.notation['lyric_events']=[e for e in w.project.notation['lyric_events'] if not(e['tick']==100 and e.get('verse')==1)];w.refresh()
w.change_language('en',False);w.set_theme('dark');w.switch_workspace('compose');w.resize(680,1000);QTest.qWait(60)
w.title_bar.grab().save(str(out/'lingfeng-v13-title-en.png'));w.grab().save(str(out/'lingfeng-v13-dark-narrow-en.png'))
w.melody_window.setFloating(True);w.harmony_window.setFloating(True);QTest.qWait(40)
w.harmony_window.grab().save(str(out/'lingfeng-v13-harmony-floating.png'))
w.switch_workspace('score');w.batch_lyrics();w.score_tools.setFloating(True);w.score_tools.resize(820,560);QTest.qWait(45)
w.score_tools.grab().save(str(out/'lingfeng-v13-lyrics-floating-en.png'))
Path('output/v13-ui-check.json').write_text(json.dumps(dict(status='passed',pdf_pages=pages,real_winmm_seek=True,paused_seek=True,lyrics_onsets=True,midi_unchanged=True),indent=2),'utf-8')
w.dirty=False;w.close();app.processEvents();print('v0.13 UI, actual WinMM seek, four score PDFs, lyric matching, menus and bilingual narrow layouts passed.')
