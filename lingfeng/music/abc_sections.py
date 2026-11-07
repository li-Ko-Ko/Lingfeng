"""Default label correspondences used by both ABC file directions."""

from lingfeng.music.model import SECTIONS, section_name


def section_key(label):
    return ' '.join(label.strip().casefold().replace('-', ' ').replace('_', ' ').split())


_OUTPUT = {label: label for label in SECTIONS}
_INPUT = dict(_OUTPUT)


def normalize_section_mappings(value=None):
    value = value if isinstance(value, dict) else {}
    result = {}
    for direction, defaults in (('import', _INPUT), ('export', _OUTPUT)):
        raw = value.get(direction)
        if not isinstance(raw, dict):
            raw = defaults
        # Migrate the old built-in alias while preserving custom mappings.
        raw = {source: target for source, target in raw.items()
               if (direction, source, target) not in (
                   ('export', 'Link', 'interlude'), ('import', 'interlude', 'Link'))}
        result[direction] = {
            ' '.join(source.split()): ' '.join(target.split())
            for source, target in raw.items()
            if isinstance(source, str) and source.strip() and isinstance(target, str) and target.strip()
        }
    return result


def section_lookup(mapping):
    return {section_key(source): target for source, target in mapping.items()}


def imported_section(label, lookup):
    return section_name(lookup.get(section_key(label), label))
