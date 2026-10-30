"""Delete complete bars, preserving surviving events with explicit cut edges."""
import copy
from .model import uid


def deletion_has_content(project,bars):
    from .lyrics import events
    cuts=[project.starts[i:i+2] for i in bars]
    hit=lambda a,b:any(a<end and b>start for start,end in cuts)
    return (any(hit(n.start,n.end) for n in project.notes+project.harmony_notes())
            or any(hit(e['tick'],e['tick']+max(1,e.get('duration',0))) for e in events(project))
            or any(hit(s['start'],s['end']) for s in project.notation.get('symbols',[]))
            or any(project.measures[i].section for i in bars)
            or any(set(bars)&set(range(c['start'],c['end'])) for c in project.notation.get('compressions',[])))


def delete_bars(project,bars):
    bars=sorted(set(bars));count=len(project.measures)
    if not bars or any(i<0 or i>=count for i in bars):raise ValueError('请选择有效的小节。')
    if len(bars)==count:raise ValueError('项目至少需要保留一个小节。')
    from .lyrics import detach
    detach(project)
    removed=set(bars);starts=project.starts;kept=[i for i in range(count) if i not in removed]
    # Adjacent retained bars share a segment. Only deleted intervals create cuts.
    segments=[];offset=0
    for i in kept:
        a,b=starts[i:i+2]
        if segments and segments[-1][1]==a:segments[-1]=(segments[-1][0],b,segments[-1][2])
        else:segments.append((a,b,offset))
        offset+=b-a
    def pieces(start,end):
        return [(max(start,a),min(end,b),dest-a) for a,b,dest in segments if max(start,a)<min(end,b)]
    def position(t):
        return sum(max(0,min(t,b)-a) for a,b,dest in segments)
    def bar_position(i):return sum(k<i for k in kept)
    notes=[]
    for old in project.notes:
        for index,(a,b,shift) in enumerate(pieces(old.start,old.end)):
            n=copy.deepcopy(old);n.start=a+shift;n.duration=b-a
            if index:n.id=uid();n.lyric=''
            notes.append(n)
    chords=[]
    for old in project.chords:
        for index,(a,b,shift) in enumerate(pieces(old.start,old.end)):
            c=old.clip(a,b);c.start+=shift
            if not index:c.id=old.id
            chords.append(c)
    contexts=[]
    for old in project.contexts:
        for a,b,shift in pieces(old.start,old.end):
            c=copy.copy(old);c.start=a+shift;c.end=b+shift;contexts.append(c)
    events=[]
    for old in project.notation.get('lyric_events',[]):
        if old.get('kind')=='rap':
            for index,(a,b,shift) in enumerate(pieces(old['tick'],old['tick']+old['duration'])):
                e=copy.deepcopy(old);e.update(tick=a+shift,duration=b-a)
                if index:e['id']=uid()
                if a>old['tick']:e.update(text='',continuation=True)
                events.append(e)
        elif any(a<=old['tick']<b for a,b,_ in segments):
            e=copy.deepcopy(old);e['tick']=position(e['tick']);events.append(e)
    project.notation['lyric_events']=events
    sections=[]
    for old in project.notation.get('lyric_sections',[]):
        a,b=position(old['start']),position(old.get('end',starts[-1]))
        if a<b:
            s=copy.deepcopy(old);s.update(start=a,end=b)
            remaining=[e for e in events if e.get('section_id')==s['id']]
            if remaining:
                s['text']=' '.join(e['text'] or '_' for e in sorted(remaining,key=lambda e:e['tick']))
                sections.append(s)
    project.notation['lyric_sections']=sections
    project.notation['forced_rows']=[[bar_position(a),bar_position(b)] for a,b in project.notation.get('forced_rows',[]) if bar_position(a)<bar_position(b)]
    project.notation['forced_row_fonts']=[[bar_position(a),bar_position(b),n] for a,b,n in project.notation.get('forced_row_fonts',[]) if bar_position(a)<bar_position(b)]
    compressions=[]
    for old in project.notation.get('compressions',[]):
        if removed&set(range(old['start'],old['end'])):continue
        item=copy.deepcopy(old)
        for key in ('start','first_end','hidden_start','hidden_end','end'):item[key]=bar_position(item[key])
        compressions.append(item)
    project.notation['compressions']=compressions
    project.notation['symbols']=[dict(s,start=position(s['start']),end=position(s['end'])) for s in project.notation.get('symbols',[]) if position(s['start'])<position(s['end'])]
    for key,ranges in project.groups.items():project.groups[key]=[[a+shift,b+shift] for start,end in ranges for a,b,shift in pieces(start,end)]
    project.measures=[project.measures[i] for i in kept]
    project.marks=sorted({0,*[bar_position(i) for i in project.marks if i in kept]})
    project.notes=sorted(notes,key=lambda n:(n.start,n.pitch));project.contexts=sorted(contexts,key=lambda c:c.start);project.chords=sorted(chords,key=lambda c:c.start)
    from .meter import splice_chords,rescan_chord
    splice_chords(project,0,0)
    for c in project.chords:rescan_chord(project,c)
    project.validate()
