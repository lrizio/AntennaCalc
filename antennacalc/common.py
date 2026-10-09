"""Shared tables: bands, materials, conductor sizes, feed lines, grounds."""
from __future__ import annotations

import math

from .mom import C0, Ground

# (label, f_lo MHz, f_hi MHz, design centre MHz)
BANDS = [
    ("160 m (1.8-2.0 MHz)", 1.8, 2.0, 1.85),
    ("80 m (3.5-4.0 MHz)", 3.5, 4.0, 3.6),
    ("60 m (5.33-5.40 MHz)", 5.3305, 5.4035, 5.357),
    ("40 m (7.0-7.3 MHz)", 7.0, 7.3, 7.1),
    ("30 m (10.1-10.15 MHz)", 10.1, 10.15, 10.125),
    ("20 m (14.0-14.35 MHz)", 14.0, 14.35, 14.15),
    ("17 m (18.07-18.17 MHz)", 18.068, 18.168, 18.118),
    ("15 m (21.0-21.45 MHz)", 21.0, 21.45, 21.2),
    ("12 m (24.89-24.99 MHz)", 24.89, 24.99, 24.94),
    ("10 m (28.0-29.7 MHz)", 28.0, 29.7, 28.5),
    ("6 m (50-54 MHz)", 50.0, 54.0, 51.0),
    ("4 m (70-70.5 MHz)", 70.0, 70.5, 70.25),
    ("2 m (144-148 MHz)", 144.0, 148.0, 145.0),
    ("1.25 m (222-225 MHz)", 222.0, 225.0, 223.5),
    ("70 cm (430-440 MHz)", 430.0, 440.0, 435.0),
    ("33 cm (902-928 MHz)", 902.0, 928.0, 915.0),
    ("23 cm (1240-1300 MHz)", 1240.0, 1300.0, 1270.0),
    ("13 cm (2300-2450 MHz)", 2300.0, 2450.0, 2400.0),
    ("9 cm (3300-3500 MHz)", 3300.0, 3500.0, 3400.0),
    ("5 cm (5650-5925 MHz)", 5650.0, 5925.0, 5800.0),
    ("3 cm (10.0-10.5 GHz)", 10000.0, 10500.0, 10368.0),
    ("1.2 cm (24.0-24.25 GHz)", 24000.0, 24250.0, 24048.0),
    ("Custom range", 0.0, 0.0, 0.0),
]
BAND_BY_LABEL = {b[0]: b for b in BANDS}
HF_BAND_LABELS = [b[0] for b in BANDS[:10]]
NONE_BAND = "(none)"


def band_short(label: str) -> str:
    return label.split(" (")[0]


# key -> (label, conductivity S/m, density g/cm3)
MATERIALS = {
    "copper": ("Copper (hard-drawn)", 5.65e7, 8.96),
    "ccs": ("Copper-clad steel", 5.0e7, 8.2),
    "silver": ("Silver-plated copper", 6.0e7, 8.96),
    "alu": ("Aluminium (6061 tube / wire)", 2.5e7, 2.70),
    "alu_pure": ("Aluminium (pure wire)", 3.5e7, 2.70),
    "brass": ("Brass", 1.5e7, 8.5),
    "bronze": ("Phosphor bronze", 9.0e6, 8.8),
    "stainless": ("Stainless steel (304)", 1.4e6, 8.0),
    "steel": ("Galvanised / mild steel", 6.0e6, 7.85),
    "tape": ("Steel tape (tape-measure, 25 mm flat)", 5.0e6, 7.85),
}

