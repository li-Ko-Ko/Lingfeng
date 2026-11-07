"""Read MusicXML and map its written timeline to project tracks."""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from fractions import Fraction
import json
from math import ceil
from pathlib import Path, PurePosixPath
import re
from xml.etree import ElementTree as ET
import zipfile

from lingfeng.engraving.lyrics import LYRIC_TRACK_KEYS
from lingfeng.music.abc_sections import imported_section, normalize_section_mappings, section_lookup
from lingfeng.music.model import Chord, Context, MELODY_NAMES, MODES, Measure, Note, PPQ, Project, QUALITIES, uid
from lingfeng.music.note_operations import overwrite_note
from lingfeng.music.quality_catalog import QUALITY_RELATIONS
from lingfeng.platform.i18n import tr


_LIMIT = 32 * 1024 * 1024
_STEPS = dict(zip('CDEFGAB', (0, 2, 4, 5, 7, 9, 11)))
_KEYS = {'major': ('Ionian', 0), 'ionian': ('Ionian', 0), 'dorian': ('Dorian', 2),
         'phrygian': ('Phrygian', 4), 'lydian': ('Lydian', 5), 'mixolydian': ('Mixolydian', 7),
         'minor': ('Aeolian', 9), 'aeolian': ('Aeolian', 9)}
_BEAT_UNITS = {'whole': 4, 'half': 2, 'quarter': 1, 'eighth': Fraction(1, 2),
               '16th': Fraction(1, 4), '32nd': Fraction(1, 8), '64th': Fraction(1, 16)}
_KINDS = {
    'major': '', 'minor': 'm', 'augmented': 'aug', 'diminished': 'dim', 'dominant': '7',
    'major-seventh': 'maj7', 'minor-seventh': 'm7', 'diminished-seventh': 'dim7',
    'augmented-seventh': '7#5', 'half-diminished': 'm7b5', 'major-minor': 'mM7',
    'major-sixth': '6', 'minor-sixth': 'm6', 'dominant-ninth': '9', 'major-ninth': 'maj9',
    'minor-ninth': 'm9', 'dominant-11th': '11', 'major-11th': 'maj11', 'minor-11th': 'm11',
    'dominant-13th': '13', 'major-13th': 'maj13', 'minor-13th': 'm13',
    'suspended-second': 'sus2', 'suspended-fourth': 'sus4', 'power': '5',
}
_SPELLINGS = {frozenset(tones): quality for quality, tones in reversed(tuple(QUALITY_RELATIONS.items()))}
_BAR_STYLES = {'regular': 'barline', 'light-light': 'double_bar', 'light-heavy': 'final_bar'}
_WORDS = {'fine': 'fine', 'rit': 'rit', 'ritardando': 'rit', 'ad lib': 'adlib', 'f.o': 'fade', 'fade out': 'fade'}


@dataclass(frozen=True)
class XmlNote:
    bar: int
    offset: Fraction
    duration: Fraction
    pitch: int | None
    velocity: int
    voice: tuple[str, str]
    flat: bool = False
    tie_start: bool = False
    tie_stop: bool = False
    lyrics: tuple = ()
    slurs: tuple = ()


@dataclass(frozen=True)
class XmlHarmony:
    root: int | None
    quality: str = ''
    bass: int | None = None
    flat: bool = False


@dataclass
class MusicXmlPart:
    id: str
    name: str
    role: str = ''
    notes: list[XmlNote] = field(default_factory=list)
    symbols: dict = field(default_factory=dict)
    meters: dict = field(default_factory=dict)
    keys: dict = field(default_factory=dict)
    sections: dict = field(default_factory=dict)
    annotations: set = field(default_factory=set)
    tempos: dict = field(default_factory=dict)
    lengths: list = field(default_factory=list)
    implicit: set = field(default_factory=set)
    breaks: set = field(default_factory=set)


