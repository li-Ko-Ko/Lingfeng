/* The Lingfeng native sound pack ABI over the PFSynth piano player. */
#include "src/host/pfplayer.h"
#include <math.h>
#include <stdlib.h>

#define LF_API __declspec(dllexport)
#define MIDI_KEYS 128
#define RENDER_CHUNK 1024

typedef struct {
    pf_player player;
    int volume;
    int expression;
    int pan;
    int sostenuto;
} LingfengPiano;

static _Thread_local const char *last_error;

LF_API int lf_abi(void) { return 1; }
LF_API const char *lf_error(void) { return last_error; }

LF_API void *lf_create(int rate, int model, int voices)
{
    if (rate != 44100 || model != 0 || voices < 1 || voices > PF_PLAYER_VOICES) {
        last_error = "Unsupported PFSynth sample rate, preset or voice count";
        return NULL;
    }
    LingfengPiano *piano = malloc(sizeof *piano);
    if (!piano) {
        last_error = "Cannot allocate PFSynth piano";
        return NULL;
    }
    pf_player_options options;
    pf_player_defaults(&options);
    options.limiter = 0;  /* Lingfeng applies its own mix limiter. */
    pf_player_init(&piano->player, rate, &options);
    piano->player.voice_limit = voices;
    piano->volume = 100;
    piano->expression = 127;
    piano->pan = 64;
    piano->sostenuto = 0;
    return piano;
}

LF_API void lf_free(void *handle) { free(handle); }

static void piano_event(LingfengPiano *piano, unsigned char type, int note, int value)
{
    pf_midi_event event = {0, type, (unsigned char)note, (unsigned char)value};
    pf_player_event(&piano->player, &event);
}

static void control(LingfengPiano *piano, int cc, int value)
{
    switch (cc) {
    case 7: piano->volume = value; break;
    case 10: piano->pan = value; break;
    case 11: piano->expression = value; break;
    case 64: piano_event(piano, PF_EV_PEDAL, 0, value); break;
    case 66:
        if ((value >= 64) != piano->sostenuto) {
            piano->sostenuto = value >= 64;
            piano_event(piano, PF_EV_SOSTENUTO, 0, value);
        }
        break;
    case 67: piano_event(piano, PF_EV_SOFT, 0, value); break;
    case 120: pf_player_all_sounds_off(&piano->player); break;
    case 121:
        piano->expression = 127;
        piano->sostenuto = 0;
        piano_event(piano, PF_EV_PEDAL, 0, 0);
        piano_event(piano, PF_EV_SOSTENUTO, 0, 0);
        piano_event(piano, PF_EV_SOFT, 0, 0);
        break;
    case 123:
        for (int note = 0; note < MIDI_KEYS; ++note) {
            piano_event(piano, PF_EV_NOTE_OFF, note, 0);
        }
        break;
    }
}

LF_API int lf_control(void *handle, int cc, double value)
{
    if (!handle || cc < 0 || cc > 127 || !isfinite(value) || value < 0 || value > 127) {
        last_error = "Invalid PFSynth controller";
        return -1;
    }
    control(handle, cc, (int)round(value));
    return 0;
}

LF_API int lf_event(void *handle, int status, int a, int b)
{
    if (!handle || status < 0 || status > 255 || a < 0 || a > 127 || b < 0 || b > 127) {
        last_error = "Invalid PFSynth MIDI event";
        return -1;
    }
    switch (status & 0xf0) {
    case 0x80: piano_event(handle, PF_EV_NOTE_OFF, a, b); break;
    case 0x90: piano_event(handle, b ? PF_EV_NOTE_ON : PF_EV_NOTE_OFF, a, b); break;
    case 0xb0: control(handle, a, b); break;
    }
    return 0;
}

LF_API int lf_render(void *handle, float *output, int frames)
{
    if (!handle || !output || frames < 0 || frames > 65536) {
        last_error = "Invalid PFSynth render buffer";
        return -1;
    }
    LingfengPiano *piano = handle;
    const double half_pi = 1.5707963267948966;
    const double level = (piano->volume / 127.0) * (piano->expression / 127.0);
    const double angle = piano->pan * half_pi / 127.0;
    const float left = (float)(cos(angle) * level);
    const float right = (float)(sin(angle) * level);
    float mono[RENDER_CHUNK];
    while (frames > 0) {
        const int count = frames < RENDER_CHUNK ? frames : RENDER_CHUNK;
        pf_player_render(&piano->player, mono, count);
        for (int i = 0; i < count; ++i) {
            *output++ = mono[i] * left;
            *output++ = mono[i] * right;
        }
        frames -= count;
    }
    return 0;
}
