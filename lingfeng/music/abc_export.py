"""Write standard interchange ABC or the native two-voice SheetSage2 dialect."""

from bisect import bisect_right
from fractions import Fraction
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from lingfeng.engraving.lyrics import events, lyric_track
from lingfeng.music.abc_import import _key
from lingfeng.music.abc_sections import normalize_section_mappings, section_key, section_lookup
from lingfeng.music.chord_spelling import tone_for
from lingfeng.music.model import FLAT, PPQ, QUALITIES, SHARP, section_name
from lingfeng.music.quality_catalog import YUE2_QUALITIES, yue2_lossless_quality
from lingfeng.platform.i18n import tr


YUE2_ABC_QUALITIES = tuple('m(maj7)' if q == 'mM7' else q for q in YUE2_QUALITIES)
_PITCH = r'[A-G](?:bb|##|b|#)?'
_YUE2_CHORD = re.compile(_PITCH + '(?:' + '|'.join(map(re.escape, YUE2_ABC_QUALITIES))
                         + ')(?:/' + _PITCH + ')?')


def valid_yue2_chord(symbol):
    return isinstance(symbol, str) and (not symbol or _YUE2_CHORD.fullmatch(symbol) is not None)


def abc_location(project, tick):
    starts = project.starts
    bar = min(len(project.measures), bisect_right(starts, tick))
    measure = project.measures[bar-1]
    beat = 1 + (tick-starts[bar-1]) * measure.denominator / (4*PPQ)
    return tr('第 {0} 小节，第 {1} 拍', bar, f'{beat:g}')


def abc_track_project(project, which):
    from copy import copy
    from lingfeng.audio.midi import selected_roles
    roles = selected_roles(which)
    result = copy(project)
    result.notation = project.notation.copy()
    for role, notes, prefix in (('melody', 'notes', ''), ('instrument', 'instrument_notes', 'instrument_')):
        if role not in roles:
            setattr(result, notes, [])
            for key in ('lyric_events', 'lyric_sections'):
                result.notation[prefix + key] = []
    if 'chords' not in roles:
        result.chords = []
    return result


_WHOLE = 4 * PPQ
_DURATIONS = (48, 32, 24, 16, 12, 8, 6, 4, 3, 2, 1)
_MODE_SUFFIX = {'Ionian': '', 'Aeolian': 'm', 'Dorian': 'dor', 'Phrygian': 'phr',
                'Lydian': 'lyd', 'Mixolydian': 'mix'}


def _key_symbol(context):
    pc = context.tonic % 12
    suffix = _MODE_SUFFIX[context.mode]
    candidates = [name+suffix for name in dict.fromkeys((SHARP[pc], FLAT[pc]))]
    return min(candidates, key=lambda symbol: sum(map(abs, _key(symbol)[2].values())))


def _sheet_quality(quality):
    lossless = yue2_lossless_quality(quality)
    if lossless is not None:
        return lossless
    pitches = {pitch % 12 for pitch in QUALITIES[quality]}

    def distance(candidate):
        tones = {pitch % 12 for pitch in QUALITIES[candidate]}
        return len(pitches ^ tones), len(tones - pitches)

    return min(YUE2_QUALITIES, key=distance)


def sheetsage_chord_changes(project):
    changes = []
    for chord in sorted(project.chords, key=lambda chord: chord.start):
        if chord.empty:
            continue
        original = chord.display_symbol and _symbol(project, chord, False) or tr('未识别')
        converted = _symbol(project, chord, True)
        if chord.display_symbol is None or yue2_lossless_quality(chord.display_symbol.quality) is None:
            changes.append((chord.start, original, converted))
    return changes


def _grid_ticks(project):
    ticks = {*project.starts, *(c.start for c in project.contexts)}
    for notes in (project.notes, project.instrument_notes, [c for c in project.chords if not c.empty]):
        for note in notes:
            ticks.update((note.start, note.end))
    return ticks


