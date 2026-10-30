"""GM1 program names, in wire order (0..127); UI numbering is 1..128."""

NAMES=tuple(tuple(row.split('|')) for row in '''原声大钢琴|Acoustic Grand Piano
明亮钢琴|Bright Acoustic Piano
电声三角钢琴|Electric Grand Piano
酒吧钢琴|Honky-tonk Piano
电钢琴 1|Electric Piano 1
电钢琴 2|Electric Piano 2
羽管键琴|Harpsichord
击弦古钢琴|Clavinet
钢片琴|Celesta
钟琴|Glockenspiel
音乐盒|Music Box
颤音琴|Vibraphone
马林巴|Marimba
木琴|Xylophone
管钟|Tubular Bells
扬琴|Dulcimer
拉杆风琴|Drawbar Organ
打击风琴|Percussive Organ
摇滚风琴|Rock Organ
教堂管风琴|Church Organ
簧风琴|Reed Organ
手风琴|Accordion
口琴|Harmonica
探戈手风琴|Tango Accordion
尼龙弦吉他|Acoustic Guitar (Nylon)
钢弦吉他|Acoustic Guitar (Steel)
爵士电吉他|Electric Guitar (Jazz)
清音电吉他|Electric Guitar (Clean)
闷音电吉他|Electric Guitar (Muted)
过载电吉他|Overdriven Guitar
失真电吉他|Distortion Guitar
吉他泛音|Guitar Harmonics
原声贝斯|Acoustic Bass
指弹电贝斯|Electric Bass (Finger)
拨片电贝斯|Electric Bass (Pick)
无品贝斯|Fretless Bass
击弦贝斯 1|Slap Bass 1
击弦贝斯 2|Slap Bass 2
合成贝斯 1|Synth Bass 1
合成贝斯 2|Synth Bass 2
小提琴|Violin
中提琴|Viola
大提琴|Cello
低音提琴|Contrabass
颤弓弦乐|Tremolo Strings
拨弦弦乐|Pizzicato Strings
管弦竖琴|Orchestral Harp
定音鼓|Timpani
弦乐合奏 1|String Ensemble 1
弦乐合奏 2|String Ensemble 2
合成弦乐 1|Synth Strings 1
合成弦乐 2|Synth Strings 2
合唱 啊|Choir Aahs
人声 呜|Voice Oohs
合成人声|Synth Voice
管弦齐奏|Orchestra Hit
小号|Trumpet
长号|Trombone
大号|Tuba
弱音小号|Muted Trumpet
圆号|French Horn
铜管合奏|Brass Section
合成铜管 1|Synth Brass 1
合成铜管 2|Synth Brass 2
高音萨克斯|Soprano Sax
中音萨克斯|Alto Sax
次中音萨克斯|Tenor Sax
上低音萨克斯|Baritone Sax
双簧管|Oboe
英国管|English Horn
巴松|Bassoon
单簧管|Clarinet
短笛|Piccolo
长笛|Flute
竖笛|Recorder
排箫|Pan Flute
吹瓶|Blown Bottle
尺八|Shakuhachi
口哨|Whistle
陶笛|Ocarina
方波主音|Lead 1 (Square)
锯齿波主音|Lead 2 (Sawtooth)
汽笛风琴主音|Lead 3 (Calliope)
气声主音|Lead 4 (Chiff)
电弦主音|Lead 5 (Charang)
人声主音|Lead 6 (Voice)
五度主音|Lead 7 (Fifths)
贝斯与主音|Lead 8 (Bass + Lead)
新世纪铺底|Pad 1 (New Age)
温暖铺底|Pad 2 (Warm)
复合合成铺底|Pad 3 (Polysynth)
合唱铺底|Pad 4 (Choir)
弓弦铺底|Pad 5 (Bowed)
金属铺底|Pad 6 (Metallic)
光晕铺底|Pad 7 (Halo)
扫频铺底|Pad 8 (Sweep)
雨声效果|FX 1 (Rain)
配乐效果|FX 2 (Soundtrack)
水晶效果|FX 3 (Crystal)
氛围效果|FX 4 (Atmosphere)
明亮效果|FX 5 (Brightness)
精灵效果|FX 6 (Goblins)
回声效果|FX 7 (Echoes)
科幻效果|FX 8 (Sci-fi)
西塔琴|Sitar
班卓琴|Banjo
三味线|Shamisen
筝|Koto
卡林巴|Kalimba
风笛|Bagpipe
民间小提琴|Fiddle
唢呐|Shanai
铃铛|Tinkle Bell
阿戈戈铃|Agogo
钢鼓|Steel Drums
木鱼|Woodblock
太鼓|Taiko Drum
有调通鼓|Melodic Tom
合成鼓|Synth Drum
反向镲|Reverse Cymbal
吉他换把声|Guitar Fret Noise
呼吸声|Breath Noise
海浪|Seashore
鸟鸣|Bird Tweet
电话铃|Telephone Ring
直升机|Helicopter
掌声|Applause
枪声|Gunshot'''.splitlines())

def label(program):
    from .i18n import LANGUAGE
    return f'{program+1:02} · '+NAMES[program][1 if LANGUAGE=='en' else 0]