@dataclass
class MusicXmlData:
    title: str
    author: str
    parts: dict[str, MusicXmlPart]
    bpm: int
    native_keys: dict = field(default_factory=dict)

    def default_mapping(self):
        roles = {'melody': None, 'instrument': None, 'chords': None}
        choices = [part for part in self.parts.values() if part.notes]
        for part in choices:
            if part.role in roles and roles[part.role] is None:
                roles[part.role] = part.id
        aliases = {
            'chords': ('chord', 'harmony', 'accomp', '和弦', '伴奏'),
            'melody': ('vocal', 'voice', 'singer', '人声', '旋律 1'),
            'instrument': ('instrument', 'ins melody', 'lead synth', '乐器', '旋律 2'),
        }
        for role, words in aliases.items():
            if roles[role] is None:
                roles[role] = next((part.id for part in choices if part.id not in roles.values()
                                    and any(word in part.name.casefold() for word in words)), None)
        for role in ('melody', 'instrument'):
            if roles[role] is None:
                roles[role] = next((part.id for part in choices if part.id not in roles.values()), None)
        symbol_order = dict.fromkeys((roles['chords'], roles['melody'], roles['instrument'], *self.parts))
        roles['symbols'] = next((ident for ident in symbol_order if ident in self.parts and self.parts[ident].symbols), None)
        return roles


def _number(value, default=None):
    value = (value or '').strip()
    if len(value) <= 32 and re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)', value):
        return Fraction(value)
    return default


def _integer(value, default=0):
    number = _number(value)
    return int(number) if number is not None and number.denominator == 1 else default


def _xml(payload):
    if re.search(rb'<!\s*ENTITY\b', payload.replace(b'\0', b''), re.I):
        raise ValueError(tr('MusicXML 不支持自定义实体。'))
    try:
        root = ET.fromstring(payload)
    except (ET.ParseError, LookupError) as exc:
        raise ValueError(tr('无法读取 MusicXML 文档。')) from exc
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    return root


def _archive_member(archive, name, limit):
    info = archive.getinfo(name)
    if info.file_size > limit:
        raise ValueError(tr('MusicXML 文件过大。'))
    return archive.read(info)


def _document(path):
    if path.stat().st_size > _LIMIT:
        raise ValueError(tr('MusicXML 文件过大。'))
    if path.suffix.casefold() != '.mxl':
        return _xml(path.read_bytes())
    try:
        with zipfile.ZipFile(path) as archive:
            container = _xml(_archive_member(archive, 'META-INF/container.xml', 128 * 1024))
            kinds = ('', 'application/vnd.recordare.musicxml+xml')
            filename = next((entry.get('full-path', '') for entry in container.findall('./rootfiles/rootfile')
                             if entry.get('media-type', '') in kinds), '')
            relative = PurePosixPath(filename)
            if not filename or '\\' in filename or relative.is_absolute() or '..' in relative.parts:
                raise ValueError(tr('MXL 容器缺少有效的乐谱路径。'))
            return _xml(_archive_member(archive, filename, _LIMIT))
    except (zipfile.BadZipFile, KeyError, RuntimeError, NotImplementedError) as exc:
        raise ValueError(tr('无法读取 MXL 容器。')) from exc


def _misc(element, name):
    return next((field.text or '' for field in element.findall('./identification/miscellaneous/miscellaneous-field')
                 if field.get('name') == name), '')


def _velocity(value, default):
    percent = _number(value)
    return default if percent is None or percent < 0 else max(1, min(127, round(percent * 90 / 100)))


def _duration(element, divisions):
    duration = _number(element.findtext('duration'))
    if duration is None or duration <= 0:
        raise ValueError(tr('MusicXML 含无效的音符或光标时值。'))
    return duration / divisions


def _meter(time):
    beats = time.findall('beats')
    units = time.findall('beat-type')
    if not beats or len(beats) != len(units):
        return None
    lengths = []
    for beat, unit in zip(beats, units):
        denominator = _integer(unit.text)
        numerator = sum(_integer(piece) for piece in (beat.text or '').split('+'))
        if numerator <= 0 or denominator <= 0:
            raise ValueError(tr('MusicXML 拍号无效。'))
        lengths.append((numerator, denominator))
    denominator = max(2, max(d for _, d in lengths))
    return _represent_meter(sum(Fraction(n, d) * 4 for n, d in lengths), denominator)


def _represent_meter(quarters, preferred):
    for denominator in dict.fromkeys((preferred, 2, 4, 8, 16)):
        numerator = quarters * denominator / 4
        if denominator in (2, 4, 8, 16) and numerator.denominator == 1 and 1 <= numerator <= 16:
            return int(numerator), denominator
    raise ValueError(tr('MusicXML 小节时值超出支持的拍号范围。'))


