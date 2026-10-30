"""Pitch-class template matching, informed by PyChord's root-rotation algorithm.

Independent implementation: octave duplicates are removed, every present root is
tested against exact interval sets, then candidates are ranked by previous symbol
and bass position. No guessed label is assigned to an unmatched set.
See docs/REFERENCES.md for upstream algorithm and license information.
"""
from dataclasses import dataclass
from .model import QUALITIES, Chord


@dataclass(frozen=True)
class Candidate:
    root: int
    quality: str
    bass: int | None

    @property
    def name(self):
        return Chord(0,960,self.root,self.quality,self.bass).name

    @property
    def inversion(self):
        """Chord-tone index of the bass; None for a non-chord slash bass."""
        interval=0 if self.bass is None else (self.bass-self.root)%12
        tones=[x%12 for x in QUALITIES[self.quality]]
        return tones.index(interval) if interval in tones else None


def chord_inversion(chord):
    """Verify the existing symbol and its actual voicing before moving it."""
    if not chord.recognized:return None
    pitches=chord.pitches if chord.notes is None else [n.pitch for n in chord.notes]
    candidate=next((c for c in recognize(pitches) if (c.root,c.quality)==(chord.root%12,chord.quality)),None)
    return candidate.inversion if candidate else None


def recognize(pitches, preferred=None):
    if not pitches:return []
    pcs={p%12 for p in pitches};bass=min(pitches)%12
    result=[]
    for root in sorted(pcs):
        intervals={(p-root)%12 for p in pcs}
        for quality,template in QUALITIES.items():
            if intervals=={v%12 for v in template}:
                result.append(Candidate(root,quality,None if bass==root else bass))
    return sorted(result,key=lambda c:(0 if (c.root,c.quality)==preferred else 1,
                                       c.root!=bass,len(QUALITIES[c.quality]),c.root,c.quality))


def update_symbol(chord, candidates):
    chord.recognized=bool(candidates)
    if candidates:
        c=candidates[0];chord.root=48+c.root;chord.quality=c.quality;chord.bass=c.bass
