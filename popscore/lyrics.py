"""Lyrics bind to unique melodic onsets; explicit rap tokens own unpitched onsets."""
import bisect
import copy
import re
import unicodedata
from dataclasses import dataclass
from .model import uid
from .i18n import tr


@dataclass
class Token:
    text:str
    duration:int=0
    skip:bool=False
    join_next:bool=False
    rap:bool=False
    melisma:bool=False


def is_han(char):
    return any(a<=ord(char)<=b for a,b in ((0x3400,0x4dbf),(0x4e00,0x9fff),(0xf900,0xfaff),(0x20000,0x323af)))


def melody_onsets(project,start=0,end=None):
    """Unique MIDI starts, including starts inside another note's sustain."""
    end=project.end if end is None else end
    return sorted({n.start for n in project.notes if start<=n.start<end})


def tokenize(text,syntax_version=4):
    tokens=[];index=0;prefix='';quotes={'"':False,"'":False}
    opening='“‘（(「《【〔［[';closing='”’）)」》】〕］]'
    punctuation=''.join({c for c in text if unicodedata.category(c).startswith('P') and c not in '/_&{}|'})
    def apostrophe(at):
        return text[at] in ("'’" if syntax_version<3 else "'’-") and 0<at<len(text)-1 and all(c.isalnum() and not is_han(c) for c in (text[at-1],text[at+1]))
    while index<len(text):
        char=text[index]
        if char.isspace():index+=1;continue
        if text.startswith('/x{',index):
            end=text.find('}',index+3)
            if end<0 or '{' in text[index+3:end]:raise ValueError(tr('说唱请使用 {0}，花括号必须成对且不能嵌套。','/x{歌词}'))
            group=tokenize(text[index+3:end],syntax_version)
            if not group or any(t.duration for t in group):raise ValueError(tr('{0} 按现有音符起点匹配，请填写歌词，不要附加时值。','/x{歌词}'))
            first=next((t for t in group if not t.skip and t.text!='&'),None)
            if first is not None:first.text=prefix+first.text;prefix=''
            for token in group:token.rap=True
            tokens.extend(group);index=end+1;continue
        if char in '{}':raise ValueError(tr('说唱请使用 {0}，花括号必须成对且不能嵌套。','/x{歌词}'))
        ascii_open=char in quotes and not quotes[char] and (not tokens or (index+1<len(text) and not text[index+1].isspace() and text[index+1] not in closing+',.!?;:，。！？；：、…'))
        if char in opening or ascii_open:
            prefix+=char
            if char in quotes:quotes[char]=True
            index+=1;continue
        if char in punctuation and not (char=='-' and syntax_version<3):
            target=next((t for t in reversed(tokens) if not t.skip and t.text!='&'),None)
            if target:target.text+=char
            else:prefix+=char
            if char in quotes:quotes[char]=False
            index+=1;continue
        if text.startswith(('/-','/s'),index):token=Token('',skip=True,melisma=text.startswith('/-',index) and syntax_version>=4);index+=2
        elif char=='/':raise ValueError(tr('时值必须紧跟歌词，例如 我/64.爱/64你/64。'))
        elif char=='&':token=Token('&');index+=1
        elif char=='_' or char=='-' and syntax_version<3:token=Token('',skip=True);index+=1
        elif is_han(char):token=Token(char);index+=1
        else:
            start=index
            while index<len(text) and not text[index].isspace() and (text[index] not in '-_/&{}'+punctuation or apostrophe(index)) and not is_han(text[index]):index+=1
            token=Token(text[start:index])
        if not token.skip and token.text!='&':token.text=prefix+token.text;prefix=''
        if index<len(text) and text[index]=='/' and not text.startswith(('/x{','/-','/s'),index):
            match=re.match(r'/([0-9]+)(\.)?',text[index:])
            if not match or token.skip:raise ValueError(tr('说唱时值无效；使用 /4、/8、/16、/32、/64、/128，可加附点。'))
            denominator=int(match.group(1))
            if denominator not in (1,2,4,8,16,32,64,128):raise ValueError(tr('说唱时值无效；使用 /4、/8、/16、/32、/64、/128，可加附点。'))
            token.duration=3840//denominator*(3 if match.group(2) else 2)//2;index+=len(match.group())
        tokens.append(token)
    return tokens


