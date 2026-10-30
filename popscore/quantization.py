"""Explicit-grid quantization with conservative, local triplet detection.

Inspired by music21 Stream.quantize's candidate grids and duration look-ahead;
implemented independently using integer ticks. No inference for keyboard input.
"""
import copy
from .model import PPQ


def nearest(tick,grid,origin=0):
    return origin+((int(tick)-origin+grid//2)//grid)*grid


def quantize_notes(notes,grid=240,protect_triplets=False,origin=0,starts=None):
    if not grid:return copy.deepcopy(notes)
    if grid<20:raise ValueError('量化格点过小。')
    source=sorted(notes,key=lambda n:(n.start,n.pitch));result=[]
    triplet=max(20,round(grid*2/3));triplet_beats=set()
    if protect_triplets:
        groups={}
        for n in source:groups.setdefault((n.start-origin)//PPQ,set()).add(n.start)
        for beat,onsets in groups.items():
            base=origin+beat*PPQ
            candidates=[t for t in onsets if abs(t-nearest(t,grid,base))>grid*.18 and abs(t-nearest(t,triplet,base))<triplet*.18]
            straight=sum(abs(t-nearest(t,grid,base)) for t in onsets)
            swung=sum(abs(t-nearest(t,triplet,base)) for t in onsets)
            if len({nearest(t,triplet,base) for t in candidates})>=2 and swung<straight*.6:triplet_beats.add(beat)
    def spacing(t):return triplet if (t-origin)//PPQ in triplet_beats else grid
    def anchor(t):return max((x for x in starts or [origin] if x<=t),default=origin)
    onsets=sorted({n.start for n in source})
    for old in source:
        n=copy.deepcopy(old);step=spacing(old.start);base=anchor(old.start)
        n.start=max(origin,nearest(old.start,step,base))
        end=nearest(old.end,step,base)
        following=next((t for t in onsets if t>old.start),None)
        # Only close a performance-sized gap, never erase an intentional rest.
        if following is not None and abs(old.end-following)<=step*.18:
            end=nearest(following,spacing(following),anchor(following))
        n.duration=max(step,end-n.start);result.append(n)
    return result
