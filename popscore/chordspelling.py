"""Context-aware chord spelling, separate from the configurable creation-grid spelling."""
from dataclasses import dataclass
from functools import lru_cache
from .model import MODES,MAJOR,SHARP,QUALITIES

LETTERS='CDEFGAB'
NATURALS=(0,2,4,5,7,9,11)
FLAT=('C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B')
# Written degrees determine spelling independently of performed register.
QUALITY_DEGREES={
    '':(1,3,5),'m':(1,3,5),'7':(1,3,5,7),'7b5':(1,3,5,7),'maj7':(1,3,5,7),'m7':(1,3,5,7),'mM7':(1,3,5,7),
    'dim':(1,3,5),'m7b5':(1,3,5,7),'aug':(1,3,5),'sus2':(1,2,5),'sus4':(1,4,5),
    'add2':(1,2,3,5),'6':(1,3,5,6),'m6':(1,3,5,6),'9':(1,3,5,7,9),
    'm9':(1,3,5,7,9),'maj9':(1,3,5,7,9),'dim7':(1,3,5,7),'7sus4':(1,4,5,7),'5':(1,5),
}

def accidental(pc,natural):return (pc-natural+6)%12-6

@dataclass(frozen=True)
class Tone:
    letter:int
    alteration:int
    @property
    def name(self):return LETTERS[self.letter]+('#'*self.alteration if self.alteration>0 else 'b'*-self.alteration)
    def pitch_name(self,pitch):
        # B#3 and Cb4 keep their written octaves instead of borrowing C4/B3.
        return self.name+str((pitch-NATURALS[self.letter]-self.alteration)//12-1)

@lru_cache(maxsize=72)
def scale_tones(tonic,mode):
    """Choose the ordinary seven-letter signature without needless doubles."""
    tonic%=12;options=[]
    for letter,natural in enumerate(NATURALS):
        if abs(accidental(tonic,natural))>1:continue
        tones=tuple(Tone((letter+i)%7,accidental((tonic+offset)%12,NATURALS[(letter+i)%7])) for i,offset in enumerate(MODES[mode]))
        cost=(sum(max(0,abs(t.alteration)-1) for t in tones),sum(abs(t.alteration) for t in tones),tones[0].name!=SHARP[tonic])
        options.append((cost,tones))
    return min(options,key=lambda entry:entry[0])[1]

def fallback(pc,flat=False):
    text=(FLAT if flat else SHARP)[pc%12]
    return Tone(LETTERS.index(text[0]),text.count('#')-text.count('b'))

def tone_for(pitch,context,chord=None):
    pcs=tuple((context.tonic+offset)%12 for offset in MODES[context.mode])
    tones=scale_tones(context.tonic%12,context.mode)
    if pitch%12 in pcs:return tones[pcs.index(pitch%12)]
    if chord is not None and chord.recognized:
        root=tone_for(chord.root,context) if chord.root%12 in pcs else fallback(chord.root,chord.flat)
        interval=(pitch-chord.root)%12
        for offset,degree in zip(QUALITIES[chord.quality],QUALITY_DEGREES[chord.quality]):
            if offset%12==interval:
                letter=(root.letter+degree-1)%7
                return Tone(letter,accidental(pitch%12,NATURALS[letter]))
    return fallback(pitch,chord.flat if chord is not None else False)

def degree_for(pitch,context,chord=None):
    tone=tone_for(pitch,context,chord);tonic=scale_tones(context.tonic%12,context.mode)[0]
    degree=(tone.letter-tonic.letter)%7
    return degree+1,accidental((pitch-context.tonic)%12,MAJOR[degree])

def degree_label(pitch,context,chord=None,unicode=True):
    degree,change=degree_for(pitch,context,chord)
    sharp,flat=('♯','♭') if unicode else ('#','b')
    return (sharp*change if change>0 else flat*-change)+str(degree)