def _chord_degree(quality, element):
    value = _integer(element.findtext('degree-value'))
    change = _integer(element.findtext('degree-alter'))
    action = element.findtext('degree-type', '')
    if not 1 <= value <= 30 or abs(change) > 4:
        return
    if action in ('subtract', 'alter'):
        quality.difference_update(tone for tone in tuple(quality) if tone.lstrip('#b') == str(value))
    if action in ('add', 'alter'):
        quality.add(('#' * change if change > 0 else 'b' * -change) + str(value))


def _harmony_symbol(element):
    kind = element.find('kind')
    if kind is None or element.get('type') == 'alternate':
        return None
    code = (kind.text or '').strip()
    if code == 'none':
        return XmlHarmony(None)
    root = element.findtext('./root/root-step', '').upper()
    if root not in _STEPS:
        return None
    alter = _integer(element.findtext('./root/root-alter'))
    explicit = kind.get('text')
    base = _KINDS.get(code)
    if explicit in QUALITIES:
        quality = explicit
    elif element.findall('degree') and (base in QUALITIES or code == 'other'):
        tones = set(QUALITY_RELATIONS[base]) if base in QUALITIES else {'1'}
        for item in element.findall('degree'):
            _chord_degree(tones, item)
        quality = _SPELLINGS.get(frozenset(tones))
    else:
        quality = base
    if quality not in QUALITIES:
        return None
    pc = (_STEPS[root] + alter) % 12
    bass_step = element.findtext('./bass/bass-step', '').upper()
    inversion = _integer(element.findtext('inversion'))
    if bass_step in _STEPS:
        bass = (_STEPS[bass_step] + _integer(element.findtext('./bass/bass-alter'))) % 12
    elif 0 < inversion < len(QUALITIES[quality]):
        bass = (pc + QUALITIES[quality][inversion]) % 12
    else:
        bass = None
    return XmlHarmony(48+pc, quality, bass if bass != pc else None, alter < 0)


def _lyrics(note):
    result = []
    cross_head = note.findtext('notehead') == 'x'
    for lyric in note.findall('lyric'):
        text = ''.join(child.text or '' for child in lyric if child.tag in ('text', 'elision')).strip()
        extension = lyric.find('extend')
        rap = cross_head and lyric.get('name', '').casefold() == 'rap'
        if text or extension is not None or rap:
            result.append((lyric.get('number', '1'), text, lyric.findtext('syllabic') in ('begin', 'middle'),
                           not text and extension is not None, rap))
    return tuple(result)


