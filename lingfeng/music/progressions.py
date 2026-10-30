"""Tonic-independent Roman recipes, with an explicit tonic for each operation.

PyChord validates chord components and performs pitch-class transposition.
The progression grammar and editing policy are original Lingfeng code.
"""

import copy

import re

from lingfeng.music.model import Chord, Note, MAJOR, QUALITIES, PATTERNS, PPQ, uid

from lingfeng.platform.i18n import tr

from lingfeng.music.progression_catalog import HOOKTHEORY_RECIPES, CATALOG_VERSION

DEFAULT_PRESETS=[{'name':name,'sequence':sequence} for name,sequence,_ in HOOKTHEORY_RECIPES]+[
    {'name':'vi – IV – I – V','sequence':'vi IV I V'},
    {'name':'I – V – vi – iii – IV – I – IV – V','sequence':'I V vi iii IV I IV V'},
    {'name':'ii7 – V7 – Imaj7','sequence':'ii7 V7 Imaj7'},
    {'name':'IV – V – iii7 – vi','sequence':'IV V iii7 vi'},
    {'name':'I – IV – V','sequence':'I IV V'},
]

ROMANS=('I','II','III','IV','V','VI','VII')

def tokens(text):
    parts=[p.replace('add9','add2') for p in re.split(r'[\s,，;；|→–—-]+',text.strip()) if p]
    if not 1<=len(parts)<=128:raise ValueError(tr('和弦进行须包含 1–128 个罗马数字和弦。'))
    for token in parts:resolve(token,0)
    return parts

def resolve(token,tonic):
    from pychord import Chord as PyChord,QualityManager
    QualityManager().set_quality('add2',('1','2','3','5'))
    token=token.replace('♭','b').replace('♯','#')
    if token.count('/')>4:raise ValueError(tr('无效的罗马数字和弦：{0}',token))
    # A final numeric slash is a bass degree in the original key. It may follow
    # an applied chord: V/vi/#5 means E/G# when 1=C. V6 remains an added sixth.
    main,sep,tail=token.rpartition('/')
    bm=re.fullmatch(r'([b#]?)([1-7])',tail) if sep else None
    original_tonic=tonic
    body=main if bm else token
    base,secondary,target=body.partition('/')
    m=re.fullmatch(r'([b#]?)([ivIV]+)(.*)',base)
    if not m or m[2].upper() not in ROMANS:raise ValueError(tr('无效的罗马数字和弦：{0}',token))
    accidental,roman,suffix=m.groups()
    degree=ROMANS.index(roman.upper());root=(MAJOR[degree]+(-1 if accidental=='b' else 1 if accidental=='#' else 0))%12
    quality={'M7':'maj7','M9':'maj9','M':'','°':'dim','°7':'dim7','ø7':'m7b5','+':'aug','add9':'add2'}.get(suffix,suffix)
    if roman.islower() and quality in ('','7','6','9'):quality='m'+quality
    if roman.islower() and quality=='maj7':quality='mM7'
    if quality not in QUALITIES:raise ValueError(tr('无效的罗马数字和弦：{0}',token))
    bass_pc=(original_tonic+MAJOR[int(bm[2])-1]+(-1 if bm[1]=='b' else 1 if bm[1]=='#' else 0))%12 if bm else None
    if secondary:tonic=resolve(target,tonic).root%12
    pc=PyChord('C'+quality);pc.transpose((tonic+root)%12)
    actual=pc.components(visible=False)
    result=Chord(0,PPQ,48+(tonic+root)%12,quality,bass_pc)
    if set(p%12 for p in actual)!={p%12 for p in result.pitches if bass_pc is None or p%12!=bass_pc} and bass_pc is None:
        raise ValueError(tr('和弦音程不受支持：{0}',token))
    return result

def progression_label(text):
    return ' – '.join(tokens(text))

def progression_key(text):
    """Lexicographic musical degrees; equal prefixes put shorter recipes first."""
    result=[]
    for token in tokens(text):
        normalized=token.replace('♭','b').replace('♯','#')
        match=re.match(r'([b#]?)([ivIV]+)',normalized)
        chord=resolve(token,0)
        result.append((ROMANS.index(match[2].upper()),{'b':-1,'':0,'#':1}[match[1]],
                       tuple(QUALITIES).index(chord.quality),normalized.partition('/')[2]))
    return tuple(result)

def preset_label(entry):
    sequence=progression_label(entry['sequence'])
    return sequence if entry['name']==sequence else entry['name']+': '+sequence

def make_preset(sequence,name=''):
    parts=tokens(sequence);name=name.strip()[:120]
    if not name:name=' – '.join(parts)
    else:
        try:
            if tokens(name)==parts:name=' – '.join(parts)
        except ValueError:pass
    return dict(name=name,sequence=' '.join(parts))

def presets(values):
    if not isinstance(values,list):values=DEFAULT_PRESETS
    if not values:return []
    valid=[]
    for entry in values:
        try:
            if not isinstance(entry,dict) or not isinstance(entry.get('name',''),str) or not isinstance(entry.get('sequence'),str):continue
            valid.append(make_preset(entry['sequence'],entry.get('name','')))
        except (ValueError,KeyError,TypeError):continue
    return sorted(valid,key=lambda x:(progression_key(x['sequence']),x['name'].casefold())) if valid else presets(DEFAULT_PRESETS)

