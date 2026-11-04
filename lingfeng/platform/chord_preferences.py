"""Creation defaults and the selected, ordered quick chord catalogue.

These preferences belong to the user, not the project. Dialogs edit copies and
the main window applies them only after confirmation.
"""

DEFAULT_VELOCITIES = {'melody': 92, 'harmony': 72}
DEFAULT_QUICK_QUALITIES = (
    '', 'm', '7', '7b5', 'maj7', 'm7', 'mM7', 'dim', 'm7b5', 'aug',
    'sus2', 'sus4', 'add2', '6', 'm6', '9', 'm9', 'maj9', 'dim7', '7sus4', '5',
)

_velocities = dict(DEFAULT_VELOCITIES)
_quick = list(DEFAULT_QUICK_QUALITIES)


def normalize_velocities(values):
    values = values if isinstance(values, dict) else {}
    return {role: values[role] if type(values.get(role)) is int and 1 <= values[role] <= 127 else default
            for role, default in DEFAULT_VELOCITIES.items()}


def normalize_qualities(values, fallback=DEFAULT_QUICK_QUALITIES):
    from lingfeng.music.model import QUALITIES
    if not isinstance(values, (list, tuple)):
        values = fallback
    return list(dict.fromkeys(code for code in values if isinstance(code, str) and code in QUALITIES))


def load_preferences(values):
    global _velocities, _quick
    values = values if isinstance(values, dict) else {}
    _velocities = normalize_velocities(values.get('default_velocities'))
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
    load_preferences(values)


def default_velocity(role):
    return _velocities.get('harmony' if role == 'chords' else role, DEFAULT_VELOCITIES['melody'])


def quick_qualities():
    return list(_quick)


def settings_dict():
    return {'default_velocities': dict(_velocities), 'quick_chord_qualities': list(_quick)}
