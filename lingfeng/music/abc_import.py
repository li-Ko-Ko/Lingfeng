"""Import one written ABC tune, retaining independent voice timelines."""

import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from lingfeng.engraving.lyrics import LYRIC_TRACK_KEYS
from lingfeng.music.abc_sections import imported_section, normalize_section_mappings, section_key, section_lookup
from lingfeng.music.model import Chord, Context, MELODY_NAMES, Measure, Note, PATTERNS, PPQ, Project, QUALITIES
from lingfeng.platform.i18n import tr


_WHOLE = 4 * PPQ
_PITCHES = dict(zip('CDEFGAB', (0, 2, 4, 5, 7, 9, 11)))
_SHARPS = 'FCGDAEB'
_FLATS = _SHARPS[::-1]
_MODE_KEYS = {
    'maj': ('Ionian', 0), 'ion': ('Ionian', 0), 'dor': ('Dorian', 2),
    'phr': ('Phrygian', 4), 'lyd': ('Lydian', 5), 'mix': ('Mixolydian', 7),
    'm': ('Aeolian', 9), 'min': ('Aeolian', 9), 'aeo': ('Aeolian', 9),
    'loc': ('Locrian', 11),
}
_DURATION = r'(?:\d+(?:/\d+|/+)?|/\d+|/+)?'
_NOTE = re.compile(r'(\^\^?|__?|=)?([A-Ga-g])([,\']*)(' + _DURATION + ')')
_REST = re.compile(r'([zxZXy])(' + _DURATION + ')')
_FIELD = re.compile(r'^([A-Za-z]):\s*(.*)')
_LYRIC_TOKEN = re.compile(r'(?:\\u[0-9a-fA-F]{4}|\\-|[^\s_*|\\-])+-?|[-_*|]')
_TOKEN = re.compile(
    r'(?P<field>\[[A-Za-z]:[^\]]*\])|(?P<label>"[^"]*")|'
    r'(?P<bar>\|:\||::|:\||\|:|\[\||\|\]|\|\||\|)|(?P<ending>\[?[1-9][0-9,-]*)|'
    r'(?P<group>\[[^\]]+\]' + _DURATION + r')|'
    r'(?P<tuplet>\([2-9](?::\d*(?::\d*)?)?)|(?P<broken><+|>+)|'
    r'(?P<note>' + _NOTE.pattern + r')|(?P<rest>' + _REST.pattern + r')|'
    r'(?P<tie>-)|(?P<skip>\{[^}]*\}|![^!]*!|\+[^+]+\+|[.~HLMOPSTuv()\\$!\s])'
)
_CHORD = re.compile(r'([A-Ga-g])(#{1,2}|b{1,2})?(.*?)(?:/([A-Ga-g])(#{1,2}|b{1,2})?)?')
_NO_CHORD = frozenset(('N.C.', 'N.C', 'NC', 'N', 'X', '?'))
_SECTION = re.compile(
    r'(?i)(intro|verse|pre[- ]?chorus|chorus|link|solo|refrain|tag|post[- ]?chorus|'
    r'super[- ]?chorus|coda|outro|interlude|bridge)(?:[ -]+\d+)?'
)


def _text(value):
    return re.sub(r'\\u([0-9a-fA-F]{4})', lambda match: chr(int(match[1], 16)), value)


def _fraction(text):
    if not text:
        return Fraction(1)
    if text.endswith('/'):
        numerator, _, slashes = text.partition('/')
        return Fraction(int(numerator or 1), 2 ** (len(slashes) + 1))
    return Fraction('1' + text if text.startswith('/') else text)


def _meter(text):
    common = {'C': (4, 4), 'C|': (2, 2)}
    if text in common:
        return common[text]
    match = re.fullmatch(r'\(?([\d+]+)\)?\s*/\s*(\d+)', text)
    if match:
        numerator = sum(int(n) for n in match[1].split('+'))
        denominator = int(match[2])
        if 1 <= numerator <= 16 and denominator in (2, 4, 8, 16):
            return numerator, denominator
    raise ValueError(tr('ABC 拍号不受支持：{0}', text))


