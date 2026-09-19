"""Unit tests for analytical dam-break benchmarks (Ritter and Stoker).

Adheres to AGENTS.md testing discipline:
- Argument swap sensitivity tests included for same-typed arguments.
- Pre-set assertions and exact physical formulas tested.
- Offline purity with fast analytical verification.
"""

import numpy as np
import pytest

from damsight.solvers.analytical import ritter_solution, stoker_solution


def test_ritter_exact_analytical_properties():
    """Verify exact theoretical properties of Ritter (1892) solution."""
    x0 = 500.0
    h0 = 10.0
    t = 10.0
    g = 9.80665

    x_grid = np.linspace(300.0, 800.0, 501)
    h, u, meta = ritter_solution(x_grid, t=t, x0=x0, h0=h0, g=g)

    c0 = np.sqrt(g * h0)
    expected_x_tail = x0 - c0 * t
    expected_x_front = x0 + 2.0 * c0 * t
    expected_h_dam = (4.0 / 9.0) * h0
    expected_u_dam = (2.0 / 3.0) * c0

    assert np.isclose(meta["x_tail"], expected_x_tail, atol=1e-5)
    assert np.isclose(meta["x_front"], expected_x_front, atol=1e-5)
    assert np.isclose(meta["h_dam"], expected_h_dam, atol=1e-5)
    assert np.isclose(meta["u_dam"], expected_u_dam, atol=1e-5)

    # 1. Undisturbed upstream reservoir (x <= x_tail)
    assert np.all(h[x_grid <= expected_x_tail] == h0)
    assert np.all(u[x_grid <= expected_x_tail] == 0.0)

    # 2. Downstream dry bed (x >= x_front)
    assert np.all(h[x_grid >= expected_x_front] == 0.0)
    assert np.all(u[x_grid >= expected_x_front] == 0.0)

    # 3. Exact depth and velocity at the dam axis (x = x0)
    idx_dam = np.argmin(np.abs(x_grid - x0))
    assert np.isclose(h[idx_dam], expected_h_dam, atol=0.05)
    assert np.isclose(u[idx_dam], expected_u_dam, atol=0.05)

    # 4. Monotonicity inside the rarefaction wave
    rare_mask = (x_grid > expected_x_tail + 1.0) & (x_grid < expected_x_front - 1.0)
    rare_h = h[rare_mask]
    rare_u = u[rare_mask]
    assert np.all(np.diff(rare_h) < 0.0), "Rarefaction depth must strictly decrease with x"
    assert np.all(np.diff(rare_u) > 0.0), "Rarefaction velocity must strictly increase with x"


def test_ritter_argument_swap_sensitivity():
    """Test argument swap sensitivity for same-typed arguments x0 and h0."""
    t = 5.0
    g = 9.80665
    x = np.array([500.0])

    # Normal order: x0=500.0, h0=10.0
    h_correct, _, _ = ritter_solution(x, t=t, x0=500.0, h0=10.0, g=g)

    # Swapped arguments: x0=10.0, h0=500.0
    h_swapped, _, _ = ritter_solution(x, t=t, x0=10.0, h0=500.0, g=g)

    # At x=500, with x0=500 and h0=10, depth is at the dam axis: (4/9)*10 ≈ 4.44 m
    # With swapped x0=10, h0=500, x=500 is far downstream; front is 10 + 2*sqrt(g*500)*5 ≈ 710 m
    # Depths must be substantially different, proving test is sensitive to argument order
    assert abs(h_correct[0] - h_swapped[0]) > 2.0, "Test must detect swapped arguments (x0, h0)"


def test_stoker_exact_analytical_properties():
    """Verify exact theoretical properties of Stoker (1957) wet-bed solution."""
    x0 = 500.0
    hL = 10.0
    hR = 2.0
    t = 10.0
    g = 9.80665

    x_grid = np.linspace(300.0, 700.0, 801)
    h, u, meta = stoker_solution(x_grid, t=t, x0=x0, hL=hL, hR=hR, g=g)

    hm = meta["hm"]
    um = meta["um"]
    shock_speed = meta["shock_speed"]
    x_tail = meta["x_tail"]
    x_rare_right = meta["x_rare_right"]
    x_shock = meta["x_shock"]

    # Invariants check
    assert hR < hm < hL, f"Intermediate depth hm ({hm}) must lie between hR ({hR}) and hL ({hL})"
    assert um > 0.0, f"Intermediate velocity um ({um}) must be positive"
    assert shock_speed > um, "Shock speed must be greater than intermediate fluid velocity"
    assert x_tail < x_rare_right < x_shock
    assert x_tail < x0 < x_shock

    # Verify Rankine-Hugoniot shock relation
    shock_speed_rh = um + np.sqrt(g * hR * (hm + hR) / (2.0 * hm))
    assert np.isclose(shock_speed, shock_speed_rh, atol=1e-5)

    # 1. Undisturbed upstream reservoir (x <= x_tail)
    assert np.all(h[x_grid <= x_tail] == hL)
    assert np.all(u[x_grid <= x_tail] == 0.0)

    # 2. Intermediate constant plateau (x_rare_right < x < x_shock)
    plateau_mask = (x_grid > x_rare_right + 1.0) & (x_grid < x_shock - 1.0)
    assert np.allclose(h[plateau_mask], hm, atol=1e-4)
    assert np.allclose(u[plateau_mask], um, atol=1e-4)

    # 3. Undisturbed downstream still water (x >= x_shock)
    assert np.all(h[x_grid >= x_shock + 1.0] == hR)
    assert np.all(u[x_grid >= x_shock + 1.0] == 0.0)


def test_stoker_argument_swap_sensitivity():
    """Test argument swap sensitivity for same-typed arguments hL and hR."""
    x = np.linspace(0.0, 100.0, 10)
    t = 2.0
    x0 = 50.0

    # Normal order: hL > hR
    _ = stoker_solution(x, t=t, x0=x0, hL=10.0, hR=2.0)

    # Swapped order: hL < hR must raise ValueError
    with pytest.raises(ValueError, match="strictly greater than downstream depth"):
        stoker_solution(x, t=t, x0=x0, hL=2.0, hR=10.0)


def test_stoker_dry_bed_delegates_to_ritter():
    """Test that Stoker solution smoothly reduces to Ritter when hR=0."""
    x = np.linspace(300.0, 800.0, 100)
    t = 5.0
    x0 = 500.0
    hL = 8.0

    h_stoker, u_stoker, _ = stoker_solution(x, t=t, x0=x0, hL=hL, hR=0.0)
    h_ritter, u_ritter, _ = ritter_solution(x, t=t, x0=x0, h0=hL)

    assert np.allclose(h_stoker, h_ritter, atol=1e-8)
    assert np.allclose(u_stoker, u_ritter, atol=1e-8)
