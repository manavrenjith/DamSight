"""Numerical benchmark verification gates for hydrodynamic solver adapter (G1).

Runs Ritter (1892) dry bed and Stoker (1957) wet bed dam-break benchmarks
THROUGH AnugaSolver.prepare/run/collect at dx = 20, 10, 5 m.

Pre-set pass thresholds written in file:
a) front error <= 5.0% of front position at dx = 5 m at all 3 timestamps (t = 5, 10, 15 s).
b) L1 depth error (disturbed region) <= 5.0% at dx = 5 m at all 3 timestamps.
c) front error AND L1 depth error non-increasing 20 -> 10 -> 5 m at each timestamp.
d) REGRESSION GUARD (set after seeing benchmark results of 10.0m/6.67m for Ritter and 5.0m for Stoker):
   front error at dx = 5 m <= 3 cells (3 * dx = 15.0 m) at all timestamps.

Runs in default pytest (marked 'slow' but never skipped). No xfail.
"""

from __future__ import annotations

from pathlib import Path

import netCDF4
import numpy as np
import pytest

from damsight.solvers.analytical import ritter_solution, stoker_solution
from damsight.solvers.anuga_solver import AnugaSolver

# Pre-set Gate Thresholds
GATE_FRONT_PCT_POS = 5.0  # Front error <= 5.0% of front position at dx=5m
GATE_L1_PCT = 5.0  # L1 depth error <= 5.0% at dx=5m
REGRESSION_GUARD_MAX_CELLS = 3  # Regression guard: front error <= 3 * dx (15.0 m)


def _extract_centerline_profile(
    sww_path: Path, t_target: float, dx: float
) -> tuple[np.ndarray, np.ndarray]:
    """Extract 1D centerline cross-section (x, depth) from 2D SWW file at specified timestamp."""
    nc = netCDF4.Dataset(str(sww_path), "r")
    x_pts = np.array(nc.variables["x"][:])
    y_pts = np.array(nc.variables["y"][:])
    vols = np.array(nc.variables["volumes"][:])
    time_arr = np.array(nc.variables["time"][:])

    t_idx = int(np.argmin(np.abs(time_arr - t_target)))
    stage_c = np.array(nc.variables["stage_c"][t_idx])
    elev_c = np.array(nc.variables["elevation_c"][:])
    nc.close()

    xc = (x_pts[vols[:, 0]] + x_pts[vols[:, 1]] + x_pts[vols[:, 2]]) / 3.0
    yc = (y_pts[vols[:, 0]] + y_pts[vols[:, 1]] + y_pts[vols[:, 2]]) / 3.0
    depth_c = np.maximum(0.0, stage_c - elev_c)

    # Centerline filter
    y_mid = 10.0
    mask_mid = np.abs(yc - y_mid) <= (dx * 0.6)
    xc_mid = xc[mask_mid]
    depth_mid = depth_c[mask_mid]

    sort_idx = np.argsort(xc_mid)
    return xc_mid[sort_idx], depth_mid[sort_idx]


