"""Operations on chord regions, independent of any particular piano-roll view."""
import copy
from dataclasses import dataclass
from lingfeng.music.model import Chord, Note, PATTERNS, QUALITIES, PPQ, uid
from lingfeng.platform.i18n import tr

QUALITY_LABELS={'':'大三和弦','m':'小三和弦','7':'属七和弦','7b5':'属七降五和弦','maj7':'大七和弦','m7':'小七和弦','mM7':'小大七和弦',
    'dim':'减三和弦','m7b5':'半减七和弦','aug':'增三和弦','sus2':'挂二和弦 · sus2','sus4':'挂四和弦 · sus4',
    'add2':'加二和弦 · add2','6':'大六和弦','m6':'小六和弦','9':'属九和弦','m9':'小九和弦',
    'maj9':'大九和弦','dim7':'减七和弦','7sus4':'挂四属七和弦','5':'五和弦'}
QUALITY_ORDER=list(QUALITIES)


def set_quality_order(order):
    order=['add2' if q=='add9' else q for q in order]
    QUALITY_ORDER[:]=list(dict.fromkeys(q for q in order if q in QUALITIES))+[q for q in QUALITIES if q not in order]


def quality_items():return [(q,({'':'M','maj7':'M7','maj9':'M9'}.get(q,q)+' · '+tr(QUALITY_LABELS[q]))) for q in QUALITY_ORDER]


def quality_voicing(chord,value,pitches):
    """Replace written chord degrees while retaining the performed registers."""
    from lingfeng.music.chord_spelling import QUALITY_DEGREES
    old=dict(zip(QUALITY_DEGREES[chord.quality],QUALITIES[chord.quality]))
    new=dict(zip(QUALITY_DEGREES[value],QUALITIES[value]))
    pitches=tuple(sorted(set(pitches)));lowest=min(pitches)
    bass_pc=chord.root%12 if chord.bass is None else chord.bass%12
    bass=lowest if lowest%12==bass_pc else None
    # A repeated root above the bass establishes the upper chord register.
    # Rootless voicings derive that register from their written chord degrees.
    upper=[p for p in pitches if p!=bass]
    roots=[p for p in upper if p%12==chord.root%12]
    anchors=[p-offset for p in upper for offset in old.values() if (p-chord.root)%12==offset%12]
    root=min(roots or anchors or [lowest-(lowest-chord.root)%12])
    result=[];present=set()
    for pitch in pitches:
        if pitch==bass:
            result.append(pitch)
            continue
        degree=next((d for d,offset in old.items() if (pitch-chord.root)%12==offset%12),None)
        if degree is None:result.append(pitch)
        elif degree in new:
            result.append(pitch+new[degree]-old[degree]);present.add(degree)
    for degree,offset in new.items():
        if degree not in present:result.append(root+offset)
    return tuple(sorted(set(result)))