def _part(element, name, role):
    part = MusicXmlPart(element.get('id', ''), name, role)
    divisions = Fraction(1)
    transpositions = {'': 0}
    velocity = 92
    held_rap = set()
    for bar, measure in enumerate(element.findall('measure')):
        if bar >= 1000:
            raise ValueError(tr('MusicXML 小节数量超过 1000。'))
        cursor = extent = Fraction(0)
        last_start = None
        if measure.get('implicit') == 'yes' or (bar == 0 and measure.get('number') == '0'):
            part.implicit.add(bar)
        for item in measure:
            position = (bar, cursor)
            if item.tag == 'attributes':
                raw_divisions = item.findtext('divisions')
                if raw_divisions is not None:
                    divisions = _number(raw_divisions)
                    if divisions is None or divisions <= 0:
                        raise ValueError(tr('MusicXML 的 divisions 必须为正数。'))
                for transpose in item.findall('transpose'):
                    transpositions[transpose.get('number', '')] = (_integer(transpose.findtext('chromatic'))
                                                                     + 12*_integer(transpose.findtext('octave-change')))
                for time in item.findall('time'):
                    if time.get('number') not in (None, '1'):
                        continue
                    meter = _meter(time)
                    if meter is not None:
                        part.meters[position] = meter
                for key in item.findall('key'):
                    fifths = _integer(key.findtext('fifths'), None)
                    if fifths is not None and key.get('number') in (None, '1'):
                        mode, step = _KEYS.get(key.findtext('mode', 'major').casefold(), _KEYS['major'])
                        part.keys[position] = (48 + (fifths*7 + step + transpositions.get('1', transpositions[''])) % 12, mode)
            elif item.tag in ('backup', 'forward'):
                duration = _duration(item, divisions)
                cursor += duration if item.tag == 'forward' else -duration
                if cursor < 0:
                    raise ValueError(tr('MusicXML 光标回退超出小节边界。'))
                extent = max(extent, cursor)
                last_start = None
            elif item.tag == 'note':
                if item.find('grace') is not None:
                    continue
                duration = _duration(item, divisions)
                if item.find('chord') is not None and last_start is not None:
                    start = last_start
                else:
                    last_start = start = cursor
                    cursor += duration
                extent = max(extent, cursor, start+duration)
                pitch = item.find('pitch')
                if item.find('cue') is not None:
                    continue
                staff = item.findtext('staff', '1')
                voice = staff, item.findtext('voice', '1')
                ties = {tie.get('type') for tie in item.findall('tie') or item.findall('./notations/tied')}
                tie_start, tie_stop = bool({'start', 'continue'} & ties), bool({'stop', 'continue'} & ties)
                lyrics = _lyrics(item)
                if pitch is None:
                    if item.find('unpitched') is None or not (any(row[-1] for row in lyrics) or
                            (tie_stop and voice in held_rap and item.findtext('notehead') == 'x')):
                        continue
                    midi, flat = None, False
                    held_rap.discard(voice)
                    if tie_start:held_rap.add(voice)
                else:
                    step = pitch.findtext('step', '').upper()
                    octave = _integer(pitch.findtext('octave'), None)
                    alter = _number(pitch.findtext('alter'), Fraction(0))
                    if step not in _STEPS or octave is None or alter.denominator != 1:
                        raise ValueError(tr('MusicXML 含不支持的音高或微分音。'))
                    midi = (octave+1)*12 + _STEPS[step] + int(alter) + transpositions.get(staff, transpositions[''])
                    flat = alter < 0
                slurs = tuple((slur.get('number', '1'), slur.get('type')) for slur in item.findall('./notations/slur'))
                part.notes.append(XmlNote(bar, start, duration, midi, _velocity(item.get('dynamics'), velocity),
                                          voice, flat, tie_start, tie_stop, lyrics, slurs))
            elif item.tag == 'harmony':
                symbol = _harmony_symbol(item)
                if symbol is not None:
                    offset = cursor + _number(item.findtext('offset'), Fraction(0)) / divisions
                    part.symbols[(bar, max(Fraction(0), offset))] = symbol
            elif item.tag in ('direction', 'sound'):
                sound = item if item.tag == 'sound' else item.find('sound')
                offset = cursor + _number(item.findtext('offset'), Fraction(0)) / divisions
                if sound is not None:
                    tempo = _number(sound.get('tempo'))
                    velocity = _velocity(sound.get('dynamics'), velocity)
                    sound_offset = _number(sound.findtext('offset'))
                    if sound_offset is not None:
                        offset = cursor + sound_offset/divisions
                    if tempo is not None and tempo > 0:
                        part.tempos[(bar, max(Fraction(0), offset))] = tempo
                    for kind in ('segno', 'coda', 'fine'):
                        if sound.get(kind):
                            part.annotations.add((bar, offset, kind))
                for direction in item.findall('direction-type'):
                    for rehearsal in direction.findall('rehearsal'):
                        label = ' '.join((rehearsal.text or '').split())
                        if label:
                            part.sections.setdefault(bar, label)
                    for kind in ('segno', 'coda'):
                        if direction.find(kind) is not None:
                            part.annotations.add((bar, offset, kind))
                    for words in direction.findall('words'):
                        kind = _WORDS.get((words.text or '').strip().casefold().rstrip('.'))
                        if kind:
                            part.annotations.add((bar, offset, kind))
                    metronome = direction.find('metronome')
                    if metronome is not None and (bar, offset) not in part.tempos:
                        rate = _number(metronome.findtext('per-minute'))
                        unit = _BEAT_UNITS.get(metronome.findtext('beat-unit'))
                        if rate is not None and rate > 0 and unit is not None:
                            dots = len(metronome.findall('beat-unit-dot'))
                            part.tempos[(bar, max(Fraction(0), offset))] = rate*unit*(2-Fraction(1, 2**min(dots, 8)))
            elif item.tag == 'barline':
                kind = _BAR_STYLES.get(item.findtext('bar-style'))
                if kind:
                    part.annotations.add((bar-1 if item.get('location') == 'left' else bar, None, kind))
                for mark in ('segno', 'coda'):
                    if item.find(mark) is not None:
                        part.annotations.add((bar, cursor, mark))
            elif item.tag == 'print' and (item.get('new-system') == 'yes' or item.get('new-page') == 'yes'):
                if bar:
                    part.breaks.add(bar-1)
        part.lengths.append(extent)
    return part


