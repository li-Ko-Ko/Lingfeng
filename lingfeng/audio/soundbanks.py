"""Folder-installed synthesis packs and a persistent, per-installation index.

Scanning validates files without executing synth DLLs. Projects store stable IDs,
never library paths.
"""
import hashlib,json,math,os,re,sys
from pathlib import Path
from lingfeng import __version__
from lingfeng.platform.i18n import tr

DEFAULT_DEVICE='synth:stk-essentials'
GENERALUSER_GS_DEVICE='synth:generaluser-gs'
MUSESCORE_LITE_DEVICE='synth:musescore-lite-piano-test'
CALIBRATION_FILE='calibration.json'
_state=None
_identity=None

def app_root():
    from lingfeng.platform.paths import application_root
    return application_root()

def default_root():return app_root()/'synths'

def cache_path():
    if os.environ.get('LINGFENG_SYNTH_CACHE'):return Path(os.environ['LINGFENG_SYNTH_CACHE'])
    ident=hashlib.sha256(str(app_root()).casefold().encode()).hexdigest()[:16]
    return Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'Lingfeng'/'synth-index'/(ident+'.json')

def profile_path():
    # Indexes remain installation-specific; choices and extra folders do not.
    return cache_path().parent/'user-settings.json'

def _user_profile():
    from lingfeng.platform.preferences import read_object
    profile=read_object(profile_path())
    if profile and profile.get('schema')==1 and isinstance(profile.get('roots'),list):return profile
    # One-time upgrade from pre-0.50 per-installation indexes. Read metadata,
    # never cached DLL paths; the new install scans and validates its own packs.
    candidates=[]
    for path in cache_path().parent.glob('*.json'):
        if path==profile_path():continue
        state=read_object(path)
        if state and state.get('schema')==1 and isinstance(state.get('packs'),dict) and isinstance(state.get('roots'),list):
            try:candidates.append((path.stat().st_mtime_ns,state))
            except OSError:pass
    if not candidates:return {}
    state=max(candidates,key=lambda item:item[0])[1]
    return dict(schema=1,roots=[p for p in state['roots'][1:] if isinstance(p,str)],defaults=state.get('defaults'))

def is_synth_source(device):return isinstance(device,str) and device.startswith('synth:')

def _inside(root,relative):
    from lingfeng.audio.sfz import relative_file
    path=(root/relative_file(relative)).resolve()
    if not path.is_relative_to(root) or not path.is_file():raise ValueError('Missing or unsafe pack file: '+relative)
    return path