@pytest.mark.slow
def test_ritter_benchmark_gates_and_convergence(tmp_path: Path):
    """Run Ritter benchmark through AnugaSolver at dx = 20, 10, 5 m and verify G1 gates.

    REGRESSION GUARD (set after seeing benchmark results):
    Front error at dx = 5 m must be <= 3 cells (15.0 m) at all 3 times (actual: 10m, 10m, 6.67m).
    """
    solver = AnugaSolver()
    resolutions = [20.0, 10.0, 5.0]
    timestamps = [5.0, 10.0, 15.0]
    h0 = 10.0
    x0 = 500.0
    g = 9.80665
    c0 = np.sqrt(g * h0)

    results_by_res: dict[float, dict[float, dict[str, float]]] = {}

    for dx in resolutions:
        spec = {
            "type": "channel",
            "length_m": 1000.0,
            "width_m": 20.0,
            "dam_x_m": x0,
            "h_left_m": h0,
            "h_right_m": 0.0,
            "manning_n": 0.0,
            "b_left": "transmissive",
            "b_right": "transmissive",
            "boundary_type": "transmissive",
            "duration_s": 16.0,
            "yieldstep_s": 1.0,
        }
        run_dir = solver.prepare(
            spec,
            mesh_resolution_m=dx,
            boundary_type="transmissive",
            run_dir=tmp_path / f"ritter_{int(dx)}m",
        )
        res = solver.run(run_dir, yieldstep=1.0, finaltime=16.0)
        assert res.success is True
        outputs = solver.collect(run_dir)
        assert outputs.run_meta_json.exists()

        sww_path = run_dir.path / "simulation.sww"
        res_t: dict[float, dict[str, float]] = {}

        for t in timestamps:
            xc_sim, h_sim = _extract_centerline_profile(sww_path, t, dx)
            h_exact, _, meta = ritter_solution(xc_sim, t=t, x0=x0, h0=h0, g=g)

            # Front threshold: depth > 0.01 * h0
            thresh = 0.01 * h0
            sim_wet = xc_sim[h_sim > thresh]
            exact_wet = xc_sim[h_exact > thresh]
            x_sim_front = float(np.max(sim_wet)) if len(sim_wet) > 0 else x0
            x_exact_front = float(np.max(exact_wet)) if len(exact_wet) > 0 else x0

            err_front_m = abs(x_sim_front - x_exact_front)
            err_front_pct_pos = (err_front_m / x_exact_front) * 100.0
            dist_travelled = abs(x_exact_front - x0)
            err_front_pct_dist = (err_front_m / dist_travelled) * 100.0 if dist_travelled > 0 else 0.0

            # L1 Symmetric: |x - x0| <= c0 * t
            mask_sym = np.abs(xc_sim - x0) <= (c0 * t)
            l1_sym_pct = (np.mean(np.abs(h_sim[mask_sym] - h_exact[mask_sym])) / h0) * 100.0

            # L1 True disturbed: [x0 - c0*t, x0 + 2*c0*t]
            mask_true = (xc_sim >= (x0 - c0 * t)) & (xc_sim <= (x0 + 2.0 * c0 * t))
            l1_true_pct = (np.mean(np.abs(h_sim[mask_true] - h_exact[mask_true])) / h0) * 100.0

            res_t[t] = {
                "front_error_m": err_front_m,
                "front_error_pct_pos": err_front_pct_pos,
                "front_error_pct_dist": err_front_pct_dist,
                "l1_sym_pct": float(l1_sym_pct),
                "l1_true_pct": float(l1_true_pct),
            }

        results_by_res[dx] = res_t

    # Assertion a: front error <= 5% of front position at dx = 5m, all 3 times
    for t in timestamps:
        pct_pos = results_by_res[5.0][t]["front_error_pct_pos"]
        assert (
            pct_pos <= GATE_FRONT_PCT_POS
        ), f"Ritter dx=5m t={t}s: Front error {pct_pos:.2f}% exceeded gate {GATE_FRONT_PCT_POS}%"

    # Assertion b: L1 depth error (disturbed region) <= 5% at dx = 5m, all 3 times
    for t in timestamps:
        l1_sym = results_by_res[5.0][t]["l1_sym_pct"]
        l1_true = results_by_res[5.0][t]["l1_true_pct"]
        assert (
            l1_sym <= GATE_L1_PCT
        ), f"Ritter dx=5m t={t}s: L1 sym {l1_sym:.2f}% exceeded gate {GATE_L1_PCT}%"
        assert (
            l1_true <= GATE_L1_PCT
        ), f"Ritter dx=5m t={t}s: L1 true disturbed {l1_true:.2f}% exceeded gate {GATE_L1_PCT}%"

    # Assertion c: front error AND L1 non-increasing 20 -> 10 -> 5 m at each timestamp
    for t in timestamps:
        e_f_20 = results_by_res[20.0][t]["front_error_m"]
        e_f_10 = results_by_res[10.0][t]["front_error_m"]
        e_f_5 = results_by_res[5.0][t]["front_error_m"]
        assert (
            e_f_10 <= e_f_20 + 1e-6 and e_f_5 <= e_f_10 + 1e-6
        ), f"Ritter t={t}s: Front error not non-increasing 20->10->5m: {e_f_20} -> {e_f_10} -> {e_f_5}"

        e_l1_20 = results_by_res[20.0][t]["l1_true_pct"]
        e_l1_10 = results_by_res[10.0][t]["l1_true_pct"]
        e_l1_5 = results_by_res[5.0][t]["l1_true_pct"]
        assert (
            e_l1_10 <= e_l1_20 + 1e-6 and e_l1_5 <= e_l1_10 + 1e-6
        ), f"Ritter t={t}s: L1 true not non-increasing 20->10->5m: {e_l1_20:.2f}% -> {e_l1_10:.2f}% -> {e_l1_5:.2f}%"

    # Assertion d: REGRESSION GUARD: front error at dx = 5m <= 3 cells (15.0 m) at all times
    guard_threshold_m = REGRESSION_GUARD_MAX_CELLS * 5.0
    for t in timestamps:
        err_m = results_by_res[5.0][t]["front_error_m"]
        assert (
            err_m <= guard_threshold_m
        ), f"Ritter dx=5m t={t}s: Front error {err_m:.2f}m exceeded regression guard {guard_threshold_m:.1f}m"


