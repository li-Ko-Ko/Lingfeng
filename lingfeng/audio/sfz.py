"""Validated SFZ assets and the small, headless sfizz C API backend.

Each channel owns its synth. Playback and export use the same renderer; export
enables freewheeling so disk streaming cannot outrun sample reads.
"""
import ctypes as C
import re
import threading
from pathlib import Path, PureWindowsPath

import numpy as np

_validation_cache = {}
_validation_lock = threading.RLock()


def _stamp(path):
    value = path.stat(follow_symlinks=False)
    return (value.st_mtime_ns, value.st_size, value.st_mode, value.st_ino,
            getattr(value, 'st_file_attributes', 0))


def relative_file(value):
    """Reject absolute/drive/ADS paths even when inspecting a cached manifest."""
    if not isinstance(value, str) or not value or '\0' in value or ':' in value:
        raise ValueError('Invalid pack-relative path')
    path = PureWindowsPath(value)
    if path.drive or path.root:
        raise ValueError('Absolute paths are not allowed in a sound pack')
    depth = 0
    for part in path.parts:
        if part == '..':
            depth -= 1
            if depth < 0:
                raise ValueError('Path escapes the sound pack')
        elif part != '.':
            depth += 1
    return value.replace('\\', '/')


def _asset(root, base, value, directory=False):
    # References in an included mapping can use ../ while remaining in its pack.
    if not isinstance(value, str) or not value or '\0' in value or ':' in value:
        raise ValueError('Invalid SFZ asset path')
    relative = PureWindowsPath(value)
    if relative.drive or relative.root:
        raise ValueError('Absolute SFZ asset path')
    path = (base / value.replace('\\', '/')).resolve()
    if not path.is_relative_to(root) or not (path.is_dir() if directory else path.is_file()):
        raise ValueError('Missing or unsafe SFZ asset: ' + value)
    return path


def validate_assets(root, relative, *, include_text=False):
    """Check includes, macros, default_path and samples before sfizz reads them.

    No audio is decoded or native code executed during a pack scan. Bounds also
    reject include cycles and unexpectedly large preprocessing input.
    """
    root = Path(root).resolve()
    mapping = _asset(root, root, relative_file(relative))
    if mapping.suffix.lower() != '.sfz':
        raise ValueError('Expected an SFZ mapping')
    cache_key = (str(root), str(mapping))
    with _validation_lock:
        cached = _validation_cache.get(cache_key)
    if cached and not include_text:
        try:
            if all(_stamp(path) == stamp for path, stamp in cached):
                return mapping
        except OSError:
            pass
    macros = {}; files = set(); total = 0; dependencies = {}; checked = {}

    def asset(base, value, directory=False):
        key = (base, value, directory)
        if key in checked:
            return checked[key]
        resolved = _asset(root, base, value, directory)
        # Track both the spelling in the mapping and its resolved destination.
        # Parent stamps invalidate cached resolution if a directory or junction
        # is replaced; lstat also notices a file replaced by a symlink.
        for path in (base / value.replace('\\', '/'), resolved):
            for dependency in (path, *path.parents):
                if dependency not in dependencies:
                    dependencies[dependency] = _stamp(dependency)
                if dependency == root:
                    break
        checked[key] = resolved
        return resolved

    asset(root, relative_file(relative))

    def expand(value):
        for _ in range(16):
            updated = re.sub(r'\$[\w]+', lambda m: macros.get(m[0], m[0]), value)
            if updated == value:
                break
            value = updated
        if '$' in value:
            raise ValueError('Unresolved SFZ path macro')
        return value.strip().strip('"')

    def source(path, stack):
        nonlocal total
        if path in stack or len(stack) >= 16 or len(files) >= 128:
            raise ValueError('Invalid SFZ include chain')
        size = path.stat().st_size; total += size
        if total > 4 * 1024 * 1024:
            raise ValueError('SFZ mappings are too large')
        files.add(path)
        text = path.read_text('utf-8-sig')
        text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
        result = []
        for line in text.splitlines():
            define = re.fullmatch(r'\s*#define\s+(\$\w+)\s+(.+?)\s*', line)
            include = re.fullmatch(r'\s*#include\s+"([^"]+)"\s*', line)
            if define:
                macros[define[1]] = expand(define[2])
            elif include:
                result.append(source(asset(path.parent, expand(include[1])), (*stack, path)))
            elif re.match(r'\s*#include\b', line):
                raise ValueError('Invalid SFZ include')
            else:
                result.append(re.sub(r'\$[\w]+', lambda m: macros.get(m[0], m[0]), line))
        return '\n'.join(result)

    text = source(mapping, ())
    # SFZ file operations (including default_path) are relative to the top-level
    # mapping's parent, as documented by sfizz_load_file.
    default = mapping.parent
    tokens = list(re.finditer(r'<[^>]*>|\b([A-Za-z_]\w*)\s*=', text))
    samples = 0
    for index, match in enumerate(tokens):
        key = match[1]
        if key not in ('sample', 'default_path'):
            continue
        end = tokens[index + 1].start() if index + 1 < len(tokens) else len(text)
        value = expand(text[match.end():end])
        if key == 'default_path':
            default = asset(mapping.parent, value, directory=True) if value else mapping.parent
        elif value.startswith('*'):
            continue  # SFZ's built-in oscillators have no external files.
        else:
            asset(default, value); samples += 1
    if not samples:
        raise ValueError('SFZ mapping contains no recorded samples')
    with _validation_lock:
        if len(_validation_cache) >= 64:
            _validation_cache.pop(next(iter(_validation_cache)))
        _validation_cache[cache_key] = tuple(dependencies.items())
    return (mapping, text) if include_text else mapping


