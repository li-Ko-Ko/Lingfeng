"""Shared vector layout for screen and PDF. No piano-roll range enters layout."""
from __future__ import annotations
from dataclasses import dataclass,field
from pathlib import Path
import math
import copy
import bisect
from PySide6.QtCore import Qt, QRectF, QPointF, QMarginsF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QPainterPath, QPdfWriter, QPageSize, QPageLayout,QTransform
from lingfeng.music.model import PPQ, MODES, Note, spelling, pitch_name
from lingfeng.ui.fonts import ensure_fonts
from lingfeng.ui.theme import color as theme_color
from lingfeng.engraving.presentation import visible_bars, active_compressions, annotation_allowed, lyric_verses

INK = QColor('#263345')
MUTED = QColor('#8692A2')
CHROMATIC = QColor('#BC6542')
PAPER_W, PAPER_H = 900, 1273
MARGIN = 52
GRID_LINE='#C9D5E3'
ANCHOR_LINE='#9AAEC6'
BEAT_LINE='#D2DCE8'
# MIDI time-base conversions can leave a 1–2 tick remainder at PPQ 960.
# This tolerance only affects engraving; note timing and playback stay exact.
RHYTHM_TOLERANCE=2
RHYTHM_VALUES=(3840,2880,1920,1440,960,720,640,480,360,320,240,180,160,120,90,80,60,45,40,30)
TRADITIONAL_BEAT_GAP=.75
SYMBOL_PADDING=1.5


def is_chord_tone(project,pitch,tick):
    """Circles describe performed MIDI, never implied or omitted chord tones."""
    chord=project.chord_at(tick)
    return bool(chord and pitch%12 in {n.pitch%12 for n in chord.render_notes()})


@dataclass
class Fragment:
    start: int
    duration: int
    pitch: int | None
    note: object = None
    continuation: bool = False
    continues: bool = False
    lyric: str = ''
    rest_pitch: int | None = None
    ghost: bool = False
    display_duration: int | None = None
    source_ids: tuple = ()

    @property
    def end(self):
        return self.start + self.duration


def rhythm_parts(start, duration):
    result = []
    while duration:
        # Keep near-exact note values whole instead of creating a spurious tie
        # (for example 118 ticks becoming dotted 64th + 28 ticks).
        if any(abs(duration-value)<=RHYTHM_TOLERANCE for value in RHYTHM_VALUES):
            result.append((start,duration));break
        # Preserve simple offbeat syncopation; nonstandard remainders remain exact.
        length = next((v for v in RHYTHM_VALUES if v <= duration), duration)
        result.append((start, length)); start += length; duration -= length
    return result


def fragments_for_bar(project,index,lyrics=None,adjustments=()):
    start,end=project.starts[index:index+2];notes=sorted((n for n in project.notes if n.start<end and n.end>start),key=lambda n:n.start)
    pieces=[];coverage=[]
    rap_ticks={e['tick'] for e in lyrics or [] if e.get('kind')=='rap_note'}
    for note in notes:
        if note.start in rap_ticks:continue
        a,b=max(start,note.start),min(end,note.end);coverage.append((a,b))
        boundaries=sorted({a,b,*[c.start for c in project.contexts if a<c.start<b],
                           *[t for item in adjustments for t in item['tail'] if a<t<b]})
        for left,right in zip(boundaries,boundaries[1:]):
            for t,d in rhythm_parts(left,right-left):pieces.append(Fragment(t,d,note.pitch,note,t>note.start,t+d<note.end,note.lyric if t==note.start else ''))
    seen=set()
    for tick in sorted(rap_ticks):
        sources=[n for n in notes if n.start==tick]
        if not sources:continue
        a,b=max(start,tick),min(end,max(n.end for n in sources))
        coverage.append((a,b));seen.add((a,b))
        for t,d in rhythm_parts(a,b-a):pieces.append(Fragment(t,d,None,ghost=True,source_ids=tuple(n.id for n in sources)))
    for event in lyrics or []:
        if event.get('kind')!='rap':continue
        a,b=max(start,event['tick']),min(end,event['tick']+event['duration'])
        if b<=a or (a,b) in seen:continue
        seen.add((a,b));coverage.append((a,b))
        for t,d in rhythm_parts(a,b-a):pieces.append(Fragment(t,d,None,ghost=True))
    cursor=start;gaps=[]
    for a,b in sorted(coverage):
        if cursor<a:gaps.append((cursor,a))
        cursor=max(cursor,b)
    if cursor<end:gaps.append((cursor,end))
    beat=PPQ*4//project.measures[index].denominator
    for left,right in gaps:
        if right-left<=RHYTHM_TOLERANCE:continue
        # Long rests are repeated zeros, including the first beat of a bar.
        boundaries=sorted({left,right,*range(start+beat,end,beat)})
        boundaries=[t for t in boundaries if left<=t<=right]
        for a,b in zip(boundaries,boundaries[1:]):
            for t,d in rhythm_parts(a,b-a):
                prior=[n for n in notes if n.end<=t]
                pieces.append(Fragment(t,d,None,rest_pitch=max(prior,key=lambda n:(n.end,n.start,n.pitch)).pitch if prior else None))
    for f in pieces:
        if any((f.start,f.end)==item['tail'] for item in adjustments):f.display_duration=PPQ//2
    return sorted(pieces,key=lambda f:(f.start,f.pitch if f.pitch is not None else -1))