def _validate(data,root,verify_files=True):
    if not isinstance(data,dict):raise ValueError('Invalid synth manifest')
    if data.get('schema')!=1 or data.get('abi')!=1 or data.get('platform')!='windows-x64':raise ValueError('Unsupported synth pack version/platform')
    engine=data.get('engine','native')
    if engine not in ('native','sfz','sf2'):raise ValueError('Unsupported synth engine')
    if not re.fullmatch('[a-z0-9][a-z0-9._-]{0,63}',data.get('id','')):raise ValueError('Invalid pack ID')
    for name in ('name','name_en','version','license','source','author','library','license_file','sha256'):
        if not isinstance(data.get(name),str) or not data[name]:raise ValueError('Missing '+name)
    from lingfeng.audio.sfz import relative_file,validate_assets
    relative_file(data['library']);relative_file(data['license_file'])
    if not re.fullmatch('[0-9a-f]{64}',data['sha256']):raise ValueError('Invalid library checksum')
    if type(data.get('voices',128)) is not int or not 32<=data.get('voices',128)<=1024:raise ValueError('Invalid polyphony')
    if engine=='sf2':
        hashes=data.get('library_hashes')
        if not isinstance(hashes,dict) or not 1<=len(hashes)<=64 or hashes.get(data['library'])!=data['sha256']:raise ValueError('Missing SF2 runtime checksums')
        for name,digest in hashes.items():
            relative_file(name)
            if not name.lower().endswith('.dll') or not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('Invalid SF2 dependency')
            if verify_files and hashlib.sha256(_inside(root,name).read_bytes()).hexdigest()!=digest:raise ValueError('SF2 dependency checksum mismatch')
    if verify_files:
        library=_inside(root,data['library']);_inside(root,data['license_file'])
        if library.suffix.lower()!='.dll':raise ValueError('Expected a Windows DLL')
        binary=library.read_bytes()
        if hashlib.sha256(binary).hexdigest()!=data.get('sha256'):raise ValueError('Library checksum mismatch')
        offset=int.from_bytes(binary[60:64],'little')
        if binary[:2]!=b'MZ' or binary[offset:offset+6]!=b'PE\x00\x00\x64\x86':raise ValueError('Expected a Windows x64 native library')
    rows=data.get('presets',[]);seen=set();assets_checked=set()
    if not isinstance(rows,list) or not 1<=len(rows)<=128:raise ValueError('Invalid preset list')
    for item in rows:
        if not isinstance(item,dict):raise ValueError('Invalid preset')
        p=item.get('program');model=item.get('model');gain=item.get('gain')
        if type(p) is not int or not 0<=p<=127 or p in seen:raise ValueError('Invalid/duplicate program')
        seen.add(p)
        if type(model) is not int or not 0<=model<=65535:raise ValueError('Invalid model')
        if type(gain) not in (int,float) or not math.isfinite(gain) or not 0<gain<=2:raise ValueError('Invalid gain')
        cutoff=item.get('cutoff_hz',6500)
        if type(cutoff) not in (int,float) or not math.isfinite(cutoff) or not 200<=cutoff<=16000:raise ValueError('Invalid tone cutoff')
        if not isinstance(item.get('name'),str) or not isinstance(item.get('name_en'),str):raise ValueError('Invalid preset name')
        controls=item.get('controls',{})
        if not isinstance(controls,dict) or any(not str(k).isdigit() or not 0<=int(k)<=128 or type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=128 for k,v in controls.items()):raise ValueError('Invalid controls')
        if engine=='sfz':
            relative_file(item.get('sfz'))
            if 'cutoff_hz' in item:raise ValueError('SFZ presets must set tone in their mapping')
            if any(int(k)>127 or v>127 for k,v in controls.items()):raise ValueError('Invalid SFZ MIDI control')
            if verify_files and item['sfz'] not in assets_checked:validate_assets(root,item['sfz']);assets_checked.add(item['sfz'])
        elif engine=='sf2':
            relative_file(item.get('sf2'))
            if model>127 or type(item.get('bank',0)) is not int or not 0<=item.get('bank',0)<=16383:raise ValueError('Invalid SF2 program/bank')
            if 'cutoff_hz' in item or any(int(k)>127 or v>127 for k,v in controls.items()):raise ValueError('Invalid SF2 controls')
            if verify_files and item['sf2'] not in assets_checked:
                with _inside(root,item['sf2']).open('rb') as file:header=file.read(12)
                if header[:4]!=b'RIFF' or header[8:12]!=b'sfbk':raise ValueError('Expected an SF2 soundfont')
                assets_checked.add(item['sf2'])
    return data

def _preset_gains(pack_data, values):
    from lingfeng.audio.events import MAX_SOURCE_GAIN_DB, MIN_SOURCE_GAIN_DB
    programs={str(row['program']) for row in pack_data['presets']}
    if not isinstance(values,dict) or values.keys()-programs or any(
        type(value) not in (int,float) or not MIN_SOURCE_GAIN_DB<=value<=MAX_SOURCE_GAIN_DB
        for value in values.values()
    ):
        raise ValueError('Invalid preset gain calibration')
    return {key:float(value) for key,value in values.items()}

def _load_calibration(root, data):
    if not (root/CALIBRATION_FILE).exists():return {}
    path=_inside(root,CALIBRATION_FILE)
    if path.stat().st_size>16384:raise ValueError('Preset gain calibration is too large')
    calibration=json.loads(path.read_text('utf-8'))
    if not isinstance(calibration,dict) or type(calibration.get('schema')) is not int or calibration['schema']!=1:
        raise ValueError('Invalid preset gain calibration schema')
    return _preset_gains(data,calibration.get('preset_gain_db'))

def _write(state):
    from lingfeng.platform.preferences import atomic_json
    atomic_json(cache_path(),state)
    atomic_json(profile_path(),dict(schema=1,roots=[p for p in state['roots'] if Path(p).resolve()!=default_root().resolve()],defaults=state.get('defaults')))

