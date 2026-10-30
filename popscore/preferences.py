"""Versioned user preferences, independent of the portable installation folder.

Loading is read-only. Saving preserves unknown fields, keeps upgrade/recovery
copies and replaces the complete JSON atomically. Projects migrate separately.
"""
import copy
import json
import os
import re
import tempfile
from pathlib import Path
from . import __version__

SCHEMA_VERSION = 1


def _invalid_constant(value):
    raise ValueError('Non-JSON numeric constant: '+value)


def read_object(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8-sig'),parse_constant=_invalid_constant)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name+'.', suffix='.tmp', delete=False) as stream:
            temp = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def load_preferences(folder):
    path = Path(folder)/'preferences.json'
    value = read_object(path)
    if value is None:
        value = read_object(path.with_suffix('.json.bak')) or {}
    result = copy.deepcopy(value)
    # Containers consumed by UI code must have the expected shape. Unknown
    # keys are intentionally retained for additive upgrades and downgrades.
    for key in ('keybindings', 'chord_edit_options', 'colors', 'roll_coloring'):
        if key in result and not isinstance(result[key], dict):
            result[key] = {}
    if isinstance(result.get('roll_coloring'), dict):
        for role in ('melody', 'harmony'):
            if not isinstance(result['roll_coloring'].get(role, {}), dict):
                result['roll_coloring'][role] = {}
    if not isinstance(result.get('chord_order', []), list):
        result['chord_order'] = []
    elif 'chord_order' in result:
        result['chord_order'] = [item for item in result['chord_order'] if isinstance(item,str)]
    if not isinstance(result.get('last_project_dir', ''), str):
        result.pop('last_project_dir', None)
    result['language'] = 'en' if result.get('language') == 'en' else 'zh'
    return result


def save_preferences(folder, changes, previous=None):
    path = Path(folder)/'preferences.json'
    current = read_object(path)
    previous = previous if isinstance(previous, dict) else {}
    result = dict(previous, **(current or {}))
    result.update(changes)
    # Never lower a newer schema when an older executable is used temporarily.
    schema = result.get('schema_version', 0)
    result['schema_version'] = max(SCHEMA_VERSION, schema if type(schema) is int else 0)
    result['app_version'] = __version__
    if current is not None:
        if current.get('app_version') != __version__ or current.get('schema_version') != SCHEMA_VERSION:
            version = re.sub(r'[^0-9A-Za-z._-]', '_', __version__)
            upgrade = path.with_name('preferences.pre-'+version+'.json')
            if not upgrade.exists():
                atomic_json(upgrade, current)
        atomic_json(path.with_suffix('.json.bak'), current)
    elif path.exists():
        # Keep the original damaged bytes for manual recovery before replacing.
        damaged = path.with_suffix('.json.corrupt')
        if not damaged.exists():
            damaged.write_bytes(path.read_bytes())
    atomic_json(path, result)
    return result