def rhythm_style(ticks):
    ticks=next((v for v in RHYTHM_VALUES if abs(ticks-v)<=RHYTHM_TOLERANCE),ticks)
    dotted = ticks in (2880,1440,720,360,180,90,45)
    base = ticks * 2 // 3 if dotted else ticks
    triplet = base in (640,320,160,80,40)
    if triplet:
        base = base * 3 // 2
    underlines = max(0, round(math.log2(PPQ/base))) if base < PPQ else 0
    dashes = max(0, base//PPQ-1)
    return underlines,dotted,triplet,dashes


def fragment_style(fragment):
    return rhythm_style(fragment.display_duration if fragment.display_duration is not None else fragment.duration)


def short_pair_adjustments(project,bar,fragments):
    """Borrow visual space from an adjacent dotted-eighth tail, never MIDI time.

    The pair is counted over the entire meter beat. Explicit sixteenths,
    additional thirty-seconds and overlapping attacks prevent this shorthand.
    A long note may supply the tail; engraving splits it at that boundary.
    """
    start,end=project.starts[bar:bar+2];beat=PPQ*4//project.measures[bar].denominator;result=[]
    notes=[n for n in project.notes if n.start<end and n.end>start]
    for left in range(start,end,beat):
        right=min(end,left+beat)
        inside=[n for n in notes if left<=n.start<right]
        pair=sorted((n for n in inside if n.duration==PPQ//8),key=lambda n:n.start)
        if len(pair)!=2 or pair[0].end!=pair[1].start or pair[1].end>right:continue
        if any(rhythm_style(n.duration)[0]==2 for n in notes if n.start<right and n.end>left):continue
        if any(f.note is None and rhythm_style(f.duration)[0] in (2,3) for f in fragments if left<=f.start<right):continue
        a,b,z=pair[0].start,pair[1].start,pair[1].end
        tail=None;knots=None
        spans=[(n.start,n.end) for n in notes]+[(f.start,f.end) for f in fragments if f.note is None and not f.ghost]
        # Prefer the preceding tail, including the last part of a sustained note.
        if a-3*PPQ//4>=left and any(s<=a-3*PPQ//4 and e==a for s,e in spans):
            tail=(a-3*PPQ//4,a);knots=[(tail[0],tail[0]),(a,a-PPQ//4),(b,b-PPQ//8),(z,z)]
        elif z+3*PPQ//4<=right and any(s==z and e>=z+3*PPQ//4 for s,e in spans):
            tail=(z,z+3*PPQ//4);knots=[(a,a),(b,b+PPQ//8),(z,z+PPQ//4),(tail[1],tail[1])]
        if tail is None:continue
        lo,hi=knots[0][0],knots[-1][0]
        if any(lo<n.start<hi and n not in pair and n.start!=tail[0] for n in notes):continue
        if any(lo<c.start<hi for c in project.contexts):continue
        result.append(dict(tail=tail,pair=(a,b),knots=knots))
    return result


@dataclass
class System:
    bars: list[int]
    fragments: dict
    pitches: list[int]
    top: float
    height: float
    page: int
    bar_widths: list[float]
    boundaries: list[int]=field(default_factory=list)
    tonic: int=48
    row_gap: float=18
    symbol_scale: float=1
    voices: dict=field(default_factory=dict)
    layout_scale: float=1
    extra_header: float=0
    grid_bottom: float=0
    lyric_rows: int=0
    verse_count: int=1
    context_height: float=0
    notation_clearance: float=0
    bar_scales: dict=field(default_factory=dict)
    lyric_gap: float=22
    lyric_offset: float=20
    note_baseline: float=60
    voice_gap: float=48
    left: float=MARGIN+40

    def pitch_position(self, pitch):
        pitches = self.pitches
        if len(pitches) < 2:
            return 0
        for i in range(len(pitches)-1):
            if pitch <= pitches[i+1]:
                return i + (pitch-pitches[i])/(pitches[i+1]-pitches[i])
        return len(pitches)-1 + (pitch-pitches[-1])/max(1,pitches[-1]-pitches[-2])


class ScoreLayout:
    def __init__(self, project):
        ensure_fonts()
        self.project = project
        self.systems = []
        self.hit_notes = []
        self.hit_bars = []
        self.hit_chords = []
        self.hit_times=[];self.hit_symbols=[];self.dark=False;self.tie_paths=[];self.rest_positions=[];self.symbol_marks=[];self.lyric_positions=[];self.symbol_boxes=[];self.unpitched_positions=[]
        self.pages = 1;self.glyph_scale=1;self.glyph_sizes=[];self.engraving_cache={};self.width_cache={};self.rhythm_adjustments={}
        self.build()

    def context_labels(self,bar):
        p=self.project;start,end=p.starts[bar:bar+2];labels={}
        for context in p.contexts:
            if not start<=context.start<end or context.start==0:continue
            previous=p.context_at(context.start-1)
            if (context.tonic,context.mode)!=(previous.tonic,previous.mode):
                labels[context.start]=f'1 = {pitch_name(context.tonic)} · {context.mode}'
        measure=p.measures[bar]
        if bar>0 and (measure.numerator,measure.denominator)!=(p.measures[bar-1].numerator,p.measures[bar-1].denominator):
            labels[start]=(labels.get(start,'')+'   '+f'{measure.numerator}/{measure.denominator}').strip()
        return sorted(labels.items())

    def build(self):
        p=self.project;per_line=p.notation['per_line'];style=p.notation['style']
        left=MARGIN if style=='traditional' else MARGIN+40
        i,page,y=0,0,140;available=PAPER_W-MARGIN-left
        visible=visible_bars(p);forced=dict(p.notation.get('forced_rows',[]));bases={(a,b):n for a,b,n in p.notation.get('forced_row_fonts',[])}
        compressions=active_compressions(p);self.compressions=compressions;self.verses=lyric_verses(p,compressions)
        from lingfeng.engraving.lyrics import display_events, melisma_links
        self.lyrics=display_events(p,compressions)
        self.melismas=melisma_links(p,self.lyrics);self.melisma_paths=[]
        self.melisma_notes={ident for _,_,left,right in self.melismas for ident in (left,right)}
        while i<len(visible):
            bars,fragments,widths=[],{},[]
            row_end=forced.get(visible[i]);forced_count=len([b for b in visible[i:] if b<row_end]) if row_end else 0
            limit=forced_count or per_line
            while i<len(visible) and len(bars)<limit:
                bar=visible[i]
                if bars and bar in forced:break
                frags=fragments_for_bar(p,bar,self.lyrics)
                adjustments=short_pair_adjustments(p,bar,frags);self.rhythm_adjustments[bar]=adjustments
                if adjustments:frags=fragments_for_bar(p,bar,self.lyrics,adjustments)
                # A bar is indivisible, including at explicit line and page breaks.
                bars.append(bar);fragments[bar]=frags;widths.append(1);i+=1
                if not forced_count and p.measures[bar].break_after:break
            notes=[f for bar in bars for f in fragments[bar] if f.pitch is not None]
            used=sorted({f.pitch for f in notes});tonic=p.context_at(p.starts[bars[0]]).tonic
            low,high=(used[0],used[-1]) if used else (tonic,tonic+7)
            anchors=sorted(tonic+12*octave+degree for octave in range(-12,13) for degree in (0,7))
            low=max(n for n in anchors if n<=low);high=min(n for n in anchors if n>=high)
            if low==high:high=next(n for n in anchors if n>high)
            boundaries=[n for n in anchors if low<=n<=high]
            contexts=[p.context_at(f.start) for f in notes] or [p.context_at(p.starts[bars[0]])]
            grid=[n for n in range(low,high+1) if any((n-c.tonic)%12 in MODES[c.mode] for c in contexts)]
            if style=='compact':
                grid=[f.pitch for f in notes if (f.pitch-p.context_at(f.start).tonic)%12 in MODES[p.context_at(f.start).mode]]
            grid=sorted(set(grid)|set(boundaries))
            # Stable independent lanes prevent simultaneous notes colliding in traditional notation.
            voices={};ends=[]
            originals=sorted({f.note.id:f.note for f in notes}.values(),key=lambda n:(n.start,-n.pitch))
            for note in originals:
                lane=next((j for j,end in enumerate(ends) if end<=note.start),len(ends))
                if lane==len(ends):ends.append(note.end)
                else:ends[lane]=note.end
                voices[note.id]=lane
            gap=p.notation['row_gap']
            height=100+max(0,len(ends)-1)*48 if style=='traditional' else (len(grid)-1)*gap+84
            row_lyrics=[e for e in self.lyrics if not e.get('skip') and e.get('text') and any(p.starts[b]<=e['tick']<p.starts[b+1] for b in bars)]
            verse_count=max((e.get('verse',0)+1 for e in row_lyrics),default=1)
            lyric_rows=verse_count*max((e.get('voice',0)+1 for e in row_lyrics),default=0) if p.notation['lyrics'] else 0
            lyric_height=lyric_rows*22
            upper=[a for a in p.notation.get('symbols',[]) if a['kind'] in ('segno','coda')]
            lower=[a for a in p.notation.get('symbols',[]) if a['kind'] in ('fine','fade','rit','adlib')]
            counts=[sum(1 for a in upper if p.starts[b]<=a['start']<p.starts[b+1]) for b in bars]
            header_scale=max(1,p.notation.get('font_size',15)/15)
            extra=max(counts,default=0)*20*header_scale
            if any(c['kind']!='repeat' and set(bars)&set(range(c['start'],c['end'])) for c in compressions):extra+=24
            context_height=max((len(self.context_labels(b)) for b in bars),default=0)*22*header_scale
            clearance=max(0,max((self.vertical_extents(f)[0] for f in notes),default=34)*p.notation.get('font_size',15)/15-30)
            extra+=context_height+clearance
            bottom_count=max((sum(1 for a in lower if p.starts[b]<=a['start']<p.starts[b+1]) for b in bars),default=0)
            if any(c['kind']!='repeat' and set(bars)&set(range(c['start'],c['end'])) for c in compressions):bottom_count+=2
            bottom_height=bottom_count*18*header_scale
            if height+extra+lyric_height+bottom_height>PAPER_H-240 and style!='traditional':
                gap=max(4,(PAPER_H-240-84-extra-lyric_height-bottom_height)/max(1,len(grid)-1));height=(len(grid)-1)*gap+84
            grid_bottom=height+extra+8
            height=grid_bottom+lyric_height+bottom_height+12
            layout_scale=1
            height*=layout_scale
            if y+height>PAPER_H-70 and y>76:
                page+=1;y=76
            scale=min(1,bases.get((bars[0],row_end),per_line)/len(bars)) if forced_count else 1
            weights=[self.minimum_bar_width(b,fragments[b]) for b in bars]
            widths=[available*w/sum(weights) for w in weights]
            system=System(bars,fragments,grid,y,height,page,widths,boundaries,tonic,gap,scale,voices,layout_scale,extra,grid_bottom,lyric_rows,verse_count)
            system.left=left
            system.context_height=context_height;system.notation_clearance=clearance
            self.systems.append(system);y+=height+p.notation.get('system_gap',12)
        self.pages=page+1
        # One safety limit for the entire score. Forced rows retain an explicit
        # ratio to this global size; neither individual bars nor glyphs shrink.
        limit=26/15
        for system in self.systems:
            ratio=system.symbol_scale
            limit=min(limit,available/sum(self.width_cache[b] for b in system.bars)/ratio)
            for bar in system.bars:
                notes=[f for f in system.fragments[bar] if f.pitch is not None]
                for i,f in enumerate(notes):
                    for g in notes[i+1:]:
                        if max(f.start,g.start)>=min(f.end,g.end) or f.pitch==g.pitch:continue
                        if style=='traditional':
                            dy=abs(system.voices[f.note.id]-system.voices[g.note.id])*48
                            upper,lower=(f,g) if system.voices[f.note.id]<system.voices[g.note.id] else (g,f)
                        else:
                            dy=abs(system.pitch_position(f.pitch)-system.pitch_position(g.pitch))*system.row_gap
                            upper,lower=(f,g) if f.pitch>g.pitch else (g,f)
                        needed=max(52,self.vertical_extents(upper)[1]+self.vertical_extents(lower)[0]+4)
                        limit=min(limit,dy/needed/ratio)
        self.max_font_size=15*limit
        # Expose a selectable limit instead of accepting larger values that
        # render identically. Sub-unit limits remain explicit for dense scores.
        self.font_limit=math.floor(self.max_font_size+1e-7) if self.max_font_size>=1 else math.floor(self.max_font_size*10000)/10000
        self.font_limit=max(.0001,min(26,self.font_limit))
        self.recommended_font_size=min(15,self.font_limit)
        self.font_size=max(.0001,min(round(p.notation.get('font_size',15),4),self.font_limit))
        self.glyph_scale=self.font_size/15
        page,y=0,140
        for system in self.systems:
            system.symbol_scale*=self.glyph_scale
            system.bar_scales={bar:system.symbol_scale for bar in system.bars}
            # Low octave dots/underlines and enlarged lyrics need real vertical
            # space too; leave pitch and polyphonic voice distances unchanged.
            notes=[f for fs in system.fragments.values() for f in fs if f.pitch is not None]
            if style=='traditional':
                last_voice=max(system.voices.values(),default=0)
                below=max((self.vertical_extents(f)[1]*system.symbol_scale-(last_voice-system.voices[f.note.id])*48 for f in notes),default=0)
                bottom_extra=max(0,below+6-48)
            else:
                below=max((self.vertical_extents(f)[1]*system.symbol_scale-system.pitch_position(f.pitch)*system.row_gap for f in notes),default=0)
                bottom_extra=max(0,below+6-32)
            system.lyric_gap=22*max(1,system.symbol_scale);system.lyric_offset=20*max(1,system.symbol_scale)
            if style=='traditional':
                scale=system.symbol_scale
                # Justify every row to the page margins. Extra space belongs
                # between beat groups, leaving the symbol cells compact.
                natural=[self.width_cache[b]*scale for b in system.bars]
                stretch=[max(1,self.beat_gap_count(b)) for b in system.bars]
                extra=max(0,available-sum(natural))
                system.bar_widths=[w+extra*g/sum(stretch) for w,g in zip(natural,stretch)]
                lower_band=system.height-system.grid_bottom-system.lyric_rows*22-12
                top=max((self.vertical_extents(f)[0] for f in notes),default=27)
                bottom=max((self.vertical_extents(f)[1] for f in notes),default=13)
                system.voice_gap=(top+bottom+6)*scale
                system.note_baseline=24+system.extra_header-system.notation_clearance+top*scale
                system.grid_bottom=system.note_baseline+last_voice*system.voice_gap+bottom*scale+3
                system.lyric_gap=max(14,17*scale);system.lyric_offset=system.lyric_gap
                system.height=system.grid_bottom+system.lyric_rows*system.lyric_gap+lower_band+7
            else:
                system.grid_bottom+=bottom_extra
                system.height+=bottom_extra+system.lyric_rows*(system.lyric_gap-22)
            page_start=140 if page==0 else 76
            if y>page_start and y+system.height>PAPER_H-70:
                page+=1;y=76
            system.top=y;system.page=page;y+=system.height+p.notation.get('system_gap',12)
        self.pages=page+1
        self.bar_symbol_scales={b:s.symbol_scale for s in self.systems for b in s.bars}

    def vertical_extents(self,f):
        octave=spelling(f.pitch,self.project.context_at(f.start).tonic,f.note.flat,mode=self.project.context_at(f.start).mode)[2] if f.note else 0
        under,_,triplet,_=fragment_style(f)
        top=max(27,24+max(0,octave-1)*4)
        if triplet:top=max(top,34+max(0,octave-1)*4)
        if f.continuation or f.continues or (f.note and f.note.id in self.melisma_notes) or self.melisma_notes.intersection(f.source_ids):top=max(top,37+max(0,octave)*4)
        bottom=max(13,11+max(0,under-1)*4+max(0,-octave)*4+2) if under else max(13,7+max(0,-octave-1)*4)
        return top,bottom

    @staticmethod
    def text_width(text,size,bold=False):
        font=QFont('Microsoft YaHei');font.setPixelSize(round(size*1.2))
        font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
        return QFontMetricsF(font).horizontalAdvance(text)

    def engraving_slots(self,bar,fragments):
        """Visible symbols own slots; duration endpoints and grid ticks do not."""
        if bar not in self.engraving_cache:
            p=self.project;start,end=p.starts[bar:bar+2]
            ticks={start,end,*[f.start for f in fragments]}
            for f in fragments:
                ticks.update(f.start+(k+1)*PPQ for k in range(fragment_style(f)[3]))
            ticks.update(e['tick'] for e in self.lyrics if start<=e['tick']<end)
            ticks.update(c.start for c in p.chords if start<c.start<end)
            self.engraving_cache[bar]=sorted(ticks)
        return self.engraving_cache[bar]

    def repeat_padding(self,bar):
        return (18 if any(c['kind']=='repeat' and c['start']==bar for c in self.compressions) else 0,
                26 if any(c['kind']=='repeat' and c['first_end']==bar+1 for c in self.compressions) else 0)

    def engraving_units(self,bar):
        """Equal symbol cells, with extra whitespace between meter-beat groups."""
        slots=self.engraving_cache[bar];start,end=self.project.starts[bar:bar+2]
        beat=PPQ*4//self.project.measures[bar].denominator;units=[0.]
        for a,b in zip(slots,slots[1:]):
            gap=TRADITIONAL_BEAT_GAP if b<end and (b-start)//beat>(a-start)//beat else 0
            units.append(units[-1]+1+gap)
        return units

    def traditional_cell(self,bar,tick,points,positions):
        slots=self.engraving_cache[bar];i=bisect.bisect_right(slots,tick)-1
        a=self.interpolate(points,positions,slots[i])
        return a,a+self.traditional_cell_width(bar)

    def traditional_cell_width(self,bar):
        return (self.width_cache[bar]-sum(self.repeat_padding(bar)))*self.bar_symbol_scales[bar]/self.engraving_units(bar)[-1]

    def beat_gap_count(self,bar):
        units=self.engraving_units(bar)
        return sum(b-a>1+1e-8 for a,b in zip(units,units[1:]))

    def column_extents(self,f):
        left,right=self.glyph_extents(f)
        if self.project.notation['lyrics']:
            width=max((self.text_width(e['text']+('-' if e.get('join_next') else ''),11)/2
                       for e in self.lyrics if e['tick']==f.start and not e.get('skip')),default=0)
            left=max(left,width);right=max(right,width)
        return left,right

    def minimum_bar_width(self,bar,fragments):
        """Required width at the common 15-point base, including annotations."""
        p=self.project;start,end=p.starts[bar:bar+2];traditional=p.notation['style']=='traditional'
        slots=self.engraving_slots(bar,fragments);leading,trailing=self.repeat_padding(bar)
        units=self.engraving_units(bar)
        def fraction(t):
            return self.interpolate(slots,units,t)/units[-1] if traditional else (self.spacing_tick(bar,t)-start)/(end-start)
        required=32.
        def reserve(a,b,width,symbol=False):
            nonlocal required
            span=1/units[-1] if traditional and symbol else max(1e-9,fraction(b)-fraction(a))
            if traditional:required=max(required,width/span+leading+trailing)
            else:required=max(required,(width+(leading if a==start else 0)+(trailing if b==end else 0))/span)
        for f in fragments:
            left,right=self.column_extents(f)
            last=slots[bisect.bisect_right(slots,f.start)] if traditional else min(f.end,f.start+PPQ)
            reserve(f.start,last,(2*max(left,right) if traditional else left+right)+SYMBOL_PADDING,True)
            for k in range(fragment_style(f)[3]):
                t=f.start+(k+1)*PPQ
                last=slots[bisect.bisect_right(slots,t)] if traditional else min(f.end,t+PPQ)
                reserve(t,last,36 if fragment_style(f)[1] and k==fragment_style(f)[3]-1 else 26,True)
        chords=[c for c in p.chords if c.start<end and c.end>start]
        from lingfeng.music.chord_operations import roman_label
        for i,c in enumerate(chords):
            last=min(end,c.end,chords[i+1].start if i+1<len(chords) else end)
            reserve(max(start,c.start),last,self.text_width(roman_label(p,c,c.flat),12,True)+8)
        if p.notation['lyrics']:
            events=[e for e in self.lyrics if start<=e['tick']<end and not e.get('skip')]
            for e in events:
                last=min((g['tick'] for g in events if g['tick']>e['tick'] and (g.get('verse',0),g.get('voice',0))==(e.get('verse',0),e.get('voice',0))),default=end)
                reserve(e['tick'],last,self.text_width(e['text']+('-' if e.get('join_next') else ''),11)+SYMBOL_PADDING,True)
        for _,label in self.context_labels(bar):required=max(required,self.text_width(label,8)+8+leading+trailing)
        for annotation in p.notation.get('symbols',[]):
            kind=annotation['kind']
            label={'fine':'Fine','fade':'F.O.','rit':'rit.','adlib':'ad lib.'}.get(kind)
            if label and start<=annotation['start']<end:
                reserve(annotation['start'],end,self.text_width(label,10,True)+8)
        for item in self.compressions:
            if item['kind']!='repeat' and bar in (item['first_end']-1,item['hidden_start']-1):
                required=max(required,self.text_width('D.S. N/R al Fine',10,True)+16)
        self.width_cache[bar]=required
        return required

    def glyph_cell(self,bar,f,points,positions,leading,trailing):
        if self.project.notation['style']=='traditional':
            return self.traditional_cell(bar,f.start,points,positions)
        start,end=self.project.starts[bar:bar+2];last=min(f.end,f.start+PPQ)
        a=self.interpolate(points,positions,f.start);b=self.interpolate(points,positions,last)
        return a+(leading if f.start==start else 0),b-(trailing if last==end else 0)

    def glyph_extents(self,f):
        accidental=spelling(f.pitch,self.project.context_at(f.start).tonic,f.note.flat,mode=self.project.context_at(f.start).mode)[1] if f.note else 0
        _,dotted,_,dashes=fragment_style(f)
        # A plain digit/underline needs 7 units, a chord-tone circle needs 11.
        # Use the actual envelope in every style rather than reserving a circle
        # around all spatial notes. The accidental starts at -17; the dot ends
        # at +14.4. Keep a small raster/vector clearance outside each mark.
        circled=f.pitch is not None and self.project.notation['circles'] and is_chord_tone(self.project,f.pitch,f.start)
        half=11 if circled else 7
        return (18 if accidental else half,15 if dotted and not dashes else half)

    def spacing_tick(self,bar,tick):
        for item in self.rhythm_adjustments.get(bar,()):
            knots=item['knots']
            if knots[0][0]<=tick<=knots[-1][0]:
                return self.interpolate([a for a,b in knots],[b for a,b in knots],tick)
        return tick

    def barline_bounds(self,system):
        if self.project.notation['style']=='traditional':
            baseline=system.top+system.note_baseline
            return baseline-18*system.symbol_scale,baseline+max(system.voices.values(),default=0)*system.voice_gap+12*system.symbol_scale
        return system.top+25,system.top+system.grid_bottom

    def time_slots(self,bar,fragments):
        p=self.project;start,end=p.starts[bar:bar+2]
        points=sorted({start,end,*range(start,end,PPQ),*[f.start for f in fragments],*[f.end for f in fragments],
                       *[t for f in fragments for t in range(f.start+PPQ,f.end,PPQ)],
                       *[e['tick'] for e in self.lyrics if start<e['tick']<end],
                       *[c.start for c in p.chords if start<c.start<end],*[c.start for c in p.contexts if start<c.start<end]})
        return points,[(b-a)/PPQ for a,b in zip(points,points[1:])]

    def bar_map(self,system,bar,x,width):
        points,_=self.time_slots(bar,system.fragments[bar])
        leading,trailing=(v*system.symbol_scale for v in self.repeat_padding(bar))
        if self.project.notation['style']=='traditional':
            slots=self.engraving_slots(bar,system.fragments[bar]);units=self.engraving_units(bar);unit=self.traditional_cell_width(bar)
            extra=max(0,width-leading-trailing-units[-1]*unit);gaps=self.beat_gap_count(bar);offset=0
            columns=[x+leading]
            for i,(a,b) in enumerate(zip(units,units[1:]),1):
                if b-a>1+1e-8:offset+=extra/gaps
                if not gaps and i==len(units)-1:offset=extra
                columns.append(x+leading+b*unit+offset)
            positions=[self.interpolate(slots,columns,t) for t in points]
            return points,positions,leading,trailing
        # Meter beats stay equal; the isolated short-pair shorthand warps only
        # its beat interior. Hit testing and the playhead use this same map.
        duration=points[-1]-points[0]
        positions=[x+width*(self.spacing_tick(bar,t)-points[0])/duration for t in points]
        return points,positions,leading,trailing

    @staticmethod
    def interpolate(points,positions,t):
        j=max(0,min(len(points)-2,bisect.bisect_right(points,t)-1));a,b=points[j:j+2]
        return positions[j]+(positions[j+1]-positions[j])*(t-a)/(b-a)

    def color(self,value):return theme_color(value,self.dark)

    def display_tick(self,tick):
        for item in self.compressions:
            if self.project.starts[item['hidden_start']]<=tick<self.project.starts[item['hidden_end']]:
                return self.project.starts[item['start']]+tick-self.project.starts[item['hidden_start']]
        return tick

    def time_position(self,tick):
        tick=self.display_tick(tick)
        for page,rect,bar,points,positions in self.hit_times:
            if points[0]<=tick<points[-1]:
                for i,(a,b) in enumerate(zip(points,points[1:])):
                    if a<=tick<=b:
                        x=positions[i]+(positions[i+1]-positions[i])*(tick-a)/(b-a)
                        system=next(s for s in self.systems if bar in s.bars)
                        return page,x,system.top+28*system.layout_scale,system.top+system.grid_bottom*system.layout_scale
        return None

    def draw_playhead(self,painter,page,tick,anchor=False):
        if tick is None:return
        position=self.time_position(tick)
        if position and position[0]==page:
            _,x,top,bottom=position;painter.setPen(QPen(self.color('#426BAA' if anchor else '#D15F49'),1.1 if anchor else 1.5,Qt.PenStyle.DashLine if anchor else Qt.PenStyle.SolidLine));painter.drawLine(QPointF(x,top),QPointF(x,bottom))

    def text(self,painter, x, y, text, size=13, color=INK, center=False, bold=False):
        font=QFont('Microsoft YaHei')
        font.setPixelSize(round(size*1.2))
        font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(self.color(color))
        width = painter.fontMetrics().horizontalAdvance(text)
        painter.drawText(QPointF(x-width/2 if center else x,y),text)

    def draw(self, painter, page, play_tick=None,dark=False):
        self.melisma_paths=[]
        self.dark=dark;self.tie_paths=[];self.rest_positions=[];self.symbol_marks=[];self.lyric_positions=[];self.symbol_boxes=[];self.unpitched_positions=[];self.glyph_sizes=[];p = self.project
        if play_tick is not None:
            for item in self.compressions:
                if p.starts[item['hidden_start']]<=play_tick<p.starts[item['hidden_end']]:
                    play_tick=p.starts[item['start']]+play_tick-p.starts[item['hidden_start']];break
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(QRectF(0,0,PAPER_W,PAPER_H),self.color('white'))
        if page == 0:
            self.text(painter,PAPER_W/2,65,p.title,23,center=True,bold=True)
            self.text(painter,PAPER_W/2,92,p.author,10,MUTED,center=True)
            c=p.context_at(0); m=p.measures[0]
            self.text(painter,MARGIN,120,f'1 = {pitch_name(c.tonic)}  ·  {c.mode}     {m.numerator}/{m.denominator}     ♩ = {p.bpm}',11)
        else:
            self.text(painter,MARGIN,44,p.title,11,MUTED)
        self.text(painter,PAPER_W/2,PAPER_H-32,str(page+1),10,MUTED,center=True)
        for system in self.systems:
            if system.page == page:
                self.draw_system(painter,system,play_tick)

    def draw_system(self, painter, system, play_tick=None):
        scale=system.layout_scale
        if scale==1:return self.draw_system_content(painter,system,play_tick)
        local=copy.copy(system);local.top=0;local.height=system.height/scale;local.bar_widths=[w/scale for w in system.bar_widths];local.symbol_scale=1
        transform=QTransform();left=system.left;transform.translate(left,system.top);transform.scale(scale,scale);transform.translate(-left,0)
        counts=[len(x) for x in (self.hit_notes,self.hit_bars,self.hit_chords,self.hit_times,self.tie_paths,self.rest_positions,self.symbol_marks,self.lyric_positions,self.hit_symbols)]
        melisma_count=len(self.melisma_paths)
        painter.save();painter.setTransform(transform,True);self.draw_system_content(painter,local,play_tick);painter.restore()
        for items,count in zip((self.hit_notes,self.hit_bars,self.hit_chords),counts[:3]):
            for i in range(count,len(items)):
                pg,r,key=items[i];items[i]=(pg,transform.mapRect(r),key)
        for i in range(counts[3],len(self.hit_times)):
            pg,r,b,ticks,positions=self.hit_times[i];self.hit_times[i]=(pg,transform.mapRect(r),b,ticks,[transform.map(QPointF(x,0)).x() for x in positions])
        for i in range(counts[4],len(self.tie_paths)):
            nid,kind,path=self.tie_paths[i];self.tie_paths[i]=(nid,kind,transform.map(path))
        for i in range(melisma_count,len(self.melisma_paths)):
            a,b,kind,path=self.melisma_paths[i];self.melisma_paths[i]=(a,b,kind,transform.map(path))
        for i in range(counts[5],len(self.rest_positions)):
            tick,pitch,x,y=self.rest_positions[i];point=transform.map(QPointF(x,y));self.rest_positions[i]=(tick,pitch,point.x(),point.y())
        for i in range(counts[6],len(self.symbol_marks)):
            kind,x,y=self.symbol_marks[i];point=transform.map(QPointF(x,y));self.symbol_marks[i]=(kind,point.x(),point.y())

        for i in range(counts[7],len(self.lyric_positions)):
            nid,verse,x,y=self.lyric_positions[i];point=transform.map(QPointF(x,y));self.lyric_positions[i]=(nid,verse,point.x(),point.y())

        for i in range(counts[8],len(self.hit_symbols)):
            pg,rect,key=self.hit_symbols[i];self.hit_symbols[i]=(pg,transform.mapRect(rect),key)

    def draw_bar_symbols(self,painter,system,bar,x,width,xpos):
        p=self.project;start,end=p.starts[bar:bar+2];y=system.top+43+system.context_height;upper_y=y;lower_y=system.top+system.grid_bottom+system.lyric_rows*system.lyric_gap+18
        def draw_mark(kind,px,text=None,right=False):
            self.symbol_marks.append((kind,px,y))
            if kind in ('barline','double_bar','final_bar','repeat_start','repeat_end'):
                top,bottom=self.barline_bounds(system)
                self.hit_symbols.append((system.page,QRectF(px-12,top-2,24,bottom-top+4),key))
                offsets=[(0,.8)] if kind=='barline' else [(-4,1),(0,3 if kind in ('final_bar','repeat_end') else 1)]
                if kind=='repeat_start':offsets=[(0,3),(4,1)]
                for dx,weight in offsets:
                    painter.setPen(QPen(self.color(INK),weight));painter.drawLine(QPointF(px+dx,top),QPointF(px+dx,bottom))
                if kind.startswith('repeat'):
                    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(self.color(INK));dx=(10 if kind=='repeat_start' else -10)*system.symbol_scale
                    for dy in (-4,4):painter.drawEllipse(QPointF(px+dx,(top+bottom)/2+dy*system.symbol_scale),1.8*system.symbol_scale,1.8*system.symbol_scale)
                return
            if kind in ('coda','segno'):self.hit_symbols.append((system.page,QRectF(px-12,y-23,24,30),key))
            if kind=='coda':
                painter.setPen(QPen(self.color(INK),1.3));painter.setBrush(Qt.BrushStyle.NoBrush);cy=y-6
                painter.drawEllipse(QPointF(px,cy),5.5,5.5);painter.drawLine(QPointF(px-9,cy),QPointF(px+9,cy));painter.drawLine(QPointF(px,cy-9),QPointF(px,cy+9));return
            if kind=='segno':
                self.text(painter,px,y,'S',15,center=True,bold=True);painter.setPen(QPen(self.color(INK),1.3));painter.drawLine(QPointF(px-7,y+1),QPointF(px+7,y-16))
                painter.setBrush(self.color(INK));painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(px-8,y-12),1.4,1.4);painter.drawEllipse(QPointF(px+8,y-3),1.4,1.4);return
            text=text or {'fine':'Fine','fade':'F.O.','rit':'rit.','adlib':'ad lib.'}.get(kind,kind)
            if right:
                font=QFont('Microsoft YaHei');font.setPixelSize(12);painter.setFont(font);px-=painter.fontMetrics().horizontalAdvance(text)
            self.hit_symbols.append((system.page,QRectF(px-4,y-17,max(28,len(text)*8+8),23),key))
            self.text(painter,px,y,text,10,bold=True)
        def mark(kind,px,text=None,right=False):
            if kind in ('barline','double_bar','final_bar','repeat_start','repeat_end'):return draw_mark(kind,px,text,right)
            transform=QTransform();transform.translate(px,y);transform.scale(system.symbol_scale,system.symbol_scale);transform.translate(-px,-y)
            first=len(self.hit_symbols)
            painter.save();painter.setTransform(transform,True);draw_mark(kind,px,text,right);painter.restore()
            for j in range(first,len(self.hit_symbols)):
                page,rect,key_=self.hit_symbols[j];self.hit_symbols[j]=(page,transform.mapRect(rect),key_)
        for index,item in enumerate(p.notation.get('symbols',[])):
            key=('symbols',index)
            if not annotation_allowed(p,item['kind'],item['start'],item['end']):continue
            kind=item['kind']
            if kind in ('barline','double_bar','final_bar') and item['end']==end:mark(kind,x+width)
            elif kind=='fine' and start<item['end']<=end:y=lower_y;mark(kind,min(x+width-7,xpos(item['end'])),right=True);lower_y+=18*max(1,system.symbol_scale)
            elif kind not in ('barline','double_bar','final_bar','fine') and start<=item['start']<end:
                y=upper_y if kind in ('segno','coda') else lower_y;mark(kind,xpos(item['start']))
                if kind in ('segno','coda'):upper_y+=20*max(1,system.symbol_scale)
                else:lower_y+=18*max(1,system.symbol_scale)
        for item in self.compressions:
            key=('compressions',p.notation.get('compressions',[]).index(item))
            kind=item['kind'];a,b,c,d=(item[k] for k in ('start','first_end','hidden_start','hidden_end'))
            y=upper_y
            if kind=='repeat':
                if bar==a:mark('repeat_start',x)
                if bar==b-1:mark('repeat_end',x+width)
            elif kind=='coda':
                if bar==a:mark('segno',x+16)
                if bar==b-1:y=lower_y;mark('to_coda',x+width-7,'To Coda',True)
                if bar==c-1:y=lower_y;mark('ds_coda',x+width-7,'D.S. al Coda',True)
                if bar==d:mark('coda',x+16)
            else:
                if kind.startswith('ds') and bar==a:mark('segno',x+16)
                if bar==b-1:
                    label=('D.C.' if kind.startswith('dc') else 'D.S.')+(' N/R' if kind.endswith('_nr') else '')+' al Fine'
                    y=lower_y;mark(kind,x+width-7,label,True);y+=18;mark('fine',x+width-7,'Fine',True)

    def draw_system_content(self, painter, system, play_tick=None):
        p=self.project;style=p.notation['style'];gap=system.row_gap;scale=system.symbol_scale
        baseline = system.top+(len(system.pitches)-1)*gap+60+system.extra_header
        if style=='traditional':
            baseline=system.top+system.note_baseline
        line_top,line_bottom=self.barline_bounds(system)
        x=system.left;tie_anchors={};slur_anchors={}
        if style!='traditional':
            for pitch in system.boundaries:
                gy=baseline-system.pitch_position(pitch)*gap
                degree,_,octave=spelling(pitch,system.tonic)
                self.text(painter,MARGIN+12,gy,str(degree),11,MUTED,center=True,bold=True)
                painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(self.color(MUTED))
                for dot in range(abs(octave)):
                    painter.drawEllipse(QPointF(MARGIN+12,gy-17-dot*3.5 if octave>0 else gy+5+dot*3.5),1.15,1.15)
        for bar,bw in zip(system.bars,system.bar_widths):
            start,end=p.starts[bar:bar+2]; measure=p.measures[bar]
            self.hit_bars.append((system.page,QRectF(x,system.top,bw,system.height),bar))
            self.text(painter,x+5,system.top-2,str(bar+1),9,MUTED)
            if measure.section:
                self.text(painter,x+28,system.top-2,measure.section,10,MUTED)
            painter.setPen(QPen(self.color('#A4ADBA'),.8))
            painter.drawLine(QPointF(x,line_top),QPointF(x,line_bottom))
            # Both styles share their engraving map with hit testing and playback.
            fragments=system.fragments[bar]
            points,positions,leading,trailing=self.bar_map(system,bar,x,bw)
            self.hit_times.append((system.page,QRectF(x,system.top,bw,system.height),bar,points,positions))
            def xpos(t):
                return self.interpolate(points,positions,t)
            # Bar/beat columns and scale rows form the light score background.
            if style!='traditional':
                context=p.context_at(start)
                painter.fillRect(QRectF(x,system.top+45,bw,system.grid_bottom-45),self.color('#F8FAFC'))
                for pitch in system.pitches:
                    if pitch in system.boundaries or (p.notation.get('show_scale_lines',False) and (pitch-context.tonic)%12 in MODES[context.mode]):
                        anchor=pitch in system.boundaries;painter.setPen(QPen(self.color(ANCHOR_LINE if anchor else GRID_LINE),1.05 if anchor else .75))
                        gy=baseline-system.pitch_position(pitch)*gap
                        painter.drawLine(QPointF(x,gy),QPointF(x+bw,gy))
            if style!='traditional':
                painter.setPen(QPen(self.color(BEAT_LINE),.7))
                for tick in range(start+PPQ*4//measure.denominator,end,PPQ*4//measure.denominator):
                    painter.drawLine(QPointF(xpos(tick),system.top+45),QPointF(xpos(tick),system.top+system.grid_bottom))
            painter.setPen(QPen(self.color('#A4ADBA'),.9));painter.drawLine(QPointF(x,line_top),QPointF(x,line_bottom))
            # Chord label and local key changes stay clear of melody octave dots.
            for chord in p.chords:
                if start<=chord.start<end or chord.start<start<chord.end:
                    t=max(start,chord.start)
                    from lingfeng.music.chord_operations import roman_label
                    label=roman_label(p,chord,chord.flat)
                    fit=scale;room=self.text_width(label,12,True)*fit
                    cx=xpos(t)+4*fit;cy=system.top+20+system.context_height
                    painter.save();painter.translate(cx,cy);painter.scale(fit,fit);self.text(painter,0,0,label,12,bold=True);painter.restore()
                    self.hit_chords.append((system.page,QRectF(cx,cy-18*fit,room,22*fit),chord.id))
            for index,(tick,label) in enumerate(self.context_labels(bar)):
                # A separate header band reserves space above octave dots and tuplets.
                label_y=system.top+20+index*22*max(1,scale)
                fit=scale
                painter.save();painter.translate(x+4,label_y);painter.scale(fit,fit)
                self.text(painter,0,0,label,8,MUTED);painter.restore()
            tuplets=[];lyric_anchors={}
            for f in fragments:
                accidental=spelling(f.pitch,p.context_at(f.start).tonic,f.note.flat,mode=p.context_at(f.start).mode)[1] if f.note else 0
                underline,dotted,triplet,dashes=fragment_style(f)
                left_extent,right_extent=self.glyph_extents(f)
                cell_left,cell_right=self.glyph_cell(bar,f,points,positions,leading,trailing)
                symbol_scale=system.bar_scales[bar]
                horizontal_scale=symbol_scale
                nx=(cell_left+cell_right)/2 if style=='traditional' else cell_left+(SYMBOL_PADDING/2+self.column_extents(f)[0])*horizontal_scale
                lyric_anchors.setdefault(f.start,nx)
                pitch=f.pitch
                center=baseline-(len(system.pitches)-1)*gap/2
                ny=baseline if style=='traditional' else center if pitch is None else baseline-system.pitch_position(pitch)*gap
                if style=='traditional' and f.note:ny+=system.voices[f.note.id]*system.voice_gap
                self.symbol_boxes.append((f.start,f.end,nx-left_extent*horizontal_scale,nx+right_extent*horizontal_scale,cell_left,cell_right))
                if pitch is None:self.unpitched_positions.append((f.start,'x' if f.ghost else '0',nx,ny))
                self.glyph_sizes.append(('x' if f.ghost else '0' if pitch is None else str(spelling(pitch,p.context_at(f.start).tonic,mode=p.context_at(f.start).mode)[0]),15*symbol_scale))
                painter.save();painter.translate(nx,ny);painter.scale(horizontal_scale,symbol_scale);painter.translate(-nx,-ny)
                if f.ghost:
                    self.text(painter,nx,ny,'x',15,center=True)
                    for ident in f.source_ids:
                        self.hit_notes.append((system.page,QRectF(nx-left_extent*horizontal_scale,ny-27*symbol_scale,(left_extent+right_extent)*horizontal_scale,52*symbol_scale),ident))
                        slur_anchors.setdefault((ident,f.start),(nx,ny-24*symbol_scale,INK))
                elif f.pitch is None:
                    self.text(painter,nx,ny,'0',15,MUTED,center=True)
                    self.rest_positions.append((f.start,f.rest_pitch,nx,ny))
                else:
                    context=p.context_at(f.start)
                    degree,accidental,octave=spelling(f.pitch,context.tonic,f.note.flat,mode=context.mode)
                    in_scale=(f.pitch-context.tonic)%12 in MODES[context.mode]
                    color=CHROMATIC if p.notation['color'] and not in_scale else INK
                    if p.notation['circles'] and is_chord_tone(p,f.pitch,f.start):
                        painter.setPen(QPen(self.color('#6B9C90'),.95));painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawEllipse(QPointF(nx,ny-6),10,12)
                    self.text(painter,nx,ny,str(degree),15,color,center=True)
                    if accidental:
                        self.text(painter,nx-17,ny,'♭' if accidental<0 else '♯',11,color)
                    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(self.color(color))
                    for k in range(abs(octave)):
                        painter.drawEllipse(QPointF(nx,ny-22-k*4 if octave>0 else ny+5+k*4),1.35,1.35)
                    tie_anchors.setdefault(f.note.id,[]).append((f,nx,ny-(24+max(0,octave)*4)*symbol_scale,color))
                    slur_anchors[(f.note.id,f.start)]=(nx,ny-(24+max(0,octave)*4)*symbol_scale,color)
                    self.hit_notes.append((system.page,QRectF(nx-left_extent*horizontal_scale,ny-27*symbol_scale,(left_extent+right_extent)*horizontal_scale,52*symbol_scale),f.note.id))
                for k in range(underline):
                    painter.setPen(QPen(self.color(INK),1))
                    uy=ny+11+k*4+(max(0,-spelling(f.pitch,p.context_at(f.start).tonic,mode=p.context_at(f.start).mode)[2])*4 if f.pitch is not None else 0)
                    painter.drawLine(QPointF(nx-5,uy),QPointF(nx+6,uy))
                dotx=nx+13
                for k in range(dashes):
                    tick=f.start+(k+1)*PPQ
                    if style=='traditional':
                        a,b=self.traditional_cell(bar,tick,points,positions);actual=(a+b)/2
                    else:actual=xpos(tick)+12.5*horizontal_scale
                    dx=nx+(actual-nx)/horizontal_scale
                    self.text(painter,dx,ny,'−',14,center=True);dotx=dx+12
                if dotted:
                    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(self.color(INK))
                    painter.drawEllipse(QPointF(dotx,ny-6),1.4,1.4)
                if triplet:
                    tuplets.append((nx,ny,f))
                painter.restore()
            if p.notation['lyrics']:
                for event in self.lyrics:
                    if not start<=event['tick']<end or event.get('skip') or not event.get('text'):continue
                    verse=event.get('verse',0);lane=event.get('voice',0)
                    ly=system.top+system.grid_bottom+system.lyric_offset+(lane*system.verse_count+verse)*system.lyric_gap
                    lx=lyric_anchors.get(event['tick'])
                    if lx is None:
                        if style=='traditional':
                            a,b=self.traditional_cell(bar,event['tick'],points,positions);lx=(a+b)/2
                        else:lx=xpos(event['tick'])+(SYMBOL_PADDING/2+self.text_width(event['text'],11)/2)*scale+(leading if event['tick']==start else 0)
                    painter.save();painter.translate(lx,ly);painter.scale(scale,scale)
                    self.text(painter,0,0,event['text']+('-' if event.get('join_next') else ''),11,center=True);painter.restore()
                    self.lyric_positions.append((event['id'],verse,lx,ly))
            # Group consecutive equal tuplets in threes; mark incomplete groups too.
            k=0
            while k<len(tuplets):
                group=[tuplets[k]]
                while k+len(group)<len(tuplets) and len(group)<3:
                    other=tuplets[k+len(group)]
                    if other[2].start!=group[-1][2].end or other[2].duration!=group[0][2].duration:
                        break
                    group.append(other)
                a=max(xpos(group[0][2].start)+1,group[0][0]-7)
                b=min(xpos(group[-1][2].end)-1,group[-1][0]+7)
                y=min(ny-(34+max(0,spelling(f.pitch,p.context_at(f.start).tonic,f.note.flat,mode=p.context_at(f.start).mode)[2]-1)*4 if f.note else 34)*system.bar_scales[bar] for nx,ny,f in group)
                ts=scale
                painter.setPen(QPen(self.color(MUTED),.8*ts))
                painter.drawLine(QPointF(a,y),QPointF(b,y))
                painter.drawLine(QPointF(a,y),QPointF(a,y+4*ts));painter.drawLine(QPointF(b,y),QPointF(b,y+4*ts))
                painter.fillRect(QRectF((a+b)/2-6*ts,y-8*ts,12*ts,12*ts),self.color('white'))
                painter.save();painter.translate((a+b)/2,y+3*ts);painter.scale(ts,ts)
                self.text(painter,0,0,'3',9,center=True);painter.restore()
                k+=len(group)
            self.draw_bar_symbols(painter,system,bar,x,bw,xpos)
            if play_tick is not None and start<=play_tick<end:
                painter.setPen(QPen(self.color('#D15F49'),1.5))
                painter.drawLine(QPointF(xpos(play_tick),system.top+28),QPointF(xpos(play_tick),system.top+system.grid_bottom))
            x+=bw
        painter.setPen(QPen(self.color('#A4ADBA'),.8))
        painter.drawLine(QPointF(x,line_top),QPointF(x,line_bottom))
        # Connect actual fragment anchors across bar lines. Only system/page breaks
        # receive paired continuations; the incoming part descends directly to
        # the first note rather than drawing a second complete arch.
        def curve(a,b,color,kind):
            path=QPainterPath(a);dx=b.x()-a.x();rise=min(13*scale,max(4*scale,abs(dx)*.12))
            if kind=='incoming':
                # The descending half of an arch: no new peak at the row entry.
                dy=b.y()-a.y()
                path.cubicTo(QPointF(a.x()+dx*.45,a.y()),QPointF(a.x()+dx*.8,a.y()+dy*.35),b)
            else:path.cubicTo(QPointF(a.x()+dx*.28,min(a.y(),b.y())-rise),QPointF(a.x()+dx*.72,min(a.y(),b.y())-rise),b)
            painter.setPen(QPen(self.color(color),.95*scale));painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawPath(path)
            return path
        def tie(nid,a,b,color,kind):
            path=curve(a,b,color,kind)
            self.tie_paths.append((nid,kind,path))
        for nid,anchors in tie_anchors.items():
            anchors.sort(key=lambda item:item[0].start)
            first=anchors[0];last=anchors[-1]
            if first[0].continuation:
                tie(nid,QPointF(system.left+scale,first[2]-4*scale),QPointF(first[1]-5*scale,first[2]),first[3],'incoming')
            for left,right in zip(anchors,anchors[1:]):
                if left[0].continues and left[0].end==right[0].start:
                    tie(nid,QPointF(left[1]+5*scale,left[2]),QPointF(right[1]-5*scale,right[2]),left[3],'continuous')
            if last[0].continues:
                tie(nid,QPointF(last[1]+5*scale,last[2]),QPointF(x-2,last[2]-2*scale),last[3],'outgoing')
        # Lyric melismas connect successive MIDI attacks, independently of
        # duration ties, and never change the note fragments or MIDI events.
        first_tick=p.starts[system.bars[0]];last_tick=p.starts[system.bars[-1]+1]
        for a,b,left_id,right_id in self.melismas:
            left=slur_anchors.get((left_id,a));right=slur_anchors.get((right_id,b))
            if left and right:
                kind='continuous';start=QPointF(left[0]+5*scale,left[1]);end=QPointF(right[0]-5*scale,right[1]);color=left[2]
            elif left and b>=last_tick:
                kind='outgoing';start=QPointF(left[0]+5*scale,left[1]);end=QPointF(x-2,left[1]-2*scale);color=left[2]
            elif right and a<first_tick:
                kind='incoming';start=QPointF(system.left+scale,right[1]-4*scale);end=QPointF(right[0]-5*scale,right[1]);color=right[2]
            else:continue
            self.melisma_paths.append((a,b,kind,curve(start,end,color,kind)))


def export_pdf(project,path,pages=None):
    project.validate()
    layout=ScoreLayout(project)
    pages=list(range(layout.pages)) if pages is None else list(pages)
    if not pages or pages!=sorted(set(pages)) or any(not 0<=p<layout.pages for p in pages):raise ValueError('谱面页码范围无效。')
    writer=QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(0,0,0,0))
    writer.setResolution(144)
    writer.setTitle(project.title)
    from lingfeng import __version__
    writer.setCreator('Lingfeng '+__version__)
    painter=QPainter(writer)
    if not painter.isActive():
        raise OSError('无法创建PDF，请检查目标文件是否被占用。')
    for index,page in enumerate(pages):
        if index:
            writer.newPage()
        painter.save(); painter.scale(writer.width()/PAPER_W,writer.height()/PAPER_H)
        layout.draw(painter,page);painter.restore()
    painter.end()
    return len(pages)
