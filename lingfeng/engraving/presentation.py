"""Notation-only structure. No routine here changes performed MIDI events."""
from lingfeng.music.model import PPQ
import bisect


def contiguous(bars):
    bars=sorted(set(bars))
    return bool(bars) and bars==list(range(bars[0],bars[-1]+1))


def segment_signature(p, first, last):
    """Compare the actual two-track performance, notation and harmonic context."""
    a,b=p.starts[first],p.starts[last]
    events=[]
    for track,notes in enumerate((p.notes,p.harmony_notes())):
        if any(n.start<a<n.end or n.start<b<n.end for n in notes):return None
        # Lyrics belong to verses. They may differ between identical performances.
        events.append(tuple(sorted((n.start-a,n.duration,n.pitch,n.velocity,n.flat) for n in notes if a<=n.start<b)))
    contexts=[]
    for c in p.contexts:
        if c.start<b and c.end>a:
            item=(max(a,c.start)-a,min(b,c.end)-a,c.tonic,c.mode)
            if contexts and contexts[-1][1]==item[0] and contexts[-1][2:]==item[2:]:contexts[-1]=(contexts[-1][0],item[1],*item[2:])
            else:contexts.append(item)
    chords=tuple((max(a,c.start)-a,min(b,c.end)-a,c.root,c.quality,c.bass,c.flat,c.recognized) for c in p.chords if c.start<b and c.end>a)
    measures=tuple((m.numerator,m.denominator,m.section) for m in p.measures[first:last])
    return b-a,tuple(events),tuple(contexts),chords,measures


def same_segment(p,a,b,c,d):
    left=segment_signature(p,a,b)
    return left is not None and left==segment_signature(p,c,d) and bool(left[1][0] or left[1][1])


def compression_candidate(p,bars,kind='repeat'):
    if not contiguous(bars):return None
    bars=sorted(set(bars));a,z=bars[0],bars[-1]+1
    if kind=='coda':
        # A B A C -> Segno A / To Coda / B / D.S. al Coda / Coda C.
        # A, B and C must all contain at least one complete measure.
        # Prefix matches on onset fingerprints avoid quadratic full-MIDI comparisons
        # when a user selects a long, nonrepeating song.
        starts=p.starts;events=[[] for _ in bars];first_onset=None
        for track,notes in enumerate((p.notes,p.harmony_notes())):
            for n in notes:
                bar=bisect.bisect_right(starts,n.start)-1
                if a<=bar<z:
                    events[bar-a].append((track,n.start-starts[bar],n.duration,n.pitch,n.velocity,n.flat))
                    first_onset=bar if first_onset is None else min(first_onset,bar)
        if first_onset is None:return None
        tokens=[]
        for bar,items in zip(bars,events):
            m=p.measures[bar];ctx=p.context_at(starts[bar]);tokens.append((m.numerator,m.denominator,ctx.tonic,ctx.mode,tuple(sorted(items))))
        matches=[0]*len(tokens);left=right=0
        for i in range(1,len(tokens)):
            if i<right:matches[i]=min(right-i,matches[i-left])
            while i+matches[i]<len(tokens) and tokens[matches[i]]==tokens[i+matches[i]]:matches[i]+=1
            if i+matches[i]>right:left,right=i,i+matches[i]
        for offset in range(2,len(tokens)-1):
            maximum=min(matches[offset],offset-1,len(tokens)-offset-1)
            for size in range(maximum,first_onset-a,-1):
                repeated=a+offset
                if same_segment(p,a,a+size,repeated,repeated+size):return dict(kind=kind,start=a,first_end=a+size,hidden_start=repeated,hidden_end=repeated+size,end=z)
        return None
    if len(bars)%2:return None
    mid=a+len(bars)//2
    if kind in ('dc','dc_nr') and a!=0:return None
    if not same_segment(p,a,mid,mid,z):return None
    # A D.C./D.S. al Fine form can only end the performed piece.
    if kind!='repeat' and any(n.end>p.starts[z] for n in p.notes+p.harmony_notes()):return None
    return dict(kind=kind,start=a,first_end=mid,hidden_start=mid,hidden_end=z,end=z)


def compression_valid(p,item):
    try:
        a,b,c,d,z=(item[k] for k in ('start','first_end','hidden_start','hidden_end','end'))
        if not 0<=a<b<=c<d<=z<=len(p.measures):return False
        if item['kind']=='coda':return b<c and d<z and same_segment(p,a,b,c,d)
        if b!=c or d!=z:return False
        return compression_candidate(p,list(range(a,z)),item['kind'])==item
    except (KeyError,TypeError,IndexError):return False


def active_compressions(p):
    result=[]
    for item in p.notation.get('compressions',[]):
        if compression_valid(p,item) and not any(item['start']<old['end'] and old['start']<item['end'] for old in result):result.append(item)
    return result


def visible_bars(p):
    hidden={i for item in active_compressions(p) for i in range(item['hidden_start'],item['hidden_end'])}
    return [i for i in range(len(p.measures)) if i not in hidden]


def forced_row_allowed(p,bars,systems):
    return contiguous(bars) and len(bars)>1 and any(s.bars[0]==min(bars) for s in systems) and all(b in visible_bars(p) for b in bars)


