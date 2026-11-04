"""Menu customization keeps every command and frequent editing actions visible."""
import os
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMenu

from lingfeng.music.model import Chord, Note, Project
from lingfeng.platform import context_menu_preferences as preferences
from lingfeng.platform.preferences import load_preferences, save_preferences
from lingfeng.platform.i18n import set_language
from lingfeng.ui.context_menu_settings_dialog import ContextMenuSettingsDialog
from lingfeng.ui.piano_roll import KEY_W, PianoRoll
from tests.menu_helpers import walk_actions

APP = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parents[1]


class MenuPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.before = preferences.settings_dict()
        self.addCleanup(preferences.set_preferences, self.before)
        preferences.load_preferences({})

    def test_defaults_unfold_frequent_commands_and_group_advanced_properties(self):
        for kind in ('chord', 'note'):
            blocks = {block['id']: block for block in preferences.blocks(kind)}
            for code in ('clipboard', 'split_merge'):
                self.assertFalse(blocks[code]['groupable'])
                self.assertFalse(blocks[code]['grouped'])
        chord = {block['id']: block for block in preferences.blocks('chord')}
        self.assertTrue(chord['properties']['grouped'])
        self.assertTrue(chord['progressions']['grouped'])
        self.assertTrue(chord['insertion']['grouped'])
        self.assertFalse(chord['recognition']['grouped'])
        self.assertFalse(chord['dynamics']['grouped'])

    def test_malformed_and_duplicate_blocks_cannot_hide_or_group_common_commands(self):
        settings = {'chord': [None, dict(id=[]), dict(id='unknown'),
                              dict(id='delete', grouped=True), dict(id='properties', grouped=False),
                              dict(id='properties', grouped=True), dict(id='clipboard', grouped=True)],
                    'note': 'damaged'}
        preferences.load_preferences({'context_menu_layout': settings})
        chord = preferences.blocks('chord')
        self.assertEqual([block['id'] for block in chord[:3]], ['delete', 'properties', 'clipboard'])
        self.assertFalse(chord[0]['grouped'])
        self.assertFalse(chord[1]['grouped'])
        self.assertFalse(chord[2]['grouped'])
        for kind in ('chord', 'note'):
            codes = [block['id'] for block in preferences.blocks(kind)]
            self.assertEqual(len(codes), len(set(codes)))
            self.assertEqual(set(codes), {block['id'] for block in preferences.BLOCKS[kind]})
        preferences.load_preferences({'context_menu_layout': {'chord': [], 'note': []}})
        self.assertEqual(preferences.settings_dict()['context_menu_layout'], preferences.default_layout())

    def test_getters_return_copies_and_saved_order_and_grouping_survive_restart(self):
        values = preferences.default_layout()
        values['chord'].reverse()
        next(row for row in values['chord'] if row['id'] == 'properties')['grouped'] = False
        preferences.set_preferences({'context_menu_layout': values})
        expected = preferences.settings_dict()
        copy = preferences.blocks('chord')
        copy[0]['labels'] = ()
        copy[0]['grouped'] = True
        saved = preferences.settings_dict()
        saved['context_menu_layout']['chord'].clear()
        self.assertEqual(preferences.settings_dict(), expected)
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as folder:
            save_preferences(folder, dict(expected, future={'keep': True}))
            preferences.load_preferences({})
            loaded = load_preferences(folder)
            preferences.load_preferences(loaded)
            self.assertEqual(preferences.settings_dict(), expected)
            self.assertEqual(loaded['future'], {'keep': True})