def _grid(project):
    ticks = _grid_ticks(project)
    return next((d for d in (32, 64, 128, 256, 512, 1024) if all(t*d % _WHOLE == 0 for t in ticks)), None)


def sheetsage_issues(project):
    issues = []
    if not (project.notes or project.instrument_notes or any(not c.empty for c in project.chords)):
        issues.append(tr('所选轨道没有可导出的旋律音符或和弦。'))
    modes = [context for context in project.contexts if context.mode not in ('Ionian', 'Aeolian')]
    if modes:
        issues.append(tr('YuE2 仅支持大调和小调。首处不支持的调式为 {0}（{1}）。',
                         modes[0].mode, abc_location(project, modes[0].start)))
    for track, notes in enumerate((project.notes, project.instrument_notes)):
        ordered = sorted(notes, key=lambda n: n.start)
        overlap = next((b for a, b in zip(ordered, ordered[1:]) if a.end > b.start), None)
        if overlap:
            issues.append(tr('{0} 有重叠音符（首处在{1}）。请整理成单声部，或取消导出该轨。',
                             project.melody_name(track), abc_location(project, overlap.start)))
    off_grid = sorted(t for t in _grid_ticks(project) if t*1024 % _WHOLE)
    if off_grid:
        issues.append(tr('有 {0} 个时点落在 YuE2 的二分时间格点之外（首处在{1}）。请调整音符、和弦或调性边界。',
                         len(off_grid), abc_location(project, off_grid[0])))
    return issues


def sheetsage_reason(project):
    return next(iter(sheetsage_issues(project)), '')