def _native_keys(root):
    try:
        raw = json.loads(_misc(root, 'lingfeng-key-contexts'))
    except (ValueError, RecursionError):
        return {}
    if not isinstance(raw, list) or len(raw) > 10000:
        return {}
    result = {}
    for row in raw:
        if (not isinstance(row, list) or len(row) != 3 or type(row[0]) is not int or row[0] < 0
                or type(row[1]) is not int or not 21 <= row[1] <= 108 or not isinstance(row[2], str) or row[2] not in MODES):
            return {}
        result[row[0]] = (row[1], row[2])
    return result if 0 in result else {}


def _part_elements(root, headers):
    if root.tag == 'score-partwise':
        yield from root.findall('part')
        return
    if root.tag != 'score-timewise':
        raise ValueError(tr('仅支持 score-partwise 或 score-timewise MusicXML 乐谱。'))
    measures = root.findall('measure')
    if len(measures) > 1000:
        raise ValueError(tr('MusicXML 小节数量超过 1000。'))
    timeline = defaultdict(dict)
    for bar, measure in enumerate(measures):
        for node in measure.findall('part'):
            ident = node.get('id', '')
            if not ident or bar in timeline[ident]:
                raise ValueError(tr('MusicXML 音轨标识缺失或重复。'))
            timeline[ident][bar] = node
    for ident in dict.fromkeys((*headers, *timeline)):
        if ident not in timeline:
            continue
        part = ET.Element('part', id=ident)
        for bar, measure in enumerate(measures):
            target = ET.SubElement(part, 'measure', measure.attrib)
            source = timeline[ident].get(bar)
            if source is not None:
                target.extend(source)
        yield part


def read_musicxml(path):
    path = Path(path)
    root = _document(path)
    headers = {header.get('id'): header for header in root.findall('./part-list/score-part')}
    parts = {}
    total = 0
    for element in _part_elements(root, headers):
        ident = element.get('id', '')
        if not ident or ident in parts:
            raise ValueError(tr('MusicXML 音轨标识缺失或重复。'))
        header = headers.get(ident)
        name = header.findtext('part-name', ident) if header is not None else ident
        role = _misc(header, 'lingfeng-role').strip() if header is not None else ''
        parts[ident] = _part(element, ' '.join(name.split()) or ident, role)
        total += len(parts[ident].notes)
        if total > 100000:
            raise ValueError(tr('MusicXML 音符数量过多。'))
    if not any(part.notes or part.symbols for part in parts.values()):
        raise ValueError(tr('MusicXML 没有可导入的音符或和弦。'))
    tempos = {}
    for part in reversed(tuple(parts.values())):
        tempos.update(part.tempos)
    bpm = max(20, min(300, round(tempos[min(tempos)]))) if tempos else 120
    title = root.findtext('movement-title') or root.findtext('./work/work-title') or path.stem
    author = next((item.text for item in root.findall('./identification/creator')
                   if item.get('type') == 'composer' and item.text), '')
    return MusicXmlData(title, author, parts, bpm, _native_keys(root))


def _position(starts, bar, offset):
    return min(starts[bar+1], starts[bar] + round(max(Fraction(0), offset)*PPQ))


def _timing(data, selected):
    parts = list(dict.fromkeys([*selected, *data.parts]))
    count = max(len(data.parts[ident].lengths) for ident in parts)
    meters, keys, sections = {}, {}, {}
    lengths = [Fraction(0) for _ in range(count)]
    implicit, breaks = set(), set()
    for ident in reversed(parts):
        part = data.parts[ident]
        meters.update(part.meters)
        keys.update(part.keys)
        sections.update(part.sections)
        breaks.update(part.breaks)
        implicit.update(part.implicit)
        for bar, length in enumerate(part.lengths):
            if ident in selected:
                lengths[bar] = max(lengths[bar], length)

    midbar_meters = defaultdict(set)
    for (bar, offset), meter in meters.items():
        if offset:
            midbar_meters[bar].add(meter)
    lookup = section_lookup(normalize_section_mappings()['import'])
    measures, starts = [], [0]
    meter = (4, 4)
    padded = False
    for bar in range(count):
        meter = meters.get((bar, 0), meter)
        if midbar_meters[bar] - {meter}:
            raise ValueError(tr('MusicXML 的拍号变化必须在小节开头。'))
        n, d = meter
        nominal = Fraction(4*n, d)
        length = lengths[bar]
        if length and (bar in implicit and length != nominal or length > nominal):
            try:
                n, d = _represent_meter(length, d)
            except ValueError:
                if bar not in implicit:
                    raise
                # Arbitrary range exports can leave a partial bar shorter than
                # the editor's smallest unit. Keep its written events in place.
                n, d = _represent_meter(Fraction(ceil(length*4), 4), d)
                padded = True
        measure = Measure(n, d, imported_section(sections.get(bar, ''), lookup), bar in breaks)
        measures.append(measure)
        starts.append(starts[-1] + measure.ticks)

    changes = {0: (48, 'Ionian')}
    for (bar, offset), key in sorted(keys.items()):
        changes[_position(starts, bar, offset)] = key
    if not padded and data.native_keys and max(data.native_keys) < starts[-1]:
        changes = data.native_keys
    ordered = sorted(tick for tick in changes if tick < starts[-1])
    contexts = [Context(start, end, *changes[start]) for start, end in zip(ordered, ordered[1:]+[starts[-1]])]
    return measures, starts, contexts


