"""Score context menus share manual-slur validation with the music API."""
import copy,os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication
from lingfeng.engraving.lyrics import apply_range
from lingfeng.music.model import Project,Note
from lingfeng.platform.i18n import set_language,tr
from lingfeng.ui.fonts import ensure_fonts
from lingfeng.ui.score_view import ScoreCanvas

APP=QApplication.instance() or QApplication([]);ensure_fonts()


class SlurMenuTests(unittest.TestCase):
    def setUp(self):
        set_language('zh');self.widgets=[]

    def tearDown(self):
        for widget in self.widgets:widget.close();widget.deleteLater()
        APP.processEvents();set_language('zh')

    def project(self):
        p=Project();p.notes=[Note(t,480,k) for t,k in ((0,60),(480,62),(960,64),(1440,65))]
        return p

    def menu(self,p,ids):
        canvas=ScoreCanvas(p);self.widgets.append(canvas);canvas.resize(780,900);canvas.show();canvas.set_selection_unit('note');canvas.selected_notes=set(ids);canvas.grab();APP.processEvents()
        page,rect,_=next(hit for hit in canvas.layout.hit_notes if hit[2] in ids);x,y=canvas.page_origin(page)
        menu=canvas.context_menu(QPoint(round(x+rect.center().x()*canvas.scale),round(y+rect.center().y()*canvas.scale)));self.widgets.append(menu)
        action=next(a for a in menu.actions() if a.text()==tr('添加连音弧'))
        return canvas,menu,action

    def test_conflicting_lyric_span_disables_manual_slur_and_explains_why(self):
        p=self.project();apply_range(p,'春/-/s/s',0,1,replace=True);before=copy.deepcopy(p.to_dict())
        canvas,menu,action=self.menu(p,[n.id for n in p.notes[:2]])
        self.assertFalse(action.isEnabled());self.assertEqual(action.toolTip(),tr('歌词连音优先：所选连音弧与歌词 /- 连音冲突。'))
        emitted=[];canvas.commandRequested.connect(lambda *args:emitted.append(args));action.trigger()
        self.assertFalse(emitted);self.assertEqual(p.to_dict(),before)

    def test_adjacent_manual_span_remains_enabled_and_emits_selected_note_ids(self):
        p=self.project();apply_range(p,'春/-/s/s',0,1,replace=True);ids={n.id for n in p.notes[1:3]}
        canvas,menu,action=self.menu(p,ids);self.assertTrue(action.isEnabled());self.assertEqual(action.toolTip(),action.text())
        emitted=[];canvas.commandRequested.connect(lambda *args:emitted.append(args));action.trigger()
        self.assertEqual(len(emitted),1);self.assertEqual(emitted[0][0],'slur');self.assertEqual(set(emitted[0][1]['note_ids']),ids)

    def test_simultaneous_notes_alone_cannot_create_a_phrase_and_are_not_lyric_conflicts(self):
        p=self.project();p.notes.append(Note(0,480,48));canvas,menu,action=self.menu(p,[p.notes[0].id,p.notes[-1].id])
        self.assertFalse(action.isEnabled());self.assertEqual(action.toolTip(),action.text())

    def test_menu_uses_canvas_snapshot_until_presentation_is_synced(self):
        live=self.project();ids={n.id for n in live.notes[:2]};canvas,menu,action=self.menu(live,ids)
        self.assertTrue(action.isEnabled());apply_range(live,'春/-/s/s',0,1,replace=True)
        menu.close();menu.deleteLater();self.widgets.remove(menu)
        page,rect,_=next(hit for hit in canvas.layout.hit_notes if hit[2] in ids);x,y=canvas.page_origin(page)
        pos=QPoint(round(x+rect.center().x()*canvas.scale),round(y+rect.center().y()*canvas.scale))
        unchanged=canvas.context_menu(pos);self.widgets.append(unchanged)
        self.assertTrue(next(a for a in unchanged.actions() if a.text()==tr('添加连音弧')).isEnabled())
        canvas.sync_presentation(live);canvas.grab();updated=canvas.context_menu(pos);self.widgets.append(updated)
        self.assertFalse(next(a for a in updated.actions() if a.text()==tr('添加连音弧')).isEnabled())


if __name__=='__main__':unittest.main()