def rescan(roots=None,persist=True):
    """Explicit scan isolates broken packs and reports duplicate IDs."""
    global _state,_identity
    prior=_state or {}
    roots=roots if roots is not None else prior.get('roots',[str(default_root())])
    roots=list(dict.fromkeys([str(default_root().resolve()),*[str(Path(p).expanduser().resolve()) for p in roots]]))
    packs={};errors=[];visited=set()
    for folder in roots:
        root=Path(folder)
        try:files=sorted(set([root/'synth.json',*root.glob('*/synth.json')]))
        except OSError as exc:errors.append(str(exc));continue
        for file in files:
            if not file.is_file() or file.resolve() in visited:continue
            visited.add(file.resolve())
            try:
                if file.stat().st_size>256000:raise ValueError('Manifest is too large')
                folder=file.parent.resolve()
                data=_validate(json.loads(file.read_text('utf-8')),folder)
                if data['id'] in packs:raise ValueError('Duplicate pack ID: '+data['id'])
                try:gains=_load_calibration(folder,data)
                except (OSError,ValueError,RecursionError) as exc:
                    gains={};errors.append(str(folder/CALIBRATION_FILE)+': '+str(exc))
                packs[data['id']]=dict(data,path=str(folder),manifest_stamp=file.stat().st_mtime_ns,preset_gain_db=gains)
            except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:errors.append(str(file)+': '+str(exc))
    state=dict(schema=1,app_version=__version__,roots=roots,packs=packs,errors=errors,defaults=prior.get('defaults'))
    if persist:_write(state)
    _state=state;_identity=(str(default_root()),str(cache_path()));return state

def registry():
    global _state,_identity
    identity=(str(default_root()),str(cache_path()))
    if _state is not None and identity==_identity:return _state
    _identity=identity;_state=None
    try:
        state=json.loads(cache_path().read_text('utf-8'))
        if state.get('schema')!=1 or not isinstance(state.get('packs'),dict) or not isinstance(state.get('roots'),list):raise ValueError('Invalid index')
        if not all(isinstance(p,str) and p for p in state['roots']):raise ValueError('Invalid cached roots')
        roots=[Path(p).resolve() for p in state['roots']]
        for ident,item in state['packs'].items():
            _validate(item,None,verify_files=False)
            _preset_gains(item,item.get('preset_gain_db',{}))
            if item['id']!=ident or not isinstance(item.get('path'),str) or type(item.get('manifest_stamp')) is not int:raise ValueError('Invalid cached pack')
            path=Path(item['path']).resolve()
            if not any(path==root or path.parent==root for root in roots):raise ValueError('Cached pack is outside its scanned folders')
        profile=_user_profile()
        if profile:
            state['defaults']=profile.get('defaults')
            roots=list(dict.fromkeys([str(default_root().resolve()),*[str(Path(p).expanduser().resolve()) for p in profile.get('roots',[]) if isinstance(p,str)]]))
            if roots!=state['roots']:
                _state=state
                return rescan(roots)
        if state.get('app_version')!=__version__:
            # In-place upgrades can add bundled packs at an unchanged path.
            # Refresh once, preserving user defaults and extra scan folders.
            _state=state
            return rescan()
        _state=state
    except (OSError,ValueError,TypeError,AttributeError,KeyError):
        profile=_user_profile()
        _state=dict(roots=[str(default_root()),*[p for p in profile.get('roots',[]) if isinstance(p,str)]],defaults=profile.get('defaults'))
        try:return rescan()
        except OSError:
            state=rescan(persist=False);state['errors'].append(tr('无法保存音源索引，请检查用户目录权限。'))
    return _state

def _installed(data):
    try:
        root=Path(data['path']).resolve();file=_inside(root,'synth.json');_inside(root,data['library']);_inside(root,data['license_file'])
        if file.stat().st_mtime_ns!=data['manifest_stamp']:return False
        engine=data.get('engine')
        if engine in ('sfz','sf2'):
            for mapping in {preset[engine] for preset in data['presets']}:_inside(root,mapping)
        return True
    except (OSError,ValueError,KeyError,TypeError):return False


def installed_packs():return [data for data in registry()['packs'].values() if _installed(data)]

def pack(device):
    found=registry()['packs'].get(device[6:]) if is_synth_source(device) else None
    if found is None or not _installed(found):raise ValueError(tr('合成音源“{0}”未安装或已更改，请复制音源文件夹后在设置中重新扫描。',device))
    return found

def pack_label(data):
    from lingfeng.platform.i18n import LANGUAGE
    return data['name_en'] if LANGUAGE=='en' else data['name']

def available_programs(device=DEFAULT_DEVICE):
    try:return [p['program'] for p in pack(device)['presets']]
    except ValueError:return []

def preset_calibration_db(program,device=DEFAULT_DEVICE):
    """Return the imported preset's measured compensation, or None if uncalibrated."""
    if not is_synth_source(device):return None
    return pack(device).get('preset_gain_db',{}).get(str(program))

