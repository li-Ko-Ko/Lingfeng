"""Symbol-first score structure drafts; performed music is never rewritten."""

import copy

from lingfeng.music.model import uid

from lingfeng.engraving.presentation import contiguous, pair_candidate, same_segment, annotation_allowed, add_annotation

from lingfeng.platform.i18n import tr

KINDS=[('repeat','反复记号'),('dc','D.C. al Fine'),('ds','D.S. al Fine'),('dc_nr','D.C. N/R al Fine'),('ds_nr','D.S. N/R al Fine'),('jump_coda','尾声跳转（A–B–A′–C）'),('barline','小节线'),('double_bar','双小节线'),('final_bar','结束线'),('segno','Segno（反复起点）'),('coda','Coda（尾声）'),('fine','Fine（结束）'),('fade','F.O.（渐弱结束）'),('rit','rit.（渐慢）'),('adlib','ad lib.（自由演奏）')]

REPEATS={'repeat','dc','ds','dc_nr','ds_nr','jump_coda'}

def region_count(kind):return 4 if kind=='jump_coda' else 2 if kind in REPEATS else 1

def draft_candidate(project,draft):
    """Return a verified presentation record or a user-facing reason."""
    kind=draft['kind'];regions=draft['regions']
    if len(regions)!=region_count(kind) or any(not r for r in regions):return None,tr('请先为此符号记录全部区域。')
    if kind in REPEATS:
        bars=[r.get('bars',[]) for r in regions]
        if any(not contiguous(b) or not all(0<=i<len(project.measures) for i in b) for b in bars):return None,tr('每个区域必须是连续的完整小节。')
        if any(max(a)+1!=min(b) for a,b in zip(bars,bars[1:])):return None,tr('区域必须按演奏顺序相邻，不能重叠或留空。')
        if kind=='jump_coda':
            a,b,c,d=(sorted(x) for x in bars)
            if len(a)!=len(c) or not same_segment(project,a[0],a[-1]+1,c[0],c[-1]+1):return None,tr('A 与 A′ 的音乐必须一致；歌词可以不同。')
            item=dict(kind='coda',start=a[0],first_end=a[-1]+1,hidden_start=c[0],hidden_end=c[-1]+1,end=d[-1]+1)
        else:
            item=pair_candidate(project,bars[0],bars[1],kind)
            if item is None:return None,tr('两区须等长且音乐一致；D.C. 从曲首开始，al Fine 须结束演奏。')
        if any(item['start']<x['end'] and x['start']<item['end'] for x in project.notation.get('compressions',[])):return None,tr('此区域已有反复逻辑，请先删除重叠符号。')
        return ('compressions',item),tr('检查通过，可应用到谱面；播放与 MIDI 保持不变。')
    ranges=regions[0].get('ranges',[])
    if len(ranges)!=1 or not annotation_allowed(project,kind,*ranges[0]):return None,tr('当前小节或拍选区不符合此符号的位置要求。')
    a,b=ranges[0];return ('symbols',dict(kind=kind,start=a,end=b)),tr('检查通过，可应用到谱面；播放与 MIDI 保持不变。')

def apply_draft(project,draft):
    candidate,reason=draft_candidate(project,draft)
    if candidate is None:raise ValueError(reason)
    collection,item=candidate
    if collection=='symbols':add_annotation(project,item['kind'],item['start'],item['end'])
    else:project.notation.setdefault(collection,[]).append(copy.deepcopy(item))
    return collection,project.notation[collection].index(item)