def _key(text):
    if re.match(r'(?i)^none(?:\s|$)', text):
        return 48, 'Ionian', {}
    match = re.fullmatch(
        r'([A-G])([#b]?)(?:\s*(maj(?:or)?|ion(?:ian)?|dor(?:ian)?|phr(?:ygian)?|'
        r'lyd(?:ian)?|mix(?:olydian)?|min(?:or)?|aeo(?:lian)?|loc(?:rian)?|m))?'
        r'((?:\s.*)?)', text, re.IGNORECASE
    )
    if not match:
        raise ValueError(tr('ABC 调号不受支持：{0}', text))
    letter, accidental, suffix, modifiers = match.groups()
    letter = letter.upper()
    mode = (suffix or '').lower()
    mode, relative = _MODE_KEYS.get(mode if mode == 'm' else mode[:3] or 'maj', ('', 0))
    if not mode or mode == 'Locrian':
        raise ValueError(tr('ABC 调号不受支持：{0}', text))
    tonic = (_PITCHES[letter] + accidental.count('#') - accidental.count('b')) % 12
    major_letter = 'CDEFGAB'[('CDEFGAB'.index(letter) - (0, 2, 4, 5, 7, 9, 11).index(relative)) % 7]
    count = 'FCGDAEB'.index(major_letter) - 1
    major_pc = count * 7 % 12
    alteration = (tonic - relative - major_pc + 6) % 12 - 6
    count += 7 * alteration
    signature = {
        name: (1 if count > 0 else -1) * len(range(index, abs(count), 7))
        for index, name in enumerate(_SHARPS if count > 0 else _FLATS)
        if index < abs(count)
    }
    if re.search(r'\bexp\b', modifiers):
        signature.clear()
    for acc, note in re.findall(r'(\^\^?|__?|=)([A-Ga-g])', modifiers):
        signature[note.upper()] = acc.count('^') - acc.count('_')
    return 48 + tonic, mode, signature


@dataclass
class AbcNote:
    bar: int
    offset: Fraction
    duration: Fraction
    pitch: int
    natural: int
    tied: bool = False
    lyric: str = ''
    lyric_join: bool = False
    lyric_melisma: bool = False


