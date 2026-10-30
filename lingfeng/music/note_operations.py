"""Selection transformations in scale coordinates, independent of the UI."""
from __future__ import annotations
from lingfeng.platform.i18n import tr
from dataclasses import dataclass
import copy
import math
from lingfeng.music.model import MODES, uid


def scale_index(pitch, context, direction=0):
    """An unbounded diatonic index; chromatic inputs resolve toward the requested move."""
    values=MODES[context.mode];delta=pitch-context.tonic
    octave,pc=divmod(delta,12)
    if pc in values:return octave*7+values.index(pc)
    if direction>0:return octave*7+max(i for i,v in enumerate(values) if v<pc)
    if direction<0:
        return next((octave*7+i for i,v in enumerate(values) if v>pc),(octave+1)*7)
    return min(range(octave*7-1,octave*7+8),key=lambda i:(abs(scale_pitch(i,context)-pitch),i))


def scale_pitch(index,context):
    octave,degree=divmod(index,7)
    return context.tonic+octave*12+MODES[context.mode][degree]


@dataclass
class NoteClipboard:
    notes:list
    degrees:list
    length:int
    kind:str='direct'

    @classmethod
    def capture(cls,notes,project,kind='direct'):
        if not notes:return None
        if kind!='direct' and any((n.pitch-project.context_at(n.start).tonic)%12 not in MODES[project.context_at(n.start).mode] for n in notes):
            raise ValueError(tr('选区包含调外音，只能直接复制。'))
        notes=sorted(copy.deepcopy(notes),key=lambda n:(n.start,n.pitch))
        start=min(n.start for n in notes);end=max(n.end for n in notes)
        degrees=[scale_index(n.pitch,project.context_at(n.start)) for n in notes]
        axis=min(degrees)+max(degrees)
        for i,n in enumerate(notes):
            n.start=end-n.end if kind in ('retrograde','retrograde_inversion') else n.start-start
            if kind in ('inversion','retrograde_inversion'):degrees[i]=axis-degrees[i]
        return cls(notes,degrees,end-start,kind)

    def paste(self,project,tick):
        if tick<0 or tick+self.length>project.end:
            raise ValueError(tr('项目长度不够，请先插入小节。'))
        result=[]
        for old,degree in zip(self.notes,self.degrees):
            n=copy.deepcopy(old);n.id=uid();n.start+=tick
            n.pitch=old.pitch if self.kind=='direct' else scale_pitch(degree,project.context_at(n.start))
            if not 21<=n.pitch<=108:raise ValueError(tr('变换后的音符超出 88 键范围。'))
            result.append(n)
        return sorted(result,key=lambda n:(n.start,n.pitch))


def shift_in_scale(notes,project,steps):
    result=[]
    for old in notes:
        context=project.context_at(old.start);n=copy.deepcopy(old)
        n.pitch=scale_pitch(scale_index(n.pitch,context,steps)+steps,context)
        if not 21<=n.pitch<=108:raise ValueError(tr('变换后的音符超出 88 键范围。'))
        result.append(n)
    return result


def can_join(notes):
    if len(notes)<2:return False
    changed=False
    for pitch in {n.pitch for n in notes}:
        row=sorted((n for n in notes if n.pitch==pitch),key=lambda n:n.start)
        end=row[0].end
        for n in row[1:]:
            if n.start>end:return False
            end=max(end,n.end);changed=True
    return changed


def join_notes(notes):
    if not can_join(notes):raise ValueError(tr('只能合并每个音高行内相邻或重叠的音符。'))
    result=[]
    for pitch in sorted({n.pitch for n in notes}):
        row=sorted((n for n in notes if n.pitch==pitch),key=lambda n:n.start)
        n=copy.deepcopy(row[0]);n.duration=max(item.end for item in row)-n.start
        n.lyric=''.join(item.lyric for item in row);result.append(n)
    return result


def can_split(notes,grid=None):
    # 1/64 = 60 ticks; its triplet = 40 ticks at 960 PPQ.
    return bool(notes) and all(n.duration>=120 or n.duration==80 for n in notes)


def split_notes(notes,grid=None):
    if not can_split(notes):raise ValueError(tr('二等分后的音符不能短于 1/64；三连音不能短于 1/64 三连音。'))
    result=[]
    for old in notes:
        left=copy.deepcopy(old);left.duration=old.duration//2
        right=copy.deepcopy(old);right.id=uid();right.start=left.end;right.duration=old.end-right.start;right.lyric=''
        result.extend((left,right))
    return result


def union_note(note,others):
    """Return the edited note's transitive overlap union and IDs consumed by it."""
    result=copy.deepcopy(note);removed={note.id}
    changed=True
    while changed:
        changed=False
        for n in others:
            if n.id not in removed and n.pitch==result.pitch and n.start<result.end and result.start<n.end:
                end=max(result.end,n.end);result.start=min(result.start,n.start);result.duration=end-result.start
                removed.add(n.id);changed=True
    lyrics={n.id:n for n in others if n.id in removed};lyrics[note.id]=note
    result.lyric=''.join(n.lyric for n in sorted(lyrics.values(),key=lambda n:(n.start,n.id)))
    return result,removed


def overwrite_note(note,others):
    """Replace only intersecting time on this pitch; never join touching notes."""
    result=[]
    for old in others:
        if old.id==note.id:continue
        if old.pitch!=note.pitch or old.end<=note.start or old.start>=note.end:
            result.append(old);continue
        if old.start<note.start:
            left=copy.deepcopy(old);left.duration=note.start-old.start;result.append(left)
        if old.end>note.end:
            right=copy.deepcopy(old);right.start=note.end;right.duration=old.end-note.end
            if old.start<note.start:right.id=uid();right.lyric=''
            result.append(right)
    return sorted(result+[copy.deepcopy(note)],key=lambda n:(n.start,n.pitch))


def resize_chord(chord,start,end,fill_pattern=True,project=None):
    if project is not None:
        from lingfeng.music.meter import resize_bounds
        start,end=resize_bounds(project,chord,start,end)
    if chord.custom_rhythm and chord.notes is None:
        chord=copy.deepcopy(chord);chord.materialize()
    if fill_pattern:
        from lingfeng.music.rhythm import regenerate
        result=regenerate(chord,start,end,project)
        if result is not None:return result
    result=copy.deepcopy(chord);result.start=start;result.duration=end-start
    if chord.notes is not None:
        result.notes=[]
        for old in chord.notes:
            a=max(start,chord.start+old.start);b=min(end,chord.start+old.end)
            if a<b:
                n=copy.deepcopy(old);n.start=a-start;n.duration=b-a;result.notes.append(n)
    if project is not None:
        from lingfeng.music.meter import rescan_chord
        rescan_chord(project,result)
    return result


def repartition_chord(project,cid,start,end):
    """Resize a structure region; vacated space is silent, covered space is replaced."""
    old=next(c for c in project.chords if c.id==cid)
    if not 0<=start<end<=project.end:raise ValueError(tr('和弦结构范围无效。'))
    result=resize_chord(old,start,end,project=project)
    result.id=old.id;project.put_chord(result);project.validate()


def window_notes(notes,start,end):
    result=[]
    for old in notes:
        a,b=max(start,old.start),min(end,old.end)
        if a<b:
            n=copy.copy(old);n.start=a-start;n.duration=b-a;result.append(n)
    return result
