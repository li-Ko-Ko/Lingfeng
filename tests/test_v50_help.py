"""Functional help navigation, bilingual search and release-text checks."""
import os
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from popscore import i18n
from popscore.helpview import HelpDialog,HELP_CATEGORIES,TOPICS
from popscore.gm_instruments import NAMES
from popscore.model import Project
from popscore.midi import export_daw_bundle
from scripts.audit_text import audit
import tempfile
import zipfile

APP=QApplication.instance() or QApplication([])


class HelpTests(unittest.TestCase):
    def setUp(self):
        self.language=i18n.LANGUAGE;self.addCleanup(i18n.set_language,self.language)
    def dialog(self,language='zh',about=False):
        i18n.set_language(language);dialog=HelpDialog(about=about)
        self.addCleanup(dialog.deleteLater);return dialog
    def visible(self,dialog):
        return [i for i in range(dialog.list.count()) if not dialog.list.item(i).isHidden()]
    def test_every_topic_has_exactly_one_functional_category(self):
        titles=[title for _,_,members in HELP_CATEGORIES for title in members]
        self.assertEqual(len(titles),len(set(titles)));self.assertEqual(titles,[t[0] for t in TOPICS])
        self.assertGreaterEqual(len(HELP_CATEGORIES),6)
        for topic in TOPICS:
            self.assertEqual(len(topic),4)
            self.assertTrue(all(isinstance(text,str) and text.strip() for text in topic))
    def test_category_filters_and_breadcrumbs_in_both_languages(self):
        for language in ('zh','en'):
            dialog=self.dialog(language);dialog.category.setCurrentIndex(3)
            visible=self.visible(dialog);self.assertTrue(visible)
            self.assertTrue(all(dialog.page_categories[index]==2 for index in visible))
            self.assertIn('3.',dialog.browser.toPlainText())
            dialog.category.setCurrentIndex(0);self.assertEqual(len(self.visible(dialog)),len(dialog.pages))
    def test_bilingual_search_selects_visible_result_and_recovers_after_no_match(self):
        for language,query in (('zh','Chord inversion'),('en','和弦转位')):
            dialog=self.dialog(language);dialog.search.setText(query)
            self.assertTrue(self.visible(dialog));self.assertIn(dialog.list.currentRow(),self.visible(dialog))
            dialog.search.setText('nonexistent-help-phrase-502918')
            self.assertFalse(self.visible(dialog));self.assertEqual(dialog.list.currentRow(),-1)
            self.assertIn('No matching' if language=='en' else '没有匹配',dialog.browser.toPlainText())
            dialog.search.clear();self.assertTrue(self.visible(dialog));self.assertGreaterEqual(dialog.list.currentRow(),0)
    def test_category_search_does_not_match_invisible_html_tags(self):
        dialog=self.dialog();dialog.search.setText('<br>');self.assertFalse(self.visible(dialog))
        dialog.search.setText('personal settings');self.assertTrue(self.visible(dialog))
        self.assertIn('升级',dialog.browser.toPlainText())
    def test_about_keeps_current_version_and_licensing(self):
        from popscore import __version__
        for language in ('zh','en'):
            dialog=self.dialog(language,True);text=dialog.browser.toPlainText()
            self.assertIn(__version__,text);self.assertIn('MIT',text);self.assertIn('37',text)
    def test_superseded_help_claims_are_removed(self):
        text=' '.join(' '.join(topic) for topic in TOPICS)
        for stale in ('歌词提交后立即更新谱面','Apply, delete, undo and redo refresh the score immediately',
                      '十九种常用性质','字母输入采用升号','Keyboard scrolling uses the selected element furthest'):
            self.assertNotIn(stale,text)


class TextTests(unittest.TestCase):
    def test_release_catalogue_and_format_placeholders(self):
        result=audit();self.assertEqual(result['status'],'passed',result)
        self.assertGreater(result['translation_calls'],700);self.assertGreater(result['catalog_entries'],1000)
    def test_all_gm_instruments_have_both_language_names(self):
        self.assertEqual(len(NAMES),128)
        self.assertTrue(all(len(row)==2 and row[0].strip() and row[1].strip() for row in NAMES))
        self.assertTrue(all(not any('\u3400'<=c<='\u9fff' for c in row[1]) for row in NAMES))
    def test_model_and_pdf_error_sources_translate(self):
        i18n.set_language('en');self.addCleanup(i18n.set_language,'zh')
        for source in ('不是支持的伶风工程文件。','无法创建PDF，请检查目标文件是否被占用。'):
            self.assertNotEqual(i18n.tr(source),source)
    def test_daw_transfer_instructions_are_bilingual(self):
        temporary=Path(__file__).resolve().parents[1]/'tmp';temporary.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as folder:
            path=Path(folder)/'transfer.zip';export_daw_bundle(Project(),path)
            with zipfile.ZipFile(path) as archive:
                text=archive.read('Readme.txt').decode('utf-8-sig')
                self.assertIn('方式 A',text);self.assertIn('Option A',text)
                self.assertIn('C4 = MIDI 60',text);self.assertIn('zero-based',text)


if __name__=='__main__':unittest.main()
