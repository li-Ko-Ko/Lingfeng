import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtTest import QTest
from lingfeng.music.model import Project, Note, BACKGROUND_COLORS, NOTE_COLORS, demo_project
from lingfeng.ui.piano_roll import PianoRoll, KEY_W
from lingfeng.ui.controls import IconButton, RollViewControls
from lingfeng.engraving.notation import ScoreLayout
from lingfeng.ui.theme import color, apply_theme

APP=QApplication.instance() or QApplication([])


class GestureTests(unittest.TestCase):
    def setUp(self):
        self.p=Project();self.r=PianoRoll(self.p);self.r.resize(1000,640);self.r.show();APP.processEvents();self.r.center_pitch(60);APP.processEvents()
        self.r.tool='draw';self.deleted=[];self.added=[];self.moved=[]
        self.r.noteAdded.connect(self.add);self.r.noteDeleted.connect(self.delete);self.r.noteMoved.connect(self.move)
        self.r.notesResized.connect(lambda notes:[self.move(n) for n in notes])
    def tearDown(self):self.r.close();apply_theme(False);APP.processEvents()
    def add(self,n):self.added.append(n);self.p.add_note(n);self.r.set_project(self.p)
    def delete(self,nid):self.deleted.append(nid);self.p.notes=[n for n in self.p.notes if n.id!=nid];self.r.set_project(self.p)
    def move(self,n):self.moved.append(n);self.p.add_note(n);self.r.set_project(self.p)
    def point(self,tick,pitch=60,dx=8,dy=10):return QPoint(round(self.r.x_at(tick)+dx),round(self.r.y_at(pitch)+dy))
    def seed(self):
        n=Note(960,960,60);self.p.add_note(n);self.r.set_project(self.p);APP.processEvents();return n
    def drag(self,a,b,hold=True):
        QTest.mousePress(self.r.viewport(),Qt.MouseButton.LeftButton,pos=a)
        if hold:QTest.qWait(310)
        QTest.mouseMove(self.r.viewport(),b);QTest.mouseRelease(self.r.viewport(),Qt.MouseButton.LeftButton,pos=b);APP.processEvents()

    def test_empty_click_and_grid_edges_never_insert(self):
        self.r.tool='smart'
        for pos in [self.point(0),self.point(240,dx=0),self.point(480,dy=0)]:
            QTest.mouseClick(self.r.viewport(),Qt.MouseButton.LeftButton,pos=pos)
            self.assertEqual(self.p.notes,[]);self.assertEqual(self.r.cursor_tick%self.r.grid,0)
        for pos in [self.point(240,dx=0),self.point(480,dy=0)]:
            QTest.mouseDClick(self.r.viewport(),Qt.MouseButton.LeftButton,pos=pos)
            self.assertEqual(self.p.notes,[])

    def test_double_click_cell_and_hold_drag_input(self):
        QTest.mouseDClick(self.r.viewport(),Qt.MouseButton.LeftButton,pos=self.point(0));APP.processEvents()
        self.assertEqual((self.p.notes[0].start,self.p.notes[0].duration),(0,240))
        self.drag(self.point(1920),self.point(2880,dx=0))
        self.assertEqual([(n.start,n.duration) for n in self.p.notes],[(0,240),(1920,960)])
        self.assertEqual(self.r.note_duration(4000),960)

    def test_note_click_selects_and_double_click_deletes(self):
        self.r.tool='smart';n=self.seed();pos=self.point(1200)
        QTest.mouseClick(self.r.viewport(),Qt.MouseButton.LeftButton,pos=pos);APP.processEvents()
        self.assertEqual(self.deleted,[]);self.assertEqual(self.r.selected_ids,{n.id})
        QTest.mouseDClick(self.r.viewport(),Qt.MouseButton.LeftButton,pos=pos);QTest.mouseRelease(self.r.viewport(),Qt.MouseButton.LeftButton,pos=pos)
        self.assertEqual(self.p.notes,[])

    def test_hold_middle_moves_without_delete(self):
        self.seed();a=self.point(1200);self.drag(a,QPoint(a.x()+78,a.y()-22))
        self.assertEqual((self.p.notes[0].start,self.p.notes[0].pitch),(1920,61));self.assertFalse(self.deleted)

    def test_hold_edges_resize_both_directions(self):
        self.seed();a=self.point(1920,dx=-3);self.drag(a,self.point(2400,dx=0));self.assertEqual(self.p.notes[0].end,2400)
        a=self.point(960,dx=2);self.drag(a,self.point(1440,dx=0));self.assertEqual((self.p.notes[0].start,self.p.notes[0].end),(1440,2400))
        a=self.point(1440,dx=2);self.drag(a,self.point(960,dx=0));self.assertEqual((self.p.notes[0].start,self.p.notes[0].end),(960,2400))

    def test_fast_drag_moves_and_draw_release_without_movement_deletes(self):
        n=self.seed();a=self.point(1200);self.drag(a,QPoint(a.x()+70,a.y()),False)
        self.assertEqual(self.p.notes[0].start,1920);self.assertFalse(self.deleted);a=self.point(2160)
        QTest.mousePress(self.r.viewport(),Qt.MouseButton.LeftButton,pos=a);QTest.qWait(310)
        QTest.mouseRelease(self.r.viewport(),Qt.MouseButton.LeftButton,pos=a);self.assertEqual(self.deleted,[n.id])

    def test_header_and_unused_vertical_space_are_not_notes(self):
        self.seed();self.r.set_compact(True);APP.processEvents()
        below=QPoint(round(self.r.x_at(2400)+8),self.r.ruler_height+3*self.r.row_height)
        self.drag(below,QPoint(below.x()+78,below.y()));self.assertEqual(len(self.p.notes),1)
        self.assertIsNone(self.r.note_hit(QPointF(self.r.x_at(1200),10)))

    def test_options_owns_visibility_menu_and_context_commands(self):
        controls=RollViewControls(self.r);APP.processEvents()
        self.assertEqual(controls.options.menu().actions()[0].menu(),controls.visibility_menu)
        self.assertFalse(self.r.panels['velocity']);controls.panel_actions['velocity'].trigger();self.assertTrue(self.r.panels['velocity'])
        menu=self.r.timeline_menu(QPoint(200,10));labels=[a.text() for a in menu.actions()]
        for text in ['设置所选小节拍号与调性…','在此小节前插入…','在此小节后插入…']:self.assertIn(text,labels)
        for text in ['选区单位','保存选区分组…','调用选区分组']:self.assertNotIn(text,labels)
        controls.close()

    def test_replay_single_and_rapid_double_are_distinct(self):
        button=IconButton('replay');button.show();APP.processEvents();single=[];double=[]
        button.activated.connect(lambda:single.append(1));button.doubleActivated.connect(lambda:double.append(1))
        QTest.mouseClick(button,Qt.MouseButton.LeftButton);QTest.qWait(APP.doubleClickInterval()+30)
        self.assertEqual((len(single),len(double)),(1,0))
        QTest.mouseClick(button,Qt.MouseButton.LeftButton);QTest.qWait(40);QTest.mouseClick(button,Qt.MouseButton.LeftButton);QTest.qWait(APP.doubleClickInterval()+30)
        self.assertEqual((len(single),len(double)),(2,1))
        QTest.mouseClick(button,Qt.MouseButton.LeftButton);QTest.mouseDClick(button,Qt.MouseButton.LeftButton);QTest.mouseRelease(button,Qt.MouseButton.LeftButton);QTest.qWait(APP.doubleClickInterval()+30)
        self.assertEqual((len(single),len(double)),(3,2));button.close()

    def test_score_spacing_and_print_colors_are_independent(self):
        p=demo_project();p.notation.update(row_gap=6,system_gap=0);layout=ScoreLayout(p)
        self.assertEqual(layout.systems[1].top,layout.systems[0].top+layout.systems[0].height)
        p.notation['system_gap']=24;other=ScoreLayout(p);self.assertEqual(other.systems[1].top-layout.systems[1].top,24)
        apply_theme(True);image=QImage(900,1273,QImage.Format.Format_RGB32);painter=QPainter(image);layout.draw(painter,0);painter.end()
        self.assertEqual(image.pixelColor(10,10).name(),'#ffffff')
        painter=QPainter(image);layout.draw(painter,0,dark=True);painter.end();self.assertEqual(image.pixelColor(10,10).name(),'#17202c')

    def test_dark_note_contrast_increases_for_outside_notes(self):
        def lum(c):
            v=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in (c.redF(),c.greenF(),c.blueF())]
            return sum(a*b for a,b in zip(v,(.2126,.7152,.0722)))
        keys=['both','scale','chord','other'];background=[lum(color(BACKGROUND_COLORS[k],True)) for k in keys]
        ratios=[(lum(color(NOTE_COLORS[k],True))+.05)/(lum(color(BACKGROUND_COLORS[k],True))+.05) for k in keys]
        self.assertEqual(background,sorted(background,reverse=True));self.assertEqual(ratios,sorted(ratios));self.assertGreater(min(ratios),3)


if __name__=='__main__':unittest.main()
