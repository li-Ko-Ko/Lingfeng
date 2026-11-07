"""Exercise MusicXML through the File menu and its real import/export dialogs."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from lingfeng.music.model import Chord, Context, Measure, Note, Project
from lingfeng.platform.i18n import tr
from lingfeng.ui.export_dialog import ExportDialog
from lingfeng.ui.main_window import MainWindow
from lingfeng.ui.musicxml_import_dialog import MusicXmlImportDialog


APP = QApplication.instance() or QApplication([])

SOURCE = '''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <work><work-title>Imported score</work-title></work>
  <part-list>
    <score-part id="V"><part-name>Vocal</part-name></score-part>
    <score-part id="I"><part-name>Instrumental</part-name></score-part>
    <score-part id="H"><part-name>Harmony</part-name></score-part>
  </part-list>
  <part id="V"><measure number="1">
    <attributes>
      <divisions>2</divisions><key><fifths>-1</fifths><mode>major</mode></key>
      <time><beats>3</beats><beat-type>4</beat-type></time>
    </attributes>
    <direction><direction-type><rehearsal>Bridge</rehearsal></direction-type><sound tempo="123"/></direction>
    <note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration>
      <lyric number="1"><text>la</text></lyric></note>
    <note><rest/><duration>5</duration></note>
  </measure></part>
  <part id="I"><measure number="1">
    <attributes><divisions>2</divisions><time><beats>3</beats><beat-type>4</beat-type></time></attributes>
    <note><rest/><duration>1</duration></note>
    <note><pitch><step>A</step><octave>4</octave></pitch><duration>1</duration></note>
    <note><rest/><duration>4</duration></note>
  </measure></part>
  <part id="H"><measure number="1">
    <attributes><divisions>2</divisions><time><beats>3</beats><beat-type>4</beat-type></time></attributes>
    <harmony><root><root-step>D</root-step></root><kind>minor-seventh</kind>
      <bass><bass-step>F</bass-step></bass></harmony>
    <note><pitch><step>F</step><octave>3</octave></pitch><duration>1</duration></note>
    <note><chord/><pitch><step>A</step><octave>3</octave></pitch><duration>1</duration></note>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration></note>
    <note><rest/><duration>4</duration></note>
  </measure></part>
</score-partwise>'''


def performed(notes):
    return [(note.start, note.duration, note.pitch) for note in notes]


class MusicXmlFileWorkflowTests(unittest.TestCase):
    def setUp(self):
        preferences = patch.object(MainWindow, 'save_preferences')
        preferences.start()
        self.addCleanup(preferences.stop)
        self.folder = Path(self.enterContext(TemporaryDirectory(dir='tmp')))
        project = Project(
            title='Destination', bpm=91, melody_names=['Lead', 'Countermelody'],
            measures=[Measure(section='Verse'), Measure(section='Outro')],
            contexts=[Context(0, 7680)],
            notes=[Note(3600, 480, 60)],
            instrument_notes=[Note(3360, 720, 72)],
            chords=[Chord(3360, 960, root=48, notes=[Note(120, 720, 48)])],
        )
        self.window = MainWindow(project)
        self.window.timer.stop()
        self.window.autosave.stop()
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.dirty = False
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()

    def file_action(self, submenu):
        def action(menu, title):
            return next(item for item in menu.actions() if item.text() == tr(title))

        file_action = action(self.window.title_bar.menu, '文件')
        file_menu = file_action.menu()
        submenu_action = action(file_menu, submenu)
        nested = submenu_action.menu()
        self.menu_refs = (file_action, file_menu, submenu_action, nested)
        return action(nested, 'MusicXML…')

    def test_file_import_maps_three_parts_and_symbols_and_undoes_splits(self):
        window = self.window
        before = window.project.to_dict()
        path = self.folder/'three-parts.musicxml'
        path.write_text(SOURCE, encoding='utf-8')
        window.dirty = True

        def accept(dialog):
            self.assertEqual(dialog.mapping(), {'melody': 'V', 'instrument': 'I', 'chords': 'H', 'symbols': 'H'})
            self.assertFalse(dialog.tempo.isChecked())
            dialog.bar.setValue(2)
            dialog.confirm.click()
            return dialog.result()

        with (
            patch.object(QFileDialog, 'getOpenFileName', return_value=(str(path), '')) as picker,
            patch.object(MusicXmlImportDialog, 'exec', accept),
            patch.object(QMessageBox, 'warning') as warning,
            patch.object(window, 'maybe_save', side_effect=AssertionError('Import must keep the current project')),
        ):
            self.file_action('导入').trigger()
        warning.assert_not_called()
        self.assertIn('*.mxl', picker.call_args.args[-1])

        result = window.project
        self.assertEqual(result.title, 'Destination')
        self.assertEqual(result.melody_names, ['Lead', 'Countermelody'])
        self.assertEqual(result.bpm, 91)
        self.assertEqual(result.starts, [0, 3840, 6720, 10560])
        self.assertEqual(window.playhead, 3840)
        self.assertEqual([bar.section for bar in result.measures], ['verse', 'bridge', 'outro'])
        self.assertEqual(performed(result.notes), [(3600, 240, 60), (3840, 480, 62), (6720, 240, 60)])
        self.assertEqual(performed(result.instrument_notes), [(3360, 480, 72), (4320, 480, 69), (6720, 240, 72)])
        self.assertEqual(performed(result.harmony_notes()),
                         [(3480, 360, 48), (3840, 480, 53), (3840, 480, 57), (4320, 480, 60), (6720, 360, 48)])
        self.assertEqual(result.chord_at(3840).name, 'Dm7/F')
        self.assertEqual(len(window.undo_history), 1)
        after = result.to_dict()
        window.undo()
        self.assertEqual(window.project.to_dict(), before)
        window.redo()
        self.assertEqual(window.project.to_dict(), after)

    def test_file_export_dialog_writes_selected_bar_as_compressed_three_part_score(self):
        window = self.window
        target = self.folder/'score.mxl'
        before = window.project.to_dict()

        def export(dialog):
            self.assertEqual(dialog.format, 'musicxml')
            self.assertEqual(dialog.tracks.roles(), ('melody','instrument','chords'))
            dialog.range.setCurrentIndex(dialog.range.findData('bars'))
            dialog.first.setValue(2)
            dialog.last.setValue(2)
            dialog.export_button.click()
            self.assertEqual(dialog.output_path, str(target))
            self.assertEqual(dialog.status.text(), tr('已导出：{0}', str(target)))
            return QDialog.DialogCode.Accepted

        with (
            patch.object(QFileDialog, 'getSaveFileName',
                         return_value=(str(target.with_suffix('.musicxml')), tr('压缩 MusicXML (*.mxl)'))) as picker,
            patch.object(ExportDialog, 'exec', export),
        ):
            self.file_action('导出').trigger()
        self.assertIn('*.musicxml', picker.call_args.args[-1])
        self.assertIn('*.mxl', picker.call_args.args[-1])
        self.assertEqual(window.project.to_dict(), before)
        self.assertFalse(window.undo_history)

        with ZipFile(target) as archive:
            container = ET.fromstring(archive.read('META-INF/container.xml'))
            score_file = container.find('.//{*}rootfile').get('full-path')
            score = ET.fromstring(archive.read(score_file))
        self.assertEqual(score.tag, 'score-partwise')
        self.assertEqual(len(score.findall('./part-list/score-part')), 3)
        parts = score.findall('./part')
        self.assertEqual(len(parts), 3)
        self.assertTrue(all(len(part.findall('measure')) == 1 for part in parts))
        self.assertEqual(len(score.findall('.//note/pitch')), 3)
        self.assertEqual(score.findtext('.//harmony/root/root-step'), 'C')


if __name__ == '__main__':
    unittest.main()