def change_quality(chord,value,project=None,regenerate_notes=True):
    if value not in QUALITIES:raise ValueError(tr('无效的和弦性质。'))
    if chord.quality==value and value!='add2':return
    from lingfeng.music.rhythm import analyze_performed, regenerate, Rhythm, clipped_bar_events, bar_grid
    rhythm=analyze_performed(chord,project) if regenerate_notes else None
    if chord.recognized and rhythm is not None:
        candidate=copy.deepcopy(chord);candidate.quality=value;candidate.bass=None
        result=regenerate(candidate,candidate.start,candidate.end,project,Rhythm(rhythm.pattern,tuple(candidate.pitches),rhythm.gate))
        if result is not None:
            voiced=Rhythm(rhythm.pattern,tuple(candidate.pitches),rhythm.gate)
            result.notes=[Note(t,d,p,result.velocity) for t,d,p in clipped_bar_events(voiced,result.duration,bar_grid(result.start,result.end,project))]
            chord.quality=value;chord.bass=None;chord.pattern=result.pattern;chord.gate=result.gate;chord.notes=result.notes;chord.bar_aligned=result.bar_aligned
            return
    old=QUALITIES[chord.quality];new=QUALITIES[value]
    if chord.notes is not None:
        lowest=min((n.pitch for n in chord.notes),default=None)
        bass_pitch=lowest if lowest is not None and chord.bass is not None and lowest%12==chord.bass%12 else None
        rewritten=[]
        for note in chord.notes:
            # A specified bass is a separate voice, not a locked inversion of
            # the old quality. Keep it while rewriting the upper chord tones.
            if note.pitch==bass_pitch:rewritten.append(copy.deepcopy(note));continue
            intervals=[i%12 for i in old];interval=(note.pitch-chord.root)%12
            if interval not in intervals:rewritten.append(copy.deepcopy(note));continue
            index=intervals.index(interval)
            if index>=len(new):continue
            n=copy.deepcopy(note);n.pitch+=new[index]-old[index];rewritten.append(n)
        missing={v%12 for v in new}-{(n.pitch-chord.root)%12 for n in rewritten}
        if rewritten and missing:
            source=min(rewritten,key=lambda n:(n.start,n.pitch))
            for interval in sorted(missing):
                pitch=source.pitch+(chord.root+interval-source.pitch)%12
                rewritten.append(Note(source.start,source.duration,pitch,source.velocity))
        from lingfeng.music.note_operations import union_note
        chord.notes=[]
        for n in rewritten:
            combined,removed=union_note(n,chord.notes);chord.notes=[x for x in chord.notes if x.id not in removed]+[combined]
    chord.quality=value
    replace_bass(chord,chord.root%12,project)


def replace_bass(chord,bass,project=None,voicing=None):
    """Replace only the bass voice; a menu action, never a voicing lock."""
    if bass not in range(12):raise ValueError(tr('无效的低音。'))
    if chord.notes:
        from lingfeng.music.rhythm import analyze
        rhythm=analyze(chord,project) if voicing is None else None
        pitches=voicing or (rhythm.pitches if rhythm else sorted({n.pitch for n in chord.notes}))
        lowest=min(pitches)
        upper=min((p for p in pitches if p>lowest),default=lowest+12)
        target=upper-1-(upper-1-bass)%12
        for note in chord.notes:
            if note.pitch==lowest:note.pitch=target
    chord.bass=None if bass==chord.root%12 else bass


def invert_chord(chord,index,project=None,voicing=None):
    tones=QUALITIES[chord.quality]
    if not 0<=index<len(tones):raise ValueError(tr('无效的和弦转位。'))
    replace_bass(chord,(chord.root+tones[index])%12,project,voicing)


def change_root(chord,target,project=None,regenerate_notes=True):
    """Match the root shortcut/menu: preserve quality, replace the bass by root."""
    if target not in range(12):raise ValueError(tr('无效的和弦根音。'))
    from lingfeng.music.rhythm import analyze_performed, regenerate, Rhythm, clipped_bar_events, bar_grid
    rhythm=analyze_performed(chord,project) if regenerate_notes else None
    voicing=rhythm.pitches if rhythm else sorted({n.pitch for n in chord.render_notes()})
    complete=bool(voicing) and {p%12 for p in voicing}>={p%12 for p in chord.pitches}
    full_voicing=tuple(chord.pitches)
    delta=(target-chord.root%12+6)%12-6
    if chord.notes is not None:
        for note in chord.notes:note.pitch+=delta
    chord.root=48+target;invert_chord(chord,0,project,[p+delta for p in voicing])
    if rhythm is not None and chord.recognized:
        result=regenerate(chord,chord.start,chord.end,project,Rhythm(rhythm.pattern,tuple(chord.pitches),rhythm.gate))
        if result is not None:
            pitches=tuple(chord.pitches)
            result.notes=[Note(t,d,p,result.velocity) for t,d,p in clipped_bar_events(Rhythm(rhythm.pattern,pitches,rhythm.gate),result.duration,bar_grid(result.start,result.end,project))]
            chord.pattern=result.pattern;chord.gate=result.gate;chord.notes=result.notes;chord.bar_aligned=True