@dataclass
class AbcVoice:
    id: str
    name: str
    meter: tuple
    unit: Fraction
    key: tuple
    bar: int = 0
    offset: Fraction = Fraction(0)
    notes: list = field(default_factory=list)
    symbols: dict = field(default_factory=dict)
    sections: dict = field(default_factory=dict)
    meters: dict = field(default_factory=dict)
    keys: dict = field(default_factory=dict)
    lengths: dict = field(default_factory=dict)
    full_rests: set = field(default_factory=set)
    accidentals: dict = field(default_factory=dict)
    accidental_scope: str = 'octave'
    recent: dict = field(default_factory=dict)
    line_onsets: list = field(default_factory=list)
    last_notes: list = field(default_factory=list)
    last_duration: Fraction = Fraction(0)
    tuplet_count: int = 0
    tuplet_factor: Fraction = Fraction(1)
    next_factor: Fraction = Fraction(1)

    @property
    def bar_count(self):
        return max(self.bar + bool(self.offset), max((bar+1 for bar, _ in self.symbols), default=0))

    def barline(self):
        if self.offset or (self.bar, Fraction(0)) in self.symbols:
            if self.offset:
                self.lengths[self.bar] = self.offset
            self.bar += 1
        if self.bar > 1000:
            raise ValueError(tr('ABC 小节数量超过 1000。'))
        self.offset = Fraction(0)
        self.accidentals.clear()
        self.last_duration = Fraction(0)
        self.last_notes = []

    def pitch(self, match):
        accidental, letter, octave = match.group(1, 2, 3)
        octave_offset = int(letter.islower()) + octave.count("'") - octave.count(',')
        natural = 60 + _PITCHES[letter.upper()] + 12 * octave_offset
        slot = natural % 12 if self.accidental_scope == 'pitch' else natural
        alter = self.key[2].get(letter.upper(), 0)
        if accidental:
            alter = accidental.count('^') - accidental.count('_')
            if self.accidental_scope != 'not':
                self.accidentals[slot] = alter
        else:
            alter = self.accidentals.get(slot, alter)
        previous = self.recent.get(natural)
        if previous and previous.tied:
            end = previous.offset + previous.duration
            adjacent = ((previous.bar == self.bar and end == self.offset)
                        or (previous.bar+1 == self.bar and self.offset == 0 and end == self.lengths.get(previous.bar)))
            if adjacent:
                if accidental and previous.pitch != natural + alter:
                    if self.accidental_scope == 'pitch':
                        raise ValueError(tr('ABC 延音线两端的音高不同。'))
                else:
                    return previous.pitch, natural
        return natural + alter, natural

    def add_event(self, tones, duration):
        if duration <= 0 or any(length <= 0 for _, _, length, _ in tones):
            raise ValueError(tr('ABC 音符或休止符长度必须为正数。'))
        factor = self.next_factor
        self.next_factor = Fraction(1)
        if self.tuplet_count:
            self.tuplet_count -= 1
            factor *= self.tuplet_factor
        self.last_duration = duration * factor
        self.last_notes = [
            AbcNote(self.bar, self.offset, length * factor, pitch, natural, tied)
            for pitch, natural, length, tied in tones
        ]
        if self.last_notes:
            self.line_onsets.append(max(self.last_notes, key=lambda note: note.pitch))
            self.notes.extend(self.last_notes)
            self.recent.update((note.natural, note) for note in self.last_notes)
        self.offset += self.last_duration

    def apply_field(self, name, value):
        if name == 'L':
            self.unit = _fraction(value)
            if self.unit <= 0:
                raise ValueError(tr('ABC 音符单位无效。'))
        elif name == 'M':
            if self.offset:
                raise ValueError(tr('ABC 拍号变化需要位于小节开头。'))
            self.meter = _meter(value)
            self.meters[self.bar] = self.meter
        elif name == 'K':
            self.key = _key(value)
            self.keys[(self.bar, self.offset)] = self.key[:2]
            self.accidentals.clear()
        elif name == 'P' and value:
            self.sections[self.bar] = value
        elif name == 'w':
            self.apply_lyrics(value)

    def apply_lyrics(self, value):
        # Attach the first written verse to this music line. Tied continuation
        # notes stay eligible for alignment, but have no separate MIDI onset.
        if any(note.lyric or note.lyric_melisma for note in self.line_onsets):
            return
        index, last_bar = 0, -1
        for token in _LYRIC_TOKEN.findall(value):
            if index >= len(self.line_onsets):
                break
            if token == '|':
                while index < len(self.line_onsets) and self.line_onsets[index].bar == last_bar:
                    index += 1
                continue
            note = self.line_onsets[index]
            if token == '_':
                note.lyric_melisma = True
            elif token not in ('*', '-'):
                note.lyric_join = token.endswith('-') and not token.endswith('\\-')
                text = token[:-1] if note.lyric_join else token
                note.lyric = _text(text.replace('~', ' ').replace('\\-', '-'))
            last_bar = note.bar
            index += 1


@dataclass
class AbcData:
    title: str
    author: str
    bpm: int
    meter: tuple
    key: tuple
    voices: dict
    sections: dict
    section_candidates: dict = field(default_factory=dict)
    native: bool = False

    def section_labels(self):
        return dict.fromkeys((*self.sections.values(), *self.section_candidates.values(),
                              *(label for voice in self.voices.values() for label in voice.sections.values())))

    def defaults(self):
        def matches(voice, keywords):
            label = (voice.id + ' ' + voice.name).casefold()
            return any(re.search(r'\b' + word + r'\b', label) for word in keywords)

        playable = [v for v in self.voices.values() if v.notes]
        chords = next((v.id for v in self.voices.values() if matches(v, ('chord', 'chords', 'harmony', 'accompaniment'))), None)
        melodic = [v for v in playable if v.id != chords]
        vocal = next((v.id for v in melodic if matches(v, ('vocal', 'voice', 'lead'))), None)
        instrument = next((v.id for v in melodic if matches(v, ('ins', 'inst', 'instrument', 'instrumental'))), None)
        remaining = [v.id for v in melodic if v.id not in (vocal, instrument)]
        vocal = vocal or (remaining.pop(0) if remaining else None)
        instrument = instrument or (remaining.pop(0) if remaining else None)
        symbols = next((v.id for v in self.voices.values() if v.symbols and v.id == chords), None)
        symbols = symbols or next((v.id for v in self.voices.values() if v.symbols), None)
        return dict(vocal=vocal, instrument=instrument, harmony=chords, symbols=symbols,
                    sections=True, pattern='block')


