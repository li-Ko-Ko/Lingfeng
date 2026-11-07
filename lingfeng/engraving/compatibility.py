"""Score-style restrictions apply only to the melodies shown on the score."""
from lingfeng.music.onsets import overlap_conflicts


def traditional_conflicts(project, notation=None):
    """Return exact overlaps in enabled melody tracks without changing notes."""
    notation=project.notation if notation is None else notation
    result={}
    for track,key in enumerate(('show_melody','show_instrument')):
        if not notation.get(key,True):continue
        conflicts=overlap_conflicts(project.melody_notes(track))
        if conflicts:result[track]=conflicts
    return result


def melody_overlap(project, notation=None):
    return bool(traditional_conflicts(project,notation))
