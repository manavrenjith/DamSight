"""Exact analytical dam-break benchmark solutions.

Implements Ritter (1892, dry bed) and Stoker (1957, wet bed) shallow-water Riemann problem solutions.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq


def ritter_solution(
    x: np.ndarray,
    t: float,
    x0: float,
    h0: float,
    g: float = 9.80665,
) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    """Exact Ritter (1892) analytical solution for 1D dam break over a flat, dry, frictionless bed.

    Parameters
    ----------
    x : np.ndarray
        Array of 1D spatial coordinates (m).
    t : float
        Elapsed time since dam removal (s). Must be >= 0.
    x0 : float
        Initial dam axis position (m).
    h0 : float
        Initial upstream reservoir water depth (m). Must be > 0.
    g : float
        Gravitational acceleration (m/s2). Default is 9.80665.

    Returns
    -------
    h : np.ndarray
        Water depth profile (m).
    u : np.ndarray
        Flow velocity profile (m/s).
    meta : dict[str, float]
        Dictionary containing wave front position, rarefaction tail, and analytical invariants.
    """
    if h0 <= 0:
        raise ValueError(f"Initial reservoir depth h0 must be strictly positive, got {h0}")
    if g <= 0:
        raise ValueError(f"Gravitational acceleration g must be positive, got {g}")
    if t < 0:
        raise ValueError(f"Time t must be non-negative, got {t}")

    c0 = np.sqrt(g * h0)
    x_arr = np.asarray(x, dtype=float)

    if t == 0.0:
        h = np.where(x_arr <= x0, h0, 0.0)
        u = np.zeros_like(x_arr)
        meta = {
            "c0": float(c0),
            "x_tail": float(x0),
            "x_front": float(x0),
            "h_dam": float((4.0 / 9.0) * h0),
            "u_dam": float((2.0 / 3.0) * c0),
        }
        return h, u, meta

    x_tail = x0 - c0 * t
    x_front = x0 + 2.0 * c0 * t

    h = np.zeros_like(x_arr)
    u = np.zeros_like(x_arr)

    # 1. Undisturbed upstream reservoir
    m_up = x_arr <= x_tail
    h[m_up] = h0
    u[m_up] = 0.0

    # 2. Rarefaction fan
    m_rare = (x_arr > x_tail) & (x_arr < x_front)
    if np.any(m_rare):
        xi = (x_arr[m_rare] - x0) / t
        h[m_rare] = (1.0 / (9.0 * g)) * (2.0 * c0 - xi) ** 2
        u[m_rare] = (2.0 / 3.0) * (c0 + xi)

    # 3. Dry bed downstream
    m_dry = x_arr >= x_front
    h[m_dry] = 0.0
    u[m_dry] = 0.0

    meta = {
        "c0": float(c0),
        "x_tail": float(x_tail),
        "x_front": float(x_front),
        "h_dam": float((4.0 / 9.0) * h0),
        "u_dam": float((2.0 / 3.0) * c0),
    }
    return h, u, meta


def stoker_solution(
    x: np.ndarray,
    t: float,
    x0: float,
    hL: float,
    hR: float,
    g: float = 9.80665,
) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    """Exact Stoker (1957) analytical solution for 1D dam break over a flat, wet, frictionless bed.

    Parameters
    ----------
    x : np.ndarray
        Array of 1D spatial coordinates (m).
    t : float
        Elapsed time since dam removal (s). Must be >= 0.
    x0 : float
        Initial dam axis position (m).
    hL : float
        Initial upstream water depth (m). Must be > hR.
    hR : float
        Initial downstream water depth (m). Must be >= 0.
    g : float
        Gravitational acceleration (m/s2). Default is 9.80665.

    Returns
    -------
    h : np.ndarray
        Water depth profile (m).
    u : np.ndarray
        Flow velocity profile (m/s).
    meta : dict[str, float]
        Dictionary containing intermediate depth hm, shock speed S, and key transition points.
    """
    if hL <= hR:
        raise ValueError(
            f"Upstream depth hL ({hL}) must be strictly greater than downstream depth hR ({hR}) for dam break shock wave"
        )
    if hR < 0:
        raise ValueError(f"Downstream depth hR must be non-negative, got {hR}")
    if g <= 0:
        raise ValueError(f"Gravitational acceleration g must be positive, got {g}")
    if t < 0:
        raise ValueError(f"Time t must be non-negative, got {t}")

    # If dry bed, delegate to Ritter solution
    if hR == 0.0:
        return ritter_solution(x, t, x0, hL, g)

    x_arr = np.asarray(x, dtype=float)
    cL = np.sqrt(g * hL)

    # Solve for intermediate depth hm between hR and hL
    def f_hm(h: float) -> float:
        c_val = 2.0 * (cL - np.sqrt(g * h))
        shock_val = (h - hR) * np.sqrt((g * (h + hR)) / (2.0 * h * hR))
        return float(c_val - shock_val)

    hm = float(brentq(f_hm, hR, hL))
    cm = np.sqrt(g * hm)
    um = float(2.0 * (cL - cm))
    shock_speed = float(hm * um / (hm - hR))

    if t == 0.0:
        h = np.where(x_arr <= x0, hL, hR)
        u = np.zeros_like(x_arr)
        meta = {
            "hm": hm,
            "um": um,
            "shock_speed": shock_speed,
            "x_tail": float(x0),
            "x_rare_right": float(x0),
            "x_shock": float(x0),
        }
        return h, u, meta

    x_tail = x0 - cL * t
    x_rare_right = x0 + (um - cm) * t
    x_shock = x0 + shock_speed * t

    h = np.zeros_like(x_arr)
    u = np.zeros_like(x_arr)

    # 1. Undisturbed upstream reservoir
    m_up = x_arr <= x_tail
    h[m_up] = hL
    u[m_up] = 0.0

    # 2. Rarefaction fan
    m_rare = (x_arr > x_tail) & (x_arr <= x_rare_right)
    if np.any(m_rare):
        xi = (x_arr[m_rare] - x0) / t
        h[m_rare] = (1.0 / (9.0 * g)) * (2.0 * cL - xi) ** 2
        u[m_rare] = (2.0 / 3.0) * (cL + xi)

    # 3. Intermediate constant state (plateau)
    m_mid = (x_arr > x_rare_right) & (x_arr < x_shock)
    h[m_mid] = hm
    u[m_mid] = um

    # 4. Undisturbed downstream still water
    m_down = x_arr >= x_shock
    h[m_down] = hR
    u[m_down] = 0.0

    meta = {
        "hm": hm,
        "um": um,
        "shock_speed": shock_speed,
        "x_tail": float(x_tail),
        "x_rare_right": float(x_rare_right),
        "x_shock": float(x_shock),
    }
    return h, u, meta
