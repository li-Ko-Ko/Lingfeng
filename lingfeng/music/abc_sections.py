"""Default label correspondences used by both ABC file directions."""

from lingfeng.music.model import SECTIONS, section_name


def section_key(label):
    return ' '.join(label.strip().casefold().replace('-', ' ').replace('_', ' ').split())


_OUTPUT = {label: label for label in SECTIONS}
_INPUT = dict(_OUTPUT)


def _migrate_link(label):
    return section_name(label) if section_key(label).partition(' ')[0] == 'link' else label


def _export_mappings(mapping):
    current = {}
    legacy = {}
    for source, target in mapping.items():
        migrated = _migrate_link(source)
        entries = current if migrated == source else legacy
        entries[section_key(migrated)] = (migrated, _migrate_link(target))
    for key, (source, target) in legacy.items():
        # A customized old entry can replace a current identity mapping.
        # An explicit current replacement wins if both entries are customized.
        current_entry = current.get(key)
        if current_entry is None or (section_key(current_entry[1]) == key and section_key(target) != key):
            current[key] = (source, target)
    return dict(current.values())


def normalize_section_mappings(value=None):
    value = value if isinstance(value, dict) else {}
    result = {}
    for direction, defaults in (('import', _INPUT), ('export', _OUTPUT)):
        raw = value.get(direction)
        if not isinstance(raw, dict):
            raw = defaults
        mapping = {
            ' '.join(source.split()): ' '.join(target.split())
            for source, target in raw.items()
            if isinstance(source, str) and source.strip() and isinstance(target, str) and target.strip()
        }
        result[direction] = _export_mappings(mapping) if direction == 'export' else mapping
    return result


def section_lookup(mapping):
    return {section_key(source): target for source, target in mapping.items()}


def imported_section(label, lookup):
    return section_name(lookup.get(section_key(label), label))
