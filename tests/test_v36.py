"""View means docked visibility; progression recipes have musical ordering."""
import copy,os,unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPointF,QEvent
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from popscore.app import MainWindow
from popscore.model import Project,Chord,Note
from popscore.progressions import presets,progression_key,progression_label,preset_label,tokens,ProgressionDialog,ProgressionSettingsDialog,DEFAULT_PRESETS
from popscore.fonts import ensure_fonts
APP=QApplication.instance() or QApplication([]);ensure_fonts()

class ProgressionTests(unittest.TestCase):
    def test_ascii_and_typographic_separators_normalize(self):
        for text in ('I-IV-V','I – IV – V','I IV V','I—IV→V'):
            self.assertEqual(tokens(text),['I','IV','V']);self.assertEqual(progression_label(text),'I – IV – V')
        self.assertEqual(tokens('V/vi-vi-I/3'),['V/vi','vi','I/3'])
    def test_degree_order_and_prefix_length(self):
        seqs=['I IV V vi IV I V','I IV vi','I IV V','ii V I','I IV','I IV V ii']
        rows=presets([dict(name=s,sequence=s) for s in seqs])
        self.assertEqual([r['sequence'] for r in rows],['I IV','I IV V','I IV V ii','I IV V vi IV I V','I IV vi','ii V I'])
        self.assertTrue(all(r['name']==progression_label(r['sequence']) for r in rows))
    def test_same_degree_quality_and_accidentals_have_stable_order(self):
        self.assertLess(progression_key('bII V'),progression_key('II V'))
        self.assertLess(progression_key('II V'),progression_key('#II V'))
        self.assertLess(progression_key('I V'),progression_key('i V'))
        self.assertLess(progression_key('I7 V'),progression_key('I9 V'))
    def test_custom_names_survive_and_default_presets_are_sorted_without_mutation(self):
        before=copy.deepcopy(DEFAULT_PRESETS);ordered=presets(None)
        self.assertEqual(DEFAULT_PRESETS,before);self.assertEqual([progression_key(x['sequence']) for x in ordered],sorted(progression_key(x['sequence']) for x in before))
        entry=presets([dict(name='副歌',sequence='I-IV-V')])[0]
        self.assertEqual(entry['name'],'副歌');self.assertEqual(preset_label(entry),'副歌: I – IV – V')
    def test_settings_and_application_show_the_same_sorted_recipes(self):
        values=[dict(name=s,sequence=s) for s in ('I IV vi','I IV V vi I V I','I IV V')]
        settings=ProgressionSettingsDialog(values);ordered=settings.value()
        p=Project();p.chords=[Chord(0,3840)];dialog=ProgressionDialog(p,p.chords[0].id,values)
        self.assertEqual([dialog.preset.itemData(i) for i in range(dialog.preset.count())],[e['sequence'] for e in ordered])
        self.assertEqual(dialog.preset.itemText(0),'I – IV – V');settings.deleteLater();dialog.deleteLater()

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.save=patch.object(MainWindow,'save_preferences');self.save.start()
        p=Project();p.chords=[Chord(0,3840)];self.w=MainWindow(p);self.w.change_language('zh',False);self.w.resize(1100,850);self.w.show();self.w.timer.stop();self.w.autosave.stop();APP.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.save.stop()
    def panes(self):return (self.w.melody_window,self.w.harmony_window)
    def test_float_unchecks_without_hiding_and_dock_checks(self):
        w=self.w
        for pane in self.panes():
            action=w.visibility_actions[pane.key];action.setChecked(True);pane.setFloating(True);APP.processEvents()
            self.assertFalse(action.isChecked());self.assertTrue(pane.isVisible());self.assertTrue(pane.isFloating())
            w.refresh();w.mount_panels();self.assertTrue(pane.isVisible())
            pane.setFloating(False);self.assertTrue(action.isChecked());self.assertTrue(pane.isVisible());self.assertIs(pane.window(),w)
    def test_close_float_stays_hidden_until_view_check_docks(self):
        w=self.w
        for pane in self.panes():
            pane.setFloating(True);pane.close();APP.processEvents();self.assertTrue(pane.isFloating());self.assertFalse(pane.isVisible());self.assertFalse(w.visibility_actions[pane.key].isChecked())
            w.mount_panels();w.refresh();self.assertFalse(pane.isVisible())
            w.visibility_actions[pane.key].setChecked(True);APP.processEvents()
            self.assertFalse(pane.isFloating());self.assertTrue(pane.isVisible());self.assertIs(pane.window(),w)
    def test_view_check_reclaims_a_visible_float(self):
        w=self.w
        for pane in self.panes():
            pane.setFloating(True);w.visibility_actions[pane.key].setChecked(True)
            self.assertFalse(pane.isFloating());self.assertTrue(pane.isVisible())
            w.visibility_actions[pane.key].setChecked(False);self.assertFalse(pane.isVisible())
    def test_navigation_and_undo_reuse_float_without_checking_view(self):
        w=self.w;pane=w.harmony_window;r=pane.roll;pane.setFloating(True);pane.close();APP.processEvents()
        w.open_harmony(w.project.chords[0].id);self.assertTrue(pane.isFloating());self.assertTrue(pane.isVisible());self.assertFalse(w.visibility_actions['harmony'].isChecked())
        pane.activateWindow();r.setFocus();APP.processEvents();w.edit_notes(r,[Note(0,240,63)],[]);w.undo()
        self.assertTrue(pane.isFloating());self.assertFalse(w.visibility_actions['harmony'].isChecked());self.assertIs(APP.activeWindow(),pane)
        w.melody_window.setFloating(True);w.switch_input_roll(r);self.assertTrue(w.melody_window.isFloating());self.assertFalse(w.visibility_actions['melody'].isChecked())
    def test_score_roundtrip_preserves_closed_float_and_docked_checkbox(self):
        w=self.w;w.melody_window.setFloating(True);w.melody_window.close();APP.processEvents();w.visibility_actions['harmony'].setChecked(True)
        w.switch_workspace('score');w.switch_workspace('compose');APP.processEvents()
        self.assertTrue(w.melody_window.isFloating());self.assertFalse(w.melody_window.isVisible());self.assertFalse(w.visibility_actions['melody'].isChecked())
        self.assertFalse(w.harmony_window.isFloating());self.assertTrue(w.visibility_actions['harmony'].isChecked());self.assertTrue(w.harmony_window.isVisible())
    def test_language_preserves_visible_and_closed_float_states(self):
        w=self.w;w.melody_window.setFloating(True);w.harmony_window.setFloating(True);w.harmony_window.close();APP.processEvents()
        w.change_language('en',False);APP.processEvents()
        self.assertTrue(w.melody_window.isFloating());self.assertTrue(w.melody_window.isVisible());self.assertFalse(w.visibility_actions['melody'].isChecked())
        self.assertTrue(w.harmony_window.isFloating());self.assertFalse(w.harmony_window.isVisible());self.assertFalse(w.visibility_actions['harmony'].isChecked())
        w.visibility_actions['harmony'].setChecked(True);self.assertFalse(w.harmony_window.isFloating());self.assertTrue(w.harmony_window.isVisible())
    def test_view_check_from_score_returns_roll_to_main_compose(self):
        w=self.w;w.melody_window.setFloating(True);w.switch_workspace('score');w.visibility_actions['melody'].setChecked(True)
        self.assertEqual(w.workspace,'compose');self.assertFalse(w.melody_window.isFloating());self.assertTrue(w.visibility_actions['melody'].isChecked())
    def test_language_change_in_score_preserves_compose_window_states(self):
        w=self.w;w.melody_window.setFloating(True);w.harmony_window.setFloating(True);w.harmony_window.close();APP.processEvents()
        w.switch_workspace('score');w.change_language('en',False);w.switch_workspace('compose');APP.processEvents()
        self.assertTrue(w.melody_window.isFloating());self.assertTrue(w.melody_window.isVisible());self.assertFalse(w.visibility_actions['melody'].isChecked())
        self.assertTrue(w.harmony_window.isFloating());self.assertFalse(w.harmony_window.isVisible());self.assertFalse(w.visibility_actions['harmony'].isChecked())
    def test_language_rebuild_disposes_focused_peer_windows(self):
        from shiboken6 import isValid
        w=self.w;old=[]
        for pane in self.panes():pane.setFloating(True)
        w.harmony_window.activateWindow();w.harmony_window.roll.setFocus();APP.processEvents()
        for language in ('en','zh','en'):
            old.extend(self.panes());w.change_language(language,False)
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()
        self.assertTrue(all(not isValid(pane) for pane in old))
        self.assertTrue(all(pane.isVisible() and pane.isFloating() for pane in self.panes()))
        self.assertTrue(all(not w.visibility_actions[pane.key].isChecked() for pane in self.panes()))
    def test_captured_recipe_defaults_to_separator_format_and_sorted_storage(self):
        w=self.w;w.project.chords=[Chord(0,960),Chord(960,960,53),Chord(1920,960,55)]
        ids={c.id for c in w.project.chords}
        from popscore.progressions import ProgressionEntryDialog
        def confirm(dialog):
            self.assertEqual(dialog.sequence.text(),'I – IV – V');self.assertEqual(dialog.name.text(),'I – IV – V');return dialog.DialogCode.Accepted
        with patch.object(ProgressionEntryDialog,'exec',confirm):w.capture_progression(ids)
        self.assertEqual([progression_key(e['sequence']) for e in w.progression_presets],sorted(progression_key(e['sequence']) for e in w.progression_presets))
    def test_ruler_rows_share_baselines_and_columns(self):
        w=self.w;p=w.project;p.measures[0].section='Intro';p.measures[1].section='Verse';p.set_markers([1],tonic=53,mode='Aeolian',numerator=3,denominator=4,allow_trim=True)
        r=w.roll;r.zoom=100;r.set_panel('ruler',True)
        class Recorder(QPainter):
            def __init__(self,image):super().__init__(image);self.texts=[]
            def drawText(self,*args):
                if isinstance(args[0],QPointF):self.texts.append((args[1],args[0].x(),args[0].y()))
                return super().drawText(*args)
        image=QImage(1000,80,QImage.Format.Format_ARGB32);painter=Recorder(image);r.paint_ruler(painter,1000,r.timeline_height,r.x_at);painter.end()
        find=lambda label:next((x,y) for text,x,y in painter.texts if text==label)
        self.assertEqual(find('1')[1],find('Intro')[1]);self.assertGreater(find('Intro')[0],find('1')[0])
        self.assertEqual(find('4/4')[0],find('1')[0]);self.assertEqual(find('4/4')[1],find('1=C3 · Ionian')[1]);self.assertGreater(find('4/4')[1],find('1')[1])
        self.assertAlmostEqual(find('1=C3 · Ionian')[0]-find('4/4')[0],find('1=F3 · Aeolian')[0]-find('3/4')[0])

if __name__=='__main__':unittest.main()
