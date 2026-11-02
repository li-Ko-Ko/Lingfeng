"""Original melody onsets and exact half-open occupancy, independent of notation."""
from dataclasses import dataclass
from itertools import groupby


@dataclass(frozen=True)
class NoteSpan:
    note_id: str
    start: int
    end: int
    pitch: int


@dataclass(frozen=True)
class Onset:
    tick: int
    notes: tuple[NoteSpan, ...]


@dataclass(frozen=True)
class Overlap:
    start: int
    end: int
    notes: tuple[NoteSpan, ...]


def group_onsets(notes):
    """Group attacks without merging notes, rounding time, or changing IDs."""
    spans=sorted((NoteSpan(n.id,n.start,n.end,n.pitch) for n in notes),
                 key=lambda n:(n.start,n.pitch,n.end,n.note_id))
    return tuple(Onset(tick,tuple(group)) for tick,group in groupby(spans,key=lambda n:n.start))


def overlap_conflicts(notes):
    """Return every interval with multiple source notes; adjacent ends are legal.

    End events are processed before attacks at the same tick. The returned
    spans keep the complete original note bounds, including short MIDI tails.
    """
    starts={};ends={}
    for onset in group_onsets(notes):
        for note in onset.notes:
            if note.end<=note.start:continue
            starts.setdefault(note.start,[]).append(note)
            ends.setdefault(note.end,[]).append(note)
    ticks=sorted(starts.keys()|ends.keys());active={};result=[]
    for tick,next_tick in zip(ticks,ticks[1:]):
        for note in ends.get(tick,()):active.pop(note.note_id,None)
        for note in starts.get(tick,()):active[note.note_id]=note
        if len(active)>1:
            result.append(Overlap(tick,next_tick,tuple(sorted(active.values(),
                key=lambda n:(n.start,n.pitch,n.end,n.note_id)))))
    return tuple(result)


def is_monophonic(notes):
    return not overlap_conflicts(notes)