def chord_contexts(project,chord):
    result=[]
    for context in project.contexts:
        if context.start>=chord.end or context.end<=chord.start:continue
        if not result or (context.tonic,context.mode)!=(result[-1].tonic,result[-1].mode):result.append(context)
    return result or [project.context_at(chord.start)]


def roman_label(project,chord,flat=False):
    # Slash remains reserved for a bass note; arrows mark temporal key changes.
    return ' → '.join(chord.roman(c.tonic,flat,c.mode) for c in chord_contexts(project,chord))


def contextual_chord_name(project,chord,context=None):
    from lingfeng.music.chord_spelling import tone_for
    if chord.notes==[]:return 'N.C.'
    if not chord.recognized:return tr('未识别')
    context=context or project.context_at(chord.start)
    label=tone_for(chord.root,context,chord).name+chord.quality
    if chord.bass is not None:label+='/'+tone_for(chord.bass,context,chord).name
    return label


def chord_pitch_name(project,chord,pitch,context=None):
    from lingfeng.music.chord_spelling import tone_for
    return tone_for(pitch,context or project.context_at(chord.start),chord).pitch_name(pitch)


def chord_degree_text(project,chord,pitch,context=None,unicode=True):
    from lingfeng.music.chord_spelling import degree_label
    return degree_label(pitch,context or project.context_at(chord.start),chord,unicode)


def chord_details(project,chord,tick=None,compact=False):
    """Actual voicing, its scale degrees, and the lowest performed pitch."""
    from html import escape
    from lingfeng.platform.i18n import tr
    if compact:return compact_chord_details(project,chord)
    pitches=sorted({n.pitch for n in chord.render_notes()})
    heading=escape(roman_label(project,chord,chord.flat)+' · '+contextual_chord_name(project,chord))
    if not pitches:return '<b>'+heading+'</b><br>'+tr('空白和弦区间，尚无音符。')
    lines=['<b>'+heading+'</b>']
    for context in chord_contexts(project,chord):
        tonic=context.tonic
        rows=' · '.join(escape(chord_degree_text(project,chord,p,context)+' = '+chord_pitch_name(project,chord,p,context)) for p in pitches)
        bass=pitches[0];bass_text=escape(chord_degree_text(project,chord,bass,context)+' = '+chord_pitch_name(project,chord,bass,context))
        lines.extend(['<b>'+escape('1 = '+chord_pitch_name(project,chord,tonic,context)+' · '+context.mode)+'</b>',tr('和弦音')+'：'+rows,tr('实际低音')+'：'+bass_text])
    return '<br>'.join(lines)