def _music(voice, source, get_voice):
    voice.line_onsets = []
    at = 0
    while at < len(source):
        token = _TOKEN.match(source, at)
        if not token:
            raise ValueError(tr('ABC 音乐记号不受支持：{0}', source[at:at+20]))
        at = token.end()
        kind, value = token.lastgroup, token[0]
        if kind == 'field':
            name, value = value[1:-1].split(':', 1)
            if name == 'V':
                voice = get_voice(value.strip())
                voice.line_onsets = []
            else:
                voice.apply_field(name, value.strip())
        elif kind == 'bar':
            voice.barline()
        elif kind == 'label':
            label = value[1:-1].strip().replace('♭', 'b').replace('♯', '#')
            if re.match(r'^[A-G][#b]{0,2}(?=[^a-z]|m|a(?:dd|ug)|d(?:im)|sus|no|omit|$)', label) or label.upper() in _NO_CHORD:
                voice.symbols[voice.bar, voice.offset] = label
        elif kind == 'tuplet':
            parts = (value[1:].split(':') + ['', ''])[:3]
            count = int(parts[0])
            compound = voice.meter[1] == 8 and voice.meter[0] % 3 == 0
            default = 3 if count in (2, 4, 8) or (count in (5, 7, 9) and compound) else 2
            voice.tuplet_factor = Fraction(int(parts[1] or default), count)
            voice.tuplet_count = int(parts[2] or count)
        elif kind == 'broken':
            if not voice.last_duration:
                raise ValueError(tr('ABC 附点节奏缺少前一个音符。'))
            short = Fraction(1, 2 ** len(value))
            first, voice.next_factor = (2-short, short) if value.startswith('>') else (short, 2-short)
            voice.offset += voice.last_duration * (first-1)
            voice.last_duration *= first
            for note in voice.last_notes:
                note.duration *= first
        elif kind == 'tie':
            for note in voice.last_notes:
                note.tied = True
        elif kind == 'note':
            match = _NOTE.fullmatch(value)
            duration = voice.unit * _fraction(match[4])
            voice.add_event([(*voice.pitch(match), duration, False)], duration)
        elif kind == 'group':
            body, multiplier = value[1:].split(']', 1)
            tones = []
            cursor = 0
            for note in re.finditer(_NOTE.pattern + r'(-?)', body):
                if body[cursor:note.start()].strip():
                    break
                cursor = note.end()
                duration = voice.unit * _fraction(note[4]) * _fraction(multiplier)
                tones.append((*voice.pitch(note), duration, bool(note[5])))
            if not tones or body[cursor:].strip():
                raise ValueError(tr('ABC 同时音符无效：{0}', value))
            voice.add_event(tones, tones[0][2])
        elif kind == 'rest':
            rest, length = _REST.fullmatch(value).groups()
            if rest in 'XZ':
                count = _fraction(length)
                if voice.offset or count.denominator != 1 or not 1 <= count <= 1000 - voice.bar:
                    raise ValueError(tr('ABC 整小节休止符位置或长度无效。'))
                voice.full_rests.update(range(voice.bar, voice.bar+int(count)))
                voice.bar += int(count)
                voice.accidentals.clear()
            elif rest != 'y':
                voice.add_event([], voice.unit * _fraction(length))
    return voice


