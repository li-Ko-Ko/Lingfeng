"""Small, deterministic Standard MIDI File Type 1 exporter."""
from pathlib import Path
import struct
import json
import zipfile
from lingfeng.music.model import MELODY_NAMES, PPQ, pitch_name
from lingfeng.audio.events import INSTRUMENT_CHANNEL

EXPORT_ROLES = ('melody','instrument','chords')


def selected_roles(which):
    if which == 'both':
        return EXPORT_ROLES
    roles = (which,) if isinstance(which,str) else which
    if not roles or any(role not in EXPORT_ROLES for role in roles):
        raise ValueError('请选择至少一个导出轨道。')
    return tuple(role for role in EXPORT_ROLES if role in roles)


def vlq(n):
    if not 0 <= n <= 0x0FFFFFFF:
        raise ValueError('MIDI delta tick is out of range')
    out = [n & 127]
    n >>= 7
    while n:
        out.insert(0, (n & 127) | 128)
        n >>= 7
    return bytes(out)


def meta(kind, text):
    data = text.encode('utf-8') if isinstance(text, str) else text
    return bytes([0xFF, kind]) + vlq(len(data)) + data


def project_tracks(project, melody=True, harmony=True, *, instrument=None):
    if melody:yield 0,'melody',project.notes
    if harmony:yield 1,'chords',project.harmony_notes()
    if instrument is None:instrument=melody and bool(project.instrument_notes)
    if instrument:yield INSTRUMENT_CHANNEL,'instrument',project.instrument_notes


def export_tracks(project, which):
    """Use the same per-role selection for SMF, audio and synth credits."""
    roles=selected_roles(which)
    has_instrument=project.instrument_notes or project.notation.get('instrument_lyric_events')
    return project_tracks(project,'melody' in roles,'chords' in roles,
                          instrument='instrument' in roles and (which!='both' or bool(has_instrument)))


def event_list(project, melody=True, harmony=True):
    return track_events(project_tracks(project,melody,harmony))


def track_events(tracks):
    events = []
    for channel,_,notes in tracks:
        for n in notes:
            events += [(n.start, 1, channel, n.pitch, n.velocity), (n.end, 0, channel, n.pitch, 0)]
    return sorted(events)


def track_bytes(events, end):
    payload, previous = bytearray(), 0
    for tick, order, message in sorted(events, key=lambda e: (e[0], e[1])):
        payload.extend(vlq(tick - previous)); payload.extend(message); previous = tick
    payload.extend(vlq(max(0, end - previous))); payload.extend(b'\xff\x2f\x00')
    return b'MTrk' + struct.pack('>I', len(payload)) + payload


def _track_names(project):
    names={'melody':'Melody','instrument':'Ins Melody','chords':'Chords'}
    for index,role in enumerate(('melody','instrument')):
        if project.melody_names[index]!=MELODY_NAMES[index]:
            names[role]=project.melody_names[index]
    return names


def export_midi(project, path, which='both', start=0, end=None):
    project.validate()
    end=project.end if end is None else end
    if not 0<=start<end<=project.end:raise ValueError('导出范围无效。')
    from lingfeng.music.note_operations import window_notes
    conductor = [(0, -3, meta(3, project.title)),
                 (0, -2, meta(0x51, round(60_000_000 / project.bpm).to_bytes(3, 'big')))]
    last_meter = None
    for tick, measure in zip(project.starts, project.measures):
        if tick>=end:break
        meter = (measure.numerator, measure.denominator)
        if tick<=start:
            conductor=[e for e in conductor if e[1]!=-1]
        if meter != last_meter or tick<=start:
            conductor.append((max(0,tick-start), -1, meta(0x58, bytes([meter[0], {2:1,4:2,8:3,16:4}[meter[1]], 24, 8]))))
            last_meter = meter
        if measure.section and tick>=start:
            conductor.append((tick-start, 0, meta(6, measure.section)))
    for c in project.contexts:
        if c.start<end and c.end>start:conductor.append((max(0,c.start-start), 0, meta(1, f'1={pitch_name(c.tonic)};mode={c.mode}')))
    tracks = [track_bytes(conductor, end-start)]
    names=_track_names(project)
    for channel,role,notes in export_tracks(project,which):
        name=names[role];program=project.audio_for(role)['program']
        messages = [(0, -3, meta(3, name)), (0, -2, bytes([0xC0 | channel, program]))]
        messages.append((0,-2,bytes([0xB0|channel,7,project.volume_for(role)])))
        for n in window_notes(notes,start,end):
            messages.append((n.start,1,bytes([0x90|channel,n.pitch,n.velocity])))
            messages.append((n.end,0,bytes([0x80|channel,n.pitch,0])))
        if role in ('melody','instrument'):
            from lingfeng.engraving.lyrics import events as lyric_events, lyric_track
            for lyric in lyric_events(lyric_track(project,int(channel==INSTRUMENT_CHANNEL))):
                if lyric.get('kind') not in ('rap','rap_note') and lyric['text'] and start<=lyric['tick']<end:
                    messages.append((lyric['tick']-start, -1, meta(5, lyric['text'])))
        else:
            for chord in project.chords:
                from lingfeng.music.chord_operations import roman_label
                if chord.start<end and chord.end>start:messages.append((max(0,chord.start-start),-1,meta(6,chord.name+' | '+roman_label(project,chord))))
        tracks.append(track_bytes(messages, end-start))
    data=b'MThd' + struct.pack('>IHHH', 6, 1, len(tracks), PPQ) + b''.join(tracks)
    if path is not None:Path(path).write_bytes(data)
    return data


