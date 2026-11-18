"""Two-way de-vig methods (REPORT_v6 §1, PREREG §11).

All take decimal odds (o1, o2) and return (p1, ok). ok = False when the method has no valid solution
for that quote; the caller decides what to do (p1 is then the multiplicative value).
  mult   p_i = (1/o_i) / sum(1/o)                                    (never fails for o_i > 1)
  power  p_i = (1/o_i)^k, k > 0 solved so that sum = 1              (fails only if no root in (0.2, 5))
  shin   Shin (1993) two-outcome model: p_i = (sqrt(z^2 + 4(1-z) pi_i^2 / S) - z) / (2(1-z)),
         pi_i = 1/o_i, S = sum pi, z in [0, 0.5) solved so that sum p = 1.
         Fails when S <= 1 (no overround: z <= 0 has no insider interpretation) or no root in [0, 0.5).
"""
from __future__ import annotations

import math

METHODS = ("mult", "power", "shin")


def _bisect(f, lo: float, hi: float, it: int = 80) -> float | None:
    flo, fhi = f(lo), f(hi)
    if flo == 0:
        return lo
    if flo * fhi > 0:
        return None
    for _ in range(it):
        mid = (lo + hi) / 2
        fm = f(mid)
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def mult(o1: float, o2: float) -> tuple[float, bool]:
    a, b = 1 / o1, 1 / o2
    return a / (a + b), True


def power(o1: float, o2: float) -> tuple[float, bool]:
    a, b = 1 / o1, 1 / o2
    k = _bisect(lambda k: a ** k + b ** k - 1, 0.2, 5.0)
    if k is None:
        return mult(o1, o2)[0], False
    return a ** k, True


def shin(o1: float, o2: float) -> tuple[float, bool]:
    pi = (1 / o1, 1 / o2)
    S = sum(pi)
    if S <= 1:
        return mult(o1, o2)[0], False

    def p(z: float, x: float) -> float:
        return (math.sqrt(z * z + 4 * (1 - z) * x * x / S) - z) / (2 * (1 - z))

    z = _bisect(lambda z: p(z, pi[0]) + p(z, pi[1]) - 1, 0.0, 0.4999)
    if z is None:
        return mult(o1, o2)[0], False
    p1 = p(z, pi[0])
    return p1 / (p1 + p(z, pi[1])), True  # renormalise the bisection residual


def devig(o1: float, o2: float, method: str = "mult") -> tuple[float, bool]:
    return {"mult": mult, "power": power, "shin": shin}[method](o1, o2)