def compact_chord_details(project,chord):
    """Creation hints: actual pitch classes, ordered and numbered by the chord."""
    from html import escape
    from lingfeng.music.chord_spelling import QUALITY_DEGREES, tone_for, Tone, accidental, NATURALS
    from lingfeng.music.model import QUALITIES, MAJOR
    from lingfeng.ui.theme import roll_pitch_name
    pitches=sorted({n.pitch for n in chord.render_notes()})
    title=escape(roman_label(project,chord,chord.flat)+' · '+contextual_chord_name(project,chord))
    if not pitches:return '<b>'+title+'</b><br>'+tr('空白和弦区间，尚无音符。')
    pcs=list(dict.fromkeys(p%12 for p in pitches));parts=['<b>'+title+'</b>']
    for context in chord_contexts(project,chord):
        parts.append('<div style="margin-top:6px"><b>'+escape('1 = '+roll_pitch_name(context.tonic)+' · '+context.mode)+'</b></div>')
        names=[]
        if chord.recognized:
            root=tone_for(chord.root,context,chord)
            for offset,degree in zip(QUALITIES[chord.quality],QUALITY_DEGREES[chord.quality]):
                pc=(chord.root+offset)%12
                if pc not in pcs:continue
                letter=(root.letter+degree-1)%7
                name=Tone(letter,accidental(pc,NATURALS[letter])).name
                alter=offset-(MAJOR[(degree-1)%7]+12*((degree-1)//7))
                label=('#'*alter if alter>0 else 'b'*-alter)+str(degree)
                names.append(escape(label+': '+name))
        else:
            names=[escape(tone_for(pc,context).name) for pc in pcs]
        parts.append('<table cellspacing="0" cellpadding="3"><tr><td>'+escape(tr('和弦音'))+'</td><td>'+' &nbsp; '.join(names)+'</td></tr><tr><td>'+escape(tr('实际低音'))+'</td><td>'+escape(tone_for(pitches[0],context,chord if chord.recognized else None).name)+'</td></tr></table>')
    return ''.join(parts)


def blank_chord(project, tick, length='auto'):
    if not 0<=tick<project.end:return None
    bar=project.measure_at(tick)
    if length=='auto':end=min([project.starts[bar+1]]+[c.start for c in project.chords if c.start>tick])
    else:
        unit,count=length.split(':');count=int(count)
        if count<1:raise ValueError(tr('和弦结构范围无效。'))
        if unit=='beats':end=tick+count*PPQ*4//project.measures[bar].denominator
        elif unit=='bars':
            # Preserve the offset inside the starting bar, including meter changes.
            end=tick+sum(m.ticks for m in project.measures[bar:bar+count])
        else:raise ValueError(tr('和弦结构范围无效。'))
    from lingfeng.music.meter import region_at
    end=min(project.end,end,region_at(project,tick)[1])
    return Chord(tick,end-tick,project.context_at(tick).tonic,notes=[],recognized=False)


def pattern_template(chord):
    """Return a canonical generator only when it preserves the performed events."""
    from lingfeng.music.rhythm import analyze, extend
    rhythm=analyze(chord)
    if rhythm is None:return None
    result=extend(chord,chord.start,chord.end,rhythm)
    return result if result.notes is None else None


def can_merge_chords(chords,project=None):
    ordered=sorted(chords,key=lambda c:c.start)
    if project and ordered:
        from lingfeng.music.meter import region_at
        if ordered[-1].end>region_at(project,ordered[0].start)[1]:return False
    return len(ordered)>1 and all(a.end==b.start for a,b in zip(ordered,ordered[1:]))


def split_chords(project,ids):
    from lingfeng.music.note_operations import can_split
    selected=[c for c in project.chords if c.id in ids]
    if not can_split(selected):raise ValueError(tr('二等分后的音符不能短于 1/64；三连音不能短于 1/64 三连音。'))
    notes=project.harmony_notes();cuts=[];result=[]
    for c in selected:
        mid=c.start+c.duration//2
        cuts.append(mid)
        result.extend([c.clip(c.start,mid),c.clip(mid,c.end)])
    project.chords=sorted([c for c in project.chords if c.id not in ids]+result,key=lambda c:c.start)
    project.set_harmony_notes(_cut_events(notes,cuts))
    return {c.id for c in result}


def _cut_events(notes,cuts):
    """Explicit splits rearticulate only at the requested cut, not every region."""
    result=[]
    for note in notes:
        points=[note.start]+sorted(t for t in cuts if note.start<t<note.end)+[note.end]
        for index,(a,b) in enumerate(zip(points,points[1:])):
            part=copy.copy(note);part.start=a;part.duration=b-a
            if index:part.id=uid();part.event_id=''
            result.append(part)
    return result


def merge_chords(project,ids):
    selected=sorted((c for c in project.chords if c.id in ids),key=lambda c:c.start)
    if not can_merge_chords(selected,project):raise ValueError(tr('只能合并同一拍号区间内相邻的和弦。'))
    notes=project.harmony_notes()
    result=copy.deepcopy(selected[0]);result.duration=selected[-1].end-result.start
    result.custom_rhythm=any(c.custom_rhythm for c in selected)
    project.chords=sorted([c for c in project.chords if c.id not in ids]+[result],key=lambda c:c.start)
    project.set_harmony_notes(notes)
    return {result.id}


def split_at_position(project,tick):
    chord=project.chord_at(tick)
    if not chord or not chord.start<tick<chord.end:raise ValueError(tr('定位线必须位于和弦内部。'))
    notes=project.harmony_notes();pieces=[chord.clip(chord.start,tick),chord.clip(tick,chord.end)]
    project.chords=sorted([c for c in project.chords if c.id!=chord.id]+pieces,key=lambda c:c.start)
    project.set_harmony_notes(_cut_events(notes,[tick]))
    return {c.id for c in pieces}


def move_chords(project,ids,delta):
    session=ChordMoveSession.capture(project,ids)
    session.apply(project,delta)


def can_move_horizontal(project,chords):
    from lingfeng.music.meter import region_at
    return bool(chords) and len({region_at(project,c.start) for c in chords})==1


@dataclass
class ChordMoveSession:
    """Unclipped originals live only while this chord selection is being moved."""
    chords:list
    bounds:tuple
    delta:int=0

    @property
    def ids(self):return {c.id for c in self.chords}

    @classmethod
    def capture(cls,project,ids):
        from lingfeng.music.meter import region_at
        selected=[c for c in project.chords if c.id in ids]
        if not can_move_horizontal(project,selected):raise ValueError(tr('只能左右移动同一连续拍号区间内的和弦。'))
        return cls(copy.deepcopy(selected),region_at(project,selected[0].start))

    def extents(self):
        result=copy.deepcopy(self.chords)
        for c in result:c.start+=self.delta
        return result

    def apply(self,project,delta,bounds=None):
        from lingfeng.music.meter import moved_chord
        bounds=bounds or self.bounds
        if bounds[2]!=self.bounds[2]:raise ValueError(tr('目标拍号与来源和弦不匹配。'))
        results=[moved_chord(project,c,c.start+self.delta+delta,bounds) for c in self.chords]
        project.chords=[c for c in project.chords if c.id not in self.ids]
        for c in results:
            if c is not None:project.put_chord(c)


def diatonic_chord(chord,context,steps,project=None):
    """Move within the local scale, adapt quality and replace bass by the new root."""
    from lingfeng.music.model import MODES
    from lingfeng.music.note_operations import scale_index, scale_pitch
    pitches=chord.pitches if chord.notes is None else [n.pitch for n in chord.notes]
    tones=[chord.root+i for i in QUALITIES[chord.quality]]
    if not chord.recognized or any((p-context.tonic)%12 not in MODES[context.mode] for p in [*tones,*pitches]):
        raise ValueError(tr('调内移动要求和弦属性可识别，且全部和弦音都在当前调式内。'))
    move=lambda p:scale_pitch(scale_index(p,context)+steps,context)
    root=move(chord.root);intervals={(move(chord.root+i)-root)%12 for i in QUALITIES[chord.quality]}
    quality=next((q for q,t in QUALITIES.items() if {i%12 for i in t}==intervals),None)
    if quality is None:raise ValueError(tr('移动后的和弦性质暂不支持识别。'))
    result=copy.deepcopy(chord)
    from lingfeng.music.rhythm import analyze
    rhythm=analyze(chord,project)
    voicing=rhythm.pitches if rhythm else sorted({n.pitch for n in chord.render_notes()})
    if result.notes is not None:
        for n in result.notes:n.pitch=move(n.pitch)
    result.root=48+root%12;result.quality=quality
    invert_chord(result,0,project,[move(p) for p in voicing])
    if any(not 21<=n.pitch<=108 for n in result.render_notes()):raise ValueError(tr('变换后的音符超出 88 键范围。'))
    return result


def can_move_diatonic(project,chords,steps):
    if not chords:return False
    try:
        for c in chords:diatonic_chord(c,project.context_at(c.start),steps,project)
    except ValueError:return False
    return True


@dataclass
class ChordClipboard:
    chords:list
    meters:tuple=()

    @classmethod
    def capture(cls,chords,project=None):
        from lingfeng.music.meter import signature
        ordered=sorted(chords,key=lambda c:c.start)
        return cls(copy.deepcopy(ordered),tuple(signature(project,c.start) if project else (4,4) for c in ordered)) if ordered else None

    def can_paste(self,project,tick):
        from lingfeng.music.meter import region_at
        if tick<0 or not self.chords:return False
        for c,meter in zip(self.chords,self.meters or ((4,4),)*len(self.chords)):
            if tick>=project.end:return False
            a,b,target=region_at(project,tick)
            if target!=meter or tick+c.duration>b:return False
            tick+=c.duration
        return True

    def paste(self,project,tick):
        from lingfeng.music.rhythm import regenerate
        if not self.can_paste(project,tick):raise ValueError(tr('粘贴范围必须完整位于匹配的拍号区间内。'))
        ids=set()
        for old in self.chords:
            c=regenerate(old,tick,tick+old.duration,project) or copy.deepcopy(old);c.id=uid();c.start=tick
            if c.notes is not None:
                for n in c.notes:n.id=uid()
            project.put_chord(c);ids.add(c.id);tick=c.end
        return ids


def can_apply_pattern(project,chords,pattern):
    from lingfeng.music.meter import signature
    from lingfeng.music.rhythm import supports
    return (bool(chords) and all(c.recognized for c in chords)
            and len({signature(project,c.start) for c in chords})==1
            and all(supports(pattern,project,c.start) for c in chords))


def change_chords(project, ids, command):
    selected=[c for c in project.chords if c.id in ids]
    if command.startswith('pattern:'):
        from lingfeng.music.rhythm import regenerate, Rhythm
        pattern=command.split(':',1)[1]
        if not can_apply_pattern(project,selected,pattern):
            raise ValueError(tr('更改节奏型要求所选和弦均可识别、拍号相同，且支持该节奏型。'))
        replacements={}
        for old in selected:
            c=copy.deepcopy(old);c.custom_rhythm=False;c.pattern=pattern
            replacements[c.id]=regenerate(c,c.start,c.end,project,Rhythm(pattern,tuple(c.pitches),c.gate))
        for c in selected:
            result=replacements[c.id]
            c.custom_rhythm=False;c.pattern=result.pattern;c.gate=result.gate;c.bar_aligned=result.bar_aligned;c.notes=result.notes
        return
    if command=='delete':project.chords=[c for c in project.chords if c.id not in ids];return
    if command.startswith('custom:'):
        enabled=command.split(':')[1]=='1'
        for c in selected:
            if enabled:c.materialize()
            c.custom_rhythm=enabled
        return
    if command.startswith('diatonic:'):
        replacements={c.id:diatonic_chord(c,project.context_at(c.start),int(command.split(':')[1]),project) for c in selected}
        project.chords=[replacements.get(c.id,c) for c in project.chords];return
    if command.startswith('root_step:'):
        if not selected or any(not c.recognized for c in selected):raise ValueError(tr('更换根音要求所选和弦属性均可识别。'))
        replacements={}
        for c in selected:
            result=copy.deepcopy(c);change_root(result,(c.root+int(command.split(':')[1]))%12,project)
            if any(not 21<=n.pitch<=108 for n in result.render_notes()):raise ValueError(tr('变换后的音符超出 88 键范围。'))
            replacements[c.id]=result
        project.chords=[replacements.get(c.id,c) for c in project.chords];return
    if command.startswith('transpose:'):
        delta=int(command.split(':')[1])
        if any(not 21<=n.pitch+delta<=108 for c in selected for n in c.render_notes()):raise ValueError('移调后的音符超出 88 键范围。')
        for c in selected:
            c.materialize();c.custom_rhythm=True
            for n in c.notes:n.pitch+=delta
            c.root=48+(c.root+delta)%12
            if c.bass is not None:c.bass=(c.bass+delta)%12
        return
    if len(selected)!=1:return
    c=selected[0]
    if not c.recognized:return
    kind,value=command.split(':',1)
    if kind=='quality':change_quality(c,value,project)
    elif kind=='root':
        change_root(c,int(value),project)
    elif kind=='bass':replace_bass(c,int(value),project)
    elif kind=='inversion':invert_chord(c,int(value),project)
