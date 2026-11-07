"""Shared vector layout for screen and PDF. No piano-roll range enters layout."""
from __future__ import annotations
from dataclasses import dataclass,field,replace
from pathlib import Path
import math
import copy
import bisect
from PySide6.QtCore import Qt, QRectF, QPointF, QMarginsF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QPainterPath, QPainterPathStroker, QPdfWriter, QPageSize, QPageLayout,QTransform
from lingfeng.music.model import PPQ, MODES, Note, spelling, pitch_name, FONT_SIZE_MAX, MELODY_NAMES
from lingfeng.ui.fonts import ensure_fonts
from lingfeng.ui.theme import color as theme_color
from lingfeng.platform.i18n import tr
from lingfeng.engraving.presentation import visible_bars, active_compressions, annotation_allowed, lyric_verses, row_groups, slur_notes, slur_conflicts, melody_voices
from lingfeng.engraving.lyrics import display_events, lyric_track, melisma_links

INK = QColor('#263345')
MUTED = QColor('#8692A2')
CHROMATIC = QColor('#BC6542')
MELODY_COLORS = (QColor('#426BAA'), QColor('#247D6E'), QColor('#7D2E48'))
MELODY_LABELS = ('人声', '乐器')
PAPER_W, PAPER_H = 900, 1273
MARGIN = 52
GRID_LINE='#C9D5E3'
ANCHOR_LINE='#9AAEC6'
BEAT_LINE='#D2DCE8'
# MIDI time-base conversions can leave a 1–2 tick remainder at PPQ 960.
# This tolerance only affects engraving; note timing and playback stay exact.
RHYTHM_TOLERANCE=2
# Imported legato tails may overlap the next attack slightly. This changes only
# traditional voice placement, never note lengths or performed polyphony.
LEGATO_TAIL_MAX=PPQ//8
LEGATO_TAIL_FRACTION=4
RHYTHM_VALUES=(3840,2880,1920,1440,960,720,640,480,360,320,240,180,160,120,90,80,60,45,40,30)
TRADITIONAL_BEAT_GAP=.75
TRADITIONAL_ROW_GAP=8.
SYMBOL_PADDING=1.5
RHYTHM_DOT_CLEARANCE=.6
CIRCLE_RADIUS_X=10.
CIRCLE_RADIUS_Y=12.
CIRCLE_PEN_WIDTH=.95


def is_chord_tone(project,pitch,tick):
    """Manual chord labels guide circles; unmarked chords use performed MIDI."""
    chord=project.chord_at(tick)
    return bool(chord and pitch%12 in chord.highlight_pcs)


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
    extension_beats: int = 0
    track: int = 0

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


