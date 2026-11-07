"""Creation defaults and the selected, ordered quick chord catalogue.

These preferences belong to the user, not the project. Dialogs edit copies and
the main window applies them only after confirmation.
"""

from lingfeng.music.quality_catalog import YUE2_QUALITIES, yue2_lossless_quality


DEFAULT_VELOCITIES = {'melody': 92, 'instrument': 80, 'harmony': 72}
DEFAULT_QUICK_QUALITIES = YUE2_QUALITIES

_velocities = dict(DEFAULT_VELOCITIES)
_quick = list(DEFAULT_QUICK_QUALITIES)
_include_instrument = False


def normalize_velocities(values):
    values = values if isinstance(values, dict) else {}
    result = {role: values[role] if type(values.get(role)) is int and 1 <= values[role] <= 127 else default
              for role, default in DEFAULT_VELOCITIES.items()}
    if 'instrument' not in values and result['melody'] != DEFAULT_VELOCITIES['melody']:
        # Preserve a customized shared melody value from older settings.
        result['instrument'] = result['melody']
    return result


def normalize_qualities(values, fallback=DEFAULT_QUICK_QUALITIES):
    from lingfeng.music.model import QUALITIES
    if not isinstance(values, (list, tuple)):
        values = fallback
    return list(dict.fromkeys(code for code in values if isinstance(code, str) and code in QUALITIES))


def load_preferences(values):
    global _velocities, _quick
    values = values if isinstance(values, dict) else {}
    _velocities = normalize_velocities(values.get('default_velocities'))
    set_include_instrument_in_recognition(values.get('include_instrument_in_recognition'))
    if isinstance(values.get('quick_chord_qualities'), list):
        _quick = normalize_qualities(values['quick_chord_qualities'])
    else:
        # Old preferences described ordering, never selection. Retain that order
        # among the original quick choices, then append any missing old choices.
        legacy = values.get('chord_order')
        legacy = legacy if isinstance(legacy, list) else []
        legacy = ['add2' if code == 'add9' else code for code in legacy if isinstance(code, str)]
        ordered = [code for code in legacy if code in DEFAULT_QUICK_QUALITIES]
        _quick = normalize_qualities(ordered + list(DEFAULT_QUICK_QUALITIES))


def set_preferences(values):
    values = values if isinstance(values, dict) else {}
    load_preferences({'include_instrument_in_recognition': _include_instrument, **values})


def default_velocity(role):
    return _velocities.get('harmony' if role == 'chords' else role, DEFAULT_VELOCITIES['melody'])


def quick_qualities():
    return [code for code in _quick if yue2_lossless_quality(code) is not None]


def include_instrument_in_recognition():
    return _include_instrument


def set_include_instrument_in_recognition(enabled):
    global _include_instrument
    _include_instrument = enabled is True


def settings_dict(*, include_recognition=False):
    settings = {'default_velocities': dict(_velocities), 'quick_chord_qualities': list(_quick)}
    if include_recognition:
        settings['include_instrument_in_recognition'] = _include_instrument
    return settings