def _normalized_notes(notes):
    rows = defaultdict(list)
    for note in sorted(notes, key=lambda n: (n.start, n.pitch)):
        row = rows[note.pitch]
        if row and row[-1].end > note.start:
            first = bisect_right(row, note.start, key=lambda item: item.end)
            last = bisect_left(row, note.end, key=lambda item: item.start)
            row[first:last] = overwrite_note(note, row[first:last])
        else:
            row.append(note)
    return sorted((note for row in rows.values() for note in row), key=lambda n: (n.start, n.pitch))


def _place_notes(part, starts):
    if part is None:
        return [], [], []
    notes, lyric_rows, slur_pairs = [], [], []
    held, open_slurs = {}, {}
    for event in sorted(part.notes, key=lambda item: (item.bar, item.offset)):
        unpitched = event.pitch is None
        if not unpitched and not 21 <= event.pitch <= 108:
            raise ValueError(tr('MusicXML 音轨 {0} 含 88 键范围之外的音符。', part.name))
        start = _position(starts, event.bar, event.offset)
        if start >= starts[event.bar+1]:
            continue
        end = max(start+1, _position(starts, event.bar, event.offset+event.duration))
        key = (event.voice, event.pitch)
        prior, last = held.pop(key, (None, None))
        adjacent_written_bars = (last is not None and event.bar == last.bar+1 and not event.offset
                                 and last.offset+last.duration == part.lengths[last.bar])
        if event.tie_stop and prior is not None and (prior.end == start or adjacent_written_bars):
            prior.duration = end-prior.start
            note = prior
        else:
            note = Note(start, end-start, 60 if unpitched else event.pitch, event.velocity, flat=event.flat)
            if not unpitched:notes.append(note)
            lyric_rows.extend((note, event.voice, *lyric, unpitched) for lyric in event.lyrics)
        if event.tie_start:
            held[key] = (note, event)
        for number, kind in event.slurs:
            key = (event.voice, number)
            if kind == 'start':
                open_slurs[key] = note
            elif kind == 'stop' and key in open_slurs:
                slur_pairs.append((open_slurs.pop(key), note))

    notes = _normalized_notes(notes)
    by_id = {note.id: note for note in notes}
    onsets = {(note.start, note.pitch) for note in notes}
    labels = tuple(dict.fromkeys(row[2] for row in lyric_rows))
    verses = {label: int(label)-1 for label in labels if label.isascii() and label.isdigit()
              and len(label) <= 2 and 1 <= int(label) <= 32}
    remaining = iter(sorted(set(range(32)) - set(verses.values())))
    for label in labels:
        if label not in verses:
            verses[label] = next(remaining, None)
    voices = {voice: index for index, voice in enumerate(dict.fromkeys(row[1] for row in lyric_rows))}
    lyric_events = {}
    for note, voice, label, text, join, extension, rap, unpitched in lyric_rows:
        verse, lane = verses[label], voices[voice]
        if verse is None or lane >= 32 or (not unpitched and (note.start, note.pitch) not in onsets):
            continue
        if unpitched and (not rap or not text):
            continue
        kind = 'rap' if unpitched else 'rap_note' if rap else 'skip' if extension else 'note'
        item = dict(id=uid(), tick=note.start, text=text, verse=verse, voice=lane, pitch=note.pitch,
                    duration=note.duration if unpitched else 0, skip=extension or not text, kind=kind, join_next=join)
        if extension:
            item['melisma'] = True
        lyric_events[(note.start, verse, lane)] = item
    slurs = []
    for a, b in slur_pairs:
        if a.id in by_id and b.id in by_id and by_id[a.id].start < by_id[b.id].start:
            slurs.append(dict(kind='slur', start=by_id[a.id].start, end=by_id[b.id].end, note_ids=[a.id, b.id]))
    return notes, sorted(lyric_events.values(), key=lambda item: (item['tick'], item['verse'], item['voice'])), slurs


