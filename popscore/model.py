from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
import bisect
import copy
import json
import os
import uuid
import zipfile
import hashlib

PPQ = 960
MAJOR = (0, 2, 4, 5, 7, 9, 11)
MODES = {
    'Ionian': (0, 2, 4, 5, 7, 9, 11),
    'Dorian': (0, 2, 3, 5, 7, 9, 10),
    'Phrygian': (0, 1, 3, 5, 7, 8, 10),
    'Lydian': (0, 2, 4, 6, 7, 9, 11),
    'Mixolydian': (0, 2, 4, 5, 7, 9, 10),
    'Aeolian': (0, 2, 3, 5, 7, 8, 10),
}
QUALITIES = {
    '': (0, 4, 7), 'm': (0, 3, 7), '7': (0, 4, 7, 10), '7b5': (0, 4, 6, 10),
    'maj7': (0, 4, 7, 11), 'm7': (0, 3, 7, 10), 'mM7': (0, 3, 7, 11),
    'dim': (0, 3, 6), 'm7b5': (0, 3, 6, 10), 'aug': (0, 4, 8),
    'sus2': (0, 2, 7), 'sus4': (0, 5, 7), 'add2': (0, 2, 4, 7),
    '6': (0,4,7,9), 'm6': (0,3,7,9), '9': (0,4,7,10,14),
    'm9': (0,3,7,10,14), 'maj9': (0,4,7,11,14),
    'dim7': (0,3,6,9), '7sus4': (0,5,7,10), '5': (0,7),
}
PATTERNS = {'block':'持续柱式', 'quarters':'四分柱式', 'eighths':'八分柱式',
            'up':'上行琶音', 'down':'下行琶音', 'alberti':'阿尔贝蒂低音',
            'bass_chord':'低音 + 和弦', 'offbeat':'反拍和弦',
            'alternating_quarters':'根五交替 · 四分柱式',
            'alternating_eighths':'根五交替 · 八分柱式',
            'alternating_offbeat':'根五交替 · 反拍柱式'}
SHARP = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')
FLAT = ('C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B')
SECTIONS = ('Intro','Verse','Prechorus','Chorus','Link','Solo','Refrain','Tag','Postchorus','Superchorus','Coda','Outro')

def section_name(value):
    return next((name for name in SECTIONS if name.casefold()==value.casefold()),value)
COLORS = {'both':'#247F70','scale':'#456DB1','chord':'#B27632','other':'#A84E62'}
# Background emphasis decreases; note contrast increases in the same category order.
BACKGROUND_COLORS = {'both':'#BBDDD3','scale':'#D3DFF3','chord':'#EEE3D2','other':'#F7F8FA'}
NOTE_COLORS = {'both':'#438F7E','scale':'#426BAA','chord':'#955E25','other':'#7D2E48'}


def uid():
    return uuid.uuid4().hex[:12]


def pitch_name(p):
    return f'{SHARP[p % 12]}{p // 12 - 1}'


def degree_pitch(tonic, degree):
    octave, index = divmod(degree, 7)
    return tonic + 12 * octave + MAJOR[index]


def spelling(pitch, tonic, flat=False, mode=None):
    """Major-reference numbers; a mode's seven degrees keep their own identity."""
    delta = pitch - tonic
    octave, pc = divmod(delta, 12)
    if mode in MODES and pc in MODES[mode]:
        index=MODES[mode].index(pc)
        return index+1,pc-MAJOR[index],octave
    if pc in MAJOR:
        return MAJOR.index(pc) + 1, 0, octave
    if flat:
        index = next(i for i, x in enumerate(MAJOR) if x > pc)
        return index + 1, -1, octave
    index = max(i for i, x in enumerate(MAJOR) if x < pc)
    return index + 1, 1, octave


def degree_text(pitch, tonic, flat=False, unicode=True, mode=None):
    d, a, _ = spelling(pitch, tonic, flat, mode)
    return (('♯' if unicode else '#') if a > 0 else ('♭' if unicode else 'b') if a < 0 else '') + str(d)


@dataclass
class Note:
    start: int
    duration: int
    pitch: int
    velocity: int = 92
    lyric: str = ''
    flat: bool = False
    id: str = field(default_factory=uid)
    event_id: str = ''  # Shared MIDI identity for views clipped by chord regions.

    @property
    def end(self):
        return self.start + self.duration


