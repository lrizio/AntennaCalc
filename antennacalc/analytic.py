"""Closed-form antenna models (dish, horn, patch, slot array, small receive antennas)."""
from __future__ import annotations

import math
from typing import Callable

import numpy as np
from scipy.special import j1


class AnalyticModel:
    def __init__(self, gain_fn: Callable, zin_fn: Callable, pol: str = "V", eta: float = 1.0,
                 upper_only: bool = False, info: list | None = None):
        self._g = gain_fn
        self._z = zin_fn
        self.pol = pol
        self.eta = eta
        self.upper_only = upper_only
        self.info = info or []

    def gain_db(self, theta, phi):
        return np.asarray(self._g(np.asarray(theta, float), np.asarray(phi, float)))

    def zin(self, f_mhz: float) -> complex:
        return self._z(f_mhz)


def unit_vec(theta, phi):
    return (np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi), np.cos(theta))


def boresight(az_deg: float, el_deg: float):
    a, e = math.radians(az_deg), math.radians(el_deg)      # compass bearing: 0 = +y (north)
    return (math.cos(e) * math.sin(a), math.cos(e) * math.cos(a), math.sin(e))


def angle_off(theta, phi, b):
    x, y, z = unit_vec(theta, phi)
    c = np.clip(x * b[0] + y * b[1] + z * b[2], -1, 1)
    return np.arccos(c)


def resonator_z(f_mhz: float, f0: float, r_match: float, q: float, z0: float = 50.0) -> complex:
    """Series-RLC style impedance: z0 at f0 (matched) with loaded Q q."""
    d = f_mhz / f0 - f0 / f_mhz
    return complex(r_match, r_match * q * d)


def flat_match(swr: float, z0: float = 50.0) -> Callable:
    g = (swr - 1) / (swr + 1)
    z = z0 * (1 + g) / (1 - g)
    return lambda f: complex(z, 0.0)
