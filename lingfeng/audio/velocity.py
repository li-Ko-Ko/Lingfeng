"""Explicit metadata-only velocity inspection. Never called by audio startup.

SFZ selection follows lovel/hivel; SF2 reads only the preset/instrument tables,
seeking past sample data. Bands are suggestions, not measurements of loudness.
"""
import re
import struct
from pathlib import Path

DEFAULT_OPTIONS = (32, 48, 64, 80, 96, 112, 127)
_options = DEFAULT_OPTIONS


def normalize_options(values):
    if not isinstance(values, (list, tuple)):
        return list(DEFAULT_OPTIONS)
    result = sorted({v for v in values if type(v) is int and 1 <= v <= 127})
    return result or list(DEFAULT_OPTIONS)


def set_options(values):
    global _options
    _options = tuple(normalize_options(values))


def options():
    return list(_options)


def parse_options(text):
    parts = re.split(r'[,，;；\s]+', text.strip())
    if not parts or any(not p.isdecimal() or not 1 <= int(p) <= 127 for p in parts):
        raise ValueError('Enter MIDI velocities from 1 to 127, separated by commas or spaces.')
    return sorted({int(p) for p in parts})


def velocity_bands(regions):
    """Deduplicate stereo/round-robin zones; retain gaps and key-specific splits."""
    regions = set(regions)
    edges = sorted({v for low, high in regions for v in (max(1, low), high + 1) if 1 <= v <= 128})
    return [(a, b - 1) for a, b in zip(edges, edges[1:])
            if any(low <= a <= high for low, high in regions)]


def sfz_ranges(root, relative):
    from lingfeng.audio.sfz import validate_assets
    _, text = validate_assets(root, relative, include_text=True)
    scopes = dict(global_={}, master={}, group={})
    current = None; values = {}; regions = []

    def finish():
        if current != 'region' or values.get('trigger', 'attack') not in ('attack', 'first', 'legato'):
            return
        if 'sample' not in values:
            return
        low, high = int(values.get('lovel', 1)), int(values.get('hivel', 127))
        if not 0 <= low <= high <= 127:
            raise ValueError('Invalid SFZ velocity range')
        if high >= 1:
            regions.append((max(1, low), high))

    tokens = list(re.finditer(r'<([^>]*)>|\b([A-Za-z_]\w*)\s*=', text))
    for index, token in enumerate(tokens):
        if token[1] is not None:
            finish(); current = token[1].strip().lower()
            if current == 'global':
                scopes = dict(global_={}, master={}, group={}); values = scopes['global_']
            elif current == 'master':
                scopes['master'] = dict(scopes['global_']); scopes['group'] = {}
                values = scopes['master']
            elif current == 'group':
                scopes['group'] = dict(scopes['global_'], **scopes['master']); values = scopes['group']
            elif current == 'region':
                values = dict(scopes['global_'], **scopes['master']); values.update(scopes['group'])
            else:
                values = {}
        else:
            end = tokens[index + 1].start() if index + 1 < len(tokens) else len(text)
            values[token[2]] = text[token.end():end].strip().strip('"')
    finish()
    return regions


def sf2_ranges(path, bank, program):
    """Read SoundFont hydra tables, including global/local range inheritance."""
    tables = {}
    with Path(path).open('rb') as stream:
        header = stream.read(12)
        if len(header) != 12 or header[:4] != b'RIFF' or header[8:12] != b'sfbk':
            raise ValueError('Expected an SF2 soundfont')
        end = 8 + struct.unpack_from('<I', header, 4)[0]
        if end > stream.seek(0, 2):
            raise ValueError('Truncated SF2 soundfont')
        stream.seek(12)
        while stream.tell() + 8 <= end:
            kind, size = struct.unpack('<4sI', stream.read(8)); start = stream.tell(); stop = start + size
            if stop > end:
                raise ValueError('Invalid SF2 chunk')
            if kind == b'LIST' and size >= 4 and stream.read(4) == b'pdta':
                if size > 16 * 1024 * 1024:
                    raise ValueError('SF2 preset metadata is too large')
                while stream.tell() + 8 <= stop:
                    name, length = struct.unpack('<4sI', stream.read(8))
                    if stream.tell() + length > stop:
                        raise ValueError('Invalid SF2 preset table')
                    tables[name] = stream.read(length)
                    stream.seek(length % 2, 1)
            stream.seek(stop + size % 2)

    def records(name, fmt):
        data = tables.get(name, b''); size = struct.calcsize(fmt)
        if not data or len(data) % size:
            raise ValueError('Missing or malformed SF2 table: ' + name.decode())
        return list(struct.iter_unpack(fmt, data))

    presets = records(b'phdr', '<20sHHHIII'); instruments = records(b'inst', '<20sH')
    pbag = records(b'pbag', '<HH'); ibag = records(b'ibag', '<HH')
    pgen = records(b'pgen', '<HH'); igen = records(b'igen', '<HH')

    def zones(first, last, bags, generators, target):
        if not 0 <= first <= last < len(bags):
            raise ValueError('Invalid SF2 zone index')
        global_zone = {}; result = []
        for index in range(first, last):
            a, b = bags[index][0], bags[index + 1][0]
            if not 0 <= a <= b <= len(generators):
                raise ValueError('Invalid SF2 generator index')
            zone = dict(generators[a:b])
            if target not in zone:
                if index == first:
                    global_zone = zone
                continue
            result.append(global_zone | zone)
        return result

    found = next((i for i, row in enumerate(presets[:-1]) if row[1:3] == (program, bank)), None)
    if found is None:
        raise ValueError('SF2 bank does not contain the selected program')
    ranges = []
    for preset in zones(presets[found][3], presets[found + 1][3], pbag, pgen, 41):
        ident = preset[41]
        if not 0 <= ident < len(instruments) - 1:
            raise ValueError('Invalid SF2 instrument index')
        for instrument in zones(instruments[ident][1], instruments[ident + 1][1], ibag, igen, 53):
            def bounds(zone, key):
                value = zone.get(key, 0x7f00); low, high = value & 255, value >> 8
                if not 0 <= low <= high <= 127:
                    raise ValueError('Invalid SF2 key/velocity range')
                return low, high
            keys = [bounds(z, 43) for z in (preset, instrument)]
            velocities = [bounds(z, 44) for z in (preset, instrument)]
            low = max(1, *(r[0] for r in velocities)); high = min(r[1] for r in velocities)
            if max(r[0] for r in keys) <= min(r[1] for r in keys) and low <= high:
                ranges.append((low, high))
    return ranges


def detect_options(spec):
    from lingfeng.audio import soundbanks as banks
    device = spec['device']
    if not banks.is_synth_source(device):
        return None
    info = banks.pack(device); item = banks.instrument(spec['program'], device)
    engine = info.get('engine', 'native')
    if engine == 'sfz':
        ranges = sfz_ranges(info['path'], item['sfz'])
    elif engine == 'sf2':
        from lingfeng.audio.sfz import relative_file
        root = Path(info['path']).resolve(); path = (root / relative_file(item['sf2'])).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Unsafe SF2 path')
        ranges = sf2_ranges(path, item.get('bank', 0), item['model'])
    else:
        return None
    bands = velocity_bands(ranges)
    if not bands:
        raise ValueError('No note-on velocity regions found')
    return dict(bands=bands, options=[(low + high) // 2 for low, high in bands])
