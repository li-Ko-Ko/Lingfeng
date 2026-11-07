"""Insert a parsed score at a bar boundary without overwriting project music."""

from copy import deepcopy
from dataclasses import replace

from lingfeng.engraving.lyrics import LYRIC_TRACK_KEYS
from lingfeng.engraving.presentation import shift_presentation
from lingfeng.music.meter import splice_events
from lingfeng.music.model import uid
from lingfeng.platform.i18n import tr


def _split_chord(chord, tick, duration):
    """Split only the events that cross the inserted gap."""
    source = replace(chord)
    source.materialize()
    split = tick - chord.start
    left = replace(chord, duration=split, notes=[])
    right = replace(chord, id=uid(), start=tick+duration, duration=chord.duration-split, notes=[])
    for note in source.notes:
        if note.start < split:
            left.notes.append(replace(note, duration=min(note.end, split)-note.start))
        if note.end > split:
            start = max(note.start, split)
            changes = dict(id=uid(), event_id=note.event_id or note.id) if note.start < split else {}
            right.notes.append(replace(note, start=start-split, duration=note.end-start, **changes))
    return left, right


def _existing_chords(chords, tick, duration):
    for chord in chords:
        if chord.end <= tick:
            yield chord
        elif chord.start >= tick:
            yield replace(chord, start=chord.start+duration)
        else:
            yield from _split_chord(chord, tick, duration)


def _move_contexts(contexts, tick, duration):
    for context in contexts:
        if context.end <= tick:
            yield context
        elif context.start >= tick:
            yield replace(context, start=context.start+duration, end=context.end+duration)
        else:
            yield replace(context, end=tick)
            yield replace(context, start=tick+duration, end=context.end+duration)


def _shift_groups(groups, source_groups, tick, duration):
    for name, ranges in groups.items():
        result = []
        for start, end in ranges:
            if start < min(end, tick):
                result.append([start, min(end, tick)])
            if max(start, tick) < end:
                result.append([max(start, tick)+duration, end+duration])
        groups[name] = result
    for name, ranges in source_groups.items():
        groups.setdefault(name, []).extend([start+tick, end+tick] for start, end in ranges)
        groups[name].sort()


def _insert_lyrics(notation, source, tick, duration, new_identity):
    for event_key, section_key in LYRIC_TRACK_KEYS:
        if not any(key in values for key in (event_key, section_key) for values in (notation, source)):
            continue
        items = notation.get(event_key, [])
        right = []
        for event in items:
            start = event['tick']
            if start >= tick:
                event['tick'] += duration
            elif event.get('kind') == 'rap' and start+event['duration'] > tick:
                right.append(dict(event, id=uid(), tick=tick+duration,
                                  duration=start+event['duration']-tick, text='', continuation=True))
                event['duration'] = tick-start
        sections = notation.get(section_key, [])
        for section in sections:
            if section['start'] >= tick:
                section['start'] += duration
            if section.get('end', 0) > tick:
                section['end'] += duration
        section_ids = {section['id']: uid() for section in source.get(section_key, [])}
        for section in source.get(section_key, []):
            item = dict(section, id=section_ids[section['id']], start=section['start']+tick)
            if 'end' in item:
                item['end'] += tick
            sections.append(item)
        for event in source.get(event_key, []):
            item = dict(event, id=new_identity(event['id']), tick=event['tick']+tick)
            if item.get('section_id'):
                section = item['section_id']
                if section not in section_ids:
                    section_ids[section] = uid()
                item['section_id'] = section_ids[section]
            items.append(item)
        notation[event_key] = sorted(items+right, key=lambda item: item['tick'])
        notation[section_key] = sorted(sections, key=lambda item: item['start'])


def insert_project(project, index, imported):
    """Splice all source bars into the destination and return the new tick range.

    The input is a parsed and validated score. Destination title, tempo, names,
    track settings and score preferences continue to describe the open project.
    """
    count = len(imported.measures)
    if type(index) is not int or not 0 <= index <= len(project.measures):
        raise ValueError(tr('插入位置无效。'))
    if not 1 <= count <= 1000-len(project.measures):
        raise ValueError(tr('插入后项目不能超过 1000 小节。'))
    imported.validate()
    # The normal call site uses an independent parsed project. Also support
    # inserting a copy of the currently open project into itself.
    if imported is project:
        imported = deepcopy(imported)
    tick, duration = project.starts[index], imported.end
    identities = {}

    def new_identity(ident):
        if ident not in identities:
            identities[ident] = uid()
        return identities[ident]

    def copy_note(note, offset=0):
        return replace(note, id=new_identity(note.id), start=note.start+offset,
                       event_id=new_identity(note.event_id) if note.event_id else '')

    for track in (0, 1):
        notes = splice_events(project.melody_notes(track), tick, tick+duration)
        notes.extend(copy_note(note, tick) for note in imported.melody_notes(track))
        project.set_melody_notes(track, sorted(notes, key=lambda note: (note.start, note.pitch)))
    chords = list(_existing_chords(project.chords, tick, duration))
    for chord in imported.chords:
        notes = None if chord.notes is None else [copy_note(note) for note in chord.notes]
        chords.append(replace(chord, id=new_identity(chord.id), start=chord.start+tick, notes=notes))
    project.chords = sorted(chords, key=lambda chord: chord.start)
    contexts = list(_move_contexts(project.contexts, tick, duration))
    contexts.extend(replace(c, start=c.start+tick, end=c.end+tick) for c in imported.contexts)
    project.contexts = sorted(contexts, key=lambda context: context.start)

    shift_presentation(project, index, tick, duration, count=count)
    _insert_lyrics(project.notation, imported.notation, tick, duration, new_identity)
    for symbol in imported.notation.get('symbols', []):
        item = dict(symbol, start=symbol['start']+tick, end=symbol['end']+tick)
        if 'note_ids' in symbol:
            item['note_ids'] = [new_identity(ident) for ident in symbol['note_ids']]
        project.notation.setdefault('symbols', []).append(item)
    _shift_groups(project.groups, imported.groups, tick, duration)
    project.measures[index:index] = [replace(measure) for measure in imported.measures]
    project.marks = sorted({0, *(mark+count if mark >= index else mark for mark in project.marks),
                            *(index+mark for mark in imported.marks)})
    project.fill_chord_gaps()
    project.rescan_instrument_recognition()
    project.validate()
    return tick, tick+duration