def _symbol(project, chord, sheetsage):
    if chord is None or chord.empty or (symbol := chord.display_symbol) is None:
        return '' if sheetsage else 'N.C.'
    context = project.context_at(chord.start + chord.duration//2 if sheetsage else chord.start)
    quality = _sheet_quality(symbol.quality) if sheetsage else symbol.quality
    if quality == 'mM7':
        quality = 'm(maj7)'
    bass = '/' + tone_for(symbol.bass, context, chord).name if symbol.bass is not None else ''
    return tone_for(symbol.root, context, chord).name + quality + bass


def _symbols(project, start, end, sheetsage, overrides):
    changes = {}
    for chord in project.chords:
        if sheetsage and chord.empty:
            continue
        if start <= chord.end < end:
            changes[chord.end] = '' if sheetsage else 'N.C.'
    for chord in project.chords:
        if sheetsage and chord.empty:
            continue
        if start <= chord.start < end or sheetsage and chord.start < start < chord.end:
            changes[max(chord.start, start)] = overrides.get(chord.start, _symbol(project, chord, sheetsage))
    return changes


def _pitch(pitch, signature, accidentals, sheetsage, flat=False, explicit=False):
    # Spell in the active key when possible. Otherwise preserve explicit flat
    # preferences and use one accidental whose state matches the chosen dialect.
    choices = [name for name in dict.fromkeys(((FLAT if flat else SHARP)[pitch%12],
                                               (SHARP if flat else FLAT)[pitch%12]))]
    name = next((name for name in choices
                 if signature.get(name[0], 0) == name.count('#') - name.count('b')), choices[0])
    letter, alter = name[0], name.count('#') - name.count('b')
    natural = pitch - alter
    octave = (natural - 60) // 12
    text = letter if octave <= 0 else letter.lower()
    text += ',' * -octave if octave < 0 else "'" * max(0, octave-1)
    slot = letter if sheetsage else natural
    if explicit or accidentals.get(slot, signature.get(letter, 0)) != alter:
        text = {-1: '_', 0: '=', 1: '^'}[alter] + text
        accidentals[slot] = alter
    return text


def _duration_chunks(duration, denominator, sheetsage):
    units = Fraction(duration * denominator, _WHOLE)
    if not sheetsage:
        yield '' if units == 1 else str(units)
        return
    remaining = int(units)
    for value in _DURATIONS:
        count, remaining = divmod(remaining, value)
        yield from (str(value) if value != 1 else '' for _ in range(count))


def _bar(notes, start, end, key, key_changes, symbols, denominator, sheetsage, lyrics):
    if not notes and not key_changes and not any(symbols.values()):
        return 'Z', []
    onsets = {}
    for note in notes:
        onsets.setdefault(max(start, note.start), []).append(note)
    boundaries = sorted({start, end, *onsets, *key_changes, *symbols,
                         *(note.end for note in notes if note.end < end)})
    active, syllables, output, accidentals = {}, [], [], {}
    signature = _key(key)[2]
    for left, right in zip(boundaries, boundaries[1:]):
        active = {pitch: note for pitch, note in active.items() if note.end > left}
        active.update((note.pitch, note) for note in onsets.get(left, []))
        if left in key_changes:
            symbol = key_changes[left]
            signature = _key(symbol)[2]
            accidentals.clear()
            output.append(f'[K:{symbol}]')
        if symbols.get(left):
            output.append(f'"{symbols[left]}"')
        durations = list(_duration_chunks(right-left, denominator, sheetsage))
        for index, duration in enumerate(durations):
            if not active:
                output.append('z'+duration)
                continue
            ordered = sorted(active.values(), key=lambda note: note.pitch)
            # Within a stack, make accidentals explicit so a fresh natural
            # cannot be mistaken for a neighboring chromatic tie continuation.
            names = [_pitch(note.pitch, signature, accidentals, sheetsage, note.flat, explicit=len(ordered)>1)
                     for note in ordered]
            ties = ['-' if note.end > right or index+1 < len(durations) else '' for note in ordered]
            if len(ordered) == 1:
                output.append(names[0]+duration+ties[0])
            else:
                output.append('['+''.join(name+tie for name, tie in zip(names, ties))+']'+duration)
            syllables.append(lyrics.get(left, '*') if index == 0 and any(n.start == left for n in ordered) else '*')
    return ''.join(output), syllables


def _text(text, specials='%'):
    return ''.join(f'\\u{ord(char):04x}' if char in specials or char == '\\' else char
                   for char in ' '.join(text.split()))


def _lyrics(project, track):
    syllables = {}
    for event in events(lyric_track(project, track)):
        if event.get('verse', 0) or event.get('voice', 0) or event.get('kind') not in (None, '', 'note', 'skip'):
            continue
        if event.get('melisma'):
            syllables[event['tick']] = '_'
        elif event.get('skip'):
            syllables[event['tick']] = '*'
        elif event['text'].strip():
            # Tildes keep legacy text assigned to a single note together.
            text = _text(event['text'], '%_*|~').replace('-', '\\-').replace(' ', '~')
            syllables[event['tick']] = text + ('-' if event.get('join_next') else '')
    return syllables


def _voice_bars(notes, starts):
    cursor, active = 0, []
    notes = sorted(notes, key=lambda n: n.start)
    for start, end in zip(starts, starts[1:]):
        active = [note for note in active if note.end > start]
        while cursor < len(notes) and notes[cursor].start < end:
            active.append(notes[cursor])
            cursor += 1
        yield active


def serialize_abc(project, *, sheetsage=False, section_mapping=None, which='both',
                  chord_overrides=None, convert_chords=True):
    from lingfeng.audio.midi import selected_roles
    roles = selected_roles(which)
    project = abc_track_project(project, roles)
    overrides = (chord_overrides or {}) if sheetsage else {}
    if any(not valid_yue2_chord(symbol) for symbol in overrides.values()):
        raise ValueError(tr('替换和弦必须符合 YuE2 和弦格式。'))
    if sheetsage and (reason := sheetsage_reason(project)):
        raise ValueError(reason)
    if sheetsage and not convert_chords and any(
            tick not in overrides for tick, _, _ in sheetsage_chord_changes(project)):
        raise ValueError(tr('请逐处填写或省略 YuE2 不支持的和弦符号。'))
    denominator = _grid(project) if sheetsage else 32
    if not project.notes and not project.instrument_notes and not project.harmony_notes() and not any(c.marked for c in project.chords):
        raise ValueError(tr('当前工程没有可导出的 ABC 音符或和弦。'))
    starts = project.starts
    mappings = normalize_section_mappings({'export': section_mapping})['export']
    labels = section_lookup(mappings)
    keys = {}
    for context in sorted(project.contexts, key=lambda item: item.start):
        symbol = _key_symbol(context)
        if not keys or symbol != next(reversed(keys.values())):
            keys[context.start] = symbol
    key = keys[0]
    first = project.measures[0]
    lines = [] if sheetsage else ['%abc-2.1', '%%propagate-accidentals octave']
    lines.extend(['X:1', 'T:' + ('' if sheetsage else _text(project.title))])
    if not sheetsage and project.author:
        lines.append('C:' + _text(project.author))
    lines.extend([f'M:{first.numerator}/{first.denominator}', f'L:1/{denominator}', f'Q:1/4={project.bpm}'])
    names = ('Vocal Melody', 'Ins Melody') if sheetsage else project.melody_names
    voices = []
    lyrics = []
    for track, (role, ident, name, short, notes) in enumerate(zip(
            ('melody', 'instrument'), ('Vocal', 'Ins'), names, ('Vocal', 'Inst.'),
            (project.notes, project.instrument_notes))):
        if not sheetsage and role not in roles:
            continue
        lines.append(f'V: {ident} clef=treble name="{_text(name, chr(34))}" snm="{short}"')
        voices.append((ident, notes))
        lyrics.append({} if sheetsage else _lyrics(project, track))
    if not sheetsage and 'chords' in roles:
        lines.append('V: Chord clef=bass name="Harmony"')
        voices.append(('Chord', project.harmony_notes()))
        lyrics.append({})
    lines.append(f'K:{key}')
    streams = [_voice_bars(notes, starts) for _, notes in voices]
    meter = first.numerator, first.denominator
    for start, end, measure in zip(starts, starts[1:], project.measures):
        next_meter = measure.numerator, measure.denominator
        bar_key = keys.get(start, key)
        changes = {tick: symbol for tick, symbol in keys.items() if start < tick < end}
        if measure.section:
            section = section_name(measure.section)
            label = labels.get(section_key(section), section)
            prefix = '% ' if sheetsage else '% section: '
            lines.append(prefix + ' '.join(label.split()))
        for track, (ident, _) in enumerate(voices):
            lines.append(f'V: {ident}')
            if next_meter != meter:
                lines.append(f'M:{next_meter[0]}/{next_meter[1]}')
            if bar_key != key:
                lines.append(f'K:{bar_key}')
            if not sheetsage and start==0 and track==0:
                # abc2midi ignores this command outside the tune. Keep the
                # displayed symbols from generating a second accompaniment.
                lines.append('%%MIDI gchordoff')
            symbols = _symbols(project, start, end, sheetsage, overrides) if track == 0 and 'chords' in roles else {}
            music, syllables = _bar(next(streams[track]), start, end, bar_key, changes, symbols,
                                    denominator, sheetsage, lyrics[track])
            lines.append(music+'|')
            if any(syllable != '*' for syllable in syllables):
                lines.append('w: '+' '.join(syllables))
            elif syllables and lyrics[track]:
                # In ABC 2.1, reserve these note slots before the next lyric line.
                lines.append('w:')
        meter = next_meter
        key = next(reversed(changes.values())) if changes else bar_key
    return '\n'.join(lines)+'\n'


def write_abc(project, path, **options):
    path = Path(path)
    data = serialize_abc(project, **options)
    temporary = None
    try:
        with NamedTemporaryFile(mode='w', dir=path.parent, prefix=path.name+'.',
                                suffix='.tmp', delete=False, encoding='utf-8', newline='\n') as file:
            temporary = Path(file.name)
            file.write(data)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