def apply_forced_row(p,bars):
    a,b=min(bars),max(bars)+1
    rows=[r for r in p.notation.get('forced_rows',[]) if not (r[0]<b and a<r[1])]
    p.notation['forced_rows']=sorted(rows+[[a,b]])
    fonts=[r for r in p.notation.get('forced_row_fonts',[]) if not (r[0]<b and a<r[1])]
    p.notation['forced_row_fonts']=sorted(fonts+[[a,b,p.notation['per_line']]])


def add_compression(p,bars,kind):
    candidate=compression_candidate(p,bars,kind)
    if candidate is None:raise ValueError('所选段落的音乐内容不符合该反复记号。')
    old=p.notation.get('compressions',[])
    if any(candidate['start']<c['end'] and c['start']<candidate['end'] for c in old):raise ValueError('请先展开重叠的反复段落。')
    p.notation['compressions']=old+[candidate]


def pair_candidate(p, first, second, kind='repeat'):
    """Two explicit, adjacent, equally long selections; never guess their split."""
    if not contiguous(first) or not contiguous(second):return None
    a,b=sorted(set(first)),sorted(set(second))
    if len(a)!=len(b) or a[-1]+1!=b[0]:return None
    return compression_candidate(p,a+b,kind)


def lyric_verses(p, compressions):
    """Map visible note IDs to verse rows without changing the source lyrics."""
    result={n.id:[n.lyric] for n in p.notes}
    for item in compressions:
        a,b,c,d=(p.starts[item[k]] for k in ('start','first_end','hidden_start','hidden_end'))
        hidden={(n.start-c,n.duration,n.pitch):n for n in p.notes if c<=n.start<d}
        originals=[n for n in p.notes if a<=n.start<b]
        if not any(n.lyric!=hidden[(n.start-a,n.duration,n.pitch)].lyric for n in originals):continue
        for n in originals:result[n.id]=[n.lyric,hidden[(n.start-a,n.duration,n.pitch)].lyric]
    return result


def annotation_allowed(p,kind,start,end):
    if not 0<=start<end<=p.end:return False
    notes=p.notes+p.harmony_notes();has_notes=any(n.start<end and n.end>start for n in notes)
    if kind in ('barline','double_bar','final_bar'):return end in p.starts and (kind!='final_bar' or not any(n.end>end for n in notes))
    if kind in ('segno','coda'):return start in p.starts and has_notes
    if kind in ('fine','fade'):return has_notes and not any(n.end>end for n in notes)
    if kind in ('rit','adlib'):return has_notes
    return False


def add_annotation(p,kind,start,end):
    if not annotation_allowed(p,kind,start,end):raise ValueError('该符号不适用于当前小节或拍选区。')
    items=[a for a in p.notation.get('symbols',[]) if not (a['kind']==kind and a['start']==start and a['end']==end)]
    if kind in ('barline','double_bar','final_bar'):items=[a for a in items if not (a['kind'] in ('barline','double_bar','final_bar') and a['end']==end)]
    items.append(dict(kind=kind,start=start,end=end));p.notation['symbols']=items


def shift_presentation(p,index,tick,duration):
    for row in p.notation.get('forced_rows',[]):
        row[0]+=row[0]>=index;row[1]+=row[1]>index
    for row in p.notation.get('forced_row_fonts',[]):
        row[0]+=row[0]>=index;row[1]+=row[1]>index
    for item in p.notation.get('compressions',[]):
        for key in ('start','first_end','hidden_start','hidden_end','end'):
            item[key]+=item[key]>=index if key in ('start','hidden_start') else item[key]>index
    for item in p.notation.get('symbols',[]):
        for key in ('start','end'):
            if item[key]>=tick:item[key]+=duration


def validate_presentation(p):
    n=len(p.measures)
    rows=p.notation.get('forced_rows',[])
    if any(not isinstance(r,list) or len(r)!=2 or not all(type(v) is int for v in r) or not 0<=r[0]<r[1]<=n for r in rows):raise ValueError('局部分行设置无效。')
    if any(a[1]>b[0] for a,b in zip(sorted(rows),sorted(rows)[1:])):raise ValueError('局部分行设置重叠。')
    fonts=p.notation.get('forced_row_fonts',[])
    if any(not isinstance(r,list) or len(r)!=3 or not all(type(v) is int for v in r) or not 0<=r[0]<r[1]<=n or not 1<=r[2]<=16 for r in fonts):raise ValueError('局部分行设置无效。')
    for item in p.notation.get('symbols',[]):
        if item.get('kind') not in ('barline','double_bar','final_bar','segno','coda','fine','fade','rit','adlib') or not all(type(item.get(k)) is int for k in ('start','end')) or not 0<=item['start']<item['end']<=p.end:raise ValueError('谱面符号设置无效。')
    for item in p.notation.get('compressions',[]):
        if item.get('kind') not in ('repeat','dc','ds','dc_nr','ds_nr','coda') or not all(type(item.get(k)) is int for k in ('start','first_end','hidden_start','hidden_end','end')):raise ValueError('反复排版设置无效。')
        a,b,c,d,z=(item[k] for k in ('start','first_end','hidden_start','hidden_end','end'))
        if not 0<=a<b<=c<d<=z<=n:raise ValueError('反复排版设置无效。')
