"""Chord velocity menus, opt-in metadata inspection and persisted preferences."""
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QDialog
from lingfeng.audio import velocity
from lingfeng.music.model import Project, Chord, Note
from lingfeng.ui.piano_roll import PianoRoll, KEY_W
from lingfeng.ui.velocity_dialog import VelocityOptionsDialog

APP = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parents[1]


def sf2_fixture():
    def chunk(name, data):
        return name + struct.pack('<I', len(data)) + data + b'\0' * (len(data) % 2)
    def table(name, fmt, rows):
        return chunk(name, b''.join(struct.pack(fmt, *row) for row in rows))
    data = b'pdta' + b''.join([
        table(b'phdr', '<20sHHHIII', [(b'other', 0, 0, 0, 0, 0, 0), (b'wanted', 5, 2, 1, 0, 0, 0), (b'EOP', 0, 0, 3, 0, 0, 0)]),
        table(b'pbag', '<HH', [(0, 0), (1, 0), (2, 0), (3, 0)]),
        table(b'pgen', '<HH', [(41, 0), (44, 20 | (110 << 8)), (41, 0), (0, 0)]),
        table(b'inst', '<20sH', [(b'piano', 0), (b'EOI', 3)]),
        table(b'ibag', '<HH', [(0, 0), (1, 0), (3, 0), (5, 0)]),
        table(b'igen', '<HH', [(43, 127 << 8), (44, 63 << 8), (53, 0), (44, 64 | (127 << 8)), (53, 1), (0, 0)]),
    ])
    body = b'sfbk' + chunk(b'LIST', b'sdta' + chunk(b'smpl', b'\0' * 4096)) + chunk(b'LIST', data)
    return chunk(b'RIFF', body)


class VelocityMetadataTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT/'tmp'); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_options_reject_bad_input_and_normalize_saved_preferences(self):
        self.assertEqual(velocity.parse_options('127， 32;64 64'), [32, 64, 127])
        for text in ('', '0,64', '128', '3.5', 'no'):
            with self.subTest(text=text), self.assertRaises(ValueError): velocity.parse_options(text)
        self.assertEqual(velocity.normalize_options([True, 0, 128, '72', 64, 64]), [64])
        self.assertEqual(velocity.normalize_options({}), list(velocity.DEFAULT_OPTIONS))

    def test_bands_deduplicate_round_robin_and_keep_gaps_and_overlap_boundaries(self):
        self.assertEqual(velocity.velocity_bands([(1, 40), (1, 40), (60, 127)]), [(1, 40), (60, 127)])
        self.assertEqual(velocity.velocity_bands([(1, 80), (60, 127)]), [(1, 59), (60, 80), (81, 127)])

    def test_sfz_includes_macros_inheritance_local_override_and_release_exclusion(self):
        (self.root/'a.wav').write_bytes(b'sample fixture')
        (self.root/'layers.inc').write_text('<group> lovel=1 hivel=$split\n<region> sample=a.wav\n<region> sample=a.wav seq_position=2\n<group> lovel=64 hivel=127\n<region> sample=a.wav\n<region> sample=a.wav trigger=release lovel=10 hivel=20', 'utf-8')
        (self.root/'tone.sfz').write_text('#define $split 63\n<global> lovel=30\n#include "layers.inc"', 'utf-8')
        self.assertEqual(velocity.sfz_ranges(self.root, 'tone.sfz'), [(1, 63), (1, 63), (64, 127)])
        (self.root/'tone.sfz').write_text('<global> lovel=2 hivel=120\n<master> lovel=10\n<group> hivel=80\n<region> sample=a.wav\n<region> lovel=81 hivel=100 sample=a.wav', 'utf-8')
        self.assertEqual(velocity.sfz_ranges(self.root, 'tone.sfz'), [(10, 80), (81, 100)])

    def test_sfz_rejects_unsafe_include_and_invalid_range(self):
        (self.root/'a.wav').write_bytes(b'sample fixture')
        for source in ('#include "../outside.sfz"', '<region> sample=a.wav lovel=128'):
            (self.root/'tone.sfz').write_text(source, 'utf-8')
            with self.subTest(source=source), self.assertRaises(ValueError): velocity.sfz_ranges(self.root, 'tone.sfz')

    def test_sf2_selected_bank_program_and_global_ranges_intersect(self):
        file = self.root/'test.sf2'; file.write_bytes(sf2_fixture())
        self.assertEqual(velocity.sf2_ranges(file, 2, 5), [(20, 63), (64, 110)])
        self.assertEqual(velocity.sf2_ranges(file, 0, 0), [(1, 63), (64, 127)])
        with self.assertRaises(ValueError): velocity.sf2_ranges(file, 0, 5)
        file.write_bytes(file.read_bytes()[:-4])
        with self.assertRaises(ValueError): velocity.sf2_ranges(file, 2, 5)

    def test_external_and_native_do_not_invent_layer_counts(self):
        self.assertIsNone(velocity.detect_options(dict(device='default', program=0)))
        with patch('lingfeng.audio.soundbanks.pack', return_value=dict(engine='native')), patch('lingfeng.audio.soundbanks.instrument', return_value={}):
            self.assertIsNone(velocity.detect_options(dict(device='synth:test', program=0)))