class MenuSettingsDialogTests(unittest.TestCase):
    def setUp(self):
        self.before = preferences.settings_dict()
        self.addCleanup(preferences.set_preferences, self.before)
        preferences.load_preferences({})
        self.dialog = ContextMenuSettingsDialog()
        self.addCleanup(self.dialog.close)

    def item(self, kind, code):
        listing = self.dialog.lists[kind]
        return next(listing.item(row) for row in range(listing.count())
                    if listing.item(row).data(Qt.ItemDataRole.UserRole) == code)

    def test_fixed_commands_cannot_be_grouped_but_can_be_reordered(self):
        clipboard = self.item('chord', 'clipboard')
        self.assertFalse(clipboard.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        self.dialog.lists['chord'].setCurrentItem(clipboard)
        self.dialog.move_item('chord', -1)
        clipboard.setCheckState(Qt.CheckState.Checked)
        result = self.dialog.value()['context_menu_layout']['chord']
        self.assertEqual(result[0], dict(id='clipboard', grouped=False))

    def test_advanced_grouping_and_order_apply_only_after_confirmation(self):
        before = preferences.settings_dict()
        self.item('chord', 'properties').setCheckState(Qt.CheckState.Unchecked)
        self.dialog.lists['note'].setCurrentItem(self.item('note', 'delete'))
        self.dialog.move_item('note', -1)
        value = self.dialog.value()
        self.dialog.accept()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(preferences.settings_dict(), before)
        preferences.set_preferences(value)
        self.assertFalse(next(block for block in preferences.blocks('chord') if block['id'] == 'properties')['grouped'])
        self.assertEqual(preferences.blocks('note')[-2]['id'], 'delete')

    def test_cancel_discards_changes_and_reset_affects_only_current_page(self):
        before = preferences.settings_dict()
        self.item('chord', 'properties').setCheckState(Qt.CheckState.Unchecked)
        self.item('note', 'pitch').setCheckState(Qt.CheckState.Unchecked)
        self.dialog.reset_page('chord')
        value = self.dialog.value()['context_menu_layout']
        self.assertEqual(value['chord'], preferences.default_layout()['chord'])
        self.assertFalse(next(row for row in value['note'] if row['id'] == 'pitch')['grouped'])
        self.dialog.reject()
        self.assertEqual(preferences.settings_dict(), before)


class MenuLayoutIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.before = preferences.settings_dict()
        self.addCleanup(preferences.set_preferences, self.before)
        preferences.load_preferences({})
        set_language('zh')
        p = Project()
        p.notes = [Note(0, 960, 60)]
        p.chords = [Chord(0, 3840)]
        self.roll = PianoRoll(p)
        self.addCleanup(self.roll.close)
        self.roll.selected_ids = {p.notes[0].id}

    def menu(self, kind):
        if kind == 'chord':
            menu = self.roll.lane.context_menu(QPoint(KEY_W + 8, 15))
        else:
            menu = QMenu()
            self.roll.selected_ids = {self.roll.project.notes[0].id}
            self.roll.selection_menu(menu, 0)
        self.addCleanup(menu.close)
        return menu

    def labels(self, menu, recursive=False):
        actions = walk_actions(menu) if recursive else menu.actions()
        return [action.text().split('\t', 1)[0] for action in actions if not action.isSeparator()]

    def test_frequent_editing_commands_are_direct_by_default(self):
        chord = self.labels(self.menu('chord'))
        for label in ('复制所选和弦', '在此和弦开头覆盖粘贴', '在定位线处粘贴和弦', '在定位线处分割和弦', '二等分和弦', '合并相邻和弦'):
            self.assertIn(label, chord)
        note = self.labels(self.menu('note'))
        for label in ('复制所选音符', '复制变换', '在此粘贴音符', '在定位线处粘贴音符', '合并相邻音符', '二等分音符'):
            self.assertIn(label, note)

    def test_reordering_and_unfolding_preserve_all_leaf_commands(self):
        for kind in ('chord', 'note'):
            before = self.menu(kind)
            before_leaves = [action.text().split('\t', 1)[0] for action in walk_actions(before)
                             if not action.isSeparator() and action.menu() is None]
            layout = preferences.default_layout()
            layout[kind].reverse()
            for row in layout[kind]:
                row['grouped'] = False
            preferences.set_preferences({'context_menu_layout': layout})
            after = self.menu(kind)
            after_leaves = [action.text().split('\t', 1)[0] for action in walk_actions(after)
                            if not action.isSeparator() and action.menu() is None]
            self.assertCountEqual(after_leaves, before_leaves)
            self.assertEqual(self.labels(after)[0], '删除所选和弦' if kind == 'chord' else '删除所选音符')
            if kind == 'chord':
                self.assertIn('和弦根音', self.labels(after))

    def test_main_window_confirms_saves_restarts_and_discards_cancelled_layout(self):
        from lingfeng.ui.main_window import MainWindow
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as folder, \
                patch.dict(os.environ, {'LINGFENG_USER_DATA': folder}), ExitStack() as stack:
            window = MainWindow(Project())
            window.timer.stop(); window.autosave.stop()
            stack.callback(lambda: (setattr(window, 'dirty', False), window.close()))
            layout = preferences.default_layout()
            layout['chord'].reverse()
            next(row for row in layout['chord'] if row['id'] == 'properties')['grouped'] = False
            chosen = {'context_menu_layout': layout}
            dialog = Mock()
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.value.return_value = chosen
            with patch('lingfeng.ui.context_menu_settings_dialog.ContextMenuSettingsDialog', return_value=dialog):
                window.context_menu_preferences()
            self.assertEqual(load_preferences(folder)['context_menu_layout'], layout)
            window.dirty = False; window.close()
            preferences.load_preferences({})
            reopened = MainWindow(Project())
            reopened.timer.stop(); reopened.autosave.stop()
            stack.callback(lambda: (setattr(reopened, 'dirty', False), reopened.close()))
            self.assertEqual(preferences.settings_dict(), chosen)
            dialog.exec.return_value = QDialog.DialogCode.Rejected
            dialog.value.side_effect = AssertionError('Cancelled changes must not be applied')
            with patch('lingfeng.ui.context_menu_settings_dialog.ContextMenuSettingsDialog', return_value=dialog), \
                    patch.object(reopened, 'save_preferences') as save:
                reopened.context_menu_preferences()
                save.assert_not_called()
            self.assertEqual(preferences.settings_dict(), chosen)
            reopened.dirty = False; reopened.close()


if __name__ == '__main__':
    unittest.main()
