"""MusicXML 4.0 score-partwise and compressed score export."""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from io import BytesIO
from itertools import groupby
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from lingfeng.audio.events import INSTRUMENT_CHANNEL
from lingfeng.engraving.lyrics import events, lyric_track
from lingfeng.music.chord_spelling import LETTERS, NATURALS, fallback, scale_tones, tone_for
from lingfeng.music.model import MODES, Note, PPQ, QUALITY_RELATIONS
from lingfeng.music.note_operations import window_notes
from lingfeng.platform.i18n import tr


_PARTS = (('P1', 'melody', 0, 0), ('P2', 'instrument', INSTRUMENT_CHANNEL, 1),
          ('P3', 'chords', 1, None))
_MIME = 'application/vnd.recordare.musicxml'
_INVALID_XML = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]')
_MODES = {'Ionian':'major', 'Aeolian':'minor', **{mode:mode.lower() for mode in MODES if mode not in ('Ionian','Aeolian')}}
_KINDS = {'':'major', 'm':'minor', 'dim':'diminished', 'aug':'augmented', '7':'dominant',
          'maj7':'major-seventh', 'm7':'minor-seventh', 'dim7':'diminished-seventh',
          'm7b5':'half-diminished', 'mM7':'major-minor', '6':'major-sixth', 'm6':'minor-sixth',
          '9':'dominant-ninth', 'maj9':'major-ninth', 'm9':'minor-ninth', '11':'dominant-11th',
          'm11':'minor-11th', '13':'dominant-13th', 'maj13':'major-13th', '5':'power',
          'sus2':'suspended-second', 'sus4':'suspended-fourth'}
