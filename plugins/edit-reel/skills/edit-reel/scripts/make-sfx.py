"""Generates the bundled sfx_*.mp3 sound effects from code, so every sound in this repo has a
provable source (CC0, see CREDITS.md). Standard library only; ffmpeg converts WAV to MP3.

    python3 scripts/make-sfx.py            # writes ../audios/sfx_*.mp3

The tones come from a small game's sound script: a quick attack and an exponential fade per note.
"""

import math
import random
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

RATE = 44100
OUT = Path(__file__).resolve().parent.parent / "audios"
random.seed(7)


def wave_value(kind, phase):
    x = phase % 1.0
    if kind == "sine":
        return math.sin(2 * math.pi * x)
    if kind == "square":
        return 1.0 if x < 0.5 else -1.0
    if kind == "sawtooth":
        return 2.0 * x - 1.0
    return 4.0 * abs(x - 0.5) - 1.0  # triangle


def grow(buf, need):
    if len(buf) < need:
        buf.extend([0.0] * (need - len(buf)))


def tone(buf, freq, dur, kind="triangle", vol=0.16, at=0.0, freq_end=None, decay=5.5):
    start, n = int(at * RATE), int(dur * RATE)
    grow(buf, start + n + 1)
    phase, attack = 0.0, max(1, int(0.012 * RATE))
    for k in range(n):
        t = k / n
        f = freq if freq_end is None else freq * (freq_end / freq) ** t
        phase += f / RATE
        env = (k / attack) if k < attack else math.exp(-decay * (k - attack) / max(1, n - attack))
        buf[start + k] += vol * env * wave_value(kind, phase)


def noise(buf, dur, vol=0.2, at=0.0, rise=False, smooth_from=0.9, smooth_to=0.2):
    """Filtered noise. smooth goes from smooth_from to smooth_to (lower = brighter)."""
    start, n = int(at * RATE), int(dur * RATE)
    grow(buf, start + n + 1)
    y = 0.0
    for k in range(n):
        t = k / n
        a = smooth_from + (smooth_to - smooth_from) * t
        y = a * y + (1 - a) * random.uniform(-1, 1)
        env = t ** 2 if rise else math.sin(math.pi * t)
        buf[start + k] += vol * env * y * 3


def save(name, buf, gain=1.6):
    peak = max(1e-9, max(abs(v) for v in buf))
    scale = min(gain, 0.9 / peak)
    frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v * scale)) * 32767)) for v in buf)
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / f"{name}.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(frames)
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                            "-codec:a", "libmp3lame", "-q:a", "3", str(OUT / f"{name}.mp3")], check=True)
        else:
            shutil.copy(wav, OUT / f"{name}.wav")


def make():
    b = []; tone(b, 880, 0.10); tone(b, 1320, 0.14, vol=0.12, at=0.06); save("sfx_ding", b)
    b = []
    for i, f in enumerate([988, 1319, 1568, 1976]):
        tone(b, f, 0.18, vol=0.14, at=i * 0.06)
    save("sfx_success", b)
    b = []; tone(b, 420, 0.12, "sine", 0.10, freq_end=280); save("sfx_undo", b)
    b = []; tone(b, 950, 0.05, "square", 0.05); save("sfx_tick", b, gain=1.0)
    b = []; tone(b, 150, 0.8, "sawtooth", 0.14); tone(b, 157, 0.8, "sawtooth", 0.10); save("sfx_buzzer", b, gain=1.2)
    b = []
    for i, f in enumerate([523, 659, 784, 1047, 784, 1047, 1319]):
        tone(b, f, 0.22, vol=0.16, at=i * 0.09)
    save("sfx_fanfare", b)
    b = []; tone(b, 300, 0.24, "sine", 0.12, freq_end=900); save("sfx_swoop_up", b)
    b = []; tone(b, 700, 0.10, "square", 0.07); tone(b, 1050, 0.18, "square", 0.07, at=0.09); save("sfx_alert", b, gain=1.0)
    # Soft pack: quiet accents that sit under a voice.
    b = []; tone(b, 900, 0.07, "sine", 0.2, freq_end=500, decay=7); save("sfx_pop", b)
    b = []; noise(b, 0.35, 0.25, smooth_from=0.95, smooth_to=0.55); save("sfx_swish", b)
    b = []; tone(b, 220, 0.09, "sine", 0.25, freq_end=140, decay=8); noise(b, 0.02, 0.1); save("sfx_thock", b)
    b = []; tone(b, 90, 0.35, "sine", 0.35, freq_end=50, decay=6); save("sfx_thud", b)
    b = []; tone(b, 120, 0.9, "sine", 0.35, freq_end=38, decay=3); save("sfx_subdrop", b)
    b = []
    for i, f in enumerate([2093, 2637, 3136, 3951, 3136]):
        tone(b, f, 0.35, "sine", 0.05, at=i * 0.05, decay=4)
    save("sfx_shimmer", b)
    b = []; noise(b, 1.4, 0.18, rise=True, smooth_from=0.97, smooth_to=0.3); tone(b, 200, 1.4, "sine", 0.06, freq_end=800, decay=0.5); save("sfx_rise", b)


if __name__ == "__main__":
    make()
    for p in sorted(OUT.glob("sfx_*")):
        print(p.name, p.stat().st_size, "bytes")