def instrument(program,device=DEFAULT_DEVICE,*,apply_calibration=False):
    """Return preset metadata with optional playback compensation folded into gain."""
    data=pack(device)
    item=next((p for p in data['presets'] if p['program']==program),None)
    if item is None:raise ValueError(tr('音源“{0}”不包含音色 {1}，请在音源设置中选择可用音色。',device,program+1))
    gain_db=data.get('preset_gain_db',{}).get(str(program)) if apply_calibration else None
    if gain_db:return dict(item,gain=item['gain']*10**(gain_db/20))
    return item

def instrument_label(program,device=DEFAULT_DEVICE):
    from lingfeng.platform.i18n import LANGUAGE
    item=instrument(program,device);return f'{program+1:02} · '+item['name_en' if LANGUAGE=='en' else 'name']

def default_audio():
    from lingfeng.audio.events import TRACK_ROLES, complete_track_values, source_gain_db
    saved=complete_track_values(registry().get('defaults'))
    settings={}
    if isinstance(saved,dict) and set(saved)==set(TRACK_ROLES):
        for role,spec in saved.items():
            if not isinstance(spec,dict) or not isinstance(spec.get('device'),str) or type(spec.get('program')) is not int or not 0<=spec['program']<=127:
                continue
            if is_synth_source(spec['device']) and spec['program'] not in available_programs(spec['device']):
                continue
            settings[role]=dict(spec)
            try:source_gain_db(settings[role])
            except ValueError:settings[role].pop('gain_db',None)
        if len(settings)==len(TRACK_ROLES):return settings
    for device in (GENERALUSER_GS_DEVICE,MUSESCORE_LITE_DEVICE,'synth:ydp-grand'):
        if 0 in available_programs(device):
            melody_program=0
            break
    else:
        piano=available_programs('synth:piano-small')
        if 0 in piano:
            device='synth:piano-small';melody_program=1 if 1 in piano else 0
        else:
            device=DEFAULT_DEVICE if available_programs() else 'default';melody_program=1
    return {role:settings.get(role,dict(device=device,program=0 if role=='chords' else melody_program)) for role in TRACK_ROLES}

def save_defaults(settings):
    from lingfeng.audio.events import complete_track_values
    settings=complete_track_values(settings)
    state=dict(registry(),defaults=settings);_write(state);registry()['defaults']={k:dict(v) for k,v in settings.items()}

def export_instruments(project,which,start,end):
    from lingfeng.audio.midi import export_tracks
    used=[]
    for _,role,notes in export_tracks(project,which):
        if not any(n.start<end and n.end>start for n in notes):continue
        spec=project.audio_for(role);device=spec['device']
        if not is_synth_source(device):raise ValueError(tr('所选轨道使用 Windows MIDI，离线导出需先选择合成音源，或改用 Windows 实时录制。'))
        item=dict(instrument(spec['program'],device),pack=pack(device))
        if item not in used:used.append(item)
    return used

def commercial_notice(project,which='both',start=0,end=None,mode='offline'):
    from lingfeng.platform.i18n import LANGUAGE
    if mode=='windows':return tr('商用版权提示：Windows MIDI 音色由系统或设备提供，商用前请核对对应音源授权。作品、歌词及其他录入声音的权利也需自行确认。')
    rows=export_instruments(project,which,start,project.end if end is None else end)
    lines=[tr('商用版权提示：本次使用以下合成音源；软件开源许可与作品版权分别适用。')]
    lines.extend(pack_label(i['pack'])+' · '+i['name_en' if LANGUAGE=='en' else 'name']+' — '+i['pack']['license'] for i in rows)
    lines.append(tr('导出附带音源许可说明。作品、歌词及其他素材的权利需自行确认。'))
    return '\n'.join(lines)

def credits_text(project,which,start,end,mode):
    lines=['Lingfeng audio export — synthesis source credits / 合成音源许可说明','',commercial_notice(project,which,start,end,mode),'']
    if mode!='windows':
        notice_files={GENERALUSER_GS_DEVICE:'GeneralUser-GS-LICENSE.txt',
                      MUSESCORE_LITE_DEVICE:'MuseScore_General_Lite.copyright'}
        notices={}
        for item in export_instruments(project,which,start,end):
            p=item['pack'];lines.extend([item['name_en'],p['author'],'License: '+p['license'],'Source: '+p['source'],'Pack: '+p['id']+' '+p['version'],''])
            name=notice_files.get('synth:'+p['id'])
            if name: notices[p['id']]=(Path(p['path']).resolve(),name)
        for root,name in notices.values():
            notice=_inside(root,name)
            lines.extend([notice.read_text('utf-8').strip(),''])
    return '\n'.join(lines)+'\n'
