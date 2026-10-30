"""Independent score panes, immediate lyric presentation, isolated audio IO."""
import copy,os,unittest
from unittest.mock import patch,MagicMock
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from popscore.app import MainWindow
from popscore.model import Project,Note
from popscore.lyrics import events

APP=QApplication.instance() or QApplication([])


class ScorePanelsTests(unittest.TestCase):
    def setUp(self):
        p=Project();p.notes=[Note(0,960,60),Note(960,960,62)]
        self.w=MainWindow(p);self.w.timer.stop();self.w.autosave.stop();self.w.show();self.w.switch_workspace('score');APP.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents()

    def test_first_entry_order_and_mode_specific_menu(self):
        w=self.w
        self.assertEqual([w.score_tabs.tabText(i) for i in range(4)],['旋律卷帘','和弦卷帘','歌词','结构逻辑'])
        self.assertTrue(w.score_tools.isVisible());self.assertFalse(w.edit_toggle.isVisible())
        self.assertEqual(w.view_menu.actions(),list(w.score_view_actions.values()))
        w.switch_workspace('compose');self.assertEqual(w.view_menu.actions(),w.compose_menu_actions)
        w.switch_workspace('score');self.assertEqual(w.score_tabs.count(),4)

    def test_float_close_and_reopen_affect_one_tab_and_restore_modes(self):
        w=self.w;w.show_score_panel('lyrics');w.score_float.activated.emit();APP.processEvents()
        lyrics=w.score_floats['lyrics'];self.assertTrue(lyrics.isVisible());self.assertEqual(w.score_tabs.count(),3)
        w.toggle_score_panel_floating('melody');w.set_score_panel_visible('logic',False)
        self.assertEqual(w.score_tabs.currentWidget(),w.score_harmony_page)
        self.assertIs(w.roll.window(),w.score_floats['melody'])
        self.assertTrue(w.melody_toolbar.isVisible());self.assertTrue(w.harmony_window.toolbar.isVisible())
        state=copy.deepcopy(w.score_panel_state);lyrics.resize(820,490);position=lyrics.geometry()
        w.switch_workspace('compose');self.assertFalse(lyrics.isVisible());self.assertIs(w.roll.window(),w)
        w.switch_workspace('score');APP.processEvents()
        self.assertEqual(w.score_panel_state,state);self.assertTrue(lyrics.isVisible());self.assertEqual(lyrics.geometry(),position)
        lyrics.close();self.assertFalse(w.score_panel_state['lyrics']['visible']);self.assertTrue(w.score_floats['melody'].isVisible())
        w.score_view_actions['lyrics'].setChecked(True);self.assertTrue(lyrics.isVisible())
        lyrics.title_bar.dock.activated.emit();self.assertFalse(lyrics.isFloating());self.assertIs(w.score_tabs.currentWidget(),w.lyric_panel)
        w.show_score_panel('logic');self.assertEqual([w.score_tabs.tabText(i) for i in range(w.score_tabs.count())],['和弦卷帘','歌词','结构逻辑'])

    def test_all_closed_and_restore_one_then_language_keeps_float_and_draft(self):
        w=self.w
        for key in w.score_pages:w.set_score_panel_visible(key,False)
        self.assertFalse(w.score_tools.isVisible());w.switch_workspace('compose');w.switch_workspace('score')
        self.assertFalse(w.score_tools.isVisible());w.show_score_panel('lyrics');self.assertEqual(w.score_tabs.count(),1)
        w.lyric_panel.text.setPlainText('草稿');w.toggle_score_panel_floating('lyrics')
        w.change_language('en',persist=False);APP.processEvents()
        self.assertTrue(w.score_floats['lyrics'].isVisible());self.assertEqual(w.lyric_panel.text.toPlainText(),'草稿')
        self.assertFalse(w.score_panel_state['logic']['visible']);w.change_language('zh',persist=False)

    def test_lyrics_apply_update_delete_and_undo_change_current_score(self):
        w=self.w;w.show_score_panel('lyrics');panel=w.lyric_panel;panel.count.setValue(1);panel.text.setPlainText('春风');panel.commit()
        ident=panel.current_id;self.assertIsNotNone(ident)
        self.assertEqual([e['text'] for e in events(w.score_view.canvas.project)],['春','风'])
        panel.text.setPlainText('秋雨');panel.commit();self.assertEqual(panel.current_id,ident)
        self.assertEqual([e['text'] for e in events(w.score_view.canvas.project)],['秋','雨'])
        w.undo();self.assertEqual([e['text'] for e in events(w.score_view.canvas.project)],['春','风'])
        w.redo();panel.delete();self.assertEqual(events(w.score_view.canvas.project),[])
        w.undo();self.assertEqual([e['text'] for e in events(w.score_view.canvas.project)],['秋','雨'])

    def test_floating_roll_shortcuts_and_score_navigation(self):
        w=self.w;w.toggle_score_panel_floating('harmony');w.harmony_window.roll.setFocus();APP.processEvents()
        self.assertIs(w.active_roll(),w.harmony_window.roll)
        with patch.object(w.score_view,'locate_bar') as locate:w.harmony_window.roll.measureActivated.emit(0);locate.assert_not_called()
        w.toggle_score_panel_floating('lyrics');w.lyric_panel.apply.setFocus();APP.processEvents()
        with patch.object(w,'save') as save:
            QTest.keyClick(w.lyric_panel.apply,Qt.Key.Key_S,Qt.KeyboardModifier.ControlModifier);save.assert_called_once()


class AudioProcessTests(unittest.TestCase):
    def test_worker_refills_full_blocks_and_preserves_midi_stop_order(self):
        from popscore.synthesis import _synthesis_worker,BLOCK
        connection=MagicMock();commands=iter([('midi',(0x90,60,90)),('stop',()),('close',())])
        # Render once, then drain the commands and clean up on close.
        connection.poll.side_effect=[False,True,True,True];connection.recv.side_effect=lambda:next(commands)
        player=MagicMock();player.buffersize=4096;player.currentpadding=0;player.deviceperiod=(.01,.003)
        with patch('popscore.synthesis.SynthEngine') as engine,patch('popscore.exporting._com_apartment'),patch('soundcard.default_speaker') as speaker,patch('popscore.synthesis.write_output') as output:
            speaker.return_value.player.return_value.__enter__.return_value=player
            _synthesis_worker(connection,{0:'synth:stk-essentials'},{0:1})
            engine.return_value.render.assert_called_once_with(BLOCK);output.assert_called_once()
            self.assertEqual(engine.return_value.send.call_args_list[-1].args,(0x90,60,90))
            engine.return_value.stop.assert_called_once();engine.return_value.close.assert_called_once();connection.close.assert_called_once()

    def test_startup_failure_closes_process_and_pipe(self):
        from popscore.synthesis import NativeSynth
        with patch('popscore.synthesis.multiprocessing.get_context') as context:
            parent=MagicMock();child=MagicMock();context.return_value.Pipe.return_value=(parent,child)
            parent.recv.return_value=('error','No audio device');process=context.return_value.Process.return_value
            process.is_alive.return_value=False
            with self.assertRaisesRegex(RuntimeError,'No audio device'):NativeSynth({}, {})
            parent.close.assert_called_once();process.close.assert_called_once()


if __name__=='__main__':unittest.main()