@pytest.mark.slow
def test_stoker_benchmark_gates_and_convergence(tmp_path: Path):
    """Run Stoker benchmark through AnugaSolver at dx = 20, 10, 5 m and verify G1 gates.

    REGRESSION GUARD (set after seeing benchmark results):
    Front error at dx = 5 m must be <= 3 cells (15.0 m) at all 3 times (actual: 5.0 m at all times).
    """
    solver = AnugaSolver()
    resolutions = [20.0, 10.0, 5.0]
    timestamps = [5.0, 10.0, 15.0]
    h0 = 10.0
    hR = 2.0
    x0 = 500.0
    g = 9.80665
    c0 = np.sqrt(g * h0)

    results_by_res: dict[float, dict[float, dict[str, float]]] = {}

    for dx in resolutions:
        spec = {
            "type": "channel",
            "length_m": 1000.0,
            "width_m": 20.0,
            "dam_x_m": x0,
            "h_left_m": h0,
            "h_right_m": hR,
            "manning_n": 0.0,
            "b_left": "transmissive",
            "b_right": "transmissive",
            "boundary_type": "transmissive",
            "duration_s": 16.0,
            "yieldstep_s": 1.0,
        }
        run_dir = solver.prepare(
            spec,
            mesh_resolution_m=dx,
            boundary_type="transmissive",
            run_dir=tmp_path / f"stoker_{int(dx)}m",
        )
        res = solver.run(run_dir, yieldstep=1.0, finaltime=16.0)
        assert res.success is True
        outputs = solver.collect(run_dir)
        assert outputs.run_meta_json.exists()

        sww_path = run_dir.path / "simulation.sww"
        res_t: dict[float, dict[str, float]] = {}

        for t in timestamps:
            xc_sim, h_sim = _extract_centerline_profile(sww_path, t, dx)
            h_exact, _, meta = stoker_solution(xc_sim, t=t, x0=x0, hL=h0, hR=hR, g=g)

            # Front threshold: hR + 0.01 * (hm - hR)
            thresh = hR + 0.01 * (meta["hm"] - hR)
            sim_wet = xc_sim[h_sim > thresh]
            exact_wet = xc_sim[h_exact > thresh]
            x_sim_front = float(np.max(sim_wet)) if len(sim_wet) > 0 else x0
            x_exact_front = float(np.max(exact_wet)) if len(exact_wet) > 0 else x0

            err_front_m = abs(x_sim_front - x_exact_front)
            err_front_pct_pos = (err_front_m / x_exact_front) * 100.0
            dist_travelled = abs(x_exact_front - x0)
            err_front_pct_dist = (err_front_m / dist_travelled) * 100.0 if dist_travelled > 0 else 0.0

            # L1 Disturbed: |x - x0| <= c0 * t
            mask_dist = np.abs(xc_sim - x0) <= (c0 * t)
            l1_pct = (np.mean(np.abs(h_sim[mask_dist] - h_exact[mask_dist])) / h0) * 100.0

            res_t[t] = {
                "front_error_m": err_front_m,
                "front_error_pct_pos": err_front_pct_pos,
                "front_error_pct_dist": err_front_pct_dist,
                "l1_pct": float(l1_pct),
            }

        results_by_res[dx] = res_t

    # Assertion a: front error <= 5% of front position at dx = 5m, all 3 times
    for t in timestamps:
        pct_pos = results_by_res[5.0][t]["front_error_pct_pos"]
        assert (
            pct_pos <= GATE_FRONT_PCT_POS
        ), f"Stoker dx=5m t={t}s: Shock error {pct_pos:.2f}% exceeded gate {GATE_FRONT_PCT_POS}%"

    # Assertion b: L1 depth error (disturbed region) <= 5% at dx = 5m, all 3 times
    for t in timestamps:
        l1_val = results_by_res[5.0][t]["l1_pct"]
        assert (
            l1_val <= GATE_L1_PCT
        ), f"Stoker dx=5m t={t}s: L1 {l1_val:.2f}% exceeded gate {GATE_L1_PCT}%"

    # Assertion c: front error AND L1 non-increasing 20 -> 10 -> 5 m at each timestamp
    for t in timestamps:
        e_f_20 = results_by_res[20.0][t]["front_error_m"]
        e_f_10 = results_by_res[10.0][t]["front_error_m"]
        e_f_5 = results_by_res[5.0][t]["front_error_m"]
        assert (
            e_f_10 <= e_f_20 + 1e-6 and e_f_5 <= e_f_10 + 1e-6
        ), f"Stoker t={t}s: Shock error not non-increasing 20->10->5m: {e_f_20} -> {e_f_10} -> {e_f_5}"

        e_l1_20 = results_by_res[20.0][t]["l1_pct"]
        e_l1_10 = results_by_res[10.0][t]["l1_pct"]
        e_l1_5 = results_by_res[5.0][t]["l1_pct"]
        assert (
            e_l1_10 <= e_l1_20 + 1e-6 and e_l1_5 <= e_l1_10 + 1e-6
        ), f"Stoker t={t}s: L1 not non-increasing 20->10->5m: {e_l1_20:.2f}% -> {e_l1_10:.2f}% -> {e_l1_5:.2f}%"

    # Assertion d: REGRESSION GUARD: front error at dx = 5m <= 3 cells (15.0 m) at all times
    guard_threshold_m = REGRESSION_GUARD_MAX_CELLS * 5.0
    for t in timestamps:
        err_m = results_by_res[5.0][t]["front_error_m"]
        assert (
            err_m <= guard_threshold_m
        ), f"Stoker dx=5m t={t}s: Shock error {err_m:.2f}m exceeded regression guard {guard_threshold_m:.1f}m"
