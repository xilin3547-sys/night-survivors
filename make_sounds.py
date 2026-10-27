"""Make the sound files in sounds/. Run this on your computer:

    python make_sounds.py

Only Python's standard library is used here (wave, math, array, random), so
this script can be run anywhere. It writes short 16-bit mono .wav files.

main.py never imports wave and never makes a sound itself: it only reads the
finished files from sounds/, because that also works in a web browser.
"""

import math
import os
import random
import sys
import wave
from array import array

RATE = 22050        # samples per second
VOLUME = 0.5        # how loud the files are (1.0 would be full scale)
FADE = 0.003        # seconds of fade in/out, so the samples do not click
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sounds")

RNG = random.Random(20261027)


# ------------------------------------------------------------------ building

def tone(freq, seconds, volume=1.0, decay=8.0, shape="sine"):
    """One note that fades away. shape is "sine" or "square"."""
    samples = []
    count = int(RATE * seconds)
    for i in range(count):
        t = i / RATE
        phase = (freq * t) % 1.0
        if shape == "square":
            # a soft square: the fundamental plus its first two odd harmonics
            value = (math.sin(2 * math.pi * phase)
                     + 0.35 * math.sin(2 * math.pi * 3 * phase)
                     + 0.2 * math.sin(2 * math.pi * 5 * phase)) / 1.55
        else:
            value = math.sin(2 * math.pi * freq * t)
        samples.append(value * volume * math.exp(-decay * t))
    return samples


def noise(seconds, volume=1.0, decay=40.0):
    """A short burst of random hiss, used for the "tick" of a hit."""
    return [RNG.uniform(-1.0, 1.0) * volume * math.exp(-decay * i / RATE)
            for i in range(int(RATE * seconds))]


def shift(part, seconds):
    """Move a sound part later in time."""
    return [0.0] * int(RATE * seconds) + list(part)


def mix(*parts):
    """Add parts on top of each other, keeping the loudest length."""
    length = max((len(p) for p in parts), default=0)
    out = [0.0] * length
    for part in parts:
        for i, value in enumerate(part):
            out[i] += value
    return out


def smooth(samples):
    """Fade the first and last few milliseconds, so nothing clicks."""
    n = int(RATE * FADE)
    if n * 2 < len(samples):
        for i in range(n):
            samples[i] *= i / n
            samples[-1 - i] *= i / n
    return samples


# ------------------------------------------------------------------- the five

def make_sounds():
    """The five short sounds of the game, as lists of samples."""
    hit = mix(
        noise(0.05, 0.7, decay=90.0),
        tone(1250, 0.05, 0.5, decay=55.0),
    )

    gem = mix(
        shift(tone(880, 0.06, 0.7, decay=20.0), 0.0),
        shift(tone(1320, 0.11, 0.7, decay=16.0), 0.05),
    )

    levelup = mix(
        shift(tone(523.25, 0.10, 0.7, decay=10.0), 0.00),
        shift(tone(659.25, 0.10, 0.7, decay=10.0), 0.08),
        shift(tone(783.99, 0.10, 0.7, decay=10.0), 0.16),
        shift(tone(1046.5, 0.30, 0.8, decay=7.0), 0.24),
    )

    hurt = mix(
        tone(155, 0.20, 0.9, decay=11.0, shape="square"),
        shift(noise(0.08, 0.5, decay=45.0), 0.0),
    )

    # one soft chord: it fits both VICTORY and GAME OVER
    end = mix(
        tone(523.25, 0.9, 0.5, decay=3.0),
        tone(659.25, 0.9, 0.45, decay=3.0),
        tone(783.99, 0.9, 0.4, decay=3.0),
    )

    return {"hit": hit, "gem": gem, "levelup": levelup, "hurt": hurt, "end": end}


# --------------------------------------------------------------------- saving

def write(name, samples):
    """Save one list of -1..1 samples as a 16-bit mono .wav file."""
    data = array("h")
    for value in samples:
        scaled = max(-1.0, min(1.0, value * VOLUME))
        data.append(int(scaled * 32767))
    if sys.byteorder != "little":
        data.byteswap()
    path = os.path.join(OUT, name + ".wav")
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(data.tobytes())
    return path


def main():
    os.makedirs(OUT, exist_ok=True)
    made = []
    for name, samples in make_sounds().items():
        write(name, smooth(samples))
        made.append((name, len(samples) / RATE))
    print(f"wrote {len(made)} files to sounds/ ({RATE} Hz, mono, 16-bit):")
    for name, seconds in made:
        print(f"   {name}.wav   {seconds:.2f} s")


if __name__ == "__main__":
    main()