def parse_abc(source, fallback_title=''):
    """Parse a tune written for the standard melodic and harmony ABC voices."""
    title, author, bpm = '', '', 120
    meter, unit, key = (4, 4), None, _key('C')
    voices, sections, section_candidates = {}, {}, {}
    header, index_seen, voice = True, False, None
    accidental_scope, native, standard_version = None, False, False

    def get_voice(text):
        match = re.match(r'(\S+)(.*)', text)
        if not match:
            raise ValueError(tr('ABC 音轨编号为空。'))
        ident, options = match.groups()
        name = re.search(r'(?:^|\s)(?:name|nm)\s*=\s*(?:"([^"]+)"|(\S+))', options)
        if ident not in voices:
            default_unit = Fraction(1, 16 if Fraction(*meter) < Fraction(3, 4) else 8)
            voices[ident] = AbcVoice(ident, ident, meter, unit or default_unit, key,
                                     accidental_scope=accidental_scope or ('pitch' if native else 'octave'))
        if name:
            voices[ident].name = _text(name[1] or name[2])
        return voices[ident]

    for line_number, raw in enumerate(source.splitlines(), 1):
        if raw.lstrip().startswith('%abc-'):
            standard_version = True
        if raw.lstrip().startswith('%%'):
            directive = re.fullmatch(r'%%propagate-accidentals\s+(pitch|octave|not)', raw.strip())
            if directive:
                accidental_scope = directive[1]
                for item in voices.values():
                    item.accidental_scope = accidental_scope
            continue
        # Preserve percent signs inside quoted chord/voice annotations.
        parts = re.split(r'("[^"]*")', raw)
        comment = ''
        for index in range(0, len(parts), 2):
            if '%' in parts[index]:
                parts[index], _, comment = parts[index].partition('%')
                parts = parts[:index+1]
                break
        line, comment = ''.join(parts).strip(), comment.strip()
        try:
            if header and not line:
                continue
            if not line:
                explicit = re.match(r'(?i)section\s*:\s*(.+)', comment)
                bar = voice.bar if voice else 0
                if explicit or _SECTION.fullmatch(comment) or (native and comment):
                    sections[bar] = explicit[1] if explicit else comment
                elif comment and (not voice or voice.offset == 0):
                    section_candidates[bar] = comment
                continue
            match = _FIELD.fullmatch(line)
            if match:
                name, value = match.groups()
                if name == 'X':
                    if index_seen or not header:
                        raise ValueError(tr('一次只能导入一首 ABC 曲目。'))
                    index_seen = True
                elif name == 'V':
                    voice = get_voice(value)
                elif header and name == 'T' and not title:
                    title = _text(value)
                elif header and name == 'C':
                    author = _text(value)
                elif header and name == 'Q':
                    tempo = re.search(r'(?:(\d+\s*/\s*\d+)\s*=\s*)?(\d+)\s*$', re.sub(r'"[^"]*"', '', value))
                    if tempo:
                        bpm = round(int(tempo[2]) * (4 * _fraction(tempo[1].replace(' ', '')) if tempo[1] else 1))
                elif header and name == 'M':
                    meter = _meter(value)
                elif header and name == 'L':
                    unit = _fraction(value)
                    if unit <= 0:
                        raise ValueError(tr('ABC 音符单位无效。'))
                elif header and name == 'K':
                    key = _key(value)
                    native = not standard_version and set(voices) == {'Vocal', 'Ins'}
                    for item in voices.values():
                        item.meter, item.key = meter, key
                        item.unit = unit or Fraction(1, 16 if Fraction(*meter) < Fraction(3, 4) else 8)
                        item.accidental_scope = accidental_scope or ('pitch' if native else 'octave')
                    voice = next(iter(voices.values()), None)
                    header = False
                elif not header:
                    voice = voice or get_voice('1')
                    voice.apply_field(name, value)
                continue
            if header:
                for item in voices.values():
                    item.meter, item.unit = meter, unit or Fraction(1, 16 if Fraction(*meter) < Fraction(3, 4) else 8)
            header = False
            voice = _music(voice or next(iter(voices.values()), None) or get_voice('1'), line, get_voice)
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            raise ValueError(tr('ABC 第 {0} 行：{1}', line_number, str(exc))) from exc
    voices = {ident: v for ident, v in voices.items() if v.bar_count or v.symbols}
    if not voices or not any(v.notes or v.symbols for v in voices.values()):
        raise ValueError(tr('ABC 文件没有可导入的音符或和弦。'))
    if not 20 <= bpm <= 300:
        raise ValueError(tr('ABC 速度超出 20–300 BPM 范围。'))
    return AbcData(title or fallback_title or tr('未命名作品'), author, bpm, meter, key, voices,
                   sections, section_candidates, native)


def read_abc(path):
    path = Path(path)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError(tr('ABC 文件过大。'))
    payload = path.read_bytes()
    encoding = 'utf-16' if payload.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
    try:
        source = payload.decode(encoding)
    except UnicodeError:
        source = payload.decode('gb18030')
    return parse_abc(source, path.stem)


