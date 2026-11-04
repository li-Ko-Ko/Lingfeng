"""User-wide rhythm recognition preference, independent of project data."""

_enabled = True


def enabled():
    return _enabled


def set_enabled(value):
    global _enabled
    _enabled = value if type(value) is bool else True


def load_preferences(values):
    values = values if isinstance(values, dict) else {}
    set_enabled(values.get('rhythm_recognition', True))


def settings_dict():
    return {'rhythm_recognition': _enabled}