def configure_library(lib):
    pointer = C.c_void_p; integer = C.c_int; floating = C.c_float
    signatures = {
        'create_synth': ([], pointer), 'free': ([pointer], None),
        'load_file': ([pointer, C.c_char_p], C.c_bool),
        'set_sample_rate': ([pointer, floating], None),
        'set_samples_per_block': ([pointer, integer], None),
        'set_num_voices': ([pointer, integer], None),
        'get_num_voices': ([pointer], integer), 'get_num_regions': ([pointer], integer),
        'send_note_on': ([pointer, integer, integer, integer], None),
        'send_note_off': ([pointer, integer, integer, integer], None),
        'send_cc': ([pointer, integer, integer, integer], None),
        'send_pitch_wheel': ([pointer, integer, integer], None),
        'all_sound_off': ([pointer], None), 'enable_freewheeling': ([pointer], None),
        'render_block': ([pointer, C.POINTER(C.POINTER(floating)), integer, integer], None),
    }
    for name, (args, result) in signatures.items():
        function = getattr(lib, 'sfizz_' + name)
        function.argtypes = args; function.restype = result
    return lib


class SfzVoice:
    def __init__(self, api, info, item, rate, block, offline=False):
        self.handle = None; self.api = api; self.gain = item['gain']; self.block = block
        self.volume = 100; self.expression = 127; self.pan = 64
        self.started = False
        self.planar = np.empty((2, block), np.float32)
        self.outputs = (C.POINTER(C.c_float) * 2)(*(row.ctypes.data_as(C.POINTER(C.c_float)) for row in self.planar))
        mapping = validate_assets(info['path'], item['sfz'])
        self.handle = api.sfizz_create_synth()
        if not self.handle:
            raise RuntimeError('Cannot create sfizz synthesizer')
        try:
            api.sfizz_set_sample_rate(self.handle, rate)
            api.sfizz_set_samples_per_block(self.handle, block)
            api.sfizz_set_num_voices(self.handle, info.get('voices', 128))
            if not api.sfizz_load_file(self.handle, str(mapping).encode('utf-8')) or not api.sfizz_get_num_regions(self.handle):
                raise ValueError('Cannot load SFZ mapping: ' + item['sfz'])
            if offline:
                api.sfizz_enable_freewheeling(self.handle)
            # Host controls are applied after rendering so every mapping supports
            # volume, expression and pan without relying on optional SFZ opcodes.
            for cc, value in item.get('controls', {}).items():
                self.send(0xb0, int(cc), round(value))
        except Exception:
            self.close(); raise

    def send(self, status, a=0, b=0):
        kind = status & 0xf0
        if kind == 0x90 and b:
            self.started = True
            self.api.sfizz_send_note_on(self.handle, 0, a, b)
        elif kind == 0x80 or kind == 0x90:
            self.api.sfizz_send_note_off(self.handle, 0, a, b)
        elif kind == 0xe0:
            self.api.sfizz_send_pitch_wheel(self.handle, 0, a + (b << 7) - 8192)
        elif kind == 0xb0:
            if a == 7: self.volume = b
            elif a == 11: self.expression = b
            elif a == 10: self.pan = b
            elif a == 120:
                self.api.sfizz_all_sound_off(self.handle); self.started = False
            else:
                if a != 123: self.started = True  # CC-triggered pedal/noise regions.
                self.api.sfizz_send_cc(self.handle, 0, a, b)

    def render(self, count):
        if not self.started:
            return np.zeros((count, 2), np.float32)
        result = np.empty((count, 2), np.float32)
        if not count:
            return result
        for start in range(0, count, self.block):
            size = min(self.block, count - start)
            self.api.sfizz_render_block(self.handle, self.outputs, 2, size)
            result[start:start + size] = self.planar[:, :size].T
        result *= self.gain * (self.volume / 127) * (self.expression / 127)
        # Preserve the library's stereo image at centre; attenuate the opposite
        # side toward each endpoint, matching MIDI's conventional 64 centre.
        if self.pan < 64: result[:, 1] *= self.pan / 64
        elif self.pan > 64: result[:, 0] *= (127 - self.pan) / 63
        return result

    def close(self):
        if self.handle:
            self.api.sfizz_free(self.handle); self.handle = None

    def __del__(self): self.close()
