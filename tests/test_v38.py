"""Chord-selection searches and lossless inversion recipes."""
import copy,os,unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPoint,QEvent
from PySide6.QtWidgets import QApplication,QDialog
from lingfeng.ui.main_window import MainWindow
from lingfeng.platform.i18n import set_language
from lingfeng.music.model import Project, Chord, Context, QUALITIES, PPQ
from lingfeng.music.progressions import capture, selection_root_query, resolve, tokens, make_preset, matches_roots, apply; from lingfeng.ui.progression_dialogs import ProgressionManagerDialog, ProgressionEntryDialog, ProgressionDialog
APP=QApplication.instance() or QApplication([])

def project():
    p=Project();p.chords=[Chord(i*3840,3840,root,quality,bass) for i,(root,quality,bass) in enumerate(
        [(48,'',4),(55,'',None),(53,'maj7',9),(50,'m',None),(52,'m',11)])]
    return p

class RecipeTests(unittest.TestCase):
    def test_chronological_roots_ignore_unselected_chords_quality_and_bass(self):
        p=project();before=copy.deepcopy(p.to_dict());ids={p.chords[i].id for i in (4,0,2)}
        self.assertEqual(selection_root_query(p,ids),'I IV III')
        self.assertEqual(capture(p,ids),'I/3 IVmaj7/6 iii/7');self.assertEqual(p.to_dict(),before)
    def test_modal_spelling_against_one_starting_tonic(self):
        p=project();p.contexts=[Context(0,3840,48,'Lydian'),Context(3840,p.end,53,'Aeolian')]
        p.chords=[Chord(0,3840,54,'',1,flat=True),Chord(3840,3840,56,'m',0)]
        self.assertEqual(selection_root_query(p,{c.id for c in p.chords}),'#IV #V')
        self.assertFalse(matches_roots('bV III','#IV bIII'))
    def test_unknown_and_nc_do_not_supply_placeholder_roots(self):
        p=project()
        for c in (Chord(0,3840,recognized=False),Chord(0,3840,notes=[])):
            p.chords=[c]
            with self.assertRaises(ValueError):selection_root_query(p,{c.id})
        with self.assertRaises(ValueError):selection_root_query(p,set())
    def test_all_quality_inversions_roundtrip_in_different_keys_and_modes(self):
        p=Project()
        for tonic,mode in [(48,'Ionian'),(53,'Aeolian')]:
            p.contexts=[Context(0,p.end,tonic,mode)]
            for quality,intervals in QUALITIES.items():
                for interval in intervals:
                    c=Chord(0,3840,tonic+7,quality,(tonic+7+interval)%12,flat=True);p.chords=[c]
                    sequence=capture(p,{c.id});parsed=resolve(sequence,tonic)
                    self.assertEqual((parsed.root%12,parsed.quality,parsed.bass),(c.root%12,c.quality,c.bass))
                    self.assertIn('/',sequence);self.assertEqual(selection_root_query(p,{c.id}),'V')
    def test_saved_inversions_generate_their_bass_and_only_roots_filter(self):
        p=project();seq=capture(p,{p.chords[i].id for i in (0,2,4)})
        q=Project();q.fill_chord_gaps();ids=apply(q,q.chords[0].id,seq,False,'block')
        self.assertEqual([min(n.pitch for n in c.render_notes())%12 for c in q.chords if c.id in ids],[4,9,11])
        self.assertTrue(matches_roots(seq,'I IV III'));self.assertTrue(matches_roots(seq,'i7/5 IV/1 III7/2'))
        self.assertFalse(matches_roots(seq,'I IV #III'));q.validate()

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.saving=patch.object(MainWindow,'save_preferences');self.save=self.saving.start()
        self.w=MainWindow(project());self.w.change_language('zh',False);self.w.timer.stop();self.w.autosave.stop()
        self.w.resize(1100,820);self.w.show();APP.processEvents();self.dialogs=[]
    def tearDown(self):
        for d in self.dialogs:d.close();d.deleteLater()
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents();self.saving.stop()
    def menu(self,lane,ids,tick=100):
        lane.selection_event(ids);menu=lane.context_menu(QPoint(round(lane.x_at(tick)),25));self.dialogs.append(menu);return menu
    def find(self,menu):return next(a for a in menu.actions() if a.text()=='检索和弦进行…')
    def test_manager_prefills_roots_without_removing_recipe_inversions(self):
        values=[make_preset('I/3 V7/7 IVmaj7/6 iii/7','match'),make_preset('I IV #III','raised')]
        d=ProgressionManagerDialog(values,query='I IV III');self.dialogs.append(d)
        self.assertEqual(d.search_mode.currentData(),'roots');self.assertEqual(d.search.text(),'I – IV – III')
        self.assertEqual(d.table.rowCount(),1);self.assertEqual(d.table.item(0,1).text(),'I/3 – V7/7 – IVmaj7/6 – iii/7')
        self.assertCountEqual(d.value(),values)
    def test_menu_single_and_noncontiguous_multi_use_same_action(self):
        w=self.w;lane=w.chord_lane;calls=[]
        def inspect(d):
            calls.append((d.search.text(),d.parentWidget()));return QDialog.DialogCode.Rejected
        with patch.object(ProgressionManagerDialog,'exec',inspect):
            single=self.menu(lane,{w.project.chords[0].id});self.assertTrue(self.find(single).isEnabled());self.find(single).trigger()
            ids={w.project.chords[i].id for i in (4,0,2)};multi=self.menu(lane,ids);self.assertTrue(self.find(multi).isEnabled());self.find(multi).trigger()
        self.assertEqual([x[0] for x in calls],['I','I – IV – III']);self.assertTrue(all(x[1] is w for x in calls))
        self.assertEqual([a.text() for a in single.actions()],[a.text() for a in multi.actions()]);self.assertEqual(lane.editor.selected_chords,ids)
    def test_unknown_nc_mixed_and_empty_disable_search(self):
        w=self.w;lane=w.chord_lane;w.project.chords[1].recognized=False
        nc=Chord(5*3840,3840,notes=[]);w.project.chords.append(nc);w.refresh()
        for ids,tick in [({w.project.chords[1].id},4000),({w.project.chords[0].id,w.project.chords[1].id},100),({nc.id},nc.start+100)]:
            menu=self.menu(lane,ids,tick);self.assertFalse(self.find(menu).isEnabled())
        w.project.chords=[];w.refresh();self.assertFalse(self.find(self.menu(lane,set())).isEnabled())
    def test_independent_windows_keep_dialog_and_focus_local(self):
        w=self.w
        for pane,roll in ((w.melody_window,w.roll),(w.harmony_window,w.harmony_window.roll)):
            pane.setFloating(True);pane.activateWindow();roll.setFocus();APP.processEvents()
            menu=self.menu(roll.lane,{w.project.chords[0].id});before=copy.deepcopy(w.project.to_dict());parents=[]
            def inspect(d):parents.append(d.parentWidget());return QDialog.DialogCode.Rejected
            with patch.object(ProgressionManagerDialog,'exec',inspect):self.find(menu).trigger()
            self.assertIs(parents[0],pane);self.assertIs(APP.activeWindow(),pane);self.assertTrue(pane.isFloating())
            self.assertEqual(w.project.to_dict(),before)
    def test_search_cancel_changes_neither_music_library_nor_history(self):
        w=self.w;before=(copy.deepcopy(w.project.to_dict()),copy.deepcopy(w.progression_presets),list(w.undo_history),w.dirty)
        def edit_then_cancel(d):d.store_entry(make_preset('I/5 V/7','discard'));return QDialog.DialogCode.Rejected
        with patch.object(ProgressionManagerDialog,'exec',edit_then_cancel):w.search_progressions({w.project.chords[0].id},w.roll)
        self.assertEqual((w.project.to_dict(),w.progression_presets,w.undo_history,w.dirty),before)
    def test_search_confirm_saves_library_without_music_edit(self):
        w=self.w;entry=make_preset('I/5 V/7','saved');before=copy.deepcopy(w.project.to_dict());self.save.reset_mock()
        def edit_then_accept(d):d.store_entry(entry);return QDialog.DialogCode.Accepted
        with patch.object(ProgressionManagerDialog,'exec',edit_then_accept):w.search_progressions({w.project.chords[0].id},w.roll)
        self.assertIn(entry,w.progression_presets);self.assertEqual(w.project.to_dict(),before);self.save.assert_called_once()
    def test_capture_form_and_application_preview_keep_inversions(self):
        w=self.w;seen=[];ids={w.project.chords[i].id for i in (0,2,4)}
        def confirm(d):seen.append(d.value());return QDialog.DialogCode.Accepted
        with patch.object(ProgressionEntryDialog,'exec',confirm):w.capture_progression(ids)
        self.assertEqual(seen[0]['sequence'],'I/3 IVmaj7/6 iii/7');self.assertIn(seen[0],w.progression_presets)
        d=ProgressionDialog(w.project,w.project.chords[0].id,seen);self.dialogs.append(d)
        self.assertEqual(d.roman.text(),'I/3 – IVmaj7/6 – iii/7');self.assertEqual(d.resolved.text(),'C/E – Fmaj7/A – Em/B')
    def test_settings_menu_still_opens_unfiltered_library(self):
        seen=[]
        def inspect(d):seen.append(d.search.text());return QDialog.DialogCode.Rejected
        action=next(a for a in self.w.findChildren(type(self.w.visibility_actions['melody'])) if a.text()=='管理和弦进行…')
        with patch.object(ProgressionManagerDialog,'exec',inspect):action.trigger()
        self.assertEqual(seen,[''])

if __name__=='__main__':unittest.main()
