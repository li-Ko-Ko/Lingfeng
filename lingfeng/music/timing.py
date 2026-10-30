"""Shared, meter-aware grid for drawing, snapping and time selection."""
from bisect import bisect_right


def grid_points(project, step, bars=0):
    if bars:return list(project.starts[::bars])+([project.end] if project.end not in project.starts[::bars] else [])
    return [tick for a,b in zip(project.starts,project.starts[1:]) for tick in range(a,b,max(1,step))]+[project.end]


def grid_bucket(project, tick, step, bars=0):
    points=grid_points(project,step,bars);i=max(0,min(len(points)-2,bisect_right(points,tick)-1))
    return points[i:i+2]


def snap_time(project,tick,step,bars=0):
    a,b=grid_bucket(project,tick,step,bars)
    return a if tick-a<b-tick else b


def selected_measures(project,ranges):
    return [i for i,(a,b) in enumerate(zip(project.starts,project.starts[1:])) if any(x<b and y>a for x,y in ranges)]
