"""Pitch-class template matching, informed by PyChord's root-rotation algorithm.

Independent implementation: octave duplicates are removed, every present root is
tested against exact interval sets, then candidates are ranked by previous symbol
and bass position. No guessed label is assigned to an unmatched set.
See docs/THIRD_PARTY.md for upstream algorithm and license information.
"""
from dataclasses import dataclass, replace
from lingfeng.music.model import QUALITIES, Chord

# Recognition always uses the complete fixed catalogue, independent of quick-menu
# selection and ordering. Index each pitch set once, retaining every alias.
_QUALITY_ORDER={quality:index for index,quality in enumerate(QUALITIES)}
_TEMPLATES={}
for _quality,_intervals in QUALITIES.items():
    _TEMPLATES.setdefault(frozenset(value%12 for value in _intervals),[]).append(_quality)


@dataclass(frozen=True)
class Candidate:
    root: int
    quality: str
    bass: int | None

    @property
    def name(self):
        return Chord(0,960,self.root,self.quality,self.bass).name

    @property
    def inversion(self):
        """Chord-tone index of the bass; None for a non-chord slash bass."""
        interval=0 if self.bass is None else (self.bass-self.root)%12
        tones=[x%12 for x in QUALITIES[self.quality]]
        return tones.index(interval) if interval in tones else None


@dataclass(frozen=True)
class InstrumentAnalysis:
    pitch_classes: frozenset[int]
    candidates: tuple[Candidate, ...]

    @property
    def symbol(self):
        return self.candidates[0] if self.candidates else None


def apply_instrument_recognition(project, chords):
    """Derive the chord track's display without altering either roll's notes."""
    from lingfeng.platform.chord_preferences import include_instrument_in_recognition

    inherited = include_instrument_in_recognition()
    eligible = []
    for chord in chords:
        if hasattr(chord, '_instrument_analysis'):
            del chord._instrument_analysis
        override = chord.include_instrument_in_recognition
        if not chord.recognition_disabled and (inherited if override is None else override):
            eligible.append(chord)
    if not eligible or not project.instrument_notes:
        return

    notes = iter(sorted(project.instrument_notes, key=lambda note: note.start))
    incoming = next(notes, None)
    sounding = []
    for chord in sorted(eligible, key=lambda chord: chord.start):
        sounding = [note for note in sounding if note.end > chord.start]
        while incoming is not None and incoming.start < chord.end:
            if incoming.end > chord.start:
                sounding.append(incoming)
            incoming = next(notes, None)
        if not sounding:
            continue

        performed = {note.pitch for note in chord.render_notes()}
        pitches = performed | {note.pitch for note in sounding}
        pitch_classes = frozenset(pitch % 12 for pitch in pitches)
        if performed and {pitch % 12 for pitch in performed} == pitch_classes:
            if min(performed) % 12 == min(pitches) % 12:
                continue
        preferred = chord.instrument_symbol_preference or (chord.root % 12, chord.quality)
        chord._instrument_analysis = InstrumentAnalysis(pitch_classes, tuple(recognize(pitches, preferred)))


def chord_candidates(chord):
    """Return exact names from the recognition source currently in use."""
    if chord.recognition_disabled:
        return ()
    analysis = chord.instrument_analysis
    if analysis is not None:
        return analysis.candidates
    return tuple(recognize((note.pitch for note in chord.render_notes()),
                           preferred=(chord.root % 12, chord.quality)))


def candidate_label(project, chord, candidate):
    from lingfeng.music.chord_operations import contextual_chord_name, roman_label

    preview = replace(chord, root=48+candidate.root, quality=candidate.quality, bass=candidate.bass,
                      recognized=True, marked=True)
    return roman_label(project, preview, preview.flat) + ' · ' + contextual_chord_name(project, preview)


def choose_chord_candidate(project, chord, candidate):
    """Adopt an exact recognition name while retaining all performed notes."""
    if candidate not in chord_candidates(chord):
        raise ValueError('此和弦名称已不匹配当前识别结果。')
    if chord.instrument_analysis is not None:
        chord.instrument_symbol_preference = (candidate.root, candidate.quality)
        project.rescan_instrument_recognition([chord])
    else:
        chord.materialize()
        update_symbol(chord, (candidate,))


def chord_inversion(chord):
    """Verify the existing symbol and its actual voicing before moving it."""
    if chord.recognition_disabled or not chord.recognized:return None
    pitches=chord.pitches if chord.notes is None else [n.pitch for n in chord.notes]
    candidate=next((c for c in recognize(pitches) if (c.root,c.quality)==(chord.root%12,chord.quality)),None)
    return candidate.inversion if candidate else None


def recognize(pitches, preferred=None):
    pitches=tuple(pitches)
    if not pitches:return []
    pcs={p%12 for p in pitches};bass=min(pitches)%12
    result=[]
    for root in sorted(pcs):
        intervals=frozenset((p-root)%12 for p in pcs)
        for quality in _TEMPLATES.get(intervals,()):
            result.append(Candidate(root,quality,None if bass==root else bass))
    return sorted(result,key=lambda c:(0 if (c.root,c.quality)==preferred else 1,
                                       c.root!=bass,len(QUALITIES[c.quality]),c.root,_QUALITY_ORDER[c.quality]))


def update_symbol(chord, candidates):
    if chord.recognition_disabled:return
    chord.recognized=bool(candidates)
    if candidates:
        c=candidates[0];chord.root=48+c.root;chord.quality=c.quality;chord.bass=c.bass


def set_recognition_disabled(chord, disabled, project=None):
    """Pause automatic labels; resuming discards any manual label without MIDI edits.

    The independent custom_rhythm preference is retained. Chord recognition being
    disabled is sufficient to block pattern recognition, including explicit
    regeneration requests, so enabling it restores the prior rhythm preference.
    """
    if type(disabled) is not bool:raise ValueError('和弦识别参数无效。')
    chord.materialize()
    if disabled:
        chord.recognition_disabled=True
        chord.recognized=chord.marked
    else:
        chord.recognition_disabled=False;chord.marked=False
        chord.instrument_symbol_preference=None
        update_symbol(chord,recognize([n.pitch for n in chord.render_notes()]))
        from lingfeng.music.rhythm import analyze
        match=analyze(chord,project)
        if match:chord.pattern=match.pattern;chord.gate=match.gate
        if project is not None:project.rescan_instrument_recognition([chord])
    return chord


def set_marker(chord, root, quality, bass=None):
    """Attach a symbol to the performed notes without replacing a single event."""
    if type(root) is not int or not 0<=root<=127 or quality not in QUALITIES:
        raise ValueError('和弦标记参数无效。')
    if bass is not None and (type(bass) is not int or bass not in range(12)):
        raise ValueError('和弦标记低音无效。')
    chord.materialize()
    chord.root=48+root%12;chord.quality=quality;chord.bass=bass
    chord.recognition_disabled=True;chord.marked=True;chord.recognized=True
    return chord