def _timing(data, selected, count, sections):
    meters, key_changes = {}, {}
    for voice in selected:
        for bar, meter in voice.meters.items():
            if bar in meters and meters[bar] != meter:
                raise ValueError(tr('ABC 音轨在第 {0} 小节的拍号不同。', bar+1))
            meters[bar] = meter
        for time, key in voice.keys.items():
            if time in key_changes and key_changes[time] != key:
                raise ValueError(tr('ABC 音轨在第 {0} 小节的调号不同。', time[0]+1))
            key_changes[time] = key
    measures = []
    meter = data.meter
    for bar in range(count):
        meter = meters.get(bar, meter)
        measures.append(Measure(*meter, section=sections.get(bar, '')))
    first_lengths = [voice.lengths.get(0, Fraction(0)) for voice in selected]
    pickup = max(first_lengths, default=Fraction(0))
    if count > 1 and 0 < pickup < Fraction(*meters.get(0, data.meter)) and not any(0 in v.full_rests for v in selected):
        if pickup.denominator <= 16:
            denominator = max(pickup.denominator, measures[0].denominator)
            measures[0].numerator = int(pickup * denominator)
            measures[0].denominator = denominator
    starts = [0]
    for measure in measures:
        starts.append(starts[-1] + measure.ticks)
    for voice in selected:
        for bar, length in (*voice.lengths.items(), (voice.bar, voice.offset)):
            if bar < count and length > Fraction(measures[bar].ticks, _WHOLE):
                raise ValueError(tr('ABC 音轨 {0} 的第 {1} 小节超过拍号长度。', voice.name, bar+1))
    changes = {0: data.key[:2]}
    for (bar, offset), key in key_changes.items():
        if bar < count:
            changes[starts[bar] + round(offset*_WHOLE)] = key
    cuts = sorted(tick for tick in changes if tick < starts[-1])
    contexts = [Context(a, b, *changes[a]) for a, b in zip(cuts, cuts[1:] + [starts[-1]])]
    return measures, starts, contexts


def _notes(voice, starts, lyric_events=None):
    if voice is None:
        return []
    notes, previous = [], {}
    for event in sorted(voice.notes, key=lambda item: (item.bar, item.offset, item.pitch)):
        start = starts[event.bar] + round(event.offset * _WHOLE)
        end = starts[event.bar] + round((event.offset+event.duration) * _WHOLE)
        if not 21 <= event.pitch <= 108:
            raise ValueError(tr('ABC 音轨 {0} 含 88 键范围之外的音符。', voice.name))
        if end <= start or end > starts[-1]:
            raise ValueError(tr('ABC 音轨 {0} 的第 {1} 小节含超出工程时间的音符。', voice.name, event.bar+1))
        old, tied = previous.get(event.pitch, (None, False))
        if old and tied and old.end == start:
            old.duration = end - old.start
            previous[event.pitch] = old, event.tied
        else:
            if old and old.end > start:
                old.duration = start - old.start
            annotated = lyric_events is not None and (
                event.lyric_join or event.lyric_melisma or event.lyric in ('-', '_')
            )
            note = Note(start, end-start, event.pitch, lyric='' if annotated else event.lyric)
            notes.append(note)
            if annotated:
                lyric_events.append(dict(id=note.id, tick=start, text=event.lyric, verse=0, voice=0,
                                         pitch=note.pitch, duration=0, join_next=event.lyric_join,
                                         skip=event.lyric_melisma, melisma=event.lyric_melisma,
                                         kind='skip' if event.lyric_melisma else 'note'))
            previous[event.pitch] = note, event.tied
    return [note for note in notes if note.duration]


def _chord(label, start, end, pattern):
    if label.upper() in _NO_CHORD:
        return Chord(start, end-start, notes=[], recognized=False)
    match = _CHORD.fullmatch(label)
    if match:
        root, accidental, quality, bass, bass_accidental = match.groups()
        quality = {'maj': '', 'M': '', 'min': 'm', '°': 'dim', '°7': 'dim7',
                   'ø': 'm7b5', 'ø7': 'm7b5', '+': 'aug', 'm(maj7)': 'mM7'}.get(quality, quality)
        if quality in QUALITIES:
            def pitch(letter, acc):
                acc = acc or ''
                return (_PITCHES[letter.upper()] + acc.count('#') - acc.count('b')) % 12

            return Chord(start, end-start, 48+pitch(root, accidental), quality,
                         pitch(bass, bass_accidental) if bass else None,
                         flat=accidental == 'b', pattern=pattern)
    raise ValueError(tr('ABC 和弦符号不受支持：{0}', label))


