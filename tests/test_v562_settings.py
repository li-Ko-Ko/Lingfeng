"""Module settings navigation and atomic saved dynamics preferences."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QMenu
from PySide6.QtGui import QAction, QFont
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from lingfeng.audio import velocity
from lingfeng.music.model import Project
from lingfeng.platform import chord_preferences, context_menu_preferences, i18n, rhythm_preferences
from lingfeng.platform.preferences import load_preferences, save_preferences
from lingfeng.ui import theme
from lingfeng.ui.chord_settings_dialog import ChordSettingsDialog
from lingfeng.ui.velocity_dialog import DynamicsSettingsDialog

APP = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parents[1]


class ModuleSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        environment = patch.dict(os.environ, {
            'LINGFENG_USER_DATA': str(self.folder / 'user-data'),
            'LINGFENG_SYNTH_CACHE': str(self.folder / 'synth-index' / 'current.json'),
        })
        environment.start(); self.addCleanup(environment.stop)
        self.user_data = self.folder / 'user-data'
        self.addCleanup(chord_preferences.set_preferences, chord_preferences.settings_dict())
        self.addCleanup(context_menu_preferences.set_preferences, context_menu_preferences.settings_dict())
        self.addCleanup(rhythm_preferences.load_preferences, rhythm_preferences.settings_dict())
        self.addCleanup(velocity.set_options, velocity.options())
        self.addCleanup(i18n.set_language, i18n.LANGUAGE)
        self.addCleanup(theme.apply_theme, theme.is_dark())
        self.addCleanup(theme.set_roll_palettes, copy.deepcopy(theme.CUSTOM_PALETTES))
        self.addCleanup(theme.set_roll_coloring, copy.deepcopy(theme.ROLL_COLORING))
        self.addCleanup(theme.set_note_degrees, theme.SHOW_NOTE_DEGREES)
        self.addCleanup(theme.set_accidental_preference, theme.ACCIDENTAL_PREFERENCE)
        self.windows = []
        self.addCleanup(self.close_windows)

    def close_windows(self):
        for window in self.windows:
            window.dirty = False; window.close()

    def window(self, language='zh'):
        from lingfeng.ui.main_window import MainWindow
        saved = load_preferences(self.user_data)
        save_preferences(self.user_data, {'language': language}, saved)
        window = MainWindow(Project())
        window.timer.stop(); window.autosave.stop()
        self.windows.append(window)
        return window

    def action(self, menu, *path):
        for index, source in enumerate(path):
            label = i18n.tr(source)
            if i18n.LANGUAGE == 'en' and source not in ('语言 / Language', '简体中文') and any('\u3400' <= c <= '\u9fff' for c in source):
                self.assertNotEqual(label, source, source)
            action = next((a for a in menu.actions() if a.text() == label), None)
            self.assertIsNotNone(action, ' / '.join(path[:index + 1]))
            self.assertTrue(action.isVisible()); self.assertTrue(action.isEnabled())
            if index < len(path) - 1:
                menu = action.menu(); self.assertIsNotNone(menu)
        return action

    def test_all_settings_are_reachable_in_both_languages(self):
        for language in ('zh', 'en'):
            with self.subTest(language=language):
                window = self.window(language)
                # Keep Qt-owned wrappers alive during recursive traversal.
                menus = window.findChildren(QMenu)
                actions = window.findChildren(QAction)
                settings_action = self.action(window.title_bar.menu, '设置')
                settings = settings_action.menu()
                modules = ['音源与输入', '音符与力度…', '和弦', '卷帘显示', '界面与操作']
                self.assertEqual([a.text() for a in settings.actions() if not a.isSeparator()],
                                 [i18n.tr(text) for text in modules])
                paths = [
                    ('音源与输入', '音源与音色…'), ('音源与输入', 'MIDI 键盘输入…'),
                    ('音符与力度…',), ('和弦', '和弦性质…'), ('和弦', '和弦音级快捷键…'), ('和弦', '管理和弦进行…'),
                    ('和弦', '节奏型识别'), ('和弦', '和弦识别包含旋律 2'),
                    ('卷帘显示', '和弦轨高度…'),
                    ('卷帘显示', '卷帘滚轮速度…'),
                    ('卷帘显示', '显示音符音级数字'),
                    ('界面与操作', '显示底部信息提示'), ('界面与操作', '右键菜单…'),
                    ('界面与操作', '快捷键设置…'),
                ]
                paths += [('卷帘显示', '和弦轨辅助时间尺', label)
                          for label in ('关闭', '1/4 拍', '1/2 拍', '1 拍', '2 拍', '1 小节')]
                paths += [('卷帘显示', '导航器', label)
                          for label in ('人声', '乐器', '和弦', '按轨道数量自动调整高度', '导航器高度…')]
                paths += [('卷帘显示', '卷帘染色', roll, label)
                          for roll, labels in [('旋律卷帘', ('按和弦音染色', '按调内音染色')),
                                               ('和弦卷帘', ('按旋律音染色', '按调内音染色'))]
                          for label in labels]
                paths += [('卷帘显示', '卷帘染色', '和弦卷帘', '背景颜色提示', label)
                          for label in ('仅人声旋律', '仅乐器旋律', '人声与乐器旋律')]
                paths += [('卷帘显示', '卷帘升降号偏好', label) for label in ('升号 #', '降号 b')]
                paths += [('界面与操作', '外观', label) for label in ('浅色', '深色', '自定义色彩方案')]
                paths += [('界面与操作', '语言 / Language', label) for label in ('简体中文', 'English')]
                leaves = []
                for path in paths:
                    with self.subTest(path=path):
                        leaves.append(self.action(settings, *path))
                def leaf_count(menu):
                    return sum(leaf_count(a.menu()) if a.menu() is not None else 1
                               for a in menu.actions() if not a.isSeparator())
                self.assertEqual(leaf_count(settings), len(leaves))
                self.assertIs(self.action(settings, '卷帘显示', '显示音符音级数字'), window.note_degrees_action)
                self.assertIs(self.action(settings, '界面与操作', '显示底部信息提示'), window.information_action)
                for role, label in [('vocal', '人声'), ('instrument', '乐器'), ('chords', '和弦')]:
                    navigator_track = self.action(settings, '卷帘显示', '导航器', label)
                    self.assertIs(navigator_track, window.navigator_track_actions[role])
                    self.assertTrue(navigator_track.isCheckable())
                self.assertIs(self.action(settings, '卷帘显示', '导航器', '按轨道数量自动调整高度'),
                              window.navigator_auto_height_action)
                for value, action in window.chord_ruler_actions.items():
                    self.assertEqual(action.isChecked(), value == window.chord_ruler_scale)
                window.close()

    def test_chord_lane_height_setting_is_applied_and_saved(self):
        window = self.window()
        menus = window.findChildren(QMenu)
        settings_action = self.action(window.title_bar.menu, '设置')
        settings = settings_action.menu()
        height_action = self.action(settings, '卷帘显示', '和弦轨高度…')
        with patch('lingfeng.ui.main_window.QInputDialog.getInt', return_value=(88, True)):
            height_action.trigger()
        self.assertEqual(window.chord_lane_height, 88)
        self.assertEqual(window.chord_lane.card_height(), 88)
        self.assertEqual(load_preferences(self.user_data)['chord_lane_height'], 88)
        reopened = self.window()
        self.assertEqual(reopened.chord_lane_height, 88)
        self.assertEqual(reopened.chord_lane.card_height(), 88)

    def test_combined_dialog_cancel_preserves_defaults_and_presets(self):
        chord_preferences.load_preferences({'default_velocities': {'melody': 41, 'harmony': 83},
                                            'quick_chord_qualities': ['m', 'maj9']})
        velocity.set_options([45, 81, 119])
        before = chord_preferences.settings_dict(); presets = velocity.options()
        with patch('lingfeng.ui.velocity_dialog.detect_options') as detect:
            dialog = DynamicsSettingsDialog(presets, dict(device='default', program=0))
            self.addCleanup(dialog.close)
            self.assertFalse(hasattr(dialog, 'bass_velocity'))
            self.assertEqual((dialog.melody_velocity.value(), dialog.chord_velocity.value()), (41, 83))
            self.assertEqual(dialog.instrument_velocity.value(), 41)
            dialog.melody_velocity.setValue(27); dialog.instrument_velocity.setValue(56); dialog.chord_velocity.setValue(111)
            dialog.values.setText('32, 96, 127'); dialog.reject()
            detect.assert_not_called()
        self.assertEqual(chord_preferences.settings_dict(), before)
        self.assertEqual(velocity.options(), presets)

    def test_main_window_confirm_saves_all_dynamics_and_restart_keeps_qualities(self):
        save_preferences(self.user_data, {'default_velocities': {'melody': 48, 'harmony': 79},
                                         'quick_chord_qualities': ['maj9', 'm', '7'],
                                         'chord_velocity_options': [40, 80, 120]})
        with patch('lingfeng.ui.velocity_dialog.detect_options', side_effect=AssertionError('Detection must be requested')):
            window = self.window()
            dialog = DynamicsSettingsDialog(velocity.options(), window.project.audio['chords'])
            self.addCleanup(dialog.close)
            dialog.melody_velocity.setValue(51); dialog.instrument_velocity.setValue(68); dialog.chord_velocity.setValue(103)
            dialog.values.setText('35, 75, 115')
            with patch.object(dialog, 'exec', return_value=QDialog.DialogCode.Accepted), \
                    patch('lingfeng.ui.velocity_dialog.DynamicsSettingsDialog', return_value=dialog):
                window.velocity_preferences()
            saved = load_preferences(self.user_data)
            self.assertEqual(saved['default_velocities'], {'melody': 51, 'instrument': 68, 'harmony': 103})
            self.assertEqual(saved['chord_velocity_options'], [35, 75, 115])
            self.assertEqual(saved['quick_chord_qualities'], ['maj9', 'm', '7'])
            window.close(); chord_preferences.load_preferences({}); velocity.set_options(None)
            reopened = self.window()
        self.assertEqual(chord_preferences.settings_dict(), {
            'default_velocities': {'melody': 51, 'instrument': 68, 'harmony': 103},
            'quick_chord_qualities': ['maj9', 'm', '7']})
        self.assertEqual(velocity.options(), [35, 75, 115])
        dialog.values.setText('1, 2, 3'); dialog.chord_velocity.setValue(22)
        with patch.object(dialog, 'exec', return_value=QDialog.DialogCode.Rejected), \
                patch.object(dialog, 'value', side_effect=AssertionError('Cancelled values must not be read')), \
                patch('lingfeng.ui.velocity_dialog.DynamicsSettingsDialog', return_value=dialog), \
                patch.object(reopened, 'save_preferences') as save:
            reopened.velocity_preferences(); save.assert_not_called()
        self.assertEqual(load_preferences(self.user_data), saved)
        self.assertEqual(velocity.options(), [35, 75, 115])

    def test_compact_dynamics_keeps_buttons_visible_and_scrolls_to_long_detection_results(self):
        from lingfeng.ui.fonts import ensure_fonts
        ensure_fonts(); self.addCleanup(APP.setFont, APP.font())
        APP.setFont(QFont('Microsoft YaHei', 9)); i18n.set_language('en')
        dialog = DynamicsSettingsDialog([32, 64, 96], dict(device='default', program=0))
        self.addCleanup(dialog.close)
        dialog.resize(520, 500); dialog.show(); APP.processEvents()
        report = {'options': [32, 64, 96], 'bands': [(value, value) for value in range(1, 128)]}
        with patch('lingfeng.ui.velocity_dialog.detect_options', return_value=report):
            dialog.detect_button.click()
        QTest.qWait(30)
        self.assertIn('127', dialog.notice.text())
        self.assertEqual(dialog.value()['chord_velocity_options'], [32, 64, 96])
        for label in dialog.findChildren(QLabel):
            if label.isVisible() and label.hasHeightForWidth():
                self.assertGreaterEqual(label.height() + 1, label.heightForWidth(label.width()), label.text())
        scroll = dialog.scroll; bar = scroll.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        bottom_label = next(label for label in dialog.findChildren(QLabel)
                            if label.text().startswith('Sampled instruments'))
        bar.setValue(bar.maximum()); APP.processEvents()
        bottom = bottom_label.mapTo(scroll.viewport(), bottom_label.rect().bottomLeft())
        self.assertTrue(scroll.viewport().rect().contains(bottom))
        for button in dialog.buttons.buttons():
            rect = button.rect().translated(button.mapTo(dialog, QPoint()))
            self.assertTrue(dialog.rect().contains(rect)); self.assertTrue(button.isVisible())
        self.assertIsNotNone(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok))
        self.assertIsNotNone(dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel))

    def test_quality_confirmation_does_not_reset_saved_dynamics(self):
        save_preferences(self.user_data, {'default_velocities': {'melody': 39, 'instrument': 55, 'harmony': 108},
                                         'chord_velocity_options': [34, 71, 113]})
        window = self.window()
        dialog = ChordSettingsDialog(); self.addCleanup(dialog.close)
        dialog.set_all(False)
        first = dialog.list.item(0)
        from PySide6.QtCore import Qt
        first.setCheckState(Qt.CheckState.Checked)
        chosen = dialog.value()['quick_chord_qualities']
        self.assertFalse(hasattr(dialog, 'chord_velocity'))
        with patch.object(dialog, 'exec', return_value=QDialog.DialogCode.Accepted), \
                patch('lingfeng.ui.chord_settings_dialog.ChordSettingsDialog', return_value=dialog):
            window.chord_preferences()
        saved = load_preferences(self.user_data)
        self.assertEqual(saved['default_velocities'], {'melody': 39, 'instrument': 55, 'harmony': 108})
        self.assertEqual(saved['chord_velocity_options'], [34, 71, 113])
        self.assertEqual(saved['quick_chord_qualities'], chosen)


if __name__ == '__main__':
    unittest.main()