def format_tokens(tokens):
    """Compact Han text, word spaces only for adjacent non-Han lyric words."""
    out=[];rap=False;previous=None
    def word(token):return token and not token.skip and token.text!='&' and any(c.isalnum() for c in token.text) and not any(is_han(c) for c in token.text)
    for token in tokens:
        if token.rap!=rap:
            out.append('/x{' if token.rap else '}');rap=token.rap;previous=None
        if word(previous) and word(token):out.append(' ')
        value=('/-' if token.melisma else '/s') if token.skip else token.text
        if token.duration:
            value+=next((f'/{d}'+('.' if dot else '') for d in (1,2,4,8,16,32,64,128) for dot in (False,True) if 3840//d*(3 if dot else 2)//2==token.duration),'')
        out.append(value);previous=token
    if rap:out.append('}')
    return ''.join(out)


def bar_sources(text):
    """Newlines delimit bars, including inside a continuous rap group.

    Explicit pipes remain readable for older sources; their formatting newlines
    are whitespace. Bar-local rap fragments are closed only for parsing.
    """
    if '|' in text:return text.split('|')
    if '\n' not in text and '\r' not in text:return None
    parts=[];opened=False
    for line in re.split(r'\r\n?|\n',text):
        was_open=opened;index=0
        while index<len(line):
            if line.startswith('/x{',index):
                if opened:raise ValueError(tr('说唱请使用 {0}，花括号必须成对且不能嵌套。','/x{歌词}'))
                opened=True;index+=3;continue
            if line[index]=='}':opened=False
            index+=1
        parts.append(('/x{' if was_open else '')+line+('}' if opened else '') if line.strip() else '')
    if opened:raise ValueError(tr('说唱请使用 {0}，花括号必须成对且不能嵌套。','/x{歌词}'))
    return parts


def sections(project):
    result=copy.deepcopy(project.notation.get('lyric_sections',[]));saved=events(project)
    for item in result:
        # Old hyphens separated English syllables; underscores consumed onsets.
        # Convert only the editor source, leaving stored events and MIDI intact.
        if item.get('syntax_version',1)<2:item['text']=item['text'].replace('-',' ').replace('_','-')
    old=[e for e in saved if not e.get('section_id')]
    for verse in sorted({e.get('verse',0) for e in old}):
        items=sorted((e for e in old if e.get('verse',0)==verse),key=lambda e:e['tick'])
        result.append(dict(id=f'legacy:{verse}',start=items[0]['tick'],verse=verse,text=' '.join('-' if e.get('skip') else '/x{'+e['text']+'}' if e.get('kind')=='rap_note' else e['text']+(f"/{3840//e['duration']}" if e.get('kind')=='rap' and e.get('duration') and 3840%e['duration']==0 else '') for e in items)))
    for item in result:
        owned=[e for e in saved if belongs(e,item['id'])]
        first=project.measure_at(item['start']);end=item.get('end',max((e['tick']+max(1,e.get('duration',0)) for e in owned),default=item['start']+1))
        count=project.measure_at(min(project.end-1,end-1))-first+1
        text,valid=range_source(project,first,count,item['verse'],items=owned)
        if owned:item.update(text=text,syntax_version=4,autofill_valid=valid)
    return sorted(result,key=lambda s:(s['start'],s['verse']))


def bind(project,text,start,verse=0,section_id=None,grid=240):
    """Plan a complete edit without mutating the project on a failed match."""
    if not isinstance(start,int) or not 0<=start<project.end or not isinstance(verse,int) or not 0<=verse<32:
        raise ValueError(tr('歌词时间或内容无效。'))
    tokens=tokenize(text)
    if not tokens:raise ValueError(tr('请输入歌词，或使用“删除此段”移除歌词。'))
    onsets=melody_onsets(project);cursor=start;result=[];section_id=section_id or uid()
    for index,token in enumerate(tokens):
        if token.text=='&':raise ValueError(tr('请把 & 占位符替换为歌词，或用 /s 跳过。'))
        if token.duration:tick=cursor;cursor=tick+token.duration
        else:
            tick=next((t for t in onsets if t>=cursor),None)
            if tick is None:raise ValueError(tr('第 {0} 个字／音节“{1}”没有可匹配的音符起点。请调整歌词、补充音符，或为说唱标注时值。',index+1,token.text or '-'))
            cursor=next((t for t in onsets if t>tick),tick+grid)
        pitch=next((n.pitch for n in project.notes if n.start==tick),project.context_at(min(tick,project.end-1)).tonic)
        if token.melisma and not any(t<tick for t in onsets):raise ValueError(tr('连音标记 /- 前没有可连接的旋律起点；请使用 /s 跳过。'))
        result.append(dict(id=uid(),section_id=section_id,tick=tick,text=token.text,verse=verse,voice=0,pitch=pitch,
                           kind='rap' if token.duration else 'rap_note' if token.rap else 'skip' if token.skip else 'note',duration=token.duration,skip=token.skip,join_next=token.join_next))
        if token.melisma:result[-1]['melisma']=True
    others=[e for e in events(project) if not belongs(e,section_id)]
    if any(e.get('verse',0)==verse and e['tick'] in {r['tick'] for r in result} for e in others):
        raise ValueError(tr('此段与已有歌词使用同一段次、同一起点。请选择已有段落修改，或更改歌词段次。'))
    return result


def belongs(event,section_id):
    return event.get('section_id')==section_id or (section_id==f"legacy:{event.get('verse',0)}" and not event.get('section_id'))


def apply_section(project,text,start,verse=0,section_id=None,grid=240):
    section_id=section_id or uid();planned=bind(project,text,start,verse,section_id,grid)
    from .midi_import import _extend
    _extend(project,max(e['tick']+max(1,e.get('duration',0)) for e in planned))
    detach(project)
    project.notation['lyric_events']=[e for e in project.notation['lyric_events'] if not belongs(e,section_id)]+planned
    project.notation['lyric_sections']=[s for s in project.notation.get('lyric_sections',[]) if s['id']!=section_id]+[dict(id=section_id,start=start,verse=verse,text=text,syntax_version=4)]
    return section_id


def delete_section(project,section_id):
    detach(project)
    project.notation['lyric_events']=[e for e in project.notation['lyric_events'] if not belongs(e,section_id)]
    project.notation['lyric_sections']=[s for s in project.notation.get('lyric_sections',[]) if s['id']!=section_id]


@dataclass
class RangePlan:
    events:list
    issues:list
    start:int
    end:int


def plan_range(project,text,first,count,verse=0,section_id=None,grid=240,replace=False):
    """Bounded partial entry; unfilled template slots consume onsets but aren't saved."""
    if not 0<=first<first+count<=len(project.measures) or not 0<=verse<32:
        raise ValueError(tr('歌词小节范围无效。'))
    start,end=project.starts[first],project.starts[first+count];planned=[];issues=[];section_id=section_id or uid()
    try:parts=bar_sources(text)
    except ValueError as exc:return RangePlan([], [str(exc)], start,end)
    if parts is not None:
        while len(parts)>count and not parts[-1].strip():parts.pop()
        if len(parts)>count:issues.append(tr('每行一个小节，最多 {0} 行，目前为 {1} 行。',count,len(parts)))
        groups=[(part,*project.starts[first+i:first+i+2]) for i,part in enumerate(parts[:count])]
    else:groups=[(text,start,end)]
    onsets=melody_onsets(project,start,end)
    for part,a,b in groups:
        try:tokens=tokenize(part)
        except ValueError as exc:issues.append(str(exc));continue
        cursor=a;within=[t for t in onsets if a<=t<b]
        for index,token in enumerate(tokens):
            if token.duration:tick=cursor;cursor+=token.duration
            else:
                tick=next((t for t in within if t>=cursor),None)
                if tick is None:
                    issues.append(tr('第 {0} 小节起，第 {1} 个字／音节“{2}”超出可用起点。',project.measure_at(a)+1,index+1,token.text or '-'));continue
                cursor=next((t for t in within if t>tick),tick+grid)
            if tick>=b or (token.duration and tick+token.duration>b):
                issues.append(tr('说唱“{0}”超出所选小节范围。请缩短时值或增加小节数量。',token.text));continue
            if token.melisma and not any(n.start<tick for n in project.notes):
                issues.append(tr('连音标记 /- 前没有可连接的旋律起点；请使用 /s 跳过。'));continue
            planned.append(dict(id=uid(),section_id=section_id,tick=tick,text=token.text,verse=verse,voice=0,
                pitch=next((n.pitch for n in project.notes if n.start==tick),project.context_at(tick).tonic),
                kind='pending' if token.text=='&' else 'rap' if token.duration else 'rap_note' if token.rap else 'skip' if token.skip else 'note',duration=token.duration,skip=token.skip,join_next=token.join_next))
            if token.melisma:planned[-1]['melisma']=True
    if not any(e['kind']!='pending' for e in planned) and not issues:issues.append(tr('请输入歌词、/s 或 /-；未填写的 & 不会保存。'))
    others=[] if replace else [e for e in events(project) if not belongs(e,section_id)]
    assigned={e['tick'] for e in planned if e['kind']!='pending'}
    if any(e.get('verse',0)==verse and e['tick'] in assigned for e in others):issues.append(tr('此段与已有歌词使用同一段次、同一起点。请选择已有段落修改，或更改歌词段次。'))
    return RangePlan(planned,issues,start,end)


def apply_range(project,text,first,count,verse=0,section_id=None,grid=240,replace=False):
    section_id=section_id or uid();plan=plan_range(project,text,first,count,verse,section_id,grid,replace)
    if plan.issues:raise ValueError('\n'.join(plan.issues))
    if replace and any(belongs(e,section_id) and not (e.get('verse',0)==verse and plan.start<=e['tick']<plan.end) for e in events(project)):
        section_id=uid()
        for event in plan.events:event['section_id']=section_id
    detach(project)
    if replace:delete_range(project,first,count,verse,grid)
    project.notation['lyric_events']=[e for e in project.notation['lyric_events'] if not belongs(e,section_id)]+[e for e in plan.events if e['kind']!='pending']
    project.notation['lyric_sections']=[s for s in project.notation.get('lyric_sections',[]) if s['id']!=section_id]+[dict(id=section_id,start=plan.start,end=plan.end,verse=verse,text=text,syntax_version=4)]
    return section_id


def range_source(project,first,count,verse=0,grid=240,items=None):
    """Reconstruct input at its saved onsets, with placeholders in empty slots.

    Return whether parsing this source preserves the stored assignments. Legacy
    orphan words/overlapping timed rap remain visible but require explicit review.
    """
    start,end=project.starts[first],project.starts[first+count]
    saved=[e for e in (events(project) if items is None else items) if e.get('verse',0)==verse and start<=e['tick']<end]
    if not saved:return '',True
    parts=[]
    for bar in range(first,first+count):
        a,b=project.starts[bar:bar+2];onsets=melody_onsets(project,a,b)
        by_tick={}
        for event in saved:
            if a<=event['tick']<b:by_tick.setdefault(event['tick'],[]).append(event)
        words=[];cursor=a
        for tick in sorted(set(onsets)|set(by_tick)):
            if tick<cursor and tick not in by_tick:continue
            if tick not in by_tick:
                words.append(Token('&'));cursor=next((t for t in onsets if t>tick),tick+grid);continue
            for event in by_tick[tick]:
                token=Token(event['text'],skip=bool(event.get('skip')),rap=event.get('kind')=='rap_note',melisma=bool(event.get('melisma')))
                if event.get('kind')=='rap':
                    duration=event.get('duration',0)
                    token.duration=duration;cursor=tick+duration
                else:cursor=next((t for t in onsets if t>tick),tick+grid)
                words.append(token)
        while words and words[-1].text=='&':words.pop()
        parts.append(format_tokens(words))
    text='\n'.join(parts).replace('}\n/x{','\n')
    plan=plan_range(project,text,first,count,verse,grid=grid,replace=True)
    def signature(event):
        return (event['tick'],event['text'],event.get('kind') or ('skip' if event.get('skip') else 'note'),event.get('duration',0),bool(event.get('skip')),bool(event.get('melisma')))
    equivalent=not plan.issues and sorted(signature(e) for e in saved)==sorted(signature(e) for e in plan.events if e['kind']!='pending')
    return text,equivalent


def delete_range(project,first,count,verse=0,grid=240):
    """Remove only the selected stanza/range; retain section fragments outside it."""
    if not 0<=first<first+count<=len(project.measures) or not 0<=verse<32:raise ValueError(tr('歌词小节范围无效。'))
    start,end=project.starts[first],project.starts[first+count];detach(project)
    removed=[e for e in project.notation['lyric_events'] if e.get('verse',0)==verse and start<=e['tick']<end]
    affected={e.get('section_id') for e in removed}
    project.notation['lyric_events']=[e for e in project.notation['lyric_events'] if not (e.get('verse',0)==verse and start<=e['tick']<end)]
    rebuilt=[]
    for section in project.notation.get('lyric_sections',[]):
        if section['id'] not in affected:rebuilt.append(section);continue
        remaining=[e for e in project.notation['lyric_events'] if belongs(e,section['id'])]
        if not remaining:continue
        first_bar=project.measure_at(min(e['tick'] for e in remaining))
        last_tick=max(e['tick']+max(1,e.get('duration',0)) for e in remaining)
        last_bar=project.measure_at(min(project.end-1,last_tick-1))
        text,_=range_source(project,first_bar,last_bar-first_bar+1,section['verse'],grid,remaining)
        rebuilt.append(dict(section,start=project.starts[first_bar],end=project.starts[last_bar+1],text=text,syntax_version=4))
    project.notation['lyric_sections']=rebuilt


def matching_issues(project):
    onsets=set(melody_onsets(project));occupied=set();issues=[]
    for event in events(project):
        key=(event['tick'],event.get('verse',0))
        if key in occupied:issues.append(tr('第 {0:g} 拍的同一段歌词重复匹配。',event['tick']/960+1))
        occupied.add(key)
        if event.get('kind')=='rap':continue
        if event.get('melisma') and not any(t<event['tick'] for t in onsets):issues.append(tr('连音标记 /- 前没有可连接的旋律起点；请使用 /s 跳过。'))
        if event['tick'] not in onsets:
            issues.append(tr('第 {0:g} 拍的“{1}”没有音符起点。',event['tick']/960+1,event['text'] or '-'))
        try:tokens=tokenize(event['text'])
        except ValueError as exc:issues.append(str(exc));continue
        if len(tokens)>1 or any(t.duration or t.skip or t.text=='&' for t in tokens):
            issues.append(tr('“{0}”需要拆分并重新匹配。',event['text']))
    return issues


def events(project):
    result=copy.deepcopy(project.notation.get('lyric_events',[]))
    occupied={(e['tick'],e.get('verse',0),e.get('voice',0)) for e in result}
    voices={}
    for note in sorted(project.notes,key=lambda n:(n.start,-n.pitch)):
        if not note.lyric:continue
        voice=voices.get(note.start,0);voices[note.start]=voice+1
        if (note.start,0,voice) not in occupied:
            result.append(dict(id=note.id,tick=note.start,text=note.lyric,verse=0,voice=voice,pitch=note.pitch))
    for event in result:
        if event.get('text','').strip() in ('_','-','/-','/s'):event.update(text='',skip=True)
    return sorted(result,key=lambda e:(e['tick'],e.get('voice',0),e.get('verse',0)))


def detach(project):
    project.notation['lyric_events']=events(project)
    for note in project.notes:note.lyric=''


def put(project,tick,text,verse=0,voice=0,pitch=None):
    detach(project)
    old=next((e for e in project.notation['lyric_events'] if (e['tick'],e.get('verse',0),e.get('voice',0))==(tick,verse,voice)),None)
    if old:project.notation['lyric_events'].remove(old)
    if text:
        if pitch is None:
            prior=[n for n in project.notes if n.start<=tick]
            reference=max(prior,key=lambda n:n.start) if prior else min(project.notes,key=lambda n:n.start,default=None)
            pitch=reference.pitch if reference else project.context_at(tick).tonic
        project.notation['lyric_events'].append(dict(id=old['id'] if old else uid(),tick=int(tick),text=text,verse=verse,voice=voice,pitch=pitch or project.context_at(tick).tonic))


def display_events(project,compressions):
    result=events(project)
    for item in compressions:
        a,b=project.starts[item['hidden_start']],project.starts[item['hidden_end']]
        target=project.starts[item['start']]
        # One new stanza across the entire repeated section, including orphan words.
        offset=1+max((e.get('verse',0) for e in result if target<=e['tick']<target+b-a),default=-1)
        for event in result:
            if a<=event['tick']<b:
                event['tick']=target+event['tick']-a;event['verse']=event.get('verse',0)+offset
    return result


def validate(project):
    sections=project.notation.get('lyric_sections',[])
    if not isinstance(sections,list):raise ValueError(tr('歌词时间或内容无效。'))
    ids=set()
    for section in sections:
        if not isinstance(section,dict) or not isinstance(section.get('id'),str) or section['id'] in ids or not isinstance(section.get('text'),str) or not isinstance(section.get('start'),int) or not 0<=section['start']<project.end or not isinstance(section.get('verse'),int) or not 0<=section['verse']<32:
            raise ValueError(tr('歌词时间或内容无效。'))
        ids.add(section['id'])
        if type(section.get('syntax_version',1)) is not int or section.get('syntax_version',1) not in (1,2,3,4):raise ValueError(tr('歌词时间或内容无效。'))
        if 'end' in section and (not isinstance(section['end'],int) or not section['start']<section['end']<=project.end):raise ValueError(tr('歌词小节范围无效。'))
    for e in project.notation.get('lyric_events',[]):
        if not isinstance(e,dict) or not isinstance(e.get('id'),str) or not isinstance(e.get('text'),str) or not isinstance(e.get('tick'),int) or not 0<=e['tick']<project.end:
            raise ValueError('歌词时间或内容无效。')
        if any(not isinstance(e.get(k,0),int) or not 0<=e.get(k,0)<32 for k in ('verse','voice')) or not 21<=e.get('pitch',60)<=108:
            raise ValueError('歌词声部或音高无效。')
        if e.get('kind')=='rap' and (not isinstance(e.get('duration'),int) or e['duration']<=0 or e['tick']+e['duration']>project.end):
            raise ValueError(tr('说唱节奏的时值或范围无效。'))
        if e.get('kind')=='rap_note' and e.get('duration',0)!=0:raise ValueError(tr('说唱节奏的时值或范围无效。'))
        if type(e.get('melisma',False)) is not bool or (e.get('melisma') and (not e.get('skip') or e['text'] or e.get('duration',0))):raise ValueError(tr('歌词时间或内容无效。'))


def melisma_links(project,lyric_events=None):
    """One display-only link from the immediately preceding MIDI onset."""
    items=events(project) if lyric_events is None else lyric_events
    notes={}
    for note in project.notes:notes.setdefault(note.start,[]).append(note)
    ticks=sorted(notes);by_verse={(e['tick'],e.get('verse',0)):e for e in items};links={}
    for event in items:
        if not event.get('melisma') or event['tick'] not in notes:continue
        i=bisect.bisect_left(ticks,event['tick'])
        if i==0:continue
        a,b=ticks[i-1:i+1]
        previous=by_verse.get((a,event.get('verse',0)),{})
        left=next((n for n in notes[a] if n.pitch==previous.get('pitch')),notes[a][0])
        right=next((n for n in notes[b] if n.pitch==event.get('pitch')),notes[b][0])
        links[(left.id,right.id)]=(a,b,left.id,right.id)
    return list(links.values())