@dataclass
class Chord:
    start: int
    duration: int
    root: int = 48
    quality: str = ''
    bass: int | None = None
    id: str = field(default_factory=uid)
    flat: bool = False
    pattern: str = 'block'
    gate: float = 0.9
    velocity: int = 72
    octave: int = 0
    notes: list[Note] | None = None  # Local ticks, None = generate from pattern.
    recognized: bool = True
    custom_rhythm: bool = False  # Explicitly preserve MIDI instead of inferring a pattern.
    bar_aligned: bool = False  # Meter-edited/generated events recognize against real bars.

    @property
    def end(self):
        return self.start + self.duration

    @property
    def pitches(self):
        root = 48 + self.root % 12
        pitches = [root + x for x in QUALITIES[self.quality]]
        bass = 36 + (self.root if self.bass is None else self.bass) % 12
        return sorted(set(p + self.octave*12 for p in [bass, *pitches]))

    @property
    def pcs(self):
        if self.notes is not None:
            return {n.pitch % 12 for n in self.notes}
        return {p % 12 for p in self.pitches}

    @property
    def name(self):
        if self.notes == []:return 'N.C.'
        if not self.recognized:return '未识别'
        return SHARP[self.root % 12] + self.quality + (f'/{SHARP[self.bass % 12]}' if self.bass is not None else '')

    def roman(self, tonic, flat=False, mode=None):
        if self.notes == []:return 'N.C.'
        if not self.recognized:return '?'
        d, a, _ = spelling(self.root, tonic, flat, mode)
        r = ('I', 'II', 'III', 'IV', 'V', 'VI', 'VII')[d - 1]
        suffix = self.quality
        if suffix in ('m', 'm7', 'mM7', 'm7b5', 'dim', 'm6', 'm9', 'dim7'):
            r = r.lower()
        suffix = {'m': '', 'm7': '7', 'mM7':'M7', 'm6':'6', 'm9':'9', 'dim': '°', 'dim7':'°7', 'm7b5': 'ø7', 'aug': '+'}.get(suffix, suffix)
        label = ('♯' if a > 0 else '♭' if a < 0 else '') + r + suffix
        if self.bass is not None:
            label += '/' + degree_text(self.bass, tonic, flat, mode=mode)
        return label

    def render_notes(self, *, pitches=None):
        """Absolute events; null notes retain the legacy chord-relative generator."""
        if self.notes is not None:
            return sorted([Note(n.start+self.start,n.duration,n.pitch,n.velocity,id=n.id,event_id=n.event_id) for n in self.notes],key=lambda n:(n.start,n.pitch))
        out=[]; pitches=self.pitches if pitches is None else pitches
        from .rhythm import ALTERNATING,Rhythm
        if self.pattern in ALTERNATING:
            return sorted([Note(self.start+t,d,p,self.velocity,id=f'{self.id}:{t}:{p}')
                           for t,d,p in Rhythm(self.pattern,tuple(pitches),self.gate).events(self.duration)],key=lambda n:(n.start,n.pitch))
        step=PPQ if self.pattern in ('quarters','bass_chord') else PPQ//2
        if self.pattern=='block':step=self.duration
        offset=PPQ//2 if self.pattern=='offbeat' else 0
        if self.pattern=='offbeat':step=PPQ
        for index,t in enumerate(range(offset,self.duration,step)):
            chosen=pitches
            if self.pattern in ('up','down'):
                order=pitches if self.pattern=='up' else list(reversed(pitches))
                chosen=[order[index%len(order)]]
            elif self.pattern=='alberti':
                order=[pitches[0],pitches[-1],pitches[1],pitches[-1]];chosen=[order[index%4]]
            elif self.pattern=='bass_chord':chosen=[pitches[0]] if index%2==0 else pitches[1:]
            duration=min(self.duration-t, step if self.pattern=='block' else max(1,round(step*self.gate)))
            for pitch in chosen:
                out.append(Note(self.start+t,duration,pitch,self.velocity,id=f'{self.id}:{index}:{pitch}'))
        return sorted(out,key=lambda n:(n.start,n.pitch))

    def materialize(self):
        if self.notes is None:
            self.notes=self.render_notes()
            for n in self.notes:n.start-=self.start

    def clip(self, start, end):
        """Preserve the performed rhythm when splitting a pattern block."""
        c=copy.deepcopy(self);c.materialize();delta=start-self.start
        notes=[]
        for old in c.notes:
            a=max(old.start,delta);b=min(old.end,end-self.start)
            if a<b:
                n=copy.deepcopy(old);n.start=a-delta;n.duration=b-a;n.id=uid();n.event_id='';notes.append(n)
        c.notes=notes
        c.start=start;c.duration=end-start;c.id=uid()
        return c


@dataclass
class Context:
    start: int
    end: int
    tonic: int = 48
    mode: str = 'Ionian'
    low: int = 0
    high: int = 7


@dataclass
class Measure:
    numerator: int = 4
    denominator: int = 4
    section: str = ''
    break_after: bool = False

    def __post_init__(self):
        self.section=section_name(self.section)

    @property
    def ticks(self):
        return PPQ * 4 * self.numerator // self.denominator


