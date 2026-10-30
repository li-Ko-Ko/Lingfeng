"""Meter regions and loss-aware time edits, shared by every editing surface."""
import copy
from lingfeng.music.model import PPQ, Note, uid


def signature(project, tick):
    bar=project.measures[project.measure_at(tick)]
    return bar.numerator,bar.denominator


def regions(project):
    result=[]
    for i,bar in enumerate(project.measures):
        meter=(bar.numerator,bar.denominator);a,b=project.starts[i:i+2]
        if result and result[-1][2]==meter:result[-1]=(result[-1][0],b,meter)
        else:result.append((a,b,meter))
    return result


def region_at(project,tick):
    return next((r for r in regions(project) if r[0]<=tick<r[1]),regions(project)[-1])


def resize_bounds(project,chord,start,end):
    a,b,_=region_at(project,chord.start)
    start=max(a,min(b-1,start));end=max(start+1,min(b,end))
    return start,end


def rescan_chord(project,chord):
    """Re-read actual MIDI after a crop; explicit Custom only locks rhythm."""
    from lingfeng.music.recognition import recognize, update_symbol
    from lingfeng.music.rhythm import analyze
    pitches=[n.pitch for n in chord.render_notes()]
    if not (chord.recognized and {p%12 for p in pitches}=={p%12 for p in chord.pitches}):
        update_symbol(chord,recognize(pitches,preferred=(chord.root%12,chord.quality)))
    match=analyze(chord,project)
    if match:chord.pattern=match.pattern;chord.gate=match.gate
    return chord


def moved_chord(project,chord,start,bounds=None):
    """Translate, then crop both sides of one meter region. None means silence."""
    from lingfeng.music.rhythm import regenerate
    a,b,_=bounds or region_at(project,chord.start)
    left=max(a,start);right=min(b,start+chord.duration)
    if left>=right:return None
    generated=regenerate(chord,left,right,project)
    if generated:return generated
    result=copy.deepcopy(chord);result.materialize();result.start=start
    if left>start or right<result.end:
        clipped=result.clip(left,right);clipped.id=result.id;result=clipped
    return rescan_chord(project,result)


def losses(project,indices,numerator,denominator):
    """Count performed events that would lose time, before mutating anything."""
    cuts=[];length=PPQ*4*numerator//denominator
    for i in indices:
        a,b=project.starts[i:i+2]
        if length<b-a:cuts.append((a+length,b))
    hit=lambda a,b:any(a<end and b>start for start,end in cuts)
    return (sum(hit(n.start,n.end) for n in project.notes),
            sum(hit(n.start,n.end) for n in project.harmony_notes()),
            sum(hit(e['tick'],e['tick']+e['duration']) for e in project.notation.get('lyric_events',[]) if e.get('kind')=='rap'))


def splice_events(notes,old_end,new_end):
    """Insert silence or remove time. Do not scale note lengths with a bar."""
    delta=new_end-old_end;cut=min(old_end,new_end);out=[]
    for old in notes:
        if not delta:out.append(copy.deepcopy(old));continue
        pieces=[]
        if old.start<cut:
            n=copy.deepcopy(old);n.duration=min(old.end,cut)-old.start
            if n.duration>0:pieces.append(n)
        if old.end>old_end:
            n=copy.deepcopy(old);n.start=max(old.start,old_end)+delta;n.duration=old.end-max(old.start,old_end)
            if pieces:
                if pieces[-1].end==n.start:pieces[-1].duration+=n.duration;out.extend(pieces);continue
                n.id=uid();n.lyric=''
            pieces.append(n)
        out.extend(pieces)
    return sorted(out,key=lambda n:(n.start,n.pitch))


def splice_chords(project,old_end,new_end,split_regions=True):
    """Preserve performed MIDI, then split chord regions at every meter boundary."""
    delta=new_end-old_end;cut=min(old_end,new_end);out=[]
    for old in project.chords:
        if delta<0:
            # A removed interval closes up: preserve a surviving chord as one
            # region until the final (possibly broadcast) meter map is known.
            shift=lambda t:t+delta if t>=old_end else min(t,new_end)
            a,b=shift(old.start),shift(old.end)
            if a>=b:continue
            c=copy.deepcopy(old);c.start=a;c.duration=b-a
            c.notes=splice_events(old.render_notes(),old_end,new_end)
            for n in c.notes:n.start-=a
            old=c
        intervals=[]
        if delta<=0:intervals=[(old.start,old.end,0)]
        else:
            if old.start<cut:intervals.append((old.start,min(old.end,cut),0))
            if old.end>old_end:intervals.append((max(old.start,old_end),old.end,delta))
        first=True
        for a,b,shift in intervals:
            for ra,rb,_ in regions(project) if split_regions else [(0,project.end,None)]:
                left=max(a+shift,ra);right=min(b+shift,rb)
                if left>=right:continue
                c=old.clip(left-shift,right-shift);c.start=left
                if first:c.id=old.id;first=False
                out.append(c)
    project.chords=sorted(out,key=lambda c:c.start)
    from lingfeng.music.rhythm import analyze
    for c in project.chords:
        c.bar_aligned=True
        rescan_chord(project,c)
        match=analyze(c,project)
        if match:c.pattern=match.pattern;c.gate=match.gate
