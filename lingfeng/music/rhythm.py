"""Pattern recognition is independent of note storage, voicing and dynamics.

The bounded cache includes musical content and bar phase, so each edit is reflected
immediately. Recognition never edits MIDI; region edits rebuild named patterns.
"""
import copy
from dataclasses import dataclass
from functools import lru_cache
from lingfeng.music.model import PPQ, PATTERNS, Note, uid
from lingfeng.platform.i18n import tr

# Explicit compatibility metadata for the current generators. Compound meters
# use eighth-note textures; alternating bass/chord and offbeats require complete
# two-quarter groups. Sustain works with every meter supported by the editor.
# Root/fifth bass follows the denominator and requires an even numerator.
ALL_METERS=frozenset((n,d) for n in range(1,17) for d in (2,4,8,16))
ALTERNATING=('alternating_quarters','alternating_eighths','alternating_offbeat')
PATTERN_METERS={
    'block':ALL_METERS,
    'quarters':frozenset((n,d) for n,d in ALL_METERS if d in (2,4)),
    **{p:frozenset((n,d) for n,d in ALL_METERS if (PPQ*4*n//d)%(PPQ//2)==0) for p in ('eighths','up','down')},
    **{p:frozenset((n,d) for n,d in ALL_METERS if d in (2,4) and (4*n//d)%2==0) for p in ('alberti','bass_chord','offbeat')},
    **{p:frozenset((n,d) for n,d in ALL_METERS if n%2==0) for p in ALTERNATING},
}


def supports(pattern,project,tick):
    from lingfeng.music.meter import signature
    return signature(project,tick) in PATTERN_METERS.get(pattern,())


def supported_patterns(project,tick):
    return tuple(p for p in PATTERNS if project is None or supports(p,project,tick))


@dataclass(frozen=True)
class Rhythm:
    pattern:str
    pitches:tuple
    gate:float

    def events(self,duration,beat=PPQ):
        if self.pattern in ALTERNATING:
            if len(self.pitches)<2:return
            bass,*upper=self.pitches
            # The fifth belongs to the chord: diminished/augmented qualities
            # retain their altered fifth rather than acquiring a foreign tone.
            fifth=next((p for p in upper if (p-upper[0])%12 in (6,7,8)),upper[0]+7)-12
            for index,t in enumerate(range(0,duration,beat)):
                yield t,min(duration-t,max(1,round(beat*self.gate))),bass if index%2==0 else fifth
            step=PPQ if self.pattern=='alternating_quarters' else PPQ//2
            offset=beat//2 if self.pattern=='alternating_offbeat' else 0
            if self.pattern=='alternating_offbeat':spacing=beat;step=beat//2
            else:spacing=step
            for t in range(offset,duration,spacing):
                for pitch in upper:yield t,min(duration-t,max(1,round(step*self.gate))),pitch
            return
        step=duration if self.pattern=='block' else PPQ if self.pattern in ('quarters','bass_chord','offbeat') else PPQ//2
        offset=PPQ//2 if self.pattern=='offbeat' else 0
        for index,t in enumerate(range(offset,duration,step)):
            pitches=self.pitches
            if self.pattern in ('up','down'):
                order=pitches if self.pattern=='up' else pitches[::-1];pitches=(order[index%len(order)],)
            elif self.pattern=='alberti':pitches=((pitches[0],pitches[-1],pitches[1],pitches[-1])[index%4],)
            elif self.pattern=='bass_chord':pitches=pitches[:1] if index%2==0 else pitches[1:]
            length=min(duration-t,step if self.pattern=='block' else max(1,round(step*self.gate)))
            for pitch in pitches:yield t,length,pitch


@lru_cache(maxsize=512)
def _recognize(duration,hint,gate,canonical,notes):
    if not notes:return None
    actual=tuple(sorted(notes));actual_onsets=tuple(sorted({t for t,d,p in notes}))
    used=tuple(sorted({p for t,d,p in notes}))
    # Prefer the existing pattern for short/ambiguous fragments. An exact match
    # to the existing full voicing preserves the intended arpeggio after cropping.
    voicings=tuple(dict.fromkeys((canonical,used)))
    for pattern in dict.fromkeys((hint,*PATTERNS)):
        step=duration if pattern=='block' else PPQ if pattern in ('quarters','bass_chord','offbeat','alternating_quarters') else PPQ//2
        offset=PPQ//2 if pattern=='offbeat' else 0
        if actual_onsets!=tuple(range(offset,duration,step)):continue
        full_lengths={d for t,d,p in notes if t+d<duration}
        if pattern!='block' and pattern not in ALTERNATING and len(full_lengths)>1:continue
        gates=(gate,) if pattern=='block' else tuple(dict.fromkeys((gate,*(d/step for d in full_lengths),*(d/PPQ for d in full_lengths if pattern in ALTERNATING),1.0)))
        for pitches in voicings:
            if pattern in ('alberti','bass_chord') and len(pitches)<2:continue
            for candidate_gate in gates:
                if not .05<=candidate_gate<=1:continue
                rhythm=Rhythm(pattern,pitches,candidate_gate)
                if tuple(sorted(rhythm.events(duration)))==actual:return rhythm
    return None


def bar_grid(start,end,project=None):
    if project is None:
        return tuple((a-start,4*PPQ,PPQ) for a in range(start//(4*PPQ)*(4*PPQ),end,4*PPQ))
    starts=project.starts
    return tuple((a-start,b-a,PPQ*4//m.denominator) for a,b,m in zip(starts,starts[1:],project.measures) if a<end and b>start)


def clipped_bar_events(rhythm,duration,bars):
    for origin,length,beat in bars:
        for t,d,pitch in rhythm.events(length,beat):
            a=max(0,origin+t);b=min(duration,origin+t+d)
            if a<b:yield a,b-a,pitch


@lru_cache(maxsize=512)
def _recognize_bar(duration,bars,hint,gate,canonical,notes,allowed=tuple(PATTERNS)):
    actual=tuple(sorted(notes));used=tuple(sorted({p for t,d,p in notes}))
    for pattern in dict.fromkeys((hint,*PATTERNS)):
        if pattern not in allowed:continue
        if not notes and pattern!=hint:continue
        step=PPQ if pattern in ('quarters','bass_chord','offbeat','alternating_quarters') else PPQ//2
        lengths=tuple({step,*(beat for _,_,beat in bars),*(beat//2 for _,_,beat in bars)}) if pattern in ALTERNATING else (step,)
        gates=(gate,) if pattern=='block' else tuple(dict.fromkeys((gate,1.0,*(d/unit for t,d,p in notes for unit in lengths if .05<=d/unit<=1))))
        for pitches in dict.fromkeys((canonical,used)):
            if not pitches or pattern in ('alberti','bass_chord') and len(pitches)<2:continue
            for g in gates:
                rhythm=Rhythm(pattern,pitches,g)
                if tuple(sorted(clipped_bar_events(rhythm,duration,bars)))==actual:return rhythm
    return None


def analyze(chord,project=None):
    if chord.custom_rhythm or not chord.recognized:return None
    if chord.notes is None:
        return Rhythm(chord.pattern,tuple(chord.pitches),chord.gate) if chord.pattern in supported_patterns(project,chord.start) else None
    if chord.recognized:
        match=_recognize_bar(chord.duration,bar_grid(chord.start,chord.end,project),chord.pattern,chord.gate,
            tuple(chord.pitches),tuple(sorted((n.start,n.duration,n.pitch) for n in chord.notes)),supported_patterns(project,chord.start))
        if match:return match
        if project is not None:
            # A genuine continuous sustain may span bar lines without retriggers.
            match=_recognize(chord.duration,'block',chord.gate,tuple(chord.pitches),tuple(sorted((n.start,n.duration,n.pitch) for n in chord.notes)))
            if match and (match.pattern=='block' or not chord.bar_aligned and supports(match.pattern,project,chord.start)):return match
            return None
    return _recognize(chord.duration,chord.pattern,chord.gate,tuple(chord.pitches),
                      tuple(sorted((n.start,n.duration,n.pitch) for n in chord.notes)))


def label(chord,project=None):
    if not chord.recognized:return tr('未知节奏型')
    if chord.custom_rhythm:return tr('自定义（锁定）')
    rhythm=analyze(chord,project)
    return tr(PATTERNS[rhythm.pattern]) if rhythm else tr('未知节奏型')


def analyze_performed(chord,project=None):
    """Identify the played fragment before replacing a chord's root/quality.

    Unlike region editing, regeneration must not infer a texture from voices
    omitted by the old chord. A lone gated bass pulse is a quarter block here,
    even if it was previously cropped from a bass/chord alternation.
    """
    if chord.custom_rhythm or not chord.recognized:return None
    if chord.notes is None:return analyze(chord,project)
    if chord.pattern in ALTERNATING:
        match=analyze(chord,project)
        if match and match.pattern in ALTERNATING:return match
    notes=tuple(sorted((n.start,n.duration,n.pitch) for n in chord.notes))
    used=tuple(sorted({n.pitch for n in chord.notes}))
    if not used:return None
    match=_recognize_bar(chord.duration,bar_grid(chord.start,chord.end,project),chord.pattern,chord.gate,
                         used,notes,supported_patterns(project,chord.start))
    if match:return match
    match=_recognize(chord.duration,chord.pattern,chord.gate,used,notes)
    return match if match and match.pattern in supported_patterns(project,chord.start) else None


def regenerate(chord,start,end,project=None,rhythm=None):
    """Rebuild named patterns from full bars, then crop; reset per-note edits."""
    if not chord.recognized or chord.custom_rhythm:return None
    rhythm=rhythm or analyze(chord,project)
    if rhythm is None:return None
    if project is not None and not supports(rhythm.pattern,project,start):return None
    if project is not None:
        from lingfeng.music.meter import region_at
        end=min(end,region_at(project,start)[1])
    # A rhythmic match alone does not establish a complete chord name. Keep
    # incomplete/custom voicings intact unless they match the declared template.
    if {p%12 for p in rhythm.pitches}!={p%12 for p in chord.pitches}:return None
    result=copy.deepcopy(chord);result.start=start;result.duration=end-start
    result.bar_aligned=True
    result.pattern=rhythm.pattern;result.gate=rhythm.gate
    template=Rhythm(result.pattern,tuple(result.pitches),result.gate)
    result.notes=[Note(t,d,p,result.velocity) for t,d,p in clipped_bar_events(template,result.duration,bar_grid(start,end,project))]
    return result


def extend(chord,start,end,rhythm=None):
    """Regenerate the recognized rhythm using its actual pitches and velocities."""
    rhythm=rhythm or analyze(chord)
    if rhythm is None:return None
    result=copy.deepcopy(chord);result.start=start;result.duration=end-start;result.pattern=rhythm.pattern;result.gate=rhythm.gate
    source=chord.render_notes();by_event={(n.start,n.pitch):n for n in source};by_pitch={n.pitch:n for n in source}
    result.notes=[]
    for t,d,pitch in rhythm.events(result.duration):
        old=by_event.get((start+t,pitch));reference=old or by_pitch.get(pitch)
        result.notes.append(Note(t,d,pitch,reference.velocity if reference else chord.velocity,id=old.id if old else uid()))
    # Keep the compact generated representation only when it is lossless.
    candidate=copy.deepcopy(result);candidate.notes=None
    signature=lambda notes:sorted((n.start,n.duration,n.pitch,n.velocity) for n in notes)
    if signature(candidate.render_notes())==signature(result.render_notes()):return candidate
    return result