def _default_audio():
    from .soundbanks import default_audio
    return default_audio()


@dataclass
class Project:
    title: str = '未命名作品'
    author: str = ''
    bpm: int = 100
    measures: list[Measure] = field(default_factory=lambda: [Measure() for _ in range(8)])
    notes: list[Note] = field(default_factory=list)
    chords: list[Chord] = field(default_factory=list)
    contexts: list[Context] = field(default_factory=lambda: [Context(0, 8 * 3840)])
    groups: dict = field(default_factory=dict)
    notation: dict = field(default_factory=lambda: {'style': 'spatial', 'per_line': 4, 'circles': True, 'color': True, 'lyrics': True, 'row_gap': 15, 'system_gap':12, 'font_size':15, 'show_scale_lines':False})
    volumes: dict = field(default_factory=lambda: {'melody':100, 'chords':90})
    audio: dict = field(default_factory=_default_audio)
    marks: list[int] = field(default_factory=lambda:[0])
    schema_version: int = 6

    @property
    def starts(self):
        out = [0]
        for measure in self.measures:
            out.append(out[-1] + measure.ticks)
        return out

    @property
    def end(self):
        return self.starts[-1]

    def measure_at(self, tick):
        return min(len(self.measures) - 1, max(0, bisect.bisect_right(self.starts, tick) - 1))

    def context_at(self, tick):
        return next((c for c in self.contexts if c.start <= tick < c.end), self.contexts[-1])

    def chord_at(self, tick):
        return next((c for c in self.chords if c.start <= tick < c.end), None)

    def harmony_notes(self):
        # Region fragments with a shared identity remain ONE MIDI onset. Adjacent
        # rearticulations with different identities must never be joined.
        grouped={}
        for c in self.chords:
            for n in c.render_notes():grouped.setdefault(n.event_id or n.id,[]).append(n)
        result=[]
        for identity,parts in grouped.items():
            current=None
            for n in sorted(parts,key=lambda n:n.start):
                if current is not None and current.end==n.start and (current.pitch,current.velocity)==(n.pitch,n.velocity):current.duration+=n.duration
                else:
                    first=current is None
                    current=copy.deepcopy(n);current.id=identity if first else n.id;current.event_id='';result.append(current)
        return sorted(result,key=lambda n:(n.start,n.pitch))

    def harmony_owner(self, nid):
        return next((c for c in self.chords if any(n.id==nid or n.event_id==nid for n in c.render_notes())),None)

    def fill_chord_gaps(self):
        """N.C. regions cover gaps, split at bar lines, without touching MIDI."""
        result=[];cursor=0;starts=self.starts
        for c in sorted(self.chords,key=lambda c:c.start)+[None]:
            end=c.start if c else self.end
            for a,b in zip([cursor]+[t for t in starts if cursor<t<end], [t for t in starts if cursor<t<end]+[end]):
                if b>a:result.append(Chord(a,b-a,self.context_at(a).tonic,notes=[],recognized=False))
            if c:result.append(c);cursor=c.end
        self.chords=result

    def set_harmony_notes(self,notes):
        """Project absolute MIDI onto recognition regions without retriggering."""
        self.fill_chord_gaps()
        for c in self.chords:
            c.notes=[]
            for n in notes:
                a,b=max(n.start,c.start),min(n.end,c.end)
                if a<b:
                    part=copy.deepcopy(n);part.start=a-c.start;part.duration=b-a
                    part.event_id=n.id;part.id=n.id+'@'+c.id;c.notes.append(part)
        self.rescan_harmony()

    def rescan_harmony(self):
        from .meter import rescan_chord
        for c in self.chords:rescan_chord(self,c)

    def rescan_changed_harmony(self,before):
        from .meter import rescan_chord
        old={c['id']:c for c in before.get('chords',[])}
        meter_changed=[(m.numerator,m.denominator) for m in self.measures]!=[(m['numerator'],m['denominator']) for m in before.get('measures',[])]
        for c in self.chords:
            if meter_changed or asdict(c)!=old.get(c.id):rescan_chord(self,c)

    def sections(self):
        markers=[(i,section_name(m.section)) for i,m in enumerate(self.measures) if m.section]
        return [(name,i,markers[k+1][0] if k+1<len(markers) else len(self.measures)) for k,(i,name) in enumerate(markers)]

    def edit_harmony(self, note=None, delete_id=None, merge=False, overwrite=False):
        notes=self.harmony_notes();nid=delete_id or note.id
        notes=[n for n in notes if n.id!=nid]
        if note is not None:
            if not 0<=note.start<note.end<=self.end or not 21<=note.pitch<=108:
                raise ValueError('音符超出项目时间或88键范围。')
            from .operations import overwrite_note,union_note
            if overwrite:notes=overwrite_note(note,notes)
            elif merge:
                note,consumed=union_note(note,notes);notes=[n for n in notes if n.id not in consumed]+[note]
            else:
                if any(n.pitch==note.pitch and n.start<note.end and n.end>note.start for n in notes):raise ValueError('同音高的和弦音符不能重叠，请移动或缩短音符。')
                notes.append(note)
        self.set_harmony_notes(notes)

    def overwrite_harmony(self,note):
        self.edit_harmony(note,overwrite=True)
        return [note.id]

    def category(self, pitch, tick, role='melody', pitch_sets=None):
        c = self.context_at(tick)
        scale = (pitch - c.tonic) % 12 in MODES[c.mode]
        chord = self.chord_at(tick)
        if role=='harmony':
            if chord is None:pcs=set()
            elif pitch_sets is not None and chord.id in pitch_sets:pcs=pitch_sets[chord.id]
            else:
                pcs={n.pitch%12 for n in self.notes if n.start<chord.end and n.end>chord.start}
                if pitch_sets is not None:pitch_sets[chord.id]=pcs
        else:
            if chord is None:pcs=set()
            elif pitch_sets is not None and chord.id in pitch_sets:pcs=pitch_sets[chord.id]
            else:
                pcs={n.pitch%12 for n in chord.render_notes()}
                if pitch_sets is not None:pitch_sets[chord.id]=pcs
        inside=pitch%12 in pcs
        return 'both' if scale and inside else 'scale' if scale else 'chord' if inside else 'other'

    def set_context(self, ranges, **kwargs):
        for start, end in merge_ranges(ranges):
            pieces = []
            for c in self.contexts:
                if c.end <= start or c.start >= end:
                    pieces.append(c)
                    continue
                if c.start < start:
                    left = copy.copy(c); left.end = start; pieces.append(left)
                middle = copy.copy(c); middle.start = max(start, c.start); middle.end = min(end, c.end)
                for key, value in kwargs.items():
                    setattr(middle, key, value)
                pieces.append(middle)
                if c.end > end:
                    right = copy.copy(c); right.start = end; pieces.append(right)
            self.contexts = pieces
            if 'tonic' in kwargs or 'mode' in kwargs:
                starts=self.starts[:-1]
                self.marks=sorted(set(self.marks+[starts.index(t) for t in (start,end) if t in starts]))
        self.validate()

    def add_note(self, note, replace=False, merge=False, overwrite=False):
        if note.end > self.end or note.start < 0 or not 21 <= note.pitch <= 108 or note.duration <= 0:
            raise ValueError('音符超出项目时间或88键范围。')
        if overwrite:
            from .operations import overwrite_note
            self.notes=overwrite_note(note,self.notes);return
        if merge:
            from .operations import union_note
            note,consumed=union_note(note,self.notes)
            self.notes=[n for n in self.notes if n.id not in consumed]
        overlap = [n for n in self.notes if n.id != note.id and n.pitch==note.pitch and n.start < note.end and n.end > note.start]
        if overlap and not replace:
            raise ValueError('同音高音符不能重叠；不同音高可自由叠加为多声部。')
        if replace:
            self.notes = [n for n in self.notes if n not in overlap]
        self.notes = sorted([n for n in self.notes if n.id != note.id] + [note], key=lambda n:(n.start,n.pitch))

    def marker_value(self,index):
        c=self.context_at(self.starts[index]);m=self.measures[index]
        return m.numerator,m.denominator,c.tonic,c.mode

    def marker_visible(self,index):
        return index==0 or self.marker_value(index)!=self.marker_value(index-1)

    def set_markers(self,indices,tonic,mode,numerator,denominator,allow_trim=False):
        """Apply only to the explicitly selected bars, retaining other bars."""
        indices=sorted(set(indices))
        if not indices or any(i<0 or i>=len(self.measures) for i in indices):raise ValueError('请选择有效的小节。')
        from .meter import losses,splice_chords
        if not allow_trim and any(losses(self,indices,numerator,denominator)):raise ValueError('缩短小节会裁掉音符，请先移走本小节末尾或跨界的音符。')
        changed=False
        for i in reversed(indices):
            if (self.measures[i].numerator,self.measures[i].denominator)!=(numerator,denominator):self.change_meter(i,numerator,denominator,allow_trim,_split=False);changed=True
        if changed:splice_chords(self,0,0)
        self.set_context([self.starts[i:i+2] for i in indices],tonic=tonic,mode=mode)
        contexts=[]
        for c in sorted(self.contexts,key=lambda c:c.start):
            if contexts and contexts[-1].end==c.start and (contexts[-1].tonic,contexts[-1].mode,contexts[-1].low,contexts[-1].high)==(c.tonic,c.mode,c.low,c.high):contexts[-1].end=c.end
            else:contexts.append(c)
        self.contexts=contexts;self.validate()

    def set_marker(self,index,tonic,mode,numerator,denominator):
        end=next((i for i in sorted(self.marks) if i>index),len(self.measures))
        # Work backwards so earlier absolute ticks stay valid until their own edit.
        for i in reversed(range(index,end)):
            if (self.measures[i].numerator,self.measures[i].denominator)!=(numerator,denominator):
                self.change_meter(i,numerator,denominator)
        self.set_context([[self.starts[index],self.starts[end]]],tonic=tonic,mode=mode)
        self.marks=sorted(set(self.marks+[index]))

    def propagate_marker(self,index,kind,allow_trim=False):
        """Copy one bar's key or complete meter through all following bars."""
        if not 0<=index<len(self.measures) or kind not in ('key','meter'):raise ValueError('请选择有效的小节。')
        if index==len(self.measures)-1:return
        if kind=='key':
            context=self.context_at(self.starts[index])
            self.set_context([[self.starts[index+1],self.end]],tonic=context.tonic,mode=context.mode)
        else:
            meter=self.measures[index]
            from .meter import losses,splice_chords
            if not allow_trim and any(losses(self,range(index+1,len(self.measures)),meter.numerator,meter.denominator)):raise ValueError('缩短小节会裁掉音符，请先移走本小节末尾或跨界的音符。')
            changed=False
            for bar in reversed(range(index+1,len(self.measures))):
                if (self.measures[bar].numerator,self.measures[bar].denominator)!=(meter.numerator,meter.denominator):self.change_meter(bar,meter.numerator,meter.denominator,allow_trim,_split=False);changed=True
            if changed:splice_chords(self,0,0)
        self.validate()

    def insert_measures(self,index,count=1,**settings):
        if not 0<=index<=len(self.measures):raise ValueError('插入位置无效。')
        if not isinstance(count,int) or not 1<=count<=1000-len(self.measures):
            raise ValueError('插入后项目不能超过 1000 小节。')
        for offset in range(count):self.insert_measure(index+offset,**settings)

    def insert_measure(self,index,numerator=4,denominator=4,tonic=None,mode=None):
        if not 0<=index<=len(self.measures):raise ValueError('插入位置无效。')
        t=self.starts[index];d=PPQ*4*numerator//denominator
        from .presentation import shift_presentation
        shift_presentation(self,index,t,d)
        continuations=[]
        for event in self.notation.get('lyric_events',[]):
            if event['tick']>=t:event['tick']+=d
            elif event.get('kind')=='rap' and event['tick']+event['duration']>t:
                right=copy.deepcopy(event);right.update(id=uid(),tick=t+d,duration=event['tick']+event['duration']-t,text='',continuation=True)
                event['duration']=t-event['tick'];continuations.append(right)
        if continuations:self.notation['lyric_events'].extend(continuations)
        for section in self.notation.get('lyric_sections',[]):
            if section['start']>=t:section['start']+=d
            if section.get('end',0)>t:section['end']+=d
        ref=self.context_at(min(t,self.end-1))
        fresh=Context(t,t+d,ref.tonic if tonic is None else tonic,ref.mode if mode is None else mode)
        notes=[]
        for n in self.notes:
            if n.start>=t:n.start+=d;notes.append(n)
            elif n.end>t:
                right=copy.deepcopy(n);right.id=uid();right.start=t+d;right.duration=n.end-t;right.lyric=''
                n.duration=t-n.start;notes.extend([n,right])
            else:notes.append(n)
        self.notes=sorted(notes,key=lambda n:(n.start,n.pitch))
        chords=[]
        for c in self.chords:
            if c.start>=t:c.start+=d;chords.append(c)
            elif c.end>t:
                left=c.clip(c.start,t);right=c.clip(t,c.end);right.start+=d;chords.extend([left,right])
            else:chords.append(c)
        self.chords=sorted(chords,key=lambda c:c.start)
        contexts=[]
        for c in self.contexts:
            if c.end<=t:contexts.append(c)
            elif c.start>=t:c.start+=d;c.end+=d;contexts.append(c)
            else:
                left=copy.copy(c);left.end=t;right=copy.copy(c);right.start=t+d;right.end+=d;contexts.extend([left,right])
        self.contexts=sorted(contexts+[fresh],key=lambda c:c.start)
        for name,ranges in self.groups.items():
            result=[]
            for a,b in ranges:
                if b<=t:result.append([a,b])
                elif a>=t:result.append([a+d,b+d])
                else:result.extend([[a,t],[t+d,b+d]])
            self.groups[name]=result
        self.measures.insert(index,Measure(numerator,denominator));self.fill_chord_gaps()
        self.marks=sorted(set([m+1 if m>=index else m for m in self.marks]+[0,index]+([index+1] if index+1<len(self.measures) else [])))
        self.validate()

    def put_chord(self, chord):
        from .rhythm import analyze,regenerate
        from .meter import region_at,rescan_chord
        old=next((c for c in self.chords if c.id==chord.id),None)
        if old and region_at(self,old.start)[2]!=region_at(self,chord.start)[2]:
            raise ValueError('目标拍号与来源和弦不匹配。')
        # Insert/paste/edit cannot create a region spanning different meters.
        boundary=region_at(self,chord.start)[1]
        if chord.end>boundary:
            clipped=regenerate(chord,chord.start,boundary,self) or rescan_chord(self,chord.clip(chord.start,boundary))
            clipped.id=chord.id;chord=clipped
        old=next((c for c in self.chords if c.id==chord.id),None)
        rhythm=analyze(old,self) if chord.notes is not None and old and old.recognized and (old.start,old.duration)!=(chord.start,chord.duration) else None
        if chord.notes is None or rhythm is not None:
            chord=regenerate(chord,chord.start,chord.end,self,rhythm) or chord
        pieces = []
        for old in self.chords:
            if old.id == chord.id:
                continue
            if old.end <= chord.start or old.start >= chord.end:
                pieces.append(old)
                continue
            if old.start < chord.start:
                pieces.append(rescan_chord(self,old.clip(old.start,chord.start)))
            if old.end > chord.end:
                pieces.append(rescan_chord(self,old.clip(chord.end,old.end)))
        self.chords = sorted(pieces + [chord], key=lambda c: c.start)

    def append_measures(self, count=1):
        old_end = self.end
        last = copy.copy(self.context_at(old_end - 1))
        self.measures.extend(Measure() for _ in range(count))
        last.start, last.end = old_end, self.end
        self.contexts.append(last);self.fill_chord_gaps()

    def change_meter(self, index, numerator, denominator, allow_trim=False, _split=True):
        from .meter import losses,splice_events,splice_chords
        if numerator not in range(1,17) or denominator not in (2,4,8,16):raise ValueError('拍号无效。')
        if (self.measures[index].numerator,self.measures[index].denominator)==(numerator,denominator):return
        start, old_end = self.starts[index:index + 2]
        new_duration = PPQ * 4 * numerator // denominator
        new_end = start + new_duration
        delta = new_end - old_end
        if not allow_trim and any(losses(self,[index],numerator,denominator)):
            raise ValueError('缩短小节会裁掉音符，请先移走本小节末尾或跨界的音符。')
        def shift(t):
            return t + delta if t >= old_end else min(t, new_end) if t > start else t
        self.notes=splice_events(self.notes,old_end,new_end)
        for c in self.contexts:
            c.start, c.end = shift(c.start), shift(c.end)
        self.contexts = [c for c in self.contexts if c.end > c.start]
        for name, ranges in self.groups.items():
            self.groups[name] = [[shift(a), shift(b)] for a, b in ranges if shift(b) > shift(a)]
        lyric_events=[]
        for event in self.notation.get('lyric_events',[]):
            if event.get('kind')=='rap':
                for n in splice_events([Note(event['tick'],event['duration'],60,id=event['id'])],old_end,new_end):
                    e=copy.deepcopy(event);e.update(tick=n.start,duration=n.duration,id=n.id)
                    if n.id!=event['id']:e.update(text='',continuation=True)
                    lyric_events.append(e)
            else:
                event['tick']=min(self.end+delta-1,shift(event['tick']));lyric_events.append(event)
        if 'lyric_events' in self.notation:self.notation['lyric_events']=lyric_events
        for section in self.notation.get('lyric_sections',[]):
            section['start']=min(self.end+delta-1,shift(section['start']))
            if 'end' in section:section['end']=max(section['start']+1,shift(section['end']))
        self.notation['symbols']=[dict(item,start=shift(item['start']),end=shift(item['end'])) for item in self.notation.get('symbols',[]) if shift(item['end'])>shift(item['start'])]
        self.measures[index].numerator = numerator
        self.measures[index].denominator = denominator
        splice_chords(self,old_end,new_end,split_regions=_split)
        self.validate()

    def validate(self):
        from .lyrics import validate
        validate(self)
        if self.schema_version != 6:
            raise ValueError('不支持的项目版本。')
        if not 20 <= self.bpm <= 300 or not 1 <= len(self.measures) <= 1000:
            raise ValueError('速度或小节数量无效。')
        for m in self.measures:
            if m.numerator not in range(1, 17) or m.denominator not in (2, 4, 8, 16):
                raise ValueError('拍号无效。')
        previous = 0
        for c in sorted(self.contexts, key=lambda c: c.start):
            if c.start != previous or c.end <= c.start or c.mode not in MODES or not 21 <= c.tonic <= 108:
                raise ValueError('调性区间有缺口、重叠或无效参数。')
            previous = c.end
        if previous != self.end:
            raise ValueError('调性区间未覆盖整首曲子。')
        for events in (self.chords,):
            previous = 0
            for e in sorted(events, key=lambda e: e.start):
                if not isinstance(e.start, int) or not isinstance(e.duration, int) or e.start < previous or e.duration <= 0 or e.end > self.end:
                    raise ValueError('音符／和弦的时间重叠或超出范围。')
                previous = e.end
        ends={}
        for n in sorted(self.notes,key=lambda n:(n.start,n.pitch)):
            if type(n.start) is not int or type(n.duration) is not int or n.start<0 or n.duration<=0 or n.end>self.end or n.start<ends.get(n.pitch,-1):
                raise ValueError('旋律音符超出范围或同音高重叠。')
            ends[n.pitch]=n.end
        if not self.marks or self.marks[0]!=0 or sorted(set(self.marks))!=self.marks or any(type(m) is not int or not 0<=m<len(self.measures) for m in self.marks):
            raise ValueError('小节标记无效。')
        if set(self.audio)!={'melody','chords'} or any(type(a.get('program')) is not int or not 0<=a['program']<=127 or not isinstance(a.get('device'),str) for a in self.audio.values()):
            raise ValueError('音源或音色设置无效。')
        # Asset availability is checked at playback/export, never when loading
        # a project: users may install a missing pack after opening their score.
        if type(self.notation['per_line']) is not int or not 1<=self.notation['per_line']<=16 or self.notation['style'] not in ('spatial','compact','traditional'):
            raise ValueError('谱面分行或谱式设置无效。')
        if not .0001<=self.notation.get('font_size',15)<=26 or not isinstance(self.notation.get('show_scale_lines',False),bool):raise ValueError('谱面字号或谱线设置无效。')
        if not 4<=self.notation['row_gap']<=32 or not 0<=self.notation.get('system_gap',12)<=80:
            raise ValueError('谱面间距超出范围。')
        if any(not 21 <= n.pitch <= 108 or not 1 <= n.velocity <= 127 for n in self.notes):
            raise ValueError('音高或力度无效。')
        if any(c.quality not in QUALITIES for c in self.chords):
            raise ValueError('不支持的和弦类型。')
        if set(self.volumes)!={'melody','chords'} or any(type(v) is not int or not 0<=v<=127 for v in self.volumes.values()):
            raise ValueError('轨道音量必须为 0–127。')
        ids=[n.id for n in self.notes]+[c.id for c in self.chords]
        for c in self.chords:
            if c.pattern not in PATTERNS or not isinstance(c.custom_rhythm,bool) or not isinstance(c.bar_aligned,bool) or not .05<=c.gate<=1 or not 1<=c.velocity<=127 or not -1<=c.octave<=2:
                raise ValueError('和弦节奏型参数无效。')
            ends={}
            for n in c.render_notes():
                if type(n.start) is not int or type(n.duration) is not int or not c.start<=n.start<n.end<=c.end or not 21<=n.pitch<=108 or not 1<=n.velocity<=127:
                    raise ValueError('和弦音符超出时间、音高或力度范围。')
                if n.start<ends.get(n.pitch,-1):raise ValueError('和弦轨同音高不能重叠。')
                ends[n.pitch]=n.end;ids.append(n.id)
        if len(set(ids))!=len(ids):raise ValueError('项目内的事件标识不能重复。')
        from .presentation import validate_presentation
        validate_presentation(self)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        data = copy.deepcopy(data)
        for spec in data.get('audio',{}).values():
            if spec.get('device') in ('builtin','samples'):spec['device']='synth:stk-essentials'
        legacy=data.get('schema_version') in (2,3)
        if data.get('schema_version')==5:data['schema_version']=6
        for c in data.get('chords',[]):
            if c.get('notes') is not None:c['notes']=[Note(**n) for n in c['notes']]
            if c.get('quality')=='add9':
                c['quality']='add2'
                # Generated chords adopt the default close-position add2.
                # Explicit MIDI retains the user's performed voicing.
        for key, kind in [('measures', Measure), ('notes', Note), ('chords', Chord), ('contexts', Context)]:
            data[key] = [kind(**item) for item in data[key]]
        if 'notation' in data:data['notation'].setdefault('system_gap',12)
        project = cls(**data)
        if legacy and 'marks' not in data:
            project.marks=[i for i in range(len(project.measures)) if project.marker_visible(i)]
        project.validate()
        return project

    def save(self, path):
        self.validate()
        path = Path(path)
        if path.suffix.lower() not in ('.lfs','.leadsheet'):raise ValueError('不是支持的伶风工程文件。')
        temp = path.with_suffix(path.suffix + '.tmp')
        payload=json.dumps(self.to_dict(),ensure_ascii=False,indent=2).encode('utf-8')
        manifest={'format':'org.lingfeng.leadsheet','version':6,'document':'project.json',
                  'sha256':hashlib.sha256(payload).hexdigest()}
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json',json.dumps(manifest))
            archive.writestr('project.json',payload)
        os.replace(temp, path)

    @classmethod
    def load(cls, path):
        if Path(path).suffix.lower() not in ('.lfs','.leadsheet'):raise ValueError('不是支持的伶风工程文件。')
        if Path(path).stat().st_size>32*1024*1024:raise ValueError('项目文件过大。')
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for name in ('manifest.json','project.json'):
                    if archive.getinfo(name).file_size>32*1024*1024:raise ValueError('项目内容过大。')
                manifest=json.loads(archive.read('manifest.json'))
                if (manifest.get('format'),manifest.get('version')) not in (('org.lingfeng.leadsheet',5),('org.lingfeng.leadsheet',6)):
                    raise ValueError('不是支持的流行乐谱项目。')
                payload=archive.read('project.json')
                if hashlib.sha256(payload).hexdigest()!=manifest.get('sha256'):raise ValueError('项目校验失败，内容可能损坏。')
            return cls.from_dict(json.loads(payload))
        raise ValueError('不是支持的伶风工程文件。')