class VelocityUiTests(unittest.TestCase):
    def tearDown(self):
        velocity.set_options(None)

    def test_open_dialog_never_detects_and_click_is_tentative_until_confirmed(self):
        with patch('lingfeng.ui.velocity_dialog.detect_options', return_value=dict(bands=[(1, 63), (64, 127)], options=[32, 95])) as detect:
            dialog = VelocityOptionsDialog([48, 72, 96], dict(device='default', program=0))
            self.addCleanup(dialog.close); detect.assert_not_called()
            dialog.detect_button.click(); self.assertEqual(detect.call_count, 1)
            self.assertEqual(dialog.value(), [32, 95]); dialog.reject()
            self.assertEqual(velocity.options(), list(velocity.DEFAULT_OPTIONS))

    def test_detection_failure_or_unsupported_leaves_options_and_invalid_accept_stays_open(self):
        dialog = VelocityOptionsDialog([48, 72], dict(device='default', program=0)); self.addCleanup(dialog.close)
        for result in (None, OSError('missing')):
            with patch('lingfeng.ui.velocity_dialog.detect_options', side_effect=result if isinstance(result, Exception) else None, return_value=result):
                dialog.detect(); self.assertEqual(dialog.value(), [48, 72])
        dialog.values.setText('0,128'); dialog.accept(); self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_menu_single_multiple_unrecognized_and_custom_cancel(self):
        p = Project(); p.chords = [Chord(0, 1920), Chord(1920, 1920, notes=[Note(0, 480, 61, 40)], recognized=False, custom_rhythm=True)]
        roll = PianoRoll(p); self.addCleanup(roll.close); lane = roll.lane
        velocity.set_options([40, 72, 100]); commands = []; roll.chordCommand.connect(lambda *args: commands.append(args))
        roll.selected_chords = {c.id for c in p.chords}
        menu = lane.context_menu(QPoint(KEY_W + 4, 15), preserve=True); self.addCleanup(menu.close)
        self.assertEqual([a.data() for a in menu.velocity_menu.actions() if a.data() is not None], [40, 72, 100])
        menu.velocity_menu.actions()[0].trigger(); self.assertEqual(commands[-1], ('velocity:40', roll.selected_chords))
        with patch('lingfeng.ui.piano_roll.QInputDialog.getInt', return_value=(84, True)):
            menu.velocity_menu.actions()[-1].trigger(); self.assertEqual(commands[-1][0], 'velocity:84')
        count = len(commands)
        with patch('lingfeng.ui.piano_roll.QInputDialog.getInt', return_value=(72, False)):
            menu.velocity_menu.actions()[-1].trigger(); self.assertEqual(len(commands), count)
        roll.selected_chords = {p.chords[1].id}
        menu = lane.context_menu(QPoint(lane.x_at(2000), 15)); self.addCleanup(menu.close)
        self.assertTrue(menu.velocity_menu.isEnabled())

    def test_main_window_batch_velocity_undo_redo_save_and_preferences_restart(self):
        from lingfeng.ui.main_window import MainWindow
        from lingfeng.platform.paths import user_data_dir
        from lingfeng.platform.preferences import load_preferences
        p = Project(); p.chords = [Chord(0, 1920), Chord(1920, 1920, notes=[Note(0, 240, 61, 35)], custom_rhythm=True)]
        with patch('lingfeng.audio.velocity.detect_options', side_effect=AssertionError('No startup detection')):
            window = MainWindow(p); self.addCleanup(lambda: (setattr(window, 'dirty', False), window.close()))
        before = window.project.to_dict(); ids = {c.id for c in window.project.chords[:2]}
        window.chord_command('velocity:48', ids, window.roll)
        self.assertTrue(all(c.velocity == 48 and all(n.velocity == 48 for n in c.render_notes()) for c in window.project.chords if c.id in ids))
        after = window.project.to_dict(); window.undo(); self.assertEqual(window.project.to_dict(), before)
        window.redo(); self.assertEqual(window.project.to_dict(), after)
        self.assertEqual(Project.from_dict(after).to_dict(), after)
        velocity.set_options([41, 83, 121]); window.save_preferences()
        self.assertEqual(load_preferences(user_data_dir())['chord_velocity_options'], [41, 83, 121])
        window.dirty = False; window.close()
        with patch('lingfeng.audio.velocity.detect_options', side_effect=AssertionError('No restart detection')):
            reopened = MainWindow(p); self.addCleanup(lambda: (setattr(reopened, 'dirty', False), reopened.close()))
        self.assertEqual(velocity.options(), [41, 83, 121])


if __name__ == '__main__': unittest.main()
