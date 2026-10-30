"""Live score information stays current while musical snapshots remain frozen."""
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPointF,QRect,QEvent
from PySide6.QtWidgets import QApplication
from popscore.app import MainWindow
from popscore.model import Project,Note
from popscore.exportdialog import ExportDialog
from popscore import i18n

APP=QApplication.instance() or QApplication([])


class ScoreInformationTests(unittest.TestCase):
    def setUp(self):
        self.language=i18n.LANGUAGE
        self.saving=patch.object(MainWindow,'save_preferences');self.saving.start()
        p=Project(title='Original title',author='Original author');p.notes=[Note(0,960,60)]
        self.w=MainWindow(p);self.w.change_language('zh',False)
        self.w.timer.stop();self.w.autosave.stop();self.w.resize(1200,900);self.w.show()
        self.w.switch_workspace('score');APP.processEvents()

    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater()
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()
        self.saving.stop();i18n.set_language(self.language)

    def rename(self,title,accepted=True):
        with patch('popscore.app.QInputDialog.getText',return_value=(title,accepted)):
            self.w.project_info()
        APP.processEvents()

    def header(self):
        c=self.w.score_view.canvas
        return c.grab(QRect(0,0,c.width(),round(120*c.scale)+20)).toImage()

    def test_confirm_refreshes_rendered_title_and_pdf_without_importing_new_music(self):
        w=self.w;c=w.score_view.canvas;original=copy.deepcopy(c.project.notes)
        before=self.header()
        w.mutate('musical edit',lambda p:setattr(p.notes[0],'pitch',67))
        self.rename('Updated title')
        self.assertEqual(w.project.title,c.project.title)
        self.assertEqual(c.project.title,'Updated title')
        self.assertEqual(c.project.notes,original)
        self.assertEqual(w.project.notes[0].pitch,67)
        self.assertNotEqual(before,self.header())
        pdf=ExportDialog(w,'pdf')
        try:
            self.assertEqual(pdf.project.title,'Updated title')
            self.assertEqual(pdf.project.notes,original)
        finally:pdf.deleteLater()

    def test_title_undo_redo_refreshes_header_and_keeps_music_snapshot(self):
        w=self.w;c=w.score_view.canvas
        original_header=self.header()
        w.mutate('musical edit',lambda p:setattr(p.notes[0],'pitch',68))
        self.rename('Revised title');revised=self.header()
        w.undo();APP.processEvents()
        self.assertEqual(w.project.title,'Original title');self.assertEqual(c.project.title,'Original title')
        self.assertEqual(w.project.notes[0].pitch,68);self.assertEqual(c.project.notes[0].pitch,60)
        self.assertNotEqual(revised,self.header())
        w.redo();APP.processEvents()
        self.assertEqual(c.project.title,'Revised title');self.assertNotEqual(original_header,self.header())

    def test_cancel_keeps_title_history_and_rendered_layout(self):
        w=self.w;c=w.score_view.canvas;before=w.project.to_dict()
        layout=c.layout;history=len(w.undo_history);header=self.header()
        self.rename('Discarded title',False)
        self.assertEqual(w.project.to_dict(),before);self.assertIs(c.layout,layout)
        self.assertEqual(len(w.undo_history),history);self.assertEqual(self.header(),header)

    def test_blank_title_uses_localized_fallback_in_current_score(self):
        self.rename('   ')
        self.assertEqual(self.w.project.title,i18n.tr('未命名作品'))
        self.assertEqual(self.w.score_view.canvas.project.title,self.w.project.title)

    def test_metadata_still_syncs_when_bar_structure_is_pending(self):
        w=self.w;c=w.score_view.canvas;original=c.project.to_dict()
        w.mutate('insert bar',lambda p:p.insert_measure(0))
        self.assertNotEqual(w.project.starts,c.project.starts)
        w.mutate('author',lambda p:setattr(p,'author','Updated author'))
        self.rename('Structure still pending')
        self.assertEqual(c.project.title,'Structure still pending')
        self.assertEqual(c.project.author,'Updated author')
        self.assertEqual(c.project.notes[0].start,original['notes'][0]['start'])
        self.assertEqual(len(c.project.measures),len(original['measures']))
        self.assertEqual(len(w.project.measures),len(original['measures'])+1)

    def test_edit_menu_omits_section_command_but_timeline_keeps_it_in_both_languages(self):
        w=self.w
        for language in ('zh','en'):
            w.change_language(language,False);APP.processEvents()
            edit_action=next(a for a in w.title_bar.menu.actions() if a.text()==i18n.tr('编辑'))
            edit=edit_action.menu()
            texts=[a.text() for a in edit.actions()]
            self.assertIn(i18n.tr('作品信息…'),texts)
            self.assertNotIn(i18n.tr('小节段落名…'),texts)
            menu=w.roll.timeline_menu(QPointF(w.roll.x_at(240),8))
            try:
                sections=menu.section_menu
                self.assertEqual(sections.title(),i18n.tr('段落标识'))
                next(a for a in sections.actions() if a.text()=='Verse').trigger()
                self.assertEqual(w.project.measures[0].section,'Verse')
                sections.actions()[0].trigger();self.assertEqual(w.project.measures[0].section,'')
            finally:menu.deleteLater()


if __name__=='__main__':unittest.main()