def beat_rhythm_parts(start,duration,bar_start,beat):
    """Keep beat ties; prefer the offbeat when a beat-local value needs a tie."""
    if ((start-bar_start)%beat==0 and round(duration/PPQ)>=1 and
            abs(duration-round(duration/PPQ)*PPQ)<=RHYTHM_TOLERANCE):
        return [(start,duration)]
    single=lambda length:any(abs(length-value)<=RHYTHM_TOLERANCE for value in RHYTHM_VALUES)
    def boundaries(left,right):
        first=bar_start+((left-bar_start)//beat+1)*beat
        # A conversion remainder beside a beat is not a new rhythmic value.
        return [left,*[t for t in range(first,right,beat)
                       if left+RHYTHM_TOLERANCE<t<right-RHYTHM_TOLERANCE],right]
    end=start+duration
    cuts=boundaries(start,end)
    if len(cuts)==2 and single(duration):return [(start,duration)]
    result=[]
    # Retain the existing integral-quarter sustain shorthand at an on-beat
    # onset, including meters whose beat is shorter/longer than a quarter.
    prefix=duration//PPQ*PPQ
    if (start-bar_start)%beat==0 and PPQ<=prefix<duration-RHYTHM_TOLERANCE:
        result.append((start,prefix));start+=prefix;cuts=boundaries(start,end)
    for left,right in zip(cuts,cuts[1:]):
        middle=bar_start+((left-bar_start)//beat)*beat+beat//2
        if not single(right-left) and left+RHYTHM_TOLERANCE<middle<right-RHYTHM_TOLERANCE:
            result.extend(rhythm_parts(left,middle-left))
            result.extend(rhythm_parts(middle,right-middle))
        else:result.extend(rhythm_parts(left,right-left))
    return result


def voice_lanes(fragments,legato=False):
    """Allocate visible intervals; optionally disregard only short staggered tails."""
    visible={}
    for f in fragments:
        if f.note is None or f.pitch is None:continue
        note=f.note
        if note.id in visible:
            prior,a,b=visible[note.id];visible[note.id]=(prior,min(a,f.start),max(b,f.end))
        else:visible[note.id]=(note,f.start,f.end)
    voices={};lanes=[]
    for note,start,end in sorted(visible.values(),key=lambda item:(item[1],-item[0].pitch,item[0].start)):
        lane=len(lanes)
        for index,(prior,a,b) in enumerate(lanes):
            overlap=b-start
            short_tail=(legato and a<start and prior.start<note.start and
                        0<overlap<=LEGATO_TAIL_MAX and
                        overlap*LEGATO_TAIL_FRACTION<=min(prior.duration,note.duration))
            if b<=start or short_tail:
                lane=index;break
        if lane==len(lanes):lanes.append((note,start,end))
        else:lanes[lane]=(note,start,end)
        voices[note.id]=lane
    return voices


def fragments_for_bar(project,index,lyrics=None,adjustments=()):
    start,end=project.starts[index:index+2];notes=sorted((n for n in project.notes if n.start<end and n.end>start),key=lambda n:n.start)
    pieces=[];coverage=[]
    beat=PPQ*4//project.measures[index].denominator
    parts=lambda a,d:beat_rhythm_parts(a,d,start,beat)
    rap_ticks={e['tick'] for e in lyrics or [] if e.get('kind')=='rap_note'}
    for note in notes:
        if note.start in rap_ticks:continue
        a,b=max(start,note.start),min(end,note.end);coverage.append((a,b))
        boundaries=sorted({a,b,*[c.start for c in project.contexts if a<c.start<b],
                           *[t for item in adjustments for t in item['tail'] if a<t<b]})
        for left,right in zip(boundaries,boundaries[1:]):
            for t,d in parts(left,right-left):
                f=Fragment(t,d,note.pitch,note,t>note.start,t+d<note.end,note.lyric if t==note.start else '')
                if (t-start)%beat==0 and abs(d-round(d/PPQ)*PPQ)<=RHYTHM_TOLERANCE:
                    f.extension_beats=round(d/PPQ)
                pieces.append(f)
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
    pieces.extend(rest_fragments(notes,coverage,start,end,beat))
    for f in pieces:
        if any((f.start,f.end)==item['tail'] for item in adjustments):f.display_duration=PPQ//2
    return sorted(pieces,key=lambda f:(f.start,f.pitch if f.pitch is not None else -1))


def rest_fragments(notes,coverage,start,end,beat):
    cursor=start;gaps=[]
    for a,b in sorted(coverage):
        if cursor<a:gaps.append((cursor,a))
        cursor=max(cursor,b)
    if cursor<end:gaps.append((cursor,end))
    for left,right in gaps:
        if right-left<=RHYTHM_TOLERANCE:continue
        # Long rests are repeated zeros, including the first beat of a bar.
        boundaries=sorted({left,right,*range(start+beat,end,beat)})
        boundaries=[t for t in boundaries if left<=t<=right]
        for a,b in zip(boundaries,boundaries[1:]):
            for t,d in rhythm_parts(a,b-a):
                prior=[n for n in notes if n.end<=t]
                yield Fragment(t,d,None,rest_pitch=max(prior,key=lambda n:(n.end,n.start,n.pitch)).pitch if prior else None)


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
    if fragment.extension_beats and fragment.display_duration is None:
        return 0,False,False,fragment.extension_beats-1
    return rhythm_style(fragment.display_duration if fragment.display_duration is not None else fragment.duration)


def split_colliding_extensions(fragments):
    """Share a pitched glyph when an extension meets a digit in the same column."""
    heads={(f.start,f.pitch) for f in fragments if f.pitch is not None}
    for f in fragments:
        cuts=[f.start+k*PPQ for k in range(1,fragment_style(f)[3]+1)
              if (f.start+k*PPQ,f.pitch) in heads]
        if not cuts:
            yield f
            continue
        bounds=[f.start,*cuts,f.end]
        for start,end in zip(bounds,bounds[1:]):
            beats=round((end-start)/PPQ)
            if abs(end-start-beats*PPQ)>RHYTHM_TOLERANCE:beats=0
            yield replace(f,start=start,duration=end-start,extension_beats=beats,
                          continuation=f.continuation or start>f.start,
                          continues=f.continues or end<f.end,
                          lyric=f.lyric if start==f.start else '')


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
    font_ratio: float=1
    cell_width: float=0
    beat_gap: float=0
    beat_cells: list=field(default_factory=list)
    traditional_cells: dict=field(default_factory=dict)
    traditional_maps: dict=field(default_factory=dict)
    bar_side_gap: float=0
    symbol_count: int=0
    gap_units: int=0
    unit_count: int=0
    forced_font_ratio: float=1
    lower_octave_dots: int=0
    underline_offset: float=11
    notation_bottom: float=13
    notation_ink_bottom: float=12
    natural_width: float=0
    natural_height: float=0
    fit_left: float=0
    fit_width: float=0
    is_forced: bool=False
    reference_unit_count: int=0
    tracks: tuple=()
    track_voices: dict=field(default_factory=dict)
    lyric_lanes: dict=field(default_factory=dict)
    onset_extents: dict=field(default_factory=dict)
    unisons: set=field(default_factory=set)

    def voice(self,fragment):
        return self.voices.get(fragment.note.id,self.track_voices.get(fragment.track,0)) if fragment.note else self.track_voices.get(fragment.track,0)

    @property
    def last_voice(self):
        return max(max(self.voices.values(),default=0),max(self.track_voices.values(),default=0))

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
        source = project
        project = copy.copy(source)
        if not source.notation.get('show_melody', True):
            project.notes = []
        if not source.notation.get('show_instrument', True):
            project.instrument_notes = []
        if not source.notation.get('show_chords', True):
            project.chords = []
        self.lyric_source = source
        self.chord_attacks = tuple(sorted({note.start for note in project.harmony_notes()}))
        ensure_fonts()
        self.project = project
        self.systems = []
        self.hit_notes = []
        self.hit_bars = []
        self.hit_chords = []
        self.hit_times=[];self.hit_symbols=[];self.dark=False;self.tie_paths=[];self.rest_positions=[];self.symbol_marks=[];self.lyric_positions=[];self.symbol_boxes=[];self.unpitched_positions=[]
        self.time_hits_by_bar={};self.starts=project.starts
        self.pages = 1;self.glyph_scale=1;self.glyph_sizes=[];self.engraving_cache={};self.width_cache={};self.rhythm_adjustments={}
        self.traditional_grids={};self.cell_width_cache={};self.fragment_cache={};self.spacing_fragments={};self.fragment_systems={};self.ink_text_cache={};self.dot_ink_cache={}
        self.tuplet_groups=[];self.tuplet_marks=[];self.fragment_tuplets={};self.manual_slur_paths=[]
        self.build()
        self.systems_by_bar={bar:system for system in self.systems for bar in system.bars}

    def source_tuplets(self,p,lyrics,track):
        """Group original rhythmic attacks before beat/context spelling splits."""
        source={}
        def value(duration):
            return next((v for v in RHYTHM_VALUES if abs(duration-v)<=RHYTHM_TOLERANCE and rhythm_style(v)[2]),None)
        for note in p.notes:
            unit=source.setdefault((note.start,note.end),dict(start=note.start,end=note.end,source_ids=[],rest=False))
            unit['source_ids'].append(note.id)
        for event in lyrics:
            if event.get('kind')=='rap' and event.get('duration',0)>0:
                source.setdefault((event['tick'],event['tick']+event['duration']),dict(start=event['tick'],end=event['tick']+event['duration'],source_ids=[],rest=False))
        units=sorted(source.values(),key=lambda u:(u['start'],u['end']))
        for index,unit in enumerate(units):unit.update(token=index,value=value(unit['end']-unit['start']))
        groups=[];used=set()
        def add(run):
            if not any(not u['rest'] for u in run):return
            ident=f"tuplet:{track}:{run[0]['start']}:{run[-1]['end']}:{len(groups)}"
            groups.append(dict(id=ident,start=run[0]['start'],end=run[-1]['end'],duration=run[0]['value'],
                source_ids=tuple(ident for unit in run for ident in unit['source_ids']),units=tuple(run),complete=len(run)==3,track=track))
            used.update(u['token'] for u in run)
        # Full runs of three real attacks take precedence over a preceding
        # triplet-sized rest; that rest must not steal the first group member.
        run=[]
        def complete_run():
            while len(run)>=3:add(run[:3]);del run[:3]
        for unit in units:
            if not unit['value'] or (run and (unit['value']!=run[-1]['value'] or not 0<=unit['start']-run[-1]['end']<=RHYTHM_TOLERANCE)):
                complete_run();run=[]
            if unit['value']:run.append(unit)
        complete_run()
        anchors=sorted({*p.starts,*[tick for bar in range(len(p.measures)) for tick in range(p.starts[bar],p.starts[bar+1],PPQ*4//p.measures[bar].denominator)]})
        cursor=0;gaps=[]
        for unit in units:
            if cursor<unit['start']:gaps.append((cursor,unit['start']))
            cursor=max(cursor,unit['end'])
        if cursor<p.end:gaps.append((cursor,p.end))
        combined=list(units);token=len(units)
        for start,end in gaps:
            edges=[start,end] if value(end-start) else [start,*anchors[bisect.bisect_right(anchors,start):bisect.bisect_left(anchors,end)],end]
            for a,b in zip(edges,edges[1:]):
                combined.append(dict(start=a,end=b,source_ids=[],rest=True,token=token,value=value(b-a)));token+=1
        run=[]
        def finish():
            while len(run)>=3:add(run[:3]);del run[:3]
            if run:add(run[:])
        for unit in sorted(combined,key=lambda u:(u['start'],u['end'])):
            if unit['token'] in used or not unit['value']:
                finish();run=[];continue
            if run and (unit['value']!=run[-1]['value'] or not 0<=unit['start']-run[-1]['end']<=RHYTHM_TOLERANCE):
                finish();run=[]
            run.append(unit)
        finish()
        return sorted(groups,key=lambda group:(group['start'],group['end']))

    def tuplet_for_fragment(self,f):
        if f.note:return self.source_tuplet_ids.get(f.note.id)
        for ident in f.source_ids:
            if ident in self.source_tuplet_ids:return self.source_tuplet_ids[ident]
        for group,unit in self.unpitched_tuplet_units:
            if group['track']==f.track and unit['start']<=f.start and f.end<=unit['end'] and unit['rest']==(not f.ghost):return group['id']
        return None

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

    def row_tracks(self,bars):
        spans=[self.project.starts[b:b+2] for b in bars]
        def intersects(start,end):
            return any(start<b and a<end for a,b in spans)
        return tuple(track for track,(project,lyrics) in enumerate(zip(self.melodies,self.track_lyrics))
                     if any(intersects(n.start,n.end) for n in project.notes)
                     or any(e.get('kind')=='rap' and intersects(e['tick'],e['tick']+e['duration']) for e in lyrics))

    def bar_fragments(self,bar,tracks):
        parts=[];adjustments=None
        for track in tracks:
            project,lyrics=self.melodies[track],self.track_lyrics[track]
            fragments=fragments_for_bar(project,bar,lyrics)
            own=short_pair_adjustments(project,bar,fragments)
            # Both melodies share one time map. Move the short pair only if
            # each visible track can apply the same adjustment to the beat.
            adjustments=own if adjustments is None else [item for item in adjustments if item in own]
            parts.append((track,project,lyrics,fragments))
        self.rhythm_adjustments[bar]=adjustments or []
        result=[]
        for track,project,lyrics,fragments in parts:
            if adjustments:fragments=fragments_for_bar(project,bar,lyrics,adjustments)
            for fragment in fragments:
                fragment.track=track
            result.extend(fragments)
        if len(tracks)>1 and self.project.notation['style']!='traditional':
            # The two melodies share pitch space. A zero describes silence
            # across both, so it can never compete with an audible glyph.
            # Retain the original timing columns for the existing width rule.
            self.spacing_fragments[bar]=result
            result=[f for f in result if f.note is not None or f.ghost]
            result=list(split_colliding_extensions(result))
            start,end=self.project.starts[bar:bar+2]
            beat=PPQ*4//self.project.measures[bar].denominator
            notes=[f.note for f in result if f.note is not None]
            coverage=[(f.start,f.end) for f in result]
            for rest in rest_fragments(notes,coverage,start,end,beat):
                rest.track=-1
                if any((rest.start,rest.end)==item['tail'] for item in adjustments or ()):rest.display_duration=PPQ//2
                result.append(rest)
        self.fragment_tuplets.update((id(f),self.tuplet_for_fragment(f)) for f in result)
        return sorted(result,key=lambda f:f.start)

    def build(self):
        p=self.project;per_line=p.notation['per_line'];style=p.notation['style']
        self.font_size=max(.0001,min(round(p.notation.get('font_size',15),4),FONT_SIZE_MAX))
        left=MARGIN if style=='traditional' else MARGIN+40
        i,page,y=0,0,140;available=PAPER_W-MARGIN-left
        visible=visible_bars(p);forced=dict(p.notation.get('forced_rows',[]));bases={(a,b):n for a,b,n in p.notation.get('forced_row_fonts',[])}
        compressions=active_compressions(p);self.compressions=compressions;self.verses=lyric_verses(p,compressions)
        self.melodies=(p,lyric_track(p,1))
        self.track_lyrics=tuple(
            display_events(lyric_track(self.lyric_source,track),compressions)
            if p.notation['lyrics'] and p.notation.get(key,True) else []
            for track,key in enumerate(('show_melody_lyrics','show_instrument_lyrics'))
        )
        self.attack_ticks=tuple(sorted({*self.chord_attacks,
            *(note.start for melody in self.melodies for note in melody.notes),
            *(event['tick'] for lyrics in self.track_lyrics for event in lyrics if event.get('kind')=='rap')
        }))
        self.show_melody_colors=bool(p.instrument_notes or self.track_lyrics[1])
        self.lyrics=[dict(event,track=track) for track,lyrics in enumerate(self.track_lyrics) for event in lyrics]
        self.tuplet_groups=[group for track,(melody,lyrics) in enumerate(zip(self.melodies,self.track_lyrics))
                            for group in self.source_tuplets(melody,lyrics,track) if melody.notes or lyrics]
        self.source_tuplet_ids={ident:group['id'] for group in self.tuplet_groups for ident in group['source_ids']}
        self.unpitched_tuplet_units=[(group,unit) for group in self.tuplet_groups for unit in group['units'] if not unit['source_ids']]
        self.melismas=[link for melody,lyrics in zip(self.melodies,self.track_lyrics) for link in melisma_links(melody,lyrics)]
        self.melisma_paths=[]
        self.melisma_notes={ident for _,_,left,right in self.melismas for ident in (left,right)}
        while i<len(visible):
            bars=[]
            row_end=forced.get(visible[i]);forced_count=len([b for b in visible[i:] if b<row_end]) if row_end else 0
            limit=forced_count or per_line
            while i<len(visible) and len(bars)<limit:
                bar=visible[i]
                if bars and bar in forced:break
                # A bar is indivisible, including at explicit line and page breaks.
                bars.append(bar);i+=1
                if not forced_count and p.measures[bar].break_after:break
            tracks=self.row_tracks(bars)
            row_lyrics=[e for e in self.lyrics if not e.get('skip') and e.get('text') and any(p.starts[b]<=e['tick']<p.starts[b+1] for b in bars)]
            has_chords=any(not c.empty and any(c.start<p.starts[b+1] and p.starts[b]<c.end for b in bars) for c in p.chords)
            # Legacy one-melody scores still express a wholly empty line as
            # rests. A chord/lyric-only line needs only its existing content.
            displayed=tracks or (() if self.show_melody_colors or row_lyrics or has_chords or not p.notation.get('show_melody',True) else (0,))
            fragments={bar:self.bar_fragments(bar,displayed) for bar in bars}
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
            # Genuine overlapping voices retain independent lanes. Imported
            # short legato tails alone do not push a melody into a second row.
            voices={};track_voices={};lane=0
            for track in displayed:
                track_voices[track]=lane
                assigned=voice_lanes((f for f in notes if f.track==track),style=='traditional')
                voices.update((ident,voice+lane) for ident,voice in assigned.items())
                lane+=max(assigned.values(),default=0)+1
            gap=p.notation['row_gap']
            height=100+max(0,lane-1)*48 if style=='traditional' else (len(grid)-1)*gap+84
            if not displayed:height=55
            lyric_rows=0;lyric_lanes={}
            for track in (0,1):
                events=[e for e in row_lyrics if e['track']==track]
                verses=max((e.get('verse',0)+1 for e in events),default=1)
                for event in events:
                    voice,verse=event.get('voice',0),event.get('verse',0)
                    lyric_lanes[track,voice,verse]=lyric_rows+voice*verses+verse
                if p.notation['lyrics']:lyric_rows+=verses*max((e.get('voice',0)+1 for e in events),default=0)
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
            for bar in bars:self.minimum_bar_width(bar,fragments[bar])
            weights=[self.bar_spacing_weight(b,fragments[b]) for b in bars]
            widths=[available*w/sum(weights) for w in weights]
            system=System(bars,fragments,grid,y,height,page,widths,boundaries,tonic,gap,scale,voices,layout_scale,extra,grid_bottom,lyric_rows)
            system.tracks=tracks;system.track_voices=track_voices;system.lyric_lanes=lyric_lanes
            if len(tracks)>1 and style!='traditional':
                for bar,parts in fragments.items():
                    unisons={}
                    for f in parts:
                        key=bar,f.start
                        system.onset_extents[key]=max(system.onset_extents.get(key,0),self.column_extents(f)[0])
                        if f.track>=0:unisons.setdefault((f.start,f.pitch),set()).add(f.track)
                    system.unisons.update(key for key,owners in unisons.items() if len(owners)>1)
            system.left=left
            system.is_forced=bool(forced_count)
            system.forced_font_ratio=scale
            system.font_ratio=1 if style=='traditional' else scale
            if style=='traditional':
                system.symbol_scale=1
                system.lower_octave_dots=max((self.lower_dots(f) for f in notes),default=0)
                system.underline_offset=11+4*system.lower_octave_dots
            system.context_height=context_height;system.notation_clearance=clearance
            self.fragment_systems.update((id(f),system) for parts in fragments.values() for f in parts)
            self.systems.append(system);y+=height+p.notation.get('system_gap',12)
        self.pages=page+1
        # Traditional advice follows the score-wide numeric unit budget;
        # spatial advice follows two-dimensional ink rather than time cells.
        if style=='traditional':
            self.digit_advance=max(self.text_width(str(digit),15) for digit in range(8))
            self.circle_width_ratio=(2*CIRCLE_RADIUS_X+CIRCLE_PEN_WIDTH)/self.digit_advance
            self.numeric_advance=self.digit_advance*self.circle_width_ratio
            self.cell_width=self.numeric_advance*self.font_size/15
            def budget(bars):
                groups=[beat for bar in bars for beat in self.traditional_grid(bar)]
                return sum(beat['count'] for beat in groups)+2*len(groups)
            normal=[system for system in self.systems if not system.is_forced]
            self.reference_source='nonforced' if normal else 'baseline'
            self.reference_rows=tuple(tuple(system.bars) for system in normal) if normal else tuple(row['bars'] for row in row_groups(p,use_forced=False))
            self.reference_unit_count=max((budget(bars) for bars in self.reference_rows),default=1)
            for system in self.systems:
                units=budget(system.bars);system.reference_unit_count=self.reference_unit_count
                ratio=min(1,self.reference_unit_count/max(1,units)) if system.is_forced else 1
                system.font_ratio=system.forced_font_ratio=ratio;system.symbol_scale=ratio
                self.arrange_traditional_system(system,available,self.cell_width*ratio)
            self.max_font_size=min(FONT_SIZE_MAX,15*available/self.reference_unit_count/self.numeric_advance)
            self.font_limit=max(1,math.floor(self.max_font_size))
        else:
            self.max_font_size=self.suggest_font_size()
            self.font_limit=math.floor(self.max_font_size+1e-7) if self.max_font_size>=1 else math.floor(self.max_font_size*10000)/10000
        self.font_limit=max(.0001,min(FONT_SIZE_MAX,self.font_limit))
        self.recommended_font_size=self.font_limit if style=='traditional' else min(15,self.font_limit)
        self.glyph_scale=self.font_size/15
        voices=melody_voices(p.notes)
        manual=[(i,slur_notes(p,item)) for i,item in enumerate(p.notation.get('symbols',[]))
                if item['kind']=='slur' and not slur_conflicts(p,item,self.melismas,voices)]
        page,y=0,140
        for system in self.systems:
            system.symbol_scale*=self.glyph_scale
            system.bar_scales={bar:system.symbol_scale for bar in system.bars}
            # Low octave dots/underlines and enlarged lyrics need real vertical
            # space too; leave pitch and polyphonic voice distances unchanged.
            notes=[f for fs in system.fragments.values() for f in fs if f.pitch is not None]
            if style=='traditional':
                last_voice=system.last_voice
                below=max((self.vertical_extents(f,system)[1]*system.symbol_scale-(last_voice-system.voices[f.note.id])*48 for f in notes),default=0)
                bottom_extra=max(0,below+6-48)
            else:
                below=max((self.vertical_extents(f)[1]*system.symbol_scale-system.pitch_position(f.pitch)*system.row_gap for f in notes),default=0)
                bottom_extra=max(0,below+6-32)
            system.lyric_gap=22*max(1,system.symbol_scale);system.lyric_offset=20*max(1,system.symbol_scale)
            if style=='traditional':
                scale=system.symbol_scale
                lower_band=system.height-system.grid_bottom-system.lyric_rows*22-12
                fragments=[f for fs in system.fragments.values() for f in fs]
                top=max((self.vertical_extents(f,system)[0] for f in fragments),default=27)
                bottom=max((self.vertical_extents(f,system)[1] for f in fragments),default=13)
                system.notation_bottom=bottom
                system.notation_ink_bottom=max((self.symbol_ink(f,system)[3] for f in fragments),default=12)
                system.voice_gap=(top+bottom+6)*scale
                system.note_baseline=24+system.extra_header-system.notation_clearance+top*scale
                system.grid_bottom=system.note_baseline+last_voice*system.voice_gap+bottom*scale+3
                system.lyric_gap=max(14,17*scale);system.lyric_offset=system.lyric_gap
                system.height=system.grid_bottom+system.lyric_rows*system.lyric_gap+lower_band+7
            else:
                system.grid_bottom+=bottom_extra
                system.height+=bottom_extra+system.lyric_rows*(system.lyric_gap-22)
            tuplet_fragments=[f for parts in system.fragments.values() for f in parts if self.fragment_tuplets.get(id(f))]
            if tuplet_fragments:
                tops=[]
                for f in tuplet_fragments:
                    if style=='traditional':ny=system.note_baseline+system.voice(f)*system.voice_gap
                    else:
                        baseline=(len(system.pitches)-1)*system.row_gap+60+system.extra_header
                        ny=baseline-system.pitch_position(f.pitch)*system.row_gap if f.pitch is not None else baseline-(len(system.pitches)-1)*system.row_gap/2
                    tops.append(self.tuplet_ink_top(f,system,ny))
                label_top=min(tops)+(self.text_ink('3',9,center=True)[1]-5)*system.symbol_scale
                padding=max(0,system.context_height+20+6*system.symbol_scale-label_top)
                system.extra_header+=padding;system.note_baseline+=padding;system.grid_bottom+=padding;system.height+=padding
            first,last=p.starts[system.bars[0]],p.starts[system.bars[-1]+1]
            system.melisma_through=any(a<first and b>=last for a,b,_,_ in self.melismas)
            if system.melisma_through:
                # Empty intermediate rows have no endpoint glyph to reserve
                # slur ink. Allocate an explicit band before pagination, also
                # covering the extra continuation curve above a held note.
                padding=20*system.symbol_scale
                system.extra_header+=padding;system.note_baseline+=padding;system.grid_bottom+=padding;system.height+=padding
            system.manual_slurs=[(i,notes) for i,notes in manual if len(notes)>=2 and notes[0].start<last and notes[-1].start>=first]
            if system.manual_slurs:
                padding=(20+6*min(3,len(system.manual_slurs)))*system.symbol_scale
                system.extra_header+=padding;system.note_baseline+=padding;system.grid_bottom+=padding;system.height+=padding
            system.natural_width=sum(system.bar_widths);system.natural_height=system.height
            descriptors=self.ink_descriptors(system)
            ink_right=max((x+r*system.symbol_scale for _,_,x,_,_,_,r,_ in descriptors),default=system.left+system.natural_width)
            header_x=system.left
            for bar,width in zip(system.bars,system.bar_widths):
                ink_right=max(ink_right,header_x+5+self.text_width(str(bar+1),9))
                if p.measures[bar].section:ink_right=max(ink_right,header_x+28+self.text_width(p.measures[bar].section,10))
                header_x+=width
            system.fit_left=system.left
            system.fit_width=max(system.left+system.natural_width,ink_right)-system.fit_left
            page_start=140 if page==0 else 76
            if y>page_start and y+system.natural_height>PAPER_H-70:
                page+=1;y=76
            system.layout_scale=1;system.height=system.natural_height
            system.top=y;system.page=page;y+=system.height+p.notation.get('system_gap',12)
        self.pages=page+1
        self.bar_symbol_scales={b:s.symbol_scale for s in self.systems for b in s.bars}

    def tuplet_ink_top(self,f,system,baseline):
        scale=system.symbol_scale;top=baseline+self.symbol_ink(f,system)[1]*scale
        if f.note and (f.continuation or f.continues or f.note.id in self.melisma_notes):
            octave=spelling(f.pitch,self.project.context_at(f.start).tonic,f.note.flat,mode=self.project.context_at(f.start).mode)[2]
            top=min(top,baseline-(37+max(0,octave)*4)*scale)
        return top

    @staticmethod
    def system_transform(system):
        transform=QTransform();transform.translate(system.left,system.top)
        transform.scale(system.layout_scale,system.layout_scale);transform.translate(-system.fit_left,0)
        return transform

    def system_page_rect(self,system):
        return self.system_transform(system).mapRect(QRectF(system.fit_left,0,system.fit_width,system.natural_height))

    def text_ink(self,text,size,bold=False,center=False):
        key=(text,size,bold,center)
        if key not in self.ink_text_cache:
            font=QFont('Microsoft YaHei');font.setPixelSize(round(size*1.2))
            font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
            metrics=QFontMetricsF(font);rect=metrics.tightBoundingRect(text)
            dx=-metrics.horizontalAdvance(text)/2 if center else 0
            self.ink_text_cache[key]=(rect.left()+dx,rect.top(),rect.right()+dx,rect.bottom())
        return self.ink_text_cache[key]

    def symbol_ink(self,f,system=None):
        """Visible digit, accidental, circle, dots and underlines at base size."""
        if f.note:
            degree,accidental,octave=spelling(f.pitch,self.project.context_at(f.start).tonic,f.note.flat,mode=self.project.context_at(f.start).mode)
            text=str(degree)
        else:text='x' if f.ghost else '0';accidental=octave=0
        rects=[self.text_ink(text,15,center=True)]
        if accidental:
            l,t,r,b=self.text_ink('♭' if accidental<0 else '♯',11);rects.append((l-17,t,r-17,b))
        if f.note and self.project.notation['circles'] and is_chord_tone(self.project,f.pitch,f.start):
            if self.project.notation['style']=='traditional':
                half=CIRCLE_PEN_WIDTH/2
                rects.append((-CIRCLE_RADIUS_X-half,-6-CIRCLE_RADIUS_Y-half,CIRCLE_RADIUS_X+half,-6+CIRCLE_RADIUS_Y+half))
            else:rects.append((-10.5,-18.5,10.5,6.5))
        for k in range(abs(octave)):
            y=-22-k*4 if octave>0 else 5+k*4;rects.append((-1.35,y-1.35,1.35,y+1.35))
        under,dotted,_,dashes=fragment_style(f)
        for k in range(under):
            offset=self.underline_y(f,system) if self.project.notation['style']=='traditional' else 11+max(0,-octave)*4
            y=offset+k*4;rects.append((-5.5,y-.5,6.5,y+.5))
        if dotted and not dashes:rects.append((11.6,-7.4,14.4,-4.6))
        return min(r[0] for r in rects),min(r[1] for r in rects),max(r[2] for r in rects),max(r[3] for r in rects)

    def ink_descriptors(self,system):
        """Affine ink boxes, built once per row before the advisory search."""
        p=self.project;traditional=p.notation['style']=='traditional';result=[];x=system.left
        notes=[f for fs in system.fragments.values() for f in fs if f.pitch is not None]
        extents=[f for fs in system.fragments.values() for f in fs] if traditional else notes
        voice_gap=max((self.vertical_extents(f,system)[0] for f in extents),default=27)+max((self.vertical_extents(f,system)[1] for f in extents),default=13)+6
        def add(group,layer,x,y,rect,dx=0,dy=0):
            l,t,r,b=rect;result.append((group,layer,x,y,l+dx,t+dy,r+dx,b+dy))
        for bar,width in zip(system.bars,system.bar_widths):
            points,positions,*_=self.bar_map(system,bar,x,width);origins={}
            def xpos(t):return self.interpolate(points,positions,t)
            for f in system.fragments[bar]:
                if traditional:
                    a,b=system.traditional_cells[(bar,f.start)];nx=x+(a+b)/2;dx=0
                    ny=0;dy=system.voice(f)*voice_gap
                else:
                    nx=xpos(f.start);dx=self.onset_left(system,bar,f)
                    ny=-system.pitch_position(f.pitch)*system.row_gap if f.pitch is not None else -(len(system.pitches)-1)*system.row_gap/2;dy=0
                group=(f.start,f.pitch) if (f.start,f.pitch) in system.unisons else id(f)
                origins.setdefault((f.track,f.start),(nx,dx));add(group,(0,),nx,ny,self.symbol_ink(f,system),dx,dy)
                _,dotted,_,dashes=fragment_style(f)
                for k in range(dashes):
                    tick=f.start+(k+1)*PPQ
                    if traditional:
                        a,b=system.traditional_cells[(bar,tick)];dashx=x+(a+b)/2;offset=0
                    else:dashx=xpos(tick);offset=12.5
                    rect=self.text_ink('−',14,center=True)
                    if dotted and k==dashes-1:rect=(rect[0],min(rect[1],-7.4),max(rect[2],13.4),max(rect[3],-4.6))
                    add(group,(0,),dashx,ny,rect,offset,dy)
            start,end=p.starts[bar:bar+2]
            if p.notation['lyrics']:
                for event in self.lyrics:
                    if not start<=event['tick']<end or event.get('skip') or not event.get('text'):continue
                    text=event['text']+('-' if event.get('join_next') else '')
                    key=event['track'],event['tick']
                    if key in origins:nx,dx=origins[key]
                    elif traditional:
                        nx=xpos(event['tick'])+system.cell_width/2;dx=0
                    else:nx=xpos(event['tick']);dx=SYMBOL_PADDING/2+self.text_width(text,11)/2
                    add(('lyric',event['id'],event.get('verse',0)),(1,event['track'],event.get('voice',0),event.get('verse',0)),nx,0,self.text_ink(text,11,center=True),dx)
            for chord in p.chords:
                if start<=chord.start<end or chord.start<start<chord.end:
                    from lingfeng.music.chord_operations import roman_label
                    add(('chord',chord.id),(2,),xpos(max(start,chord.start)),0,self.text_ink(roman_label(p,chord,chord.flat),12,True),4)
            if traditional:
                middle=system.last_voice*voice_gap/2-3
                leading,trailing=self.repeat_padding(bar)
                distance,radius=self.repeat_dot_geometry(system);distance/=system.symbol_scale;radius/=system.symbol_scale
                if leading:add(('repeat-start',bar),(0,),x,0,(distance-radius,middle-4-radius,distance+radius,middle+4+radius))
                if trailing:add(('repeat-end',bar),(0,),x+width,0,(-distance-radius,middle-4-radius,-distance+radius,middle+4+radius))
            x+=width
        return result

    @staticmethod
    def ink_fits(descriptors,scale,left=MARGIN,right=PAPER_W-MARGIN):
        layers={}
        for group,layer,x,y,l,t,r,b in descriptors:
            box=(x+l*scale,y+t*scale,x+r*scale,y+b*scale,group,x,y)
            if box[0]<left-1e-7 or box[2]>right+1e-7:return False
            layers.setdefault(layer,[]).append(box)
        clearance=.6*scale
        for boxes in layers.values():
            active=[]
            for current in sorted(boxes,key=lambda box:box[0]):
                active=[box for box in active if box[2]+clearance>current[0]]
                for prior in active:
                    if (prior[4]!=current[4] and prior[5:]!=current[5:]
                            and prior[1]<current[3]+clearance and current[1]<prior[3]+clearance):
                        return False
                active.append(current)
        return True

    def suggest_font_size(self):
        advice=float(FONT_SIZE_MAX)
        for system in self.systems:
            descriptors=self.ink_descriptors(system);ratio=system.font_ratio/15
            x=system.left
            for bar,width in zip(system.bars,system.bar_widths):
                points,positions,*_=self.bar_map(system,bar,x,width)
                for f in system.fragments[bar]:
                    _,dotted,_,dashes=fragment_style(f)
                    if not dotted:continue
                    tick=f.start+dashes*PPQ;beat=self.beat_cell(system,bar,tick)
                    if self.project.notation['style']=='traditional':
                        a,b=system.traditional_cells[(bar,tick)];anchor=x+(a+b)/2
                        offset=12 if dashes else 13
                    else:
                        anchor=self.interpolate(points,positions,tick)
                        offset=24.5 if dashes else self.onset_left(system,bar,f)+13
                        if not dashes and f.start==self.project.starts[bar]:offset+=self.repeat_padding(bar)[0]
                    # Advice leaves the ordinary dot offset intact, with its
                    # full ellipse inside the beat's content boundary.
                    room=beat['right']-anchor
                    if room>0 and offset>0:
                        advice=min(advice,room/(offset+1.4+RHYTHM_DOT_CLEARANCE)/ratio)
                x+=width
            if self.ink_fits(descriptors,advice*ratio):continue
            low,high=0.,advice
            for _ in range(15):
                middle=(low+high)/2
                if self.ink_fits(descriptors,middle*ratio):low=middle
                else:high=middle
            advice=low
        return max(1,advice)

    @staticmethod
    def traditional_beat_cell(system,bar,tick):
        return next(beat for beat in system.beat_cells if beat['bar']==bar and beat['start']<=tick<beat['end'])

    def beat_cell(self,system,bar,tick):
        if self.project.notation['style']=='traditional':return self.traditional_beat_cell(system,bar,tick)
        start,end=self.project.starts[bar:bar+2];beat=PPQ*4//self.project.measures[bar].denominator
        a=start+((tick-start)//beat)*beat;b=min(a+beat,end)
        index=system.bars.index(bar);x=system.left+sum(system.bar_widths[:index]);width=system.bar_widths[index]
        points,positions,*_=self.bar_map(system,bar,x,width)
        return dict(bar=bar,start=a,end=b,left=self.interpolate(points,positions,a),right=self.interpolate(points,positions,b))

    def beat_dot(self,system,bar,tick,center,radius):
        """Keep the physical dot inside its beat even with a manual large font."""
        beat=self.beat_cell(system,bar,tick);left,right=beat['left'],beat['right']
        clearance=min(RHYTHM_DOT_CLEARANCE*system.symbol_scale,(right-left)/4)
        # Only pathological manual sizes in tiny beat cells reduce the dot
        # radius; the requested digit size and the row gap are unchanged.
        radius=min(radius,max(0,(right-left)/2-clearance))
        return min(max(center,left+radius+clearance),right-radius-clearance),radius

    def traditional_dot(self,system,bar,tick,center,radius):
        return self.beat_dot(system,bar,tick,center,radius)

    def traditional_cell_dot(self,system,bar,tick,center,radius,text,size=15,circled=False):
        """Keep augmentation attached to its digit, clear of actual glyph ink."""
        index=system.bars.index(bar);origin=system.left+sum(system.bar_widths[:index])
        a,b=system.traditional_cells[(bar,tick)];anchor=origin+(a+b)/2
        beat=self.beat_cell(system,bar,tick);scale=system.symbol_scale
        left=(max(origin+a,beat['left'])-anchor)/scale
        right=(min(origin+b,beat['right'])-anchor)/scale
        if circled:right=min(right,CIRCLE_RADIUS_X-CIRCLE_PEN_WIDTH/2)
        desired=(center-anchor)/scale;radius/=scale
        clearance=min(.2,(right-left)/4)
        key=(text,size)
        if key not in self.dot_ink_cache:
            font=QFont('Microsoft YaHei');font.setPixelSize(round(size*1.2))
            path=QPainterPath();path.addText(QPointF(-QFontMetricsF(font).horizontalAdvance(text)/2,0),font,text)
            stroke=QPainterPathStroker();stroke.setWidth(.4)
            self.dot_ink_cache[key]=path.united(stroke.createStroke(path))
        ink=self.dot_ink_cache[key]
        radius=min(radius,max(0,(right-left)/2-clearance))
        def position(r):return min(max(desired,left+r+clearance),right-r-clearance)
        def fits(r):
            dot=QPainterPath();dot.addEllipse(QPointF(position(r),-6),r,r)
            return not ink.intersects(dot)
        if not fits(radius):
            low,high=0.,radius
            for _ in range(14):
                middle=(low+high)/2
                if fits(middle):low=middle
                else:high=middle
            radius=low
        return anchor+position(radius)*scale,radius*scale

    def repeat_dot_geometry(self,system):
        distance=10*system.symbol_scale;radius=1.8*system.symbol_scale
        if self.project.notation['style']=='traditional':
            side=system.bar_side_gap;clearance=min(RHYTHM_DOT_CLEARANCE*system.symbol_scale,side/4)
            radius=min(radius,max(0,side/2-clearance))
            distance=min(max(distance,radius+clearance),side-radius-clearance)
        return distance,radius

    def lower_dots(self,f):
        return max(0,-spelling(f.pitch,self.project.context_at(f.start).tonic,f.note.flat,mode=self.project.context_at(f.start).mode)[2]) if f.note else 0

    def underline_y(self,f,system=None):
        if self.project.notation['style']=='traditional':
            if system is None:system=self.fragment_systems.get(id(f))
            if system is not None:return system.underline_offset
        octave=spelling(f.pitch,self.project.context_at(f.start).tonic,mode=self.project.context_at(f.start).mode)[2] if f.pitch is not None else 0
        return 11+4*max(0,-octave)

    def vertical_extents(self,f,system=None):
        octave=spelling(f.pitch,self.project.context_at(f.start).tonic,f.note.flat,mode=self.project.context_at(f.start).mode)[2] if f.note else 0
        under,_,triplet,_=fragment_style(f)
        top=max(27,24+max(0,octave-1)*4)
        if triplet:top=max(top,34+max(0,octave-1)*4)
        if f.continuation or f.continues or (f.note and f.note.id in self.melisma_notes) or self.melisma_notes.intersection(f.source_ids):top=max(top,37+max(0,octave)*4)
        offset=self.underline_y(f,system) if self.project.notation['style']=='traditional' else 11+max(0,-octave)*4
        bottom=max(13,offset+max(0,under-1)*4+2) if under else max(13,7+max(0,-octave-1)*4)
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
        system=next(s for s in self.systems if bar in s.bars)
        if (bar,tick) in system.traditional_cells:
            a,b=system.traditional_cells[(bar,tick)]
            return positions[0]+a,positions[0]+b
        a=self.interpolate(points,positions,tick)
        return a,a+system.cell_width

    def traditional_cell_width(self,bar):
        return next(s.cell_width for s in self.systems if bar in s.bars)

    def traditional_grid(self,bar):
        """Visible notation columns in each beat; labels do not add note slots."""
        if bar not in self.traditional_grids:
            start,end=self.project.starts[bar:bar+2]
            beat=PPQ*4//self.project.measures[bar].denominator
            slots={f.start for f in self.fragment_cache[bar]}
            for f in self.fragment_cache[bar]:slots.update(f.start+(k+1)*PPQ for k in range(fragment_style(f)[3]))
            regions=[]
            for a in range(start,end,beat):
                b=min(a+beat,end);visible=[t for t in slots if a<=t<b]
                regions.append(dict(start=a,end=b,slots=sorted(visible),count=len(visible)))
            self.traditional_grids[bar]=regions
        return self.traditional_grids[bar]

    def arrange_traditional_system(self,system,available,unit):
        """Score-wide font-driven cells; beat gaps are twice barline-side gaps."""
        groups=[(bar,beat) for bar in system.bars for beat in self.traditional_grid(bar)]
        system.symbol_count=sum(beat['count'] for _,beat in groups)
        system.gap_units=2*len(groups);system.unit_count=system.symbol_count+system.gap_units
        side=max(unit,(available-system.symbol_count*unit)/max(1,system.gap_units))
        system.cell_width=unit;system.bar_side_gap=side;system.beat_gap=2*side
        system.beat_cells=[];system.traditional_cells={};system.traditional_maps={}
        widths=[];cursor=0.
        for bar in system.bars:
            origin=cursor;start,end=self.project.starts[bar:bar+2];knots={start:0.}
            cursor+=side
            for index,beat in enumerate(self.traditional_grid(bar)):
                if index:cursor+=2*side
                a,b=beat['start'],beat['end'];left=cursor
                if a!=start:knots[a]=left-origin
                for column,tick in enumerate(beat['slots']):
                    cell_left=left+column*unit
                    system.traditional_cells[(bar,tick)]=(cell_left-origin,cell_left+unit-origin)
                    if tick!=a:knots[tick]=cell_left+unit/2-origin
                cursor+=beat['count']*unit
                system.beat_cells.append(dict(beat,bar=bar,left=system.left+left,right=system.left+cursor))
                knots[b]=cursor-origin
            cursor+=side;knots[end]=cursor-origin
            points=sorted(knots);system.traditional_maps[bar]=(points,[knots[t] for t in points])
            widths.append(cursor-origin)
        system.bar_widths=widths

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

    def onset_left(self,system,bar,fragment):
        extent=system.onset_extents.get((bar,fragment.start))
        if extent is None:extent=self.column_extents(fragment)[0]
        return SYMBOL_PADDING/2+extent

    def melody_color(self,system,fragment,default):
        if fragment.track<0 or self.project.notation['style']=='traditional' or not self.show_melody_colors:
            return default
        if (fragment.start,fragment.pitch) in system.unisons:return MELODY_COLORS[2]
        return MELODY_COLORS[fragment.track]

    def bar_spacing_weight(self,bar,fragments):
        """The densest meter beat sets the width of every beat in its bar.

        Simultaneous tones share a column. Use source attacks, including rap,
        so ties, rests and spelling fragments do not inflate the density.
        Empty bars keep one unit per beat.
        Scale by the actual duration so short bars also retain fractional beats.
        """
        start,end=self.project.starts[bar:bar+2]
        beat=PPQ*4//self.project.measures[bar].denominator
        groups={}
        for tick in self.attack_ticks[bisect.bisect_left(self.attack_ticks,start):bisect.bisect_left(self.attack_ticks,end)]:
            groups.setdefault((tick-start)//beat,set()).add(tick)
        density=max(1,max((len(ticks) for ticks in groups.values()),default=0))
        return density*(end-start)/beat

    def minimum_bar_width(self,bar,fragments):
        """Required width at the common 15-point base, including annotations."""
        p=self.project;start,end=p.starts[bar:bar+2];traditional=p.notation['style']=='traditional'
        self.fragment_cache[bar]=fragments
        slots=self.engraving_slots(bar,fragments);leading,trailing=self.repeat_padding(bar)
        cell_width=0.;reservations=[]
        def fraction(t):
            return (self.spacing_tick(bar,t)-start)/(end-start)
        required=32.
        def reserve(a,b,width,symbol=False):
            nonlocal required,cell_width
            if traditional:
                if symbol:cell_width=max(cell_width,width)
                else:
                    reservations.append((a,b,width))
            else:
                span=max(1e-9,fraction(b)-fraction(a))
                required=max(required,(width+(leading if a==start else 0)+(trailing if b==end else 0))/span)
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
                lane=lambda item:(item['track'],item.get('verse',0),item.get('voice',0))
                last=min((g['tick'] for g in events if g['tick']>e['tick'] and lane(g)==lane(e)),default=end)
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
        if traditional:
            cell_width=max(1.,cell_width)
            groups=self.traditional_grid(bar)
            required=max(required,sum(g['count'] for g in groups)*cell_width+max(0,len(groups)-1)*TRADITIONAL_ROW_GAP+leading+trailing)
            self.cell_width_cache[bar]=cell_width
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
            return baseline-18*system.symbol_scale,baseline+system.last_voice*system.voice_gap+max(12,system.notation_ink_bottom)*system.symbol_scale
        return system.top+25,system.top+system.grid_bottom

    def time_slots(self,bar,fragments):
        p=self.project;start,end=p.starts[bar:bar+2]
        if bar in self.spacing_fragments:fragments=fragments+self.spacing_fragments[bar]
        points=sorted({start,end,*range(start,end,PPQ),*[f.start for f in fragments],*[f.end for f in fragments],
                       *range(start,end,PPQ*4//p.measures[bar].denominator),
                       *[t for f in fragments for t in range(f.start+PPQ,f.end,PPQ)],
                       *[e['tick'] for e in self.lyrics if start<e['tick']<end],
                       *[c.start for c in p.chords if start<c.start<end],*[c.start for c in p.contexts if start<c.start<end]})
        return points,[(b-a)/PPQ for a,b in zip(points,points[1:])]

    def bar_map(self,system,bar,x,width):
        points,_=self.time_slots(bar,system.fragments[bar])
        leading,trailing=(v*system.symbol_scale for v in self.repeat_padding(bar))
        if self.project.notation['style']=='traditional':
            grid,anchors=system.traditional_maps[bar]
            positions=[x+self.interpolate(grid,anchors,t) for t in points]
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
            if self.starts[item['hidden_start']]<=tick<self.starts[item['hidden_end']]:
                return self.starts[item['start']]+tick-self.starts[item['hidden_start']]
        return tick

    def time_position(self,tick):
        tick=self.display_tick(tick)
        bar=bisect.bisect_right(self.starts,tick)-1
        hit=self.time_hits_by_bar.get(bar)
        if hit is None:return None
        page,_,_,points,positions=hit;system=self.systems_by_bar[bar]
        return page,self.interpolate(points,positions,tick),system.top+28*system.layout_scale,system.top+system.grid_bottom*system.layout_scale

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

    def melody_label(self,track,size,width):
        name=self.project.melody_names[track]
        if name==MELODY_NAMES[track]:return tr(MELODY_LABELS[track])
        font=QFont('Microsoft YaHei');font.setPixelSize(round(size*1.2))
        return QFontMetricsF(font).elidedText(name,Qt.TextElideMode.ElideRight,width)

    def draw(self, painter, page, play_tick=None,dark=False):
        self.melisma_paths=[];self.manual_slur_paths=[]
        self.dark=dark;self.tie_paths=[];self.rest_positions=[];self.symbol_marks=[];self.lyric_positions=[];self.symbol_boxes=[];self.unpitched_positions=[];self.glyph_sizes=[];self.tuplet_marks=[];p = self.project
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
        if (self.show_melody_colors or tuple(p.melody_names)!=MELODY_NAMES) and p.notation['style']!='traditional':
            legend_y=120 if page==0 else 44
            labels=[(self.melody_label(track,10,155),MELODY_COLORS[track] if self.show_melody_colors else INK) for track in (0,1)
                    if self.melodies[track].notes or self.track_lyrics[track]]
            if any(system.unisons for system in self.systems):labels.append((tr('重合'),MELODY_COLORS[2]))
            x=PAPER_W-MARGIN
            for label,color in reversed(labels):
                x-=self.text_width(label,10)
                self.text(painter,x,legend_y,label,10,color)
                x-=17
        self.text(painter,PAPER_W/2,PAPER_H-32,str(page+1),10,MUTED,center=True)
        for system in self.systems:
            if system.page == page:
                self.draw_system(painter,system,play_tick)

    def draw_system(self, painter, system, play_tick=None):
        scale=system.layout_scale
        if scale==1 and system.fit_left==system.left:return self.draw_system_content(painter,system,play_tick)
        local=copy.copy(system);local.top=0;local.height=system.natural_height
        transform=self.system_transform(system)
        counts=[len(x) for x in (self.hit_notes,self.hit_bars,self.hit_chords,self.hit_times,self.tie_paths,self.rest_positions,self.symbol_marks,self.lyric_positions,self.hit_symbols)]
        melisma_count=len(self.melisma_paths)
        manual_count=len(self.manual_slur_paths)
        box_count=len(self.symbol_boxes);unpitched_count=len(self.unpitched_positions);tuplet_count=len(self.tuplet_marks)
        painter.save();painter.setTransform(transform,True);self.draw_system_content(painter,local,play_tick);painter.restore()
        for items,count in zip((self.hit_notes,self.hit_bars,self.hit_chords),counts[:3]):
            for i in range(count,len(items)):
                pg,r,key=items[i];items[i]=(pg,transform.mapRect(r),key)
        for i in range(counts[3],len(self.hit_times)):
            pg,r,b,ticks,positions=self.hit_times[i];self.hit_times[i]=(pg,transform.mapRect(r),b,ticks,[transform.map(QPointF(x,0)).x() for x in positions])
            self.time_hits_by_bar[b]=self.hit_times[i]
        for i in range(counts[4],len(self.tie_paths)):
            nid,kind,path=self.tie_paths[i];self.tie_paths[i]=(nid,kind,transform.map(path))
        for i in range(melisma_count,len(self.melisma_paths)):
            a,b,kind,path=self.melisma_paths[i];self.melisma_paths[i]=(a,b,kind,transform.map(path))
        for i in range(manual_count,len(self.manual_slur_paths)):
            index,kind,path=self.manual_slur_paths[i];self.manual_slur_paths[i]=(index,kind,transform.map(path))
        for i in range(counts[5],len(self.rest_positions)):
            tick,pitch,x,y=self.rest_positions[i];point=transform.map(QPointF(x,y));self.rest_positions[i]=(tick,pitch,point.x(),point.y())
        for i in range(counts[6],len(self.symbol_marks)):
            kind,x,y=self.symbol_marks[i];point=transform.map(QPointF(x,y));self.symbol_marks[i]=(kind,point.x(),point.y())

        for i in range(counts[7],len(self.lyric_positions)):
            nid,verse,x,y=self.lyric_positions[i];point=transform.map(QPointF(x,y));self.lyric_positions[i]=(nid,verse,point.x(),point.y())

        for i in range(counts[8],len(self.hit_symbols)):
            pg,rect,key=self.hit_symbols[i];self.hit_symbols[i]=(pg,transform.mapRect(rect),key)
        for i in range(box_count,len(self.symbol_boxes)):
            a,b,*xs=self.symbol_boxes[i];self.symbol_boxes[i]=(a,b,*[transform.map(QPointF(x,0)).x() for x in xs])
        for i in range(unpitched_count,len(self.unpitched_positions)):
            tick,kind,x,y=self.unpitched_positions[i];point=transform.map(QPointF(x,y));self.unpitched_positions[i]=(tick,kind,point.x(),point.y())
        for mark in self.tuplet_marks[tuplet_count:]:
            a=transform.map(QPointF(mark['left'],mark['top']));b=transform.map(QPointF(mark['right'],mark['top']))
            mark.update(left=a.x(),right=b.x(),top=a.y())

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
                    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(self.color(INK))
                    distance,radius=self.repeat_dot_geometry(system);dx=distance if kind=='repeat_start' else -distance
                    for dy in (-4,4):painter.drawEllipse(QPointF(px+dx,(top+bottom)/2+dy*system.symbol_scale),radius,radius)
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
            if self.show_melody_colors or tuple(p.melody_names)!=MELODY_NAMES:
                for track,voice in system.track_voices.items():
                    self.text(painter,MARGIN/2,baseline+voice*system.voice_gap,self.melody_label(track,8,MARGIN-8),8,MUTED,center=True)
        line_top,line_bottom=self.barline_bounds(system)
        x=system.left;tie_anchors={};slur_anchors={};tuplet_anchors={}
        tie_start=len(self.tie_paths);melisma_start=len(self.melisma_paths)
        if style!='traditional' and system.track_voices:
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
            hit=(system.page,QRectF(x,system.top,bw,system.height),bar,points,positions)
            self.hit_times.append(hit);self.time_hits_by_bar[bar]=hit
            def xpos(t):
                return self.interpolate(points,positions,t)
            # Bar/beat columns and scale rows form the light score background.
            if style!='traditional' and system.track_voices:
                context=p.context_at(start)
                painter.fillRect(QRectF(x,system.top+45,bw,system.grid_bottom-45),self.color('#F8FAFC'))
                for pitch in system.pitches:
                    if pitch in system.boundaries or (p.notation.get('show_scale_lines',False) and (pitch-context.tonic)%12 in MODES[context.mode]):
                        anchor=pitch in system.boundaries;painter.setPen(QPen(self.color(ANCHOR_LINE if anchor else GRID_LINE),1.05 if anchor else .75))
                        gy=baseline-system.pitch_position(pitch)*gap
                        painter.drawLine(QPointF(x,gy),QPointF(x+bw,gy))
            if style!='traditional' and system.track_voices:
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
            lyric_anchors={}
            for f in fragments:
                accidental=spelling(f.pitch,p.context_at(f.start).tonic,f.note.flat,mode=p.context_at(f.start).mode)[1] if f.note else 0
                underline,dotted,triplet,dashes=fragment_style(f)
                left_extent,right_extent=self.glyph_extents(f)
                cell_left,cell_right=self.glyph_cell(bar,f,points,positions,leading,trailing)
                symbol_scale=system.bar_scales[bar]
                horizontal_scale=symbol_scale
                nx=(cell_left+cell_right)/2 if style=='traditional' else cell_left+self.onset_left(system,bar,f)*horizontal_scale
                lyric_anchors.setdefault((f.track,f.start),nx)
                pitch=f.pitch
                center=baseline-(len(system.pitches)-1)*gap/2
                ny=baseline if style=='traditional' else center if pitch is None else baseline-system.pitch_position(pitch)*gap
                if style=='traditional':ny+=system.voice(f)*system.voice_gap
                self.symbol_boxes.append((f.start,f.end,nx-left_extent*horizontal_scale,nx+right_extent*horizontal_scale,cell_left,cell_right))
                if pitch is None:self.unpitched_positions.append((f.start,'x' if f.ghost else '0',nx,ny))
                self.glyph_sizes.append(('x' if f.ghost else '0' if pitch is None else str(spelling(pitch,p.context_at(f.start).tonic,mode=p.context_at(f.start).mode)[0]),15*symbol_scale))
                painter.save();painter.translate(nx,ny);painter.scale(horizontal_scale,symbol_scale);painter.translate(-nx,-ny)
                rhythm_color=self.melody_color(system,f,INK)
                if f.ghost:
                    self.text(painter,nx,ny,'x',15,rhythm_color,center=True)
                    for ident in f.source_ids:
                        self.hit_notes.append((system.page,QRectF(nx-left_extent*horizontal_scale,ny-27*symbol_scale,(left_extent+right_extent)*horizontal_scale,52*symbol_scale),ident))
                        slur_anchors.setdefault((ident,f.start),(nx,ny-24*symbol_scale,rhythm_color))
                elif f.pitch is None:
                    self.text(painter,nx,ny,'0',15,self.melody_color(system,f,MUTED),center=True)
                    self.rest_positions.append((f.start,f.rest_pitch,nx,ny))
                else:
                    context=p.context_at(f.start)
                    degree,accidental,octave=spelling(f.pitch,context.tonic,f.note.flat,mode=context.mode)
                    in_scale=(f.pitch-context.tonic)%12 in MODES[context.mode]
                    color=self.melody_color(system,f,CHROMATIC if p.notation['color'] and not in_scale else INK)
                    if p.notation['circles'] and is_chord_tone(p,f.pitch,f.start):
                        painter.setPen(QPen(self.color('#6B9C90'),CIRCLE_PEN_WIDTH));painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawEllipse(QPointF(nx,ny-6),CIRCLE_RADIUS_X,CIRCLE_RADIUS_Y)
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
                    painter.setPen(QPen(self.color(rhythm_color),1))
                    uy=ny+self.underline_y(f,system)+k*4
                    painter.drawLine(QPointF(nx-5,uy),QPointF(nx+6,uy))
                dotx=nx+13
                for k in range(dashes):
                    tick=f.start+(k+1)*PPQ
                    if style=='traditional':
                        a,b=self.traditional_cell(bar,tick,points,positions);actual=(a+b)/2
                    else:actual=xpos(tick)+12.5*horizontal_scale
                    dx=nx+(actual-nx)/horizontal_scale
                    self.text(painter,dx,ny,'−',14,rhythm_color,center=True);dotx=dx+12
                if dotted:
                    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(self.color(rhythm_color))
                    radius=1.4
                    actual=nx+(dotx-nx)*horizontal_scale
                    if style=='traditional':
                        text='−' if dashes else 'x' if f.ghost else '0' if f.pitch is None else str(degree)
                        circled=f.pitch is not None and p.notation['circles'] and is_chord_tone(p,f.pitch,f.start)
                        actual,radius=self.traditional_cell_dot(system,bar,f.start+dashes*PPQ,actual,radius*horizontal_scale,text,14 if dashes else 15,circled)
                    else:actual,radius=self.beat_dot(system,bar,f.start+dashes*PPQ,actual,radius*horizontal_scale)
                    dotx=nx+(actual-nx)/horizontal_scale;radius/=horizontal_scale
                    painter.drawEllipse(QPointF(dotx,ny-6),radius,radius)
                group=self.fragment_tuplets.get(id(f))
                if group:tuplet_anchors.setdefault(group,[]).append((f,nx,ny,bar))
                painter.restore()
            if p.notation['lyrics']:
                for event in self.lyrics:
                    if not start<=event['tick']<end or event.get('skip') or not event.get('text'):continue
                    verse=event.get('verse',0);track=event['track']
                    lane=system.lyric_lanes[track,event.get('voice',0),verse]
                    ly=system.top+system.grid_bottom+system.lyric_offset+lane*system.lyric_gap
                    lx=lyric_anchors.get((track,event['tick']))
                    if lx is None:
                        if style=='traditional':
                            a,b=self.traditional_cell(bar,event['tick'],points,positions);lx=(a+b)/2
                        else:lx=xpos(event['tick'])+(SYMBOL_PADDING/2+self.text_width(event['text'],11)/2)*scale+(leading if event['tick']==start else 0)
                    painter.save();painter.translate(lx,ly);painter.scale(scale,scale)
                    color=MELODY_COLORS[track] if style!='traditional' and self.show_melody_colors else INK
                    self.text(painter,0,0,event['text']+('-' if event.get('join_next') else ''),11,color,center=True);painter.restore()
                    self.lyric_positions.append((event['id'],verse,lx,ly))
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
            elif a<first_tick and b>=last_tick:
                # Adjacent MIDI attacks can straddle whole rows of rests or a
                # sustained source note. Keep the lyric arc visible on every
                # intervening row/page, just as a manual phrase annotation is.
                anchors=[value for (ident,tick),value in slur_anchors.items() if ident in (left_id,right_id) and first_tick<=tick<last_tick]
                rest_baseline=baseline if style=='traditional' else baseline-(len(system.pitches)-1)*gap/2
                y=min((value[1] for value in anchors),default=rest_baseline-24*scale)
                kind='through';start=QPointF(system.left+scale,y-4*scale);end=QPointF(x-2,y-2*scale);color=INK
            else:continue
            self.melisma_paths.append((a,b,kind,curve(start,end,color,kind)))
        manual_for_tuplets=[]
        for layer,(index,notes) in enumerate(getattr(system,'manual_slurs',[])):
            a,b=notes[0].start,notes[-1].start
            left=slur_anchors.get((notes[0].id,a));right=slur_anchors.get((notes[-1].id,b))
            anchors=[value for (_,tick),value in slur_anchors.items() if a<=tick<=b]
            y=min((value[1] for value in anchors),default=baseline-24*scale)-(6+6*min(layer,3))*scale
            start=QPointF(left[0]+3*scale,left[1]-6*scale) if left else QPointF(system.left+scale,y)
            end=QPointF(right[0]-3*scale,right[1]-6*scale) if right else QPointF(x-2*scale,y)
            if end.x()<=start.x():continue
            kind='continuous' if left and right else 'outgoing' if left else 'incoming' if right else 'through'
            path=QPainterPath(start);dx=end.x()-start.x();rise=min(16*scale,max(5*scale,dx*.06))
            top=y-rise
            if kind=='incoming':path.cubicTo(QPointF(start.x()+dx*.35,y-rise*.4),QPointF(start.x()+dx*.8,top),end)
            else:path.cubicTo(QPointF(start.x()+dx*.25,top),QPointF(start.x()+dx*.75,top),end)
            painter.setPen(QPen(self.color(INK),1.05*scale));painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawPath(path)
            self.manual_slur_paths.append((index,kind,path));manual_for_tuplets.append((a,b,kind,path))
            self.hit_symbols.append((system.page,path.boundingRect().adjusted(-4*scale,-4*scale,4*scale,4*scale),('symbols',index)))
        self.draw_tuplet_groups(painter,system,tuplet_anchors,self.tie_paths[tie_start:],self.melisma_paths[melisma_start:]+manual_for_tuplets)

    def draw_tuplet_groups(self,painter,system,anchors,ties,melismas):
        scale=system.symbol_scale
        for group in self.tuplet_groups:
            members=anchors.get(group['id'],[])
            if not members:continue
            left=min(nx+min(-7,self.symbol_ink(f,system)[0])*scale for f,nx,_,_ in members)
            right=max(nx+max(7,self.symbol_ink(f,system)[2])*scale for f,nx,_,_ in members)
            left=max(system.fit_left,left);right=min(system.fit_left+system.fit_width,right)
            ink_top=min(self.tuplet_ink_top(f,system,ny) for f,_,ny,_ in members)
            for ident,_,path in ties:
                if ident in group['source_ids']:ink_top=min(ink_top,path.boundingRect().top()-.475*scale)
            for a,b,_,path in melismas:
                if a<group['end'] and b>=group['start']:ink_top=min(ink_top,path.boundingRect().top()-.475*scale)
            top=ink_top-8*scale
            painter.setPen(QPen(self.color(MUTED),.8*scale))
            painter.drawLine(QPointF(left,top),QPointF(right,top))
            painter.drawLine(QPointF(left,top),QPointF(left,top+4*scale))
            painter.drawLine(QPointF(right,top),QPointF(right,top+4*scale))
            painter.fillRect(QRectF((left+right)/2-6*scale,top-8*scale,12*scale,12*scale),self.color('white'))
            painter.save();painter.translate((left+right)/2,top+3*scale);painter.scale(scale,scale)
            self.text(painter,0,0,'3',9,center=True);painter.restore()
            self.tuplet_marks.append(dict(group_id=group['id'],start=group['start'],end=group['end'],source_ids=group['source_ids'],
                fragment_starts=tuple(sorted({f.start for f,_,_,_ in members})),
                fragments=tuple(dict(start=f.start,end=f.end,note_id=f.note.id if f.note else None) for f,_,_,_ in members),
                page=system.page,bars=tuple(system.bars),left=left,right=right,top=top))


def export_pdf(project,path,pages=None):
    project.validate()
    from lingfeng.engraving.compatibility import melody_overlap
    if project.notation['style']=='traditional' and melody_overlap(project):
        raise ValueError('传统简谱仅支持单声部旋律，请使用立体简谱或立体简谱 · 紧凑。')
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