_KIND_BY_FORMULA = {QUALITY_RELATIONS[quality]:kind for quality,kind in _KINDS.items()}
_TYPES = {}
for _duration,_type in zip((PPQ*4,PPQ*2,PPQ,PPQ//2,PPQ//4,PPQ//8,PPQ//16,PPQ//32),
                           ('whole','half','quarter','eighth','16th','32nd','64th','128th')):
    _TYPES[_duration]=(_type,0,False)
    if _duration%2==0:_TYPES[_duration*3//2]=(_type,1,False)
    if _duration%4==0:_TYPES[_duration*7//4]=(_type,2,False)
    if _duration%3==0:_TYPES[_duration*2//3]=(_type,0,True)


def _element(parent,tag,value=None,**attributes):
    node=ET.SubElement(parent,tag,{key:str(item) for key,item in attributes.items()})
    if value is not None:node.text=_INVALID_XML.sub('\ufffd',str(value))
    return node


def _key(attributes,context):
    key=_element(attributes,'key')
    _element(key,'fifths',sum(tone.alteration for tone in scale_tones(context.tonic,context.mode)))
    _element(key,'mode',_MODES[context.mode])


def _pitch(parent,tag,tone,midi=None):
    node=_element(parent,tag)
    prefix='' if tag=='pitch' else tag+'-'
    _element(node,prefix+'step',LETTERS[tone.letter])
    if tone.alteration:_element(node,prefix+'alter',tone.alteration)
    if midi is not None:_element(node,'octave',(midi-NATURALS[tone.letter]-tone.alteration)//12-1)


def _notation_type(node,duration):
    kind=_TYPES.get(duration)
    if kind is None:return
    name,dots,triplet=kind
    _element(node,'type',name)
    for _ in range(dots):_element(node,'dot')
    if triplet:
        timing=_element(node,'time-modification')
        _element(timing,'actual-notes',3)
        _element(timing,'normal-notes',2)


def _lyric_nodes(node,lyrics):
    for lyric in lyrics:
        item=_element(node,'lyric',number=lyric['verse']+1)
        if lyric.get('rap'):item.set('name','Rap')
        if lyric['text'] or (lyric.get('rap') and not lyric.get('extend')):
            _element(item,'syllabic',lyric['syllabic'])
            _element(item,'text',lyric['text'])
        if lyric.get('extend'):_element(item,'extend',type=lyric['extend'])


def _note(measure,note,voice,start,end,chord,tones,lyrics,rap):
    node=_element(measure,'note',dynamics=f'{note.velocity*100/90:.8f}')
    if chord:_element(node,'chord')
    if rap.get(note.id):_element(node,'unpitched')
    else:_pitch(node,'pitch',tones[note.id],note.pitch)
    _element(node,'duration',end-start)
    ties=[kind for active,kind in ((start>note.start,'stop'),(end<note.end,'start')) if active]
    for kind in ties:_element(node,'tie',type=kind)
    _element(node,'voice',voice)
    _notation_type(node,end-start)
    if note.id in rap:_element(node,'notehead','x')
    if ties:
        notations=_element(node,'notations')
        for kind in ties:_element(notations,'tied',type=kind)
    if start==note.start:_lyric_nodes(node,lyrics.get(note.id,()))


def _silence(measure,voice,duration,full_measure=False):
    if voice>1:
        node=_element(measure,'forward')
        _element(node,'duration',duration);_element(node,'voice',voice)
        return
    node=_element(measure,'note')
    _element(node,'rest',**({'measure':'yes'} if full_measure else {}))
    _element(node,'duration',duration);_element(node,'voice',voice)
    if not full_measure:_notation_type(node,duration)


def _lyrics(project,track,notes,origin,end):
    """Map score lyric verses onto the same note attacks, with word extenders."""
    if track is None:return {},{},{},[]
    onsets=defaultdict(list)
    for note in sorted(notes,key=lambda note:-note.pitch):onsets[note.start].append(note)
    lanes=defaultdict(list);unattached=defaultdict(list);rap={};timed={}
    for event in events(lyric_track(project,track)):
        kind=event.get('kind');tick=event['tick']
        verse,voice=event.get('verse',0),event.get('voice',0)
        if kind=='rap':
            left,right=max(origin,tick),min(end,tick+event['duration'])
            if left>=right:continue
            if (left,right) not in timed:timed[left,right]=Note(left-origin,right-left,60)
            note=timed[left,right]
        else:
            if not origin<=tick<end:continue
            choices=onsets.get(tick-origin,())
            if not choices:
                if event.get('text') and not event.get('skip'):unattached[tick-origin].append(event['text'])
                continue
            note=next((note for note in choices if note.pitch==event.get('pitch')),choices[min(voice,len(choices)-1)])
        if kind in ('rap','rap_note'):rap[note.id]=kind=='rap'
        lanes[verse,voice].append((note.id,event))
    attached=defaultdict(list)
    for (verse,_),lane in lanes.items():
        previous=None;extender=None;joining=False
        for ident,event in lane:
            spoken=event.get('kind') in ('rap','rap_note')
            if event.get('melisma') and previous is not None:
                previous['extend']='start'
                if extender is not None:extender['extend']='continue'
                extender=dict(verse=verse,text='',extend='stop',rap=spoken)
                attached[ident].append(extender)
            elif spoken and event.get('skip'):
                attached[ident].append(dict(verse=verse,text='',syllabic='single',rap=True))
            elif event.get('text') and not event.get('skip'):
                next_word=bool(event.get('join_next'))
                syllabic=('middle' if joining else 'begin') if next_word else ('end' if joining else 'single')
                previous=dict(verse=verse,text=event['text'],syllabic=syllabic,rap=spoken)
                attached[ident].append(previous)
                joining=next_word;extender=None
    return attached,unattached,rap,list(timed.values())


def _note_groups(notes):
    """Color overlapping intervals into persistent voices and align equal spans."""
    ends=[]
    ordered=sorted(notes,key=lambda note:(note.start,note.end,note.pitch))
    for (start,end),group in groupby(ordered,key=lambda note:(note.start,note.end)):
        index=next((index for index,stop in enumerate(ends) if stop<=start),len(ends))
        if index==len(ends):ends.append(end)
        else:ends[index]=end
        yield start,end,index+1,tuple(group)


def _groups_by_bar(notes,bars):
    groups=list(_note_groups(notes));cursor=0;active=[]
    for _,start,end in bars:
        active=[group for group in active if group[1]>start]
        while cursor<len(groups) and groups[cursor][0]<end:
            active.append(groups[cursor]);cursor+=1
        by_voice={1:[]}
        for group in active:by_voice.setdefault(group[2],[]).append(group)
        yield by_voice


def _write_voice(measure,voice,groups,a,b,keys,tones,lyrics,rap):
    cursor=a
    key_ticks=sorted(keys) if voice==1 else []

    def emit(start,end,notes=()):
        cuts=[start,*key_ticks[bisect_right(key_ticks,start):bisect_left(key_ticks,end)],end]
        for left,right in zip(cuts,cuts[1:]):
            if left==right:continue
            if voice==1 and left in keys:_key(_element(measure,'attributes'),keys[left])
            if notes:
                for index,note in enumerate(notes):_note(measure,note,voice,left,right,index>0,tones,lyrics,rap)
            else:_silence(measure,voice,right-left,left==a and right==b)

    for start,end,_,notes in groups:
        left,right=max(a,start),min(b,end)
        if cursor<left:emit(cursor,left)
        emit(left,right,notes);cursor=right
    if cursor<b:emit(cursor,b)


def _harmony_points(project,origin,end):
    points={}
    for chord in sorted(project.chords,key=lambda chord:chord.start):
        if chord.start>=end or chord.end<=origin:continue
        if chord.end<end:points[chord.end-origin]=None
        symbol=chord.display_symbol
        points[max(origin,chord.start)-origin]=chord if symbol is not None and not chord.empty else None
    previous=None
    for tick,chord in sorted(points.items()):
        if chord is not None or previous is not None:yield tick,chord
        previous=chord


def _harmony(measure,project,chord,tick,offset):
    node=_element(measure,'harmony',**({'print-object':'no'} if chord is None else {}))
    if chord is None:
        _element(_element(node,'root'),'root-step','C',text='')
        _element(node,'kind','none',text='N.C.')
    else:
        symbol=chord.display_symbol;context=project.context_at(tick)
        _pitch(node,'root',tone_for(symbol.root,context,chord))
        formula=QUALITY_RELATIONS[symbol.quality]
        kind=_KIND_BY_FORMULA.get(formula,'other')
        _element(node,'kind',kind,text=symbol.quality)
        if symbol.bass is not None:_pitch(node,'bass',tone_for(symbol.bass,context,chord))
        if kind=='other':
            for written in formula:
                degree=int(written.lstrip('b#'))
                item=_element(node,'degree',**{'print-object':'no'})
                _element(item,'degree-value',degree)
                # Added degrees use dominant reference intervals, including b7.
                _element(item,'degree-alter',written.count('#')-written.count('b')+int(degree==7))
                _element(item,'degree-type','add')
    if offset:_element(node,'offset',offset)


def _direction(measure,kind,text,offset=0,placement='above'):
    direction=_element(measure,'direction',placement=placement)
    _element(_element(direction,'direction-type'),kind,text)
    if offset:_element(direction,'offset',offset)


def _part_header(part_list,project,ident,role,channel,track):
    part=_element(part_list,'score-part',id=ident)
    misc=_element(_element(part,'identification'),'miscellaneous')
    _element(misc,'miscellaneous-field',role,name='lingfeng-role')
    name=project.melody_names[track] if track is not None else 'Chords'
    _element(part,'part-name',name)
    instrument=ident+'-I1'
    _element(_element(part,'score-instrument',id=instrument),'instrument-name',name)
    midi=_element(part,'midi-instrument',id=instrument)
    _element(midi,'midi-channel',channel+1)
    _element(midi,'midi-program',project.audio_for(role)['program']+1)
    _element(midi,'volume',f'{project.volume_for(role)*100/127:.8f}')


def _write_part(part,project,track,notes,bars,origin,end,contexts,first):
    starts=project.starts
    key_times=sorted(contexts)
    tones={}
    for note in notes:
        context=contexts[key_times[bisect_right(key_times,note.start)-1]]
        tone=tone_for(note.pitch,context)
        tones[note.id]=fallback(note.pitch,True) if note.flat and tone.alteration>0 else tone
    lyrics,words,rap,timed=_lyrics(project,track,notes,origin,end)
    words_at=sorted(words)
    harmony=dict(_harmony_points(project,origin,end)) if track is None else {}
    harmony_at=sorted(harmony)
    prior_meter=None
    for index,((bar,a,b),by_voice) in enumerate(zip(bars,_groups_by_bar(notes+timed,bars))):
        source=project.measures[bar];meter=(source.numerator,source.denominator)
        flags={'implicit':'yes'} if b-a!=source.ticks else {}
        measure=_element(part,'measure',number=index+1,**flags)
        if index and project.measures[bar-1].break_after:_element(measure,'print',**{'new-system':'yes'})
        if index==0 or a in contexts or meter!=prior_meter:
            attributes=_element(measure,'attributes')
            if index==0:_element(attributes,'divisions',PPQ)
            if a in contexts:_key(attributes,contexts[a])
            if meter!=prior_meter:
                time=_element(attributes,'time');_element(time,'beats',meter[0]);_element(time,'beat-type',meter[1])
            if index==0:
                clef=_element(attributes,'clef');_element(clef,'sign','F' if track is None else 'G');_element(clef,'line',4 if track is None else 2)
        prior_meter=meter
        if first and index==0:
            direction=_element(measure,'direction',placement='above')
            metronome=_element(_element(direction,'direction-type'),'metronome')
            _element(metronome,'beat-unit','quarter');_element(metronome,'per-minute',project.bpm)
            _element(direction,'sound',tempo=project.bpm)
        if first and source.section and a+origin==starts[bar]:_direction(measure,'rehearsal',source.section)
        for tick in words_at[bisect_left(words_at,a):bisect_left(words_at,b)]:
            for text in words[tick]:_direction(measure,'words',text,tick-a,'below')
        for tick in harmony_at[bisect_left(harmony_at,a):bisect_left(harmony_at,b)]:
            _harmony(measure,project,harmony[tick],tick+origin,tick-a)
        keys={tick:contexts[tick] for tick in key_times[bisect_right(key_times,a):bisect_left(key_times,b)]}
        for voice,groups in sorted(by_voice.items()):
            if voice>1:_element(_element(measure,'backup'),'duration',b-a)
            _write_voice(measure,voice,groups,a,b,keys,tones,lyrics,rap)


def _score(project,which,start,end):
    from lingfeng.audio.midi import selected_roles
    roles=selected_roles(which)
    project.validate()
    if not 0<=start<end<=project.end:
        raise ValueError(tr('导出范围无效。'))
    starts=project.starts
    first=bisect_right(starts,start)-1;stop=bisect_left(starts,end)
    bars=[(bar,max(starts[bar],start)-start,min(starts[bar+1],end)-start) for bar in range(first,stop)]
    contexts={0:project.context_at(start)}
    contexts.update((context.start-start,context) for context in sorted(project.contexts,key=lambda c:c.start) if start<context.start<end)
    score=ET.Element('score-partwise',version='4.0')
    _element(score,'movement-title',project.title)
    identification=_element(score,'identification')
    if project.author:_element(identification,'creator',project.author,type='composer')
    encoding=_element(identification,'encoding');_element(encoding,'software','Lingfeng')
    misc=_element(identification,'miscellaneous')
    _element(misc,'miscellaneous-field',json.dumps([[tick,c.tonic,c.mode] for tick,c in contexts.items()]),name='lingfeng-key-contexts')
    part_list=_element(score,'part-list')
    parts=[part for part in _PARTS if part[1] in roles]
    for index,(ident,role,channel,track) in enumerate(parts):
        _part_header(part_list,project,ident,role,channel,track)
        source=project.melody_notes(track) if track is not None else project.harmony_notes()
        part=_element(score,'part',id=ident)
        _write_part(part,project,track,window_notes(source,start,end),bars,start,end,contexts,index==0)
    return score


def _serialize(root):
    ET.indent(root)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)+b'\n'


def _compressed(xml):
    container=ET.Element('container')
    _element(_element(container,'rootfiles'),'rootfile',**{'full-path':'score.musicxml','media-type':_MIME+'+xml'})
    output=BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        archive.writestr(ZipInfo('mimetype'),_MIME,compress_type=ZIP_STORED)
        archive.writestr(ZipInfo('META-INF/container.xml'),_serialize(container),compress_type=ZIP_DEFLATED)
        archive.writestr(ZipInfo('score.musicxml'),xml,compress_type=ZIP_DEFLATED)
    return output.getvalue()


def export_musicxml(project,path=None,which='both',start=0,end=None):
    """Return exported bytes and atomically replace an optional target file."""
    target=Path(path) if path is not None else None
    data=_serialize(_score(project,which,start,project.end if end is None else end))
    if target is None:return data
    if target.suffix.lower()=='.mxl':data=_compressed(data)
    temporary=None
    try:
        with NamedTemporaryFile(dir=target.parent,prefix=target.name+'.',suffix='.tmp',delete=False) as file:
            temporary=Path(file.name)
            file.write(data)
        temporary.replace(target)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return data
