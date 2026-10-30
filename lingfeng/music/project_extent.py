"""Extend a project with its current meter without importing a MIDI reader."""
import copy
from lingfeng.music.model import Measure

def extend_project(project,end):
    previous=project.end
    while project.end<end:
        if len(project.measures)>=1000:raise ValueError('导入后超过 1000 小节。')
        m=project.measures[-1];project.measures.append(Measure(m.numerator,m.denominator))
    if project.end>previous:
        c=copy.deepcopy(project.contexts[-1]);c.start=previous;c.end=project.end;project.contexts.append(c)
