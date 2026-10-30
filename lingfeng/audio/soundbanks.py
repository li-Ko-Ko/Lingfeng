"""Folder-installed synthesis packs and a persistent, per-installation index.

Scanning reads JSON only. Projects store stable IDs, never library paths.
"""
import hashlib,json,math,os,re,sys
from pathlib import Path
from lingfeng.platform.i18n import tr

DEFAULT_DEVICE='synth:stk-essentials'
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
    if not isinstance(relative,str) or not relative:raise ValueError('Missing pack file')
    path=(root/relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():raise ValueError('Missing or unsafe pack file: '+relative)
    return path

def _validate(data,root,verify_files=True):
    if data.get('schema')!=1 or data.get('abi')!=1 or data.get('platform')!='windows-x64':raise ValueError('Unsupported synth pack version/platform')
    if not re.fullmatch('[a-z0-9][a-z0-9._-]{0,63}',data.get('id','')):raise ValueError('Invalid pack ID')
    for name in ('name','name_en','version','license','source','author','library','license_file','sha256'):
        if not isinstance(data.get(name),str) or not data[name]:raise ValueError('Missing '+name)
    if verify_files:
        library=_inside(root,data['library']);_inside(root,data['license_file'])
        if library.suffix.lower()!='.dll':raise ValueError('Expected a Windows DLL')
        binary=library.read_bytes()
        if hashlib.sha256(binary).hexdigest()!=data.get('sha256'):raise ValueError('Library checksum mismatch')
        offset=int.from_bytes(binary[60:64],'little')
        if binary[:2]!=b'MZ' or binary[offset:offset+6]!=b'PE\x00\x00\x64\x86':raise ValueError('Expected a Windows x64 native library')
    rows=data.get('presets',[]);seen=set()
    if not isinstance(rows,list) or not 1<=len(rows)<=128:raise ValueError('Invalid preset list')
    for item in rows:
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
    return data

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
                data=_validate(json.loads(file.read_text('utf-8')),file.parent.resolve())
                if data['id'] in packs:raise ValueError('Duplicate pack ID: '+data['id'])
                packs[data['id']]=dict(data,path=str(file.parent.resolve()),manifest_stamp=file.stat().st_mtime_ns)
            except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:errors.append(str(file)+': '+str(exc))
    state=dict(schema=1,roots=roots,packs=packs,errors=errors,defaults=prior.get('defaults'))
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
        for ident,item in state['packs'].items():
            _validate(item,None,verify_files=False)
            if item['id']!=ident or not isinstance(item.get('path'),str) or type(item.get('manifest_stamp')) is not int:raise ValueError('Invalid cached pack')
        profile=_user_profile()
        if profile:
            state['defaults']=profile.get('defaults')
            roots=list(dict.fromkeys([str(default_root().resolve()),*[str(Path(p).expanduser().resolve()) for p in profile.get('roots',[]) if isinstance(p,str)]]))
            if roots!=state['roots']:
                _state=state
                return rescan(roots)
        _state=state
    except (OSError,ValueError,TypeError,AttributeError,KeyError):
        profile=_user_profile()
        _state=dict(roots=[str(default_root()),*[p for p in profile.get('roots',[]) if isinstance(p,str)]],defaults=profile.get('defaults'))
        try:return rescan()
        except OSError:
            state=rescan(persist=False);state['errors'].append(tr('无法保存音源索引，请检查用户目录权限。'))
    return _state

def installed_packs():
    result=[]
    for data in registry()['packs'].values():
        try:
            root=Path(data['path']).resolve();file=_inside(root,'synth.json');_inside(root,data['library']);_inside(root,data['license_file'])
            if file.stat().st_mtime_ns!=data['manifest_stamp']:continue
            result.append(data)
        except (OSError,ValueError,KeyError,TypeError):continue
    return result

def pack(device):
    found=next((p for p in installed_packs() if 'synth:'+p['id']==device),None)
    if found is None:raise ValueError(tr('合成音源“{0}”未安装或已更改，请复制音源文件夹后在设置中重新扫描。',device))
    return found

def pack_label(data):
    from lingfeng.platform.i18n import LANGUAGE
    return data['name_en'] if LANGUAGE=='en' else data['name']

def available_programs(device=DEFAULT_DEVICE):
    try:return [p['program'] for p in pack(device)['presets']]
    except ValueError:return []

def instrument(program,device=DEFAULT_DEVICE):
    item=next((p for p in pack(device)['presets'] if p['program']==program),None)
    if item is None:raise ValueError(tr('音源“{0}”不包含音色 {1}，请在音源设置中选择可用音色。',device,program+1))
    return item

def instrument_label(program,device=DEFAULT_DEVICE):
    from lingfeng.platform.i18n import LANGUAGE
    item=instrument(program,device);return f'{program+1:02} · '+item['name_en' if LANGUAGE=='en' else 'name']

def default_audio():
    saved=registry().get('defaults')
    if isinstance(saved,dict) and set(saved)=={'melody','chords'}:
        if all(isinstance(s,dict) and isinstance(s.get('device'),str) and type(s.get('program')) is int and 0<=s['program']<=127 and (not is_synth_source(s['device']) or s['program'] in available_programs(s['device'])) for s in saved.values()):return {k:dict(v) for k,v in saved.items()}
    device=DEFAULT_DEVICE if available_programs() else 'default'
    return {'melody':dict(device=device,program=1),'chords':dict(device=device,program=0)}

def save_defaults(settings):
    state=dict(registry(),defaults=settings);_write(state);registry()['defaults']={k:dict(v) for k,v in settings.items()}

def export_instruments(project,which,start,end):
    used=[]
    for role,notes in [('melody',project.notes),('chords',project.harmony_notes())]:
        if which not in ('both',role) or not any(n.start<end and n.end>start for n in notes):continue
        spec=project.audio[role];device=spec['device']
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
        for item in export_instruments(project,which,start,end):
            p=item['pack'];lines.extend([item['name_en'],p['author'],'License: '+p['license'],'Source: '+p['source'],'Pack: '+p['id']+' '+p['version'],''])
    return '\n'.join(lines)+'\n'
