"""Polyphonic Score remains usable while traditional notation requires one voice."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QMessageBox
from lingfeng.audio.midi import export_midi
from lingfeng.engraving.notation import ScoreLayout, export_pdf
from lingfeng.music.model import Chord, Note, Project
from lingfeng.platform import chord_preferences, context_menu_preferences, i18n
from lingfeng.platform.preferences import save_preferences
from lingfeng.ui.export_dialog import ExportDialog
from lingfeng.ui.main_window import MainWindow

APP = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parents[1]
MESSAGE = '传统简谱仅支持单声部旋律，请使用立体简谱或立体简谱 · 紧凑。'


def song(style='spatial', polyphonic=True):
    project = Project(title='Polyphonic score')
    project.notes = [Note(0, 961 if polyphonic else 960, 60), Note(960, 960, 64)]
    project.chords = [Chord(0, 3840)]
    project.notation.update(style=style, font_layout_version=45)
    return project


class PolyphonicScoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        self.addCleanup(temporary.cleanup); self.folder = Path(temporary.name)
        self.user = self.folder / 'user'
        environment = patch.dict(os.environ, {
            'LINGFENG_USER_DATA': str(self.user),
            'LINGFENG_SYNTH_CACHE': str(self.folder / 'synth-index.json'),
        })
        environment.start(); self.addCleanup(environment.stop)
        self.addCleanup(chord_preferences.set_preferences, chord_preferences.settings_dict())
        self.addCleanup(context_menu_preferences.set_preferences, context_menu_preferences.settings_dict())
        self.addCleanup(i18n.set_language, i18n.LANGUAGE)
        messages = patch.object(QMessageBox, 'exec', side_effect=AssertionError('Polyphonic Score must not show a modal gate'))
        messages.start(); self.addCleanup(messages.stop)
        questions = patch.object(QMessageBox, 'question', side_effect=AssertionError('Unexpected save prompt in test'))
        questions.start(); self.addCleanup(questions.stop)
        self.windows = []; self.addCleanup(self.close_windows)

    def close_windows(self):
        for window in self.windows:
            window.dirty = False; window.close()

    def window(self, project=None, language='zh'):
        save_preferences(self.user, {'language': language})
        window = MainWindow(project or song())
        window.timer.stop(); window.autosave.stop(); self.windows.append(window)
        return window

    def traditional(self, window):
        return window.score_style.model().item(window.score_style.findData('traditional'))

    def test_one_tick_overlap_and_simultaneous_attacks_enter_both_supported_styles(self):
        for style in ('spatial', 'compact'):
            for simultaneous in (False, True):
                with self.subTest(style=style, simultaneous=simultaneous):
                    project = song(style)
                    if simultaneous: project.notes[1].start = 0
                    before = copy.deepcopy(project.notes); midi = export_midi(project, None)
                    window = self.window(project)
                    self.assertTrue(window.score_entry_allowed())
                    self.assertTrue(window.switch_workspace('score'))
                    self.assertEqual(window.workspace, 'score')
                    self.assertEqual(window.score_view.canvas.project.notes, before)
                    self.assertFalse(self.traditional(window).isEnabled())
                    self.assertEqual(export_midi(window.project, None), midi)
                    window.dirty = False; window.close()

    def test_saved_incompatible_style_falls_back_and_save_reopen_preserves_music(self):
        project = song('traditional'); before = copy.deepcopy(project.notes)
        midi = export_midi(project, None); original = self.folder / 'old.lfs'
        project.save(original)
        window = self.window(Project.load(original))
        self.assertEqual(window.project.notation['style'], 'spatial'); self.assertTrue(window.dirty)
        self.assertFalse(self.traditional(window).isEnabled())
        self.assertTrue(window.switch_workspace('score'))
        window.path = self.folder / 'updated.lfs'; self.assertTrue(window.save())
        saved = Project.load(window.path)
        self.assertEqual(saved.notation['style'], 'spatial'); self.assertEqual(saved.notes, before)
        self.assertEqual(export_midi(saved, None), midi)
        reopened = self.window(saved)
        self.assertTrue(reopened.switch_workspace('score')); self.assertFalse(reopened.dirty)
        self.assertFalse(self.traditional(reopened).isEnabled())

    def test_polyphonic_edit_fallback_is_in_same_undo_and_redo_stays_in_score(self):
        window = self.window(song('traditional', False)); window.switch_workspace('score')
        window.undo_history.clear(); window.redo_history.clear()
        mono = copy.deepcopy(window.project.to_dict())
        self.assertTrue(window.mutate('overlap', lambda p: setattr(p.notes[0], 'duration', 961), source='melody'))
        self.assertEqual(window.workspace, 'score'); self.assertEqual(window.project.notation['style'], 'spatial')
        self.assertFalse(self.traditional(window).isEnabled()); self.assertEqual(len(window.undo_history), 1)
        poly = copy.deepcopy(window.project.to_dict())
        window.undo()
        self.assertEqual(window.workspace, 'score'); self.assertEqual(window.project.to_dict(), mono)
        self.assertTrue(self.traditional(window).isEnabled()); self.assertEqual(len(window.undo_history), 0)
        window.redo()
        self.assertEqual(window.workspace, 'score'); self.assertEqual(window.project.to_dict(), poly)
        self.assertFalse(self.traditional(window).isEnabled()); self.assertEqual(len(window.undo_history), 1)

    def test_traditional_selection_is_rejected_without_history_or_document_changes_in_both_languages(self):
        for language in ('zh', 'en'):
            with self.subTest(language=language):
                window = self.window(song(), language); window.switch_workspace('score')
                before = copy.deepcopy(window.project.to_dict()); history = list(window.undo_history)
                window.set_notation('style', 'traditional')
                self.assertEqual(window.project.to_dict(), before); self.assertEqual(window.undo_history, history)
                self.assertEqual(window.statusBar().currentMessage(), i18n.tr(MESSAGE))
                self.assertEqual(self.traditional(window).toolTip(), i18n.tr(MESSAGE))
                if language == 'en': self.assertNotEqual(i18n.tr(MESSAGE), MESSAGE)
                window.dirty = False; window.close()

    def test_repaired_melody_reenables_traditional_and_replaces_only_incompatible_snapshot(self):
        window = self.window(song()); window.switch_workspace('score')
        old_snapshot = window.score_view.canvas.project
        self.assertEqual(old_snapshot.notes[0].duration, 961)
        window.mutate('repair', lambda p: setattr(p.notes[0], 'duration', 960), source='melody')
        self.assertTrue(self.traditional(window).isEnabled())
        self.assertEqual(window.score_view.canvas.project.notes[0].duration, 961)
        midi = export_midi(window.project, None)
        window.set_notation('style', 'traditional')
        self.assertEqual(window.project.notation['style'], 'traditional')
        self.assertIsNot(window.score_view.canvas.project, old_snapshot)
        self.assertEqual(window.score_view.canvas.project.notes, window.project.notes)
        self.assertEqual(export_midi(window.project, None), midi)
        self.assertGreater(export_pdf(window.score_view.canvas.project, self.folder / 'repaired.pdf'), 0)

    def test_replace_polyphonic_project_from_score_keeps_score_and_normalizes_style(self):
        window = self.window(song(polyphonic=False)); window.switch_workspace('score')
        for style in ('spatial', 'compact', 'traditional'):
            with self.subTest(style=style):
                project = song(style); midi = export_midi(project, None)
                window.replace_project(project)
                self.assertEqual(window.workspace, 'score')
                self.assertEqual(window.project.notation['style'], 'spatial' if style == 'traditional' else style)
                self.assertEqual(window.dirty, style == 'traditional')
                self.assertEqual(window.score_view.canvas.project.notes, project.notes)
                self.assertEqual(export_midi(window.project, None), midi)
                self.assertFalse(window.undo_history)

    def test_traditional_font_after_repair_uses_live_music_instead_of_old_polyphonic_budget(self):
        project = song()
        project.notes = [Note(0, 3840, 60)] + [Note(index * 240, 240, 64) for index in range(16)]
        window = self.window(project); window.switch_workspace('score')
        old_snapshot = copy.deepcopy(window.score_view.canvas.project)
        window.mutate('repair', lambda p: setattr(p, 'notes', p.notes[:1]), source='melody')
        repaired = copy.deepcopy(window.project); repaired.notation['style'] = 'traditional'
        expected = ScoreLayout(repaired).recommended_font_size
        old_snapshot.notation['style'] = 'traditional'
        self.assertNotEqual(ScoreLayout(old_snapshot).recommended_font_size, expected)
        window.set_notation('style', 'traditional')
        self.assertEqual(window.project.notation['font_size'], expected)
        self.assertEqual(window.score_view.canvas.project.notes, window.project.notes)
        self.assertEqual(window.score_view.canvas.layout.recommended_font_size, expected)

    def test_language_rebuild_retains_polyphonic_score_and_regular_deferred_snapshot(self):
        window = self.window(song('compact')); window.switch_workspace('score')
        window.mutate('edit', lambda p: setattr(p.notes[1], 'pitch', 67), source='melody')
        live = copy.deepcopy(window.project.to_dict()); snapshot = copy.deepcopy(window.score_view.canvas.project.notes)
        window.change_language('en', False)
        self.assertEqual(window.workspace, 'score'); self.assertEqual(window.project.to_dict(), live)
        self.assertEqual(window.score_view.canvas.project.notes, snapshot)
        self.assertFalse(self.traditional(window).isEnabled())

    def test_polyphonic_supported_pdf_and_mono_traditional_export_without_music_changes(self):
        for style, polyphonic in (('spatial', True), ('compact', True), ('traditional', False)):
            with self.subTest(style=style):
                project = song(style, polyphonic); before = copy.deepcopy(project.to_dict())
                midi = export_midi(project, None); target = self.folder / (style + '.pdf')
                self.assertEqual(export_pdf(project, target, pages=[0]), 1)
                self.assertTrue(target.read_bytes().startswith(b'%PDF'))
                self.assertEqual(project.to_dict(), before); self.assertEqual(export_midi(project, None), midi)

    def test_direct_traditional_polyphonic_pdf_rejects_before_creating_or_overwriting_file(self):
        project = song('traditional'); project.validate(); before = copy.deepcopy(project.to_dict())
        for existing in (False, True):
            with self.subTest(existing=existing):
                target = self.folder / ('existing.pdf' if existing else 'new.pdf')
                if existing: target.write_bytes(b'keep existing content')
                with patch('lingfeng.engraving.notation.QPdfWriter') as writer:
                    with self.assertRaises(ValueError) as error: export_pdf(project, target)
                    self.assertEqual(str(error.exception), MESSAGE); writer.assert_not_called()
                if existing: self.assertEqual(target.read_bytes(), b'keep existing content')
                else: self.assertFalse(target.exists())
        self.assertEqual(project.to_dict(), before)

    def test_export_dialog_uses_displayed_snapshot_and_exports_supported_polyphony(self):
        for style in ('spatial', 'compact'):
            with self.subTest(style=style):
                window = self.window(song(style)); window.switch_workspace('score')
                window.mutate('edit', lambda p: setattr(p.notes[1], 'pitch', 67), source='melody')
                dialog = ExportDialog(window, 'pdf'); self.addCleanup(dialog.close)
                self.assertEqual(dialog.project.notes[1].pitch, 64)
                self.assertTrue(dialog.export_button.isEnabled()); self.assertEqual(list(dialog.options()['pages']), [0])
                target = self.folder / (style + '-dialog.pdf')
                with patch('lingfeng.ui.export_dialog.QFileDialog.getSaveFileName', return_value=(str(target), '')):
                    dialog.export()
                self.assertTrue(target.read_bytes().startswith(b'%PDF'))
                window.switch_workspace('compose')
                latest = ExportDialog(window, 'pdf'); self.addCleanup(latest.close)
                self.assertEqual(latest.project.notes[1].pitch, 67)
                window.dirty = False; window.close()

    def test_export_dialog_rejects_actual_invalid_source_in_both_languages(self):
        for language in ('zh', 'en'):
            for source in ('live', 'snapshot'):
                with self.subTest(language=language, source=source):
                    window = self.window(song(), language)
                    if source == 'snapshot':
                        window.switch_workspace('score')
                        invalid = song('traditional')
                        window.score_view.canvas.project = invalid
                        window.score_view.canvas.layout = ScoreLayout(invalid)
                    else:
                        window.project.notation['style'] = 'traditional'
                    dialog = ExportDialog(window, 'pdf'); self.addCleanup(dialog.close)
                    self.assertEqual(dialog.project.notation['style'], 'traditional')
                    self.assertFalse(dialog.export_button.isEnabled()); self.assertIn(i18n.tr(MESSAGE), dialog.info.text())
                    with patch('lingfeng.ui.export_dialog.QFileDialog.getSaveFileName') as save:
                        dialog.export(); save.assert_not_called()
                    self.assertEqual(dialog.status.text(), i18n.tr(MESSAGE))
                    window.dirty = False; window.close()


if __name__ == '__main__':
    unittest.main()