def _harmony(project, performed, labels, pattern):
    from lingfeng.music.meter import regions
    from lingfeng.music.recognition import set_marker
    from lingfeng.music.rhythm import regenerate

    cuts = [start for start, _, _ in regions(project)]
    specs = []
    for (start, label, limit), end in zip(labels, [tick for tick, _, _ in labels[1:]] + [project.end]):
        end = min(end, limit)
        boundaries = [start, *(tick for tick in cuts if start < tick < end), end]
        specs.extend(_chord(label, a, b, pattern) for a, b in zip(boundaries, boundaries[1:]) if a < b)
    project.chords = specs
    if performed is not None:
        declared = [(c, c.root, c.quality, c.bass) for c in specs if c.recognized]
        project.set_harmony_notes(performed)
        for chord, root, quality, bass in declared:
            if not chord.recognized or (chord.root, chord.quality, chord.bass) != (root, quality, bass):
                set_marker(chord, root, quality, bass)
    else:
        for index, chord in enumerate(specs):
            if chord.pattern != 'block' and chord.recognized:
                generated = regenerate(chord, chord.start, chord.end, project, explicit=True)
                if generated and generated.notes:
                    project.chords[index] = generated
                else:
                    chord.pattern = 'block'
        project.fill_chord_gaps()


def project_from_abc(data, *, vocal, instrument, harmony, symbols, sections=True, pattern='block', section_mapping=None):
    """Map the selected ABC sources into a new, fully validated project."""
    ids = (vocal, instrument, harmony, symbols)
    if pattern not in PATTERNS or not any(ids) or any(i is not None and i not in data.voices for i in ids):
        raise ValueError(tr('请选择 ABC 导入音轨和有效节奏型。'))
    selected = [data.voices[i] for i in dict.fromkeys(ids) if i is not None]
    count = max(voice.bar_count for voice in selected)
    if not 1 <= count <= 1000:
        raise ValueError(tr('ABC 小节数量超过 1000。'))
    markers = {}
    if sections:
        lookup = section_lookup(normalize_section_mappings({'import': section_mapping})['import'])
        markers.update((bar, name) for bar, name in data.section_candidates.items() if section_key(name) in lookup)
        markers.update(data.sections)
        for voice in reversed(selected):
            markers.update(voice.sections)
        markers = {bar: imported_section(name, lookup) for bar, name in markers.items()}
    measures, starts, contexts = _timing(data, selected, count, markers)
    vocal_voice, ins_voice = data.voices.get(vocal), data.voices.get(instrument)
    names = []
    for item, native_name, default in zip((vocal_voice, ins_voice), ('Vocal Melody', 'Ins Melody'), MELODY_NAMES):
        name = ' '.join(item.name.split()) if item and item.name != item.id else ''
        names.append(name[:48] if name and not (data.native and name == native_name) else default)
    vocal_lyrics, instrument_lyrics = [], []
    project = Project(title=data.title, author=data.author, bpm=data.bpm, melody_names=names,
                      measures=measures, contexts=contexts, notes=_notes(vocal_voice, starts, vocal_lyrics),
                      instrument_notes=_notes(ins_voice, starts, instrument_lyrics))
    for (key, _), lyrics in zip(LYRIC_TRACK_KEYS, (vocal_lyrics, instrument_lyrics)):
        if lyrics:
            project.notation[key] = lyrics
    symbols_voice = data.voices.get(symbols)
    labels = sorted((starts[bar]+round(offset*_WHOLE), label, starts[bar+1] if data.native else project.end)
                    for (bar, offset), label in symbols_voice.symbols.items()) if symbols_voice else []
    _harmony(project, _notes(data.voices[harmony], starts) if harmony is not None else None,
             labels, pattern)
    project.validate()
    return project
