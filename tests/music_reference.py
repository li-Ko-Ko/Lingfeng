"""Reference timing: render complete legacy bars and independently intersect."""
import copy
from lingfeng.music.model import Note, PPQ

def bar_events(chord,project,start,end):
    events=[]
    for a,b,measure in zip(project.starts,project.starts[1:],project.measures):
        if a>=end or b<=start:continue
        full=copy.deepcopy(chord);full.start=a;full.duration=b-a;full.notes=None
        if chord.pattern=='sustained_bass_beats':
            beat=4*PPQ//measure.denominator
            played=[Note(a,b-a,full.pitches[0])]
            played.extend(Note(a+i*beat,beat,pitch) for i in range(measure.numerator) for pitch in full.pitches[1:])
        else:played=full.render_notes()
        for n in played:
            left=max(start,n.start);right=min(end,n.end)
            if left<right:events.append((left,right-left,n.pitch,chord.velocity))
    return sorted(events)
