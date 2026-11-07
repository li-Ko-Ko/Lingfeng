"""Section jump menus and unlabeled overview boundaries."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPoint,Qt,QEvent
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Project,Note,PPQ
from lingfeng.platform import i18n
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.piano_roll import KEY_W

APP=QApplication.instance() or QApplication([])


class SectionNavigationTests(unittest.TestCase):
    def setUp(self):
        self.language=i18n.LANGUAGE
        self.temp=tempfile.TemporaryDirectory(dir='tmp')
        self.paths=patch('lingfeng.ui.main_window.user_data_dir',return_value=Path(self.temp.name));self.paths.start()
        self.saving=patch.object(MainWindow,'save_preferences');self.saving.start()
        p=Project();p.change_meter(2,3,4);p.notes=[Note(0,480,60)]
        p.measures[0].section='intro';p.measures[3].section='Verse';p.measures[6].section='Verse';p.measures[7].section='Outro'
        self.w=MainWindow(p);self.w.change_language('zh',False)
        self.w.timer.stop();self.w.autosave.stop();self.w.resize(1200,900);self.w.show();APP.processEvents()

    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater()
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()
        self.saving.stop();self.paths.stop();self.temp.cleanup();i18n.set_language(self.language)

    def menu(self,roll=None):
        roll=roll or self.w.roll
        return roll.timeline_menu(QPoint(round(roll.x_at(100)),10))

    def test_assignment_and_jump_are_separate_entries_with_repeated_names(self):
        for language in ('zh','en'):
            self.w.change_language(language,False);APP.processEvents();menu=self.menu()
            try:
                self.assertEqual([a.text() for a in menu.actions()][1:3],[i18n.tr('段落标识'),i18n.tr('跳转小节')])
                self.assertIn('chorus',[a.text() for a in menu.section_menu.actions()])
                actions=menu.section_jump_menu.actions()
                self.assertEqual([a.data() for a in actions],[0,3,6,7])
                self.assertEqual([a.text() for a in actions],[i18n.tr('{0} · 第 {1} 小节',name,index+1) for name,index in [('intro',0),('verse',3),('verse',6),('outro',7)]])
            finally:menu.deleteLater()

    def test_assignment_still_changes_markers_and_jump_menu_refreshes(self):
        menu=self.menu()
        next(a for a in menu.section_menu.actions() if a.text()=='chorus').trigger()
        self.assertEqual(self.w.project.measures[0].section,'chorus');menu.deleteLater()
        menu=self.menu();self.assertEqual(menu.section_jump_menu.actions()[0].text(),i18n.tr('{0} · 第 {1} 小节','chorus',1))
        menu.section_menu.actions()[0].trigger();self.assertEqual(self.w.project.measures[0].section,'');menu.deleteLater()
        menu=self.menu();self.assertEqual([a.data() for a in menu.section_jump_menu.actions()],[3,6,7]);menu.deleteLater()

    def test_unmarked_project_shows_disabled_placeholder(self):
        for m in self.w.project.measures:m.section=''
        self.w.refresh();menu=self.menu()
        try:
            actions=menu.section_jump_menu.actions();self.assertEqual(len(actions),1)
            self.assertEqual(actions[0].text(),i18n.tr('暂无段落标识'));self.assertFalse(actions[0].isEnabled())
        finally:menu.deleteLater()

    def test_jump_seeks_exact_mixed_meter_start_without_editing_selection_or_loop(self):
        w=self.w;w.open_harmony();w.set_loop_range((480,1920))
        for floating in (False,True):
            w.melody_window.setFloating(floating);w.harmony_window.setFloating(floating);APP.processEvents()
            w.melody_sync.setChecked(False);w.harmony_window.sync.setChecked(False)
            for r in (w.main_roll,w.roll,w.harmony_window.roll):
                with self.subTest(floating=floating,role=r.role,main=r is w.main_roll):
                    r.horizontalScrollBar().setValue(0);r.selected_ids={n.id for n in r.notes[:1]};r.selected_chords={w.project.chords[0].id}
                    menu=self.menu(r);selection=copy.deepcopy(r.selection);ids=set(r.selected_ids);chords=set(r.selected_chords)
                    before=w.project.to_dict();history=len(w.undo_history);dirty=w.dirty;loop=w.loop_range
                    try:menu.section_jump_menu.actions()[2].trigger()
                    finally:menu.deleteLater()
                    target=w.project.starts[6]
                    self.assertEqual(w.playhead,target);self.assertEqual(r.cursor_tick,target)
                    self.assertAlmostEqual(r.x_at(target),KEY_W,delta=1)
                    self.assertEqual(r.selection,selection);self.assertEqual(r.selected_ids,ids);self.assertEqual(r.selected_chords,chords)
                    self.assertEqual(w.loop_range,loop);self.assertEqual(w.project.to_dict(),before)
                    self.assertEqual(len(w.undo_history),history);self.assertEqual(w.dirty,dirty)

    def test_score_docked_jump_locates_score_and_ignores_stale_bar_index(self):
        w=self.w;w.switch_workspace('score');w.show_score_panel('melody');APP.processEvents()
        with patch.object(w.score_view,'locate_bar',return_value=True) as locate:
            menu=self.menu();menu.section_jump_menu.actions()[-1].trigger();menu.deleteLater()
            locate.assert_called_with(7)
        before=(w.playhead,w.roll.horizontalScrollBar().value())
        w.roll.jump_to_measure(100);w.roll.jump_to_measure(-1)
        self.assertEqual((w.playhead,w.roll.horizontalScrollBar().value()),before)

    def overview(self):
        nav=self.w.navigator;nav.resize(1040,38)
        image=QImage(nav.size(),QImage.Format.Format_RGB32);image.fill(Qt.GlobalColor.white)
        painter=QPainter(image)
        try:nav.paint_content(painter)
        finally:painter.end()
        return image

    def test_navigator_boundaries_follow_meter_positions_and_do_not_render_names(self):
        p=self.w.project
        for m in p.measures:m.section=''
        blank=self.overview()
        for bar in (0,3,7):p.measures[bar].section='Verse'
        marked=self.overview();self.assertNotEqual(blank,marked)
        changed={x for x in range(KEY_W,marked.width()) if any(marked.pixel(x,y)!=blank.pixel(x,y) for y in range(marked.height()))}
        expected=[KEY_W+p.starts[bar]/p.end*(marked.width()-KEY_W) for bar in (0,3,7)]
        self.assertTrue(all(any(abs(x-boundary)<=1 for x in changed) for boundary in expected))
        self.assertTrue(all(any(abs(x-boundary)<=4 for boundary in expected) for x in changed))
        for bar in (0,3,7):p.measures[bar].section='Long custom section name, with no navigator text'
        self.assertEqual(self.overview(),marked)


if __name__=='__main__':unittest.main()