def load_library(values,version=0):
    """Add this catalogue once; retain custom names, edits and later deletions."""
    library=presets(None if values==[] and not (isinstance(version,int) and version>=CATALOG_VERSION) else values)
    if isinstance(version,int) and version>=CATALOG_VERSION:return library
    for name,sequence,_ in HOOKTHEORY_RECIPES:
        entry=make_preset(sequence,name)
        matches=[i for i,x in enumerate(library) if x['sequence']==entry['sequence']]
        anonymous=next((i for i in matches if library[i]['name']==progression_label(sequence)),None)
        if anonymous is not None:library[anonymous]=entry
        elif entry not in library:library.append(entry)
    return presets(library)

def root_identity(token):
    """Spelled root, not pitch class: #II and bIII remain distinct.

    Qualities and numeric bass slashes are ignored. Applied roots resolve to
    the original key, so V/vi matches III and viidim/vi matches #V.
    """
    normalized=token.replace('♭','b').replace('♯','#')
    main,sep,bass=normalized.rpartition('/')
    if sep and re.fullmatch(r'[b#]?[1-7]',bass):normalized=main
    base,sep,target=normalized.partition('/')
    match=re.match(r'([b#]?)([ivIV]+)',base)
    degree=ROMANS.index(match[2].upper());alter={'b':-1,'':0,'#':1}[match[1]]
    if not sep:return degree,alter
    td,ta=root_identity(target);pc=(MAJOR[degree]+alter+MAJOR[td]+ta)%12
    degree=(degree+td)%7;alter=(pc-MAJOR[degree]+6)%12-6
    return degree,alter

def matches_roots(sequence,query):
    if not query.strip():return True
    wanted=[root_identity(t) for t in tokens(query)];position=0
    for token in tokens(sequence):
        if root_identity(token)==wanted[position]:
            position+=1
            if position==len(wanted):return True
    return False

def targets(project,cid,count):
    ordered=sorted(project.chords,key=lambda c:c.start)
    index=next((i for i,c in enumerate(ordered) if c.id==cid),None)
    return [] if index is None else ordered[index:index+count]

def common_patterns(project,chords):
    from lingfeng.music.rhythm import supports
    return [key for key in PATTERNS if all(supports(key,project,c.start) for c in chords)]

def apply(project,cid,text,keep_rhythm=True,pattern='block',velocity=None,gate=None,tonic=None):
    from lingfeng.music.rhythm import analyze_performed, Rhythm, regenerate
    sequence=tokens(text);destinations=targets(project,cid,len(sequence))
    if not destinations:raise ValueError(tr('请选择起始和弦。'))
    tonic=project.context_at(destinations[0].start).tonic if tonic is None else tonic
    if pattern not in common_patterns(project,destinations):raise ValueError(tr('节奏型必须适用于所有目标拍号。'))
    ids=[]
    for old,token in zip(destinations,sequence):
        semantic=resolve(token,tonic)
        rhythm=analyze_performed(old,project) if keep_rhythm else None
        c=copy.deepcopy(old);c.root=semantic.root;c.quality=semantic.quality;c.bass=semantic.bass;c.recognized=True;c.custom_rhythm=False
        c.pattern=rhythm.pattern if rhythm else pattern;c.gate=gate if gate is not None else rhythm.gate if rhythm else old.gate
        if velocity is not None:c.velocity=velocity
        generated=regenerate(c,c.start,c.end,project,Rhythm(c.pattern,tuple(c.pitches),c.gate))
        if generated is None:raise ValueError(tr('无法生成该拍号的和弦节奏型。'))
        # Replacement terminates crossing events in this region, as any explicit chord edit does.
        project.put_chord(generated);ids.append(c.id)
    return ids

def capture(project,ids,tonic=None):
    """Keep qualities and explicit bass degrees, including inversions."""
    ordered=sorted((c for c in project.chords if c.id in ids),key=lambda c:c.start)
    if not ordered or any(not c.recognized or c.notes==[] for c in ordered):raise ValueError(tr('只有名称可识别的和弦可以加入和弦进行。'))
    context=project.context_at(ordered[0].start)
    tonic=context.tonic if tonic is None else tonic
    mode=context.mode if tonic%12==context.tonic%12 else 'Ionian'
    return ' '.join(c.roman(tonic,c.flat,mode).replace('♭','b').replace('♯','#') for c in ordered)

def selection_root_query(project,ids,tonic=None):
    """Chronological roots against one tonic; bass is never a root."""
    try:sequence=capture(project,ids,tonic)
    except ValueError:raise ValueError(tr('请选择名称可识别的和弦进行检索。')) from None
    result=[]
    for token in tokens(sequence):
        degree,alter=root_identity(token)
        result.append(('b'*(-alter) if alter<0 else '#' * alter)+ROMANS[degree])
    return ' '.join(result)

def search_recipe(query,tonic):
    """Accept Roman relations or literal chord names interpreted at this tonic."""
    try:return ' '.join(tokens(query))
    except ValueError as roman_error:
        from pychord import Chord as PyChord
        parts=[p for p in re.split(r'[\s,，;；|→–—-]+',query.strip()) if p]
        if not 1<=len(parts)<=128:raise roman_error
        result=[]
        try:
            for part in parts:
                chord=PyChord(part.replace('♭','b').replace('♯','#'))
                root=PyChord(chord.root).components(visible=False)[0]
                result.append(Chord(0,PPQ,48+root).roman(tonic,flat='b' in chord.root).replace('♭','b').replace('♯','#'))
        except (ValueError,KeyError):raise roman_error from None
        return ' '.join(result)