# label -> diameter in mm
DIAMETERS = [
    ("AWG 6  (4.12 mm)", 4.115), ("AWG 8  (3.26 mm)", 3.264), ("AWG 10 (2.59 mm)", 2.588),
    ("AWG 12 (2.05 mm)", 2.053), ("AWG 14 (1.63 mm)", 1.628), ("AWG 16 (1.29 mm)", 1.291),
    ("AWG 18 (1.02 mm)", 1.024), ("AWG 20 (0.81 mm)", 0.812), ("AWG 22 (0.64 mm)", 0.644),
    ("AWG 24 (0.51 mm)", 0.511), ("AWG 26 (0.40 mm)", 0.405),
    ("1/4\" tube (6.35 mm)", 6.35), ("3/8\" tube (9.53 mm)", 9.53), ("1/2\" tube (12.7 mm)", 12.7),
    ("5/8\" tube (15.9 mm)", 15.875), ("3/4\" tube (19.05 mm)", 19.05), ("7/8\" tube (22.2 mm)", 22.225),
    ("1\" tube (25.4 mm)", 25.4), ("1-1/4\" tube (31.75 mm)", 31.75), ("1-1/2\" tube (38.1 mm)", 38.1),
    ("2\" tube (50.8 mm)", 50.8),
    ("2 mm", 2.0), ("3 mm", 3.0), ("4 mm", 4.0), ("5 mm", 5.0), ("6 mm", 6.0), ("8 mm", 8.0),
    ("10 mm", 10.0), ("12 mm", 12.0), ("16 mm", 16.0), ("20 mm", 20.0), ("25 mm", 25.0),
    ("Flat tape 25 mm (eq. 12.5 mm)", 12.5),
]
DIAM_BY_LABEL = dict(DIAMETERS)

# key -> (label, Z0, velocity factor, loss dB/100 m at 100 MHz)
COAX = {
    "none": ("(none / ideal)", 50.0, 1.0, 0.0),
    "rg58": ("RG-58 (50 ohm)", 50.0, 0.66, 16.0),
    "rg8x": ("RG-8X (50 ohm)", 50.0, 0.78, 11.5),
    "rg213": ("RG-213 / RG-8 (50 ohm)", 50.0, 0.66, 8.6),
    "lmr400": ("LMR-400 (50 ohm)", 50.0, 0.85, 4.1),
    "lmr600": ("LMR-600 (50 ohm)", 50.0, 0.87, 2.7),
    "hard12": ("1/2\" hardline (50 ohm)", 50.0, 0.88, 3.0),
    "rg59": ("RG-59 (75 ohm)", 75.0, 0.66, 11.0),
    "rg6": ("RG-6 (75 ohm)", 75.0, 0.78, 7.5),
    "ladder450": ("Ladder line 450 ohm", 450.0, 0.91, 0.5),
    "twin300": ("Twin-lead 300 ohm", 300.0, 0.80, 2.8),
    "open600": ("Open wire 600 ohm", 600.0, 0.97, 0.25),
}
COAX_LABELS = [(v[0], k) for k, v in COAX.items()]
FEEDER_KEYS = ["ladder450", "twin300", "open600", "rg213"]

TRANSFORMERS = [("1:1 (none / 1:1 balun)", 1.0), ("1.5:1", 1.5), ("2:1", 2.0), ("4:1 balun", 4.0),
                ("6:1", 6.0), ("9:1 unun", 9.0), ("16:1", 16.0), ("25:1", 25.0),
                ("49:1 unun", 49.0), ("64:1 unun", 64.0)]

GROUNDS = [
    ("Free space (no ground)", Ground("free")),
    ("Perfect ground", Ground("perfect")),
    ("Very poor (desert/rock) s=0.001, er=3", Ground("real", 0.001, 3.0)),
    ("Poor (dry) s=0.001, er=5", Ground("real", 0.001, 5.0)),
    ("Average s=0.005, er=13", Ground("real", 0.005, 13.0)),
    ("Good (rich farmland) s=0.0303, er=20", Ground("real", 0.0303, 20.0)),
    ("Salt water s=5, er=81", Ground("real", 5.0, 81.0)),
]
GROUND_BY_LABEL = dict(GROUNDS)


def wavelength(f_mhz: float) -> float:
    return C0 / (f_mhz * 1e6)


def db10(x):
    import numpy as np
    return 10 * np.log10(np.maximum(x, 1e-30))


def swr_from_z(z: complex, z0: float = 50.0) -> float:
    g = (z - z0) / (z + z0)
    m = min(abs(g), 0.9999)
    return (1 + m) / (1 - m)


def fmt_len(m: float) -> str:
    """Length in metres with feet/inches alongside."""
    ft = m / 0.3048
    ft_i = int(ft)
    inch = (ft - ft_i) * 12
    return f"{m:.3f} m  ({ft_i} ft {inch:.1f} in)"