def _import_harmony(project, performed, symbols, starts):
    from lingfeng.music.meter import regions
    from lingfeng.music.recognition import set_marker

    marks = {}
    if symbols:
        for (bar, offset), symbol in sorted(symbols.items()):
            tick = _position(starts, bar, offset)
            if tick < starts[-1]:
                marks[tick] = symbol
    meter_cuts = [start for start, _, _ in regions(project)]
    ordered = sorted(marks)
    declarations = []
    for start, end in zip(ordered, ordered[1:]+[starts[-1]]):
        symbol = marks[start]
        cuts = [start, *(tick for tick in meter_cuts if start < tick < end), end]
        for a, b in zip(cuts, cuts[1:]):
            if symbol.root is None:
                chord = Chord(a, b-a, notes=[], recognized=False)
            else:
                chord = Chord(a, b-a, symbol.root, symbol.quality, symbol.bass, flat=symbol.flat)
                declarations.append((chord, symbol))
            project.chords.append(chord)
    if performed is None:
        project.fill_chord_gaps()
        return
    project.set_harmony_notes(performed)
    for chord, symbol in declarations:
        if not chord.recognized or (chord.root, chord.quality, chord.bass) != (symbol.root, symbol.quality, symbol.bass):
            set_marker(chord, symbol.root, symbol.quality, symbol.bass)


def _annotations(parts, starts):
    locations = {location for part in parts for location in part.annotations}
    result = []
    for bar, offset, kind in sorted(locations, key=lambda item: (item[0], item[1] or 0, item[2])):
        if bar < 0:
            continue
        a, b = starts[bar:bar+2]
        tick = _position(starts, bar, offset) if offset is not None else a
        if kind in ('barline', 'double_bar', 'final_bar'):
            start, end = a, b
        elif kind == 'fine':
            start, end = a, tick if tick > a else b
        else:
            start, end = min(b-1, tick), b
        result.append(dict(kind=kind, start=start, end=end))
    return result


def project_from_musicxml(data, mapping):
    """Resolve the selected parts into a validated score for insertion at a bar."""
    roles = ('melody', 'instrument', 'chords', 'symbols')
    chosen = {role: mapping.get(role) for role in roles}
    if not any(chosen.values()) or any(ident is not None and ident not in data.parts for ident in chosen.values()):
        raise ValueError(tr('请选择要导入的 MusicXML 音轨。'))
    for role, ident in chosen.items():
        if ident is not None and not (data.parts[ident].symbols if role == 'symbols' else data.parts[ident].notes):
            raise ValueError(tr('选择的 MusicXML 音轨没有对应内容。'))
    selected = tuple(dict.fromkeys(ident for ident in chosen.values() if ident is not None))
    measures, starts, contexts = _timing(data, selected)
    vocal = data.parts.get(chosen['melody'])
    instrument = data.parts.get(chosen['instrument'])
    harmony = data.parts.get(chosen['chords'])
    symbols = data.parts.get(chosen['symbols'])
    notes, vocal_lyrics, slurs = _place_notes(vocal, starts)
    instrument_notes, instrument_lyrics, _ = _place_notes(instrument, starts)
    performed = _place_notes(harmony, starts)[0] if harmony is not None else None
    names = [part.name[:48] if part and part.name != part.id else default
             for part, default in zip((vocal, instrument), MELODY_NAMES)]
    project = Project(title=data.title, author=data.author, bpm=data.bpm, melody_names=names,
                      measures=measures, contexts=contexts, notes=notes, instrument_notes=instrument_notes)
    for key, events in zip((track[0] for track in LYRIC_TRACK_KEYS), (vocal_lyrics, instrument_lyrics)):
        if events:
            project.notation[key] = events
    annotations = _annotations(data.parts.values(), starts) + slurs
    if annotations:
        project.notation['symbols'] = annotations
    _import_harmony(project, performed, symbols.symbols if symbols else None, starts)
    project.validate()
    return project
