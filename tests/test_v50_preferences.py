"""Upgrade/recovery contracts and installation-independent sound choices."""
import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from lingfeng import __version__
from lingfeng.platform.preferences import load_preferences, save_preferences, atomic_json, read_object
from lingfeng.music.progressions import load_library, presets, make_preset; from lingfeng.ui.progression_dialogs import ProgressionDialog
from lingfeng.music.progression_catalog import CATALOG_VERSION
from lingfeng.music.model import Project
import lingfeng.audio.soundbanks as banks

APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parent.parent


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.folder=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup);self.path=self.folder/'preferences.json'

    def test_upgrade_preserves_custom_values_and_original_backup(self):
        old=dict(theme='dark',language='en',keybindings={'play':''},custom_future={'x':3},
                 progression_presets=[make_preset('I/3 V7/7','My ending')],progression_catalog_version=CATALOG_VERSION)
        atomic_json(self.path,old);loaded=load_preferences(self.folder)
        updated=save_preferences(self.folder,{'theme':'light'},loaded)
        self.assertEqual(updated['custom_future'],old['custom_future'])
        self.assertEqual(updated['progression_presets'],old['progression_presets'])
        self.assertEqual(updated['keybindings'],old['keybindings'])
        self.assertEqual(updated['app_version'],__version__);self.assertEqual(updated['schema_version'],1)
        backup=self.folder/f'preferences.pre-{__version__}.json'
        self.assertEqual(read_object(backup),old)
        save_preferences(self.folder,{'theme':'dark'},updated)
        self.assertEqual(read_object(backup),old)

    def test_failed_atomic_replace_leaves_old_json_intact(self):
        atomic_json(self.path,{'theme':'dark'})
        with patch('lingfeng.platform.preferences.os.replace',side_effect=OSError('busy')):
            with self.assertRaises(OSError):atomic_json(self.path,{'theme':'light'})
        self.assertEqual(read_object(self.path),{'theme':'dark'})
        self.assertEqual(list(self.folder.glob('*.tmp')),[])

    def test_corrupt_json_recovers_last_good_and_preserves_damaged_bytes(self):
        atomic_json(self.path.with_suffix('.json.bak'),{'theme':'dark','progression_presets':[]})
        self.path.write_bytes(b'{truncated')
        loaded=load_preferences(self.folder);self.assertEqual(loaded['theme'],'dark')
        save_preferences(self.folder,{},loaded)
        self.assertEqual(read_object(self.path)['progression_presets'],[])
        self.assertEqual(self.path.with_suffix('.json.corrupt').read_bytes(),b'{truncated')

    def test_invalid_root_and_nested_types_do_not_break_loading(self):
        for data in (None,[],12,dict(keybindings=None,roll_coloring={'melody':None},chord_order=4,last_project_dir=[]),dict(chord_order=[{},'m'])):
            self.path.write_text(json.dumps(data),'utf-8');loaded=load_preferences(self.folder)
            self.assertIsInstance(loaded,dict)
            self.assertIsInstance(loaded.get('roll_coloring',{}).get('melody',{}),dict)
            self.assertTrue(all(isinstance(item,str) for item in loaded.get('chord_order',[])))

    def test_non_json_numbers_recover_backup_instead_of_crashing_upgrade(self):
        atomic_json(self.path.with_suffix('.json.bak'),{'theme':'dark'})
        self.path.write_text('{"value":NaN,"other":Infinity}','utf-8')
        loaded=load_preferences(self.folder);self.assertEqual(loaded['theme'],'dark')
        self.assertNotIn('value',loaded);save_preferences(self.folder,{},loaded)
        self.assertEqual(read_object(self.path)['app_version'],__version__)

    def test_newer_schema_and_unknown_fields_survive_save(self):
        atomic_json(self.path,{'schema_version':99,'future':['a']})
        result=save_preferences(self.folder,{'theme':'light'})
        self.assertEqual(result['schema_version'],99);self.assertEqual(result['future'],['a'])

    def test_deleted_entire_library_stays_empty_and_application_is_disabled(self):
        self.assertEqual(presets([]),[]);self.assertEqual(load_library([],CATALOG_VERSION),[])
        p=Project();p.fill_chord_gaps();d=ProgressionDialog(p,p.chords[0].id,[])
        try:
            self.assertEqual(d.preset.count(),0)
            self.assertFalse(d.buttons.button(d.buttons.StandardButton.Ok).isEnabled())
        finally:d.close();d.deleteLater()

    def test_future_catalog_does_not_reintroduce_deleted_presets(self):
        kept=[make_preset('IV iv I','Keep')]
        self.assertEqual(load_library(kept,CATALOG_VERSION+1),presets(kept))

    def test_window_restart_migrates_once_without_overwriting_choices(self):
        from lingfeng.ui.main_window import MainWindow
        old=dict(language='en',theme='dark',keybindings={'play':''},progression_presets=[],
                 progression_catalog_version=CATALOG_VERSION,another_setting='preserved')
        atomic_json(self.path,old)
        with patch('lingfeng.ui.main_window.user_data_dir',return_value=self.folder):
            for _ in range(2):
                w=MainWindow(Project());w.timer.stop();w.autosave.stop()
                try:
                    self.assertEqual(w.progression_presets,[]);self.assertEqual(w.keybindings['play'],'')
                    self.assertEqual(w.language,'en');w.save_preferences()
                finally:w.dirty=False;w.close();w.deleteLater();APP.processEvents()
        self.assertEqual(read_object(self.path)['another_setting'],'preserved')
        self.assertEqual(read_object(self.folder/f'preferences.pre-{__version__}.json'),old)


class SoundUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.base=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.newroot=self.base/'new'/'synths';self.oldroot=self.base/'old'/'synths'
        self.cache=self.base/'indexes'/'new.json';self.cache.parent.mkdir()
        shutil.copytree(ROOT/'synths'/'stk-essentials',self.newroot/'stk-essentials')
        self.patches=[patch.object(banks,'cache_path',return_value=self.cache),patch.object(banks,'default_root',return_value=self.newroot)]
        for item in self.patches:item.start();self.addCleanup(item.stop)
        banks._state=None;self.addCleanup(setattr,banks,'_state',None)
        self.saved={'melody':dict(device=banks.DEFAULT_DEVICE,program=24),'chords':dict(device=banks.DEFAULT_DEVICE,program=33)}

    def test_legacy_index_migrates_choices_and_extra_roots_but_rescans_dlls(self):
        extra=self.base/'external';extra.mkdir()
        legacy=dict(schema=1,roots=[str(self.oldroot),str(extra)],packs={'untrusted':{'path':'Z:/old.dll'}},defaults=self.saved)
        atomic_json(self.cache.parent/'old.json',legacy)
        state=banks.registry()
        self.assertEqual(banks.default_audio(),self.saved)
        self.assertEqual(state['roots'],[str(self.newroot.resolve()),str(extra.resolve())])
        self.assertNotIn('untrusted',state['packs']);self.assertTrue(banks.profile_path().exists())
        self.assertEqual(state['packs']['stk-essentials']['path'],str((self.newroot/'stk-essentials').resolve()))

    def test_second_new_directory_inherits_shared_profile(self):
        banks.registry();banks.save_defaults(self.saved)
        second=self.base/'next'/'synths';shutil.copytree(self.newroot,second)
        with patch.object(banks,'default_root',return_value=second),patch.object(banks,'cache_path',return_value=self.cache.parent/'next.json'):
            banks._state=None;self.assertEqual(banks.default_audio(),self.saved)
            self.assertEqual(banks.registry()['packs']['stk-essentials']['path'],str((second/'stk-essentials').resolve()))

    def test_explicit_project_audio_is_not_replaced_by_new_defaults(self):
        banks.registry();banks.save_defaults(self.saved)
        p=Project();data=copy.deepcopy(p.to_dict());data['audio']['melody']['program']=1
        self.assertEqual(Project.from_dict(data).audio['melody']['program'],1)


if __name__=='__main__':unittest.main()
