"""Reference timing: render complete legacy bars and independently intersect."""
import copy

def bar_events(chord,project,start,end):
    events=[]
    for a,b in zip(project.starts,project.starts[1:]):
        if a>=end or b<=start:continue
        full=copy.deepcopy(chord);full.start=a;full.duration=b-a;full.notes=None
        for n in full.render_notes():
            left=max(start,n.start);right=min(end,n.end)
            if left<right:events.append((left,right-left,n.pitch,chord.velocity))
    return sorted(events)
