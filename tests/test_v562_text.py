"""Consistent visible terminology while musical identifiers and MIDI stay stable."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QLabel
from lingfeng.audio.midi import export_midi
from lingfeng.music.model import Chord,Note,PATTERNS,Project
from lingfeng.platform import i18n
from lingfeng.platform.help_content import TOPICS,HELP_CATEGORIES
from lingfeng.ui.controls import PitchRangeDialog
from lingfeng.ui.dialogs import NoteDialog,ChordDialog,ChordMarkerDialog
from lingfeng.ui.chord_settings_dialog import ChordSettingsDialog
from lingfeng.ui.velocity_dialog import DynamicsSettingsDialog
from scripts.export_help import export

APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parent.parent
ALTERNATING=('alternating_quarters','alternating_eighths','alternating_offbeat')


class TerminologyTests(unittest.TestCase):
    def setUp(self):
        previous=i18n.LANGUAGE;i18n.set_language('zh');self.addCleanup(i18n.set_language,previous)

    def test_alternating_labels_have_exact_requested_spelling_and_keep_codes(self):
        self.assertEqual([PATTERNS[code] for code in ALTERNATING],
                         ['底五交替 · 四分柱式','底五交替 · 八分柱式','底五交替 · 反拍柱式'])
        p=Project();c=Chord(0,3840);dialog=ChordDialog(c,p)
        try:
            for code in ALTERNATING:self.assertEqual(dialog.pattern.itemText(dialog.pattern.findData(code)),PATTERNS[code])
        finally:dialog.deleteLater()

    def test_display_rename_does_not_change_generated_midi_or_project_codes(self):
        for code in ALTERNATING:
            with self.subTest(code=code):
                p=Project();p.chords=[Chord(0,3840,quality='m7',pattern=code,velocity=51)]
                current=export_midi(p,None);before=p.to_dict()
                with patch.dict(PATTERNS,{code:PATTERNS[code].replace('底五交替','根五交替')}):
                    self.assertEqual(export_midi(p,None),current);self.assertEqual(p.to_dict(),before)
                serialized=json.dumps(before,ensure_ascii=False)
                self.assertIn(code,serialized);self.assertNotIn('底五交替',serialized)
                self.assertEqual(export_midi(Project.from_dict(before),None),current)

    def test_dialog_titles_preview_terms_and_velocity_units_are_explicit(self):
        p=Project();note=Note(0,480,60);chord=Chord(0,3840);p.notes=[note];p.chords=[chord];before=p.to_dict()
        dialogs=[NoteDialog(note,p),ChordDialog(chord,p),ChordMarkerDialog(chord,p),DynamicsSettingsDialog([48,72,96],{})]
        try:
            self.assertEqual([d.windowTitle() for d in dialogs[:3]],['编辑音符','编辑和弦','和弦标记'])
            for dialog in dialogs[1:3]:self.assertIn('罗马数字 / 和弦名称',{label.text() for label in dialog.findChildren(QLabel)})
            for control in (dialogs[0].velocity,dialogs[1].velocity,
                            dialogs[3].melody_velocity,dialogs[3].chord_velocity):
                self.assertEqual(control.toolTip(),'MIDI 力度（1–127）');self.assertEqual((control.minimum(),control.maximum()),(1,127))
            self.assertFalse(any(hasattr(dialog,'bass_velocity') for dialog in dialogs))
            self.assertIn('和弦默认力度',{label.text() for label in dialogs[1].findChildren(QLabel)})
            self.assertEqual(p.to_dict(),before)
        finally:
            for dialog in dialogs:dialog.deleteLater()

    def test_pitch_choices_name_midi_unit_without_changing_values(self):
        dialog=PitchRangeDialog(48,72)
        try:
            self.assertIn('MIDI 48',dialog.low.currentText());self.assertIn('MIDI 72',dialog.high.currentText())
            self.assertEqual(dialog.value(),(48,72))
        finally:dialog.deleteLater()

    def test_current_help_uses_current_menu_terms_and_exports_exactly(self):
        title='右键菜单、选择与节奏型识别';topics={topic[0]:topic for topic in TOPICS}
        self.assertIn(title,topics);self.assertTrue(any(title in group[2] for group in HELP_CATEGORIES))
        combined='\n'.join(str(topic) for topic in TOPICS)
        for old in ('根五交替','低五交替','“禁用识别”','“标记和弦”','试听实际和弦','在和弦钢琴卷帘中编辑'):
            self.assertNotIn(old,combined)
        for current in ('底五交替','禁用和弦识别','禁用节奏型识别','设置和弦标记'):
            self.assertIn(current,combined)
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as folder:
            generated=export(Path(folder)/'HELP.md')
            self.assertEqual(generated.read_text('utf-8'),(ROOT/'docs/HELP.md').read_text('utf-8'))
        self.assertNotIn('根五交替',(ROOT/'docs/FORMAT.md').read_text('utf-8'))


if __name__=='__main__':unittest.main()
