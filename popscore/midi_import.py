"""Read Standard MIDI Files and replace a bounded part of one project track."""
from dataclasses import dataclass,field
from collections import defaultdict,deque
from pathlib import Path
import struct,copy
from .model import Note,Chord,Context,Measure,PPQ,uid
from .operations import overwrite_note


@dataclass
class MidiTrack:
    name:str
    notes:list=field(default_factory=list)
    end:int=0


@dataclass
class MidiData:
    tracks:list
    tempos:list
    meters:list
    def notes_for(self,indices):return [copy.deepcopy(n) for i in indices for n in self.tracks[i].notes]
    def end_for(self,indices):return max((self.tracks[i].end for i in indices),default=0)


def read_midi(path):
    data=Path(path).read_bytes()
    if len(data)>32*1024*1024:raise ValueError('MIDI 文件过大。')
    if len(data)<14 or data[:4]!=b'MThd':raise ValueError('不是有效的标准 MIDI 文件。')
    header=struct.unpack('>I',data[4:8])[0]
    if header<6 or header+8>len(data):raise ValueError('MIDI 文件头不完整。')
    kind,count,division=struct.unpack('>HHH',data[8:14])
    if kind not in (0,1) or division==0 or division&0x8000:raise ValueError('仅支持基于 PPQ 的 MIDI Type 0／1 文件。')
    pos=8+header;tracks=[];tempos={};meters={};total=0
    def tick(value):return (value*PPQ+division//2)//division
    for index in range(count):
        if pos+8>len(data) or data[pos:pos+4]!=b'MTrk':raise ValueError('MIDI 音轨数据不完整。')
        size=int.from_bytes(data[pos+4:pos+8],'big');pos+=8;end=pos+size
        if end>len(data):raise ValueError('MIDI 音轨数据不完整。')
        track=MidiTrack(f'Track {index+1}');active=defaultdict(deque);clock=0;running=None;lyrics={}
        def byte():
            nonlocal pos
            if pos>=end:raise ValueError('MIDI 事件不完整。')
            value=data[pos];pos+=1;return value
        def vlq():
            value=0
            for _ in range(4):
                part=byte();value=(value<<7)|(part&127)
                if not part&128:return value
            raise ValueError('MIDI 可变长度数值无效。')
        def finish(key,stop):
            if not active[key]:return
            start,velocity=active[key].popleft();a,b=tick(start),tick(stop)
            if b>a:track.notes.append(Note(a,b-a,key[1],velocity))
        while pos<end:
            clock+=vlq();status=byte()
            if status<128:
                if running is None:raise ValueError('MIDI running status 无效。')
                pos-=1;status=running
            if status==0xff:
                meta=byte();length=vlq()
                if pos+length>end:raise ValueError('MIDI 元事件不完整。')
                payload=data[pos:pos+length];pos+=length
                if meta==3:track.name=payload.decode('utf-8',errors='replace')
                elif meta==5:lyrics[tick(clock)]=payload.decode('utf-8',errors='replace')
                elif meta==0x51 and length==3:
                    value=int.from_bytes(payload,'big')
                    if value:tempos[tick(clock)]=60_000_000/value
                elif meta==0x58 and length>=2:
                    if payload[1]>7:raise ValueError('MIDI 拍号无效。')
                    meters[tick(clock)]=(payload[0],2**payload[1])
                elif meta==0x2f:break
            elif status in (0xf0,0xf7):
                length=vlq();pos+=length;running=None
                if pos>end:raise ValueError('MIDI SysEx 事件不完整。')
            elif 0x80<=status<=0xef:
                running=status;kind=status&0xf0;channel=status&15;a=byte();b=byte() if kind not in (0xc0,0xd0) else 0
                if a>127 or b>127:raise ValueError('MIDI 数据字节无效。')
                if kind==0x90 and b:active[channel,a].append((clock,b))
                elif kind==0x80 or kind==0x90:finish((channel,a),clock)
            else:raise ValueError('MIDI 事件类型无效。')
        for key in active:
            while active[key]:finish(key,clock)
        track.end=max(tick(clock),max((n.end for n in track.notes),default=0))
        for n in track.notes:
            if n.start in lyrics:n.lyric=lyrics.pop(n.start)
        total+=len(track.notes)
        if total>100000:raise ValueError('MIDI 音符数量过多。')
        tracks.append(track);pos=end
    if not any(t.notes for t in tracks):raise ValueError('MIDI 文件没有可导入的音符。')
    return MidiData(tracks,sorted(tempos.items()),sorted((t,*v) for t,v in meters.items()))


def _extend(project,end):
    previous=project.end
    while project.end<end:
        if len(project.measures)>=1000:raise ValueError('导入后超过 1000 小节。')
        m=project.measures[-1];project.measures.append(Measure(m.numerator,m.denominator))
    if project.end>previous:
        c=copy.deepcopy(project.contexts[-1]);c.start=previous;c.end=project.end;project.contexts.append(c)


def _meters(project,data,start,end):
    if start not in project.starts:raise ValueError('覆盖拍号时，请将导入起点放在小节开头。')
    imported={start:(4,4)}
    imported.update({start+t:(n,d) for t,n,d in data.meters if t<end-start})
    changes=sorted(imported);meter_end=start;index=0
    for _ in range(1000):
        if meter_end>=end:break
        while index+1<len(changes) and changes[index+1]<=meter_end:index+=1
        n,d=imported[changes[index]]
        if n not in range(1,17) or d not in (2,4,8,16):raise ValueError('MIDI 拍号超出支持范围：分子 1–16，分母 2／4／8／16。')
        stop=meter_end+PPQ*4*n//d
        if index+1<len(changes) and changes[index+1]<stop:raise ValueError('拍号变化不在新小节边界，请取消覆盖拍号后导入。')
        meter_end=stop
    if meter_end<end:raise ValueError('导入后超过 1000 小节。')
    old=project.starts;events={0:(project.measures[0].numerator,project.measures[0].denominator)}
    for i,m in enumerate(project.measures):
        if i==0 or (m.numerator,m.denominator)!=(project.measures[i-1].numerator,project.measures[i-1].denominator):
            if not start<=old[i]<meter_end:events[old[i]]=(m.numerator,m.denominator)
    events.update(imported)
    restored=project.measures[project.measure_at(meter_end)]
    events[meter_end]=(restored.numerator,restored.denominator)
    changes=sorted(events);goal=max(project.end,end);measures=[];t=0;i=0
    while t<goal:
        while i+1<len(changes) and changes[i+1]<=t:i+=1
        n,d=events[changes[i]]
        if n not in range(1,17) or d not in (2,4,8,16):raise ValueError('MIDI 拍号超出支持范围：分子 1–16，分母 2／4／8／16。')
        stop=t+PPQ*4*n//d
        if i+1<len(changes) and changes[i+1]<stop:raise ValueError('拍号变化不在新小节边界，请取消覆盖拍号后导入。')
        section=project.measures[old.index(t)].section if t in old[:-1] else ''
        measures.append(Measure(n,d,section));t=stop
        if len(measures)>1000:raise ValueError('导入后超过 1000 小节。')
    project.measures=measures
    last=project.contexts[-1]
    if project.end>last.end:project.contexts.append(Context(last.end,project.end,last.tonic,last.mode))
    # Bar-index layout directives no longer refer to the same measures.
    for key in ('compressions','forced_rows','forced_row_fonts'):project.notation[key]=[]
    project.marks=[0]


def apply_midi(project,data,indices,target,start,overwrite_meter=False,overwrite_tempo=False,quantization=None):
    """Caller uses a transaction; note positions in the other track never shift."""
    indices=sorted(set(indices));notes=data.notes_for(indices);length=data.end_for(indices)
    if not notes or not length:raise ValueError('请选择包含音符的 MIDI 音轨。')
    if any(not 21<=n.pitch<=108 for n in notes):raise ValueError('选中音轨含 88 键范围之外的音符，请先在 DAW 中调整音域或选择其它音轨。')
    from .lyrics import detach
    detach(project)
    for n in notes:n.lyric=''
    if quantization:
        from .quantization import quantize_notes
        notes=quantize_notes(notes,**quantization)
        length=max(length,max(n.end for n in notes))
    end=start+length
    if overwrite_meter:_meters(project,data,start,end)
    else:_extend(project,end)
    if overwrite_tempo:
        bpm=round(data.tempos[0][1]) if data.tempos else 120
        if not 20<=bpm<=300:raise ValueError('MIDI 速度超出 20–300 BPM 范围。')
        project.bpm=bpm
    merged=[]
    for n in sorted(notes,key=lambda n:(n.start,n.pitch)):
        # Preserve rearticulation, including slightly overlapping legato notes.
        # A union erased these onsets and could misidentify the whole region as block.
        n.start+=start;n.id=uid();merged=overwrite_note(n,merged)
    if target=='melody':
        remaining=[]
        for n in project.notes:
            if n.end<=start or n.start>=end:remaining.append(n);continue
            for a,b in ((n.start,min(n.end,start)),(max(n.start,end),n.end)):
                if b>a:piece=copy.deepcopy(n);piece.start=a;piece.duration=b-a;piece.id=uid();remaining.append(piece)
        project.notes=sorted(remaining+merged,key=lambda n:(n.start,n.pitch))
    else:
        remaining=[]
        for c in project.chords:
            if c.end<=start or c.start>=end:remaining.append(c);continue
            if c.start<start:remaining.append(c.clip(c.start,start))
            if c.end>end:remaining.append(c.clip(end,c.end))
        from .recognition import recognize,update_symbol
        cuts=[start]+[t for t in project.starts if start<t<end and not any(n.start<t<n.end for n in merged)]+[end]
        for a,b in zip(cuts,cuts[1:]):
            local=[Note(n.start-a,n.duration,n.pitch,n.velocity) for n in merged if a<=n.start<b]
            if not local:continue
            chord=Chord(a,b-a,notes=local);update_symbol(chord,recognize([n.pitch for n in local]));remaining.append(chord)
        project.chords=sorted(remaining,key=lambda c:c.start)
    if overwrite_meter or target=='chords':
        from .meter import splice_chords
        actual=project.harmony_notes()
        splice_chords(project,0,0)
        if target=='chords':project.set_harmony_notes(actual)
    if target=='chords':project.fill_chord_gaps()
    project.validate()
    return start,end