def export_daw_bundle(project,path,which='both'):
    """All files retain tick zero, including leading rests and the common end."""
    project.validate()
    parts=[(channel,role) for channel,role,_ in export_tracks(project,which)]
    stems=[('01_Melody.mid','melody'),('02_Chords.mid','chords')]
    if any(role=='instrument' for _,role in parts):stems.append(('03_Instrument.mid','instrument'))
    stems=[(name,role) for name,role in stems if any(role==selected for _,selected in parts)]
    description=', '.join(filename for filename,_ in stems)
    audio={role:project.audio_for(role) for _,role in parts}
    volumes={role:project.volume_for(role) for _,role in parts}
    names=_track_names(project)
    programs='\n'.join(f'{names[role]}: MIDI channel {channel+1}, GM program {audio[role]["program"]}'
                       for channel,role in parts)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        for filename,selection in [('00_Full.mid',which),*stems]:
            archive.writestr(filename,export_midi(project,None,selection))
        archive.writestr('timeline.json',json.dumps({'title':project.title,'ppq':PPQ,'bpm':project.bpm,
            'end_tick':project.end,'volumes_cc7':volumes,'audio':audio,
            'tracks':[{'role':role,'name':names[role],'channel':channel+1} for channel,role in parts],
            'meters':[{'tick':s,'numerator':m.numerator,'denominator':m.denominator} for s,m in zip(project.starts,project.measures)],
            'contexts':[{'tick':c.start,'tonic':c.tonic,'mode':c.mode} for c in project.contexts]},ensure_ascii=False,indent=2))
        archive.writestr('Readme.txt',f'''伶风 Lingfeng → Cakewalk Next / 其他 DAW

工程：{project.title}
速度：{project.bpm} BPM；分辨率：{PPQ} PPQ；起点：第 1 小节，第 1 拍。

方式 A：导入 00_Full.mid，保留各独立 MIDI 轨。
方式 B：把分轨文件（{description}）放到第 1 小节第 1 拍。
不要同时导入 A 和 B，否则音符会重复。
分轨均保留前导休止和全曲结束时间，不要裁掉开头空白。
Cakewalk Next：Insert → Insert Audio/MIDI File；也可拖入 Clips 面板。
导入现有工程后，请核对工程 BPM 和拍号；不同 DAW 的导入方式可能忽略文件速度图。

以下 GM program 编号从零起算。
{programs}
初始轨道音量使用 CC7；逐音力度独立保留。
若目标乐器不响应 GM 音色或 CC7，请在 DAW 里手动选择音色和设置轨道音量。
C4 = MIDI 60。某些 DAW 的八度名不同，请以 MIDI 音高编号为准。
和弦自定义节奏型、转位、起点和时长按实际编辑的音符导出。

MIDI 不携带立体简谱排版、四色与排版设置。请保留原始 .lfs 工程。
这是标准 MIDI 迁移包，不是 Cakewalk Next 的原生工程文件。

Lingfeng → Cakewalk Next / other DAWs

Project: {project.title}
Tempo: {project.bpm} BPM; resolution: {PPQ} PPQ; start: bar 1, beat 1.

Option A: Import 00_Full.mid, retaining separate MIDI tracks.
Option B: Place the track files ({description}) at bar 1, beat 1.
Choose one option; importing both duplicates the notes.
Separate tracks preserve leading rests and the common song end. Keep the leading silence.
In Cakewalk Next use Insert → Insert Audio/MIDI File, or drop files into the Clips pane.
Check the destination tempo and meter after importing into an existing project;
some DAWs may ignore a file's tempo map during this operation.

GM program numbers below are zero-based.
{programs}
Track volumes use initial CC7 messages; individual note velocities are retained.
If the destination instrument ignores GM programs or CC7, set its sound and volume in the DAW.
C4 = MIDI 60. DAW octave names may differ; use the MIDI pitch number as the reference.
Chord patterns, inversions and note timing are exported from the performed notes.

MIDI does not carry spatial jianpu engraving, four-color display or layout settings.
Keep the original .lfs project. This is a standard MIDI transfer bundle,
not a native Cakewalk Next project file.
'''.encode('utf-8-sig'))