def merge_ranges(ranges):
    result = []
    for a, b in sorted(ranges):
        if a >= b:
            continue
        if result and a <= result[-1][1]:
            result[-1][1] = max(b, result[-1][1])
        else:
            result.append([a, b])
    return result


def demo_project():
    """Original technical fixture, not a transcription of the reference song."""
    p = Project(title='山色与回声', author='演示练习 · 原创旋律', bpm=84,
                measures=[Measure() for _ in range(16)], contexts=[Context(0, 16 * 3840, tonic=53)])
    patterns = [
        [(2, 480), (3, 480), (5, 960), (3, 480), (2, 480), (1, 960)],
        [(2, 480), (3, 480), (6, 960), (5, 480), (3, 480), (2, 960)],
        [(3, 960), (2, 320), (1, 320), (-1, 320), (2, 960), (3, 960)],
        [(5, 1440), (3, 480), (2, 480), (1, 480), (2, 960)],
        [(4, 480), (3, 480), (2, 960), (1, 480), (-1, 480), (1, 960)],
        [(3, 480), (4, 480), (5, 960), (3, 480), (2, 480), (1, 960)],
        [(2, 640), (3, 640), (4, 640), (5, 960), (2, 960)],
        [(1, 2880)],
    ]
    root_degrees = [0, 4, 5, 2, 3, 0, 1, 4]
    qualities = ['', '7', 'm7', 'm7', 'maj7', '', '7', '7']
    for bar in range(16):
        start = bar * 3840
        octave = 12 if bar >= 8 else 0
        for d, duration in patterns[bar % 8]:
            degree = d - 1 if d > 0 else d
            note = Note(start, duration, degree_pitch(53 + octave, degree))
            p.notes.append(note); start += duration
        p.chords.append(Chord(bar * 3840, 3840, degree_pitch(53, root_degrees[bar % 8]), qualities[bar % 8], 4 if bar == 1 else None))
    # Chromatic note, a rest, and a sustained note crossing a measure boundary.
    p.notes[9].pitch += 1
    last = next(n for n in p.notes if n.start == 7 * 3840)
    last.duration = 4320
    p.notes = [n for n in p.notes if n.id == last.id or not (last.start < n.start < last.end)]
    for note, word in zip(p.notes, '远山映着微光晚风经过窗旁我们沿着河岸听见回声悠长'):
        note.lyric = word
    p.measures[0].section = 'Verse'
    p.measures[8].section = 'Chorus'
    p.groups = {'主题': [[0, 8 * 3840]], '展开': [[8 * 3840, 16 * 3840]]}
    for c,pattern in zip(p.chords[8:],PATTERNS):c.pattern=pattern
    # Keep the original melody, adding a notation-only rap demonstration.
    from .lyrics import plan_range
    text='/x{跟着节奏来\nLet us rap now}/s唱';ident=uid()
    plan=plan_range(p,text,8,2,section_id=ident)
    if plan.issues:raise ValueError('\n'.join(plan.issues))
    p.notation['lyric_events']=plan.events
    p.notation['lyric_sections']=[dict(id=ident,start=p.starts[8],end=p.starts[10],verse=0,text=text,syntax_version=4)]
    p.validate()
    return p
