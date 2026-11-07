"""Measure preset levels offline with explicitly recognized synth runtimes."""
import hashlib
import math
import multiprocessing
from pathlib import Path
import shutil
from statistics import median
import tempfile
import time

import numpy as np

from lingfeng.audio.events import MAX_SOURCE_GAIN_DB, MIN_SOURCE_GAIN_DB
from lingfeng.audio.soundbanks import CALIBRATION_FILE
from lingfeng.platform.preferences import atomic_json


# Stock YDP with its original preset gain, measured using the same probe below.
REFERENCE_DBFS = -30.1
_NATIVE_HASH = 'ff4e67ced2e4953d99441a36cd020216df59bf6ecfa57c90612210123e4bfcee'
_SFZ_HASH = 'aa4bfa4ad9a57cfbb3c832a50be14bfe5aeaf7a36ffcdf0178547abe8719e653'
_SF2_HASHES = {
    'libfluidsynth-3.dll': 'd2819955444d4b44217be9c431f2b7e38fd4062ef71341de8725eed4e31c4957',
    'sndfile.dll': '4e3bd2de8e1485110eaebef8e1239471f73d608773831c323bf528e05645655e',
}


def _runtime_files(data):
    engine = data.get('engine', 'native')
    if engine in ('native', 'sfz'):
        expected = _NATIVE_HASH if engine == 'native' else _SFZ_HASH
        return {data['library']: expected} if data['sha256'] == expected else {}
    files = data.get('library_hashes', {})
    by_name = {Path(name).name.casefold(): value for name, value in files.items()}
    if len(files) == len(_SF2_HASHES) and by_name == _SF2_HASHES and Path(data['library']).name.casefold() == 'libfluidsynth-3.dll':
        return files
    return {}


def _measure_voice(voice, rate):
    # Compare the strongest 200 ms windows of sustained notes across registers.
    # Using the median reduces the influence of individual loud or quiet zones.
    levels = []
    window = rate // 5
    for note in (48, 60, 72):
        voice.send(0xb0, 120, 0)
        voice.send(0xb0, 7, 100)
        try:
            voice.send(0x90, note, 80)
        except RuntimeError:
            continue  # Some mapped presets have no zone for this key.
        samples = voice.render(window * 4).reshape(4, -1)
        power = float(np.square(samples, dtype=np.float64).mean(axis=1).max())
        if math.isfinite(power) and power >= 1e-8:
            levels.append(10 * math.log10(power))
    if not levels:
        return None
    gain = REFERENCE_DBFS - median(levels)
    return round(max(MIN_SOURCE_GAIN_DB, min(MAX_SOURCE_GAIN_DB, gain)), 1) or 0.0


def _measure_presets(connection, folder, runtime, data, files):
    """Copy only pinned DLLs into an isolated directory and release them on exit."""
    from lingfeng.audio.soundbanks import _inside
    from lingfeng.audio.synthesis import RATE, _library, _voice_for_pack

    try:
        for name, expected in files.items():
            target = runtime / Path(name).name
            shutil.copyfile(_inside(folder, name), target)
            with target.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                    return
        info = dict(data, path=str(folder))
        runtime_info = dict(data, path=str(runtime), library=Path(data['library']).name)
        if data.get('engine') == 'sf2':
            runtime_info['library_hashes'] = {Path(name).name: digest for name, digest in files.items()}
        library = _library(runtime_info)
        for item in data['presets']:
            gain = None
            try:
                voice = _voice_for_pack(library, info, item, offline=True)
                try:
                    gain = _measure_voice(voice, RATE)
                finally:
                    voice.close()
            except (OSError, ValueError, RuntimeError):
                pass
            connection.send((item['program'], gain))
    except (OSError, ValueError, RuntimeError, AttributeError):
        pass
    finally:
        connection.close()


def calibrate_pack(folder, data, cancel=None, progress=None):
    """Return measured corrections by program for a previously validated pack."""
    files = _runtime_files(data)
    if not files or (cancel is not None and cancel.is_set()):
        return {}

    folder = Path(folder).resolve()
    total = len(data['presets'])
    if progress:
        progress(0, total)
    gains = {}
    context = multiprocessing.get_context('spawn')
    with tempfile.TemporaryDirectory(prefix='.calibrate-', dir=folder.parent) as temporary:
        parent, child = context.Pipe(duplex=False)
        process = context.Process(target=_measure_presets, args=(child, folder, Path(temporary), data, files), daemon=True)
        try:
            process.start()
            child.close()
            deadline = time.monotonic() + 45
            done = 0
            while done < total and time.monotonic() < deadline:
                if cancel is not None and cancel.is_set():
                    break
                if not parent.poll(.05):
                    if not process.is_alive():
                        break
                    continue
                program, gain = parent.recv()
                if gain is not None:
                    gains[str(program)] = gain
                done += 1
                deadline = time.monotonic() + 45
                if progress:
                    progress(done, total)
        except (EOFError, OSError, RuntimeError):
            pass
        finally:
            parent.close()
            child.close()
            if process.pid is not None:
                process.join(.5)
                if process.is_alive():
                    process.terminate()
                    process.join()
            process.close()
    return gains


def write_calibration(folder, gains):
    atomic_json(Path(folder) / CALIBRATION_FILE, {'schema': 1, 'preset_gain_db': gains})
