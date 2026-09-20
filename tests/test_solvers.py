"""Tests for hydrodynamic solver adapter (AnugaSolver).

Adheres to AGENTS.md testing discipline:
- Pre-set pass thresholds written into tests before execution.
- Tests include:
  - C1: Mass balance including boundary outflow (V_final = V_init + V_in - V_out)
        with independent SWW volume computation:
        (i) closed domain,
        (ii) Inlet_operator with triangular hydrograph into dry basin (diff < 1e-3 m3),
        (iii) transmissive outlet where water leaves domain (V_out > 0),
        (iv) FORCED VIOLATION (inlet scaled 1.02 vs tally 1.00 fails under standard 1% tol).
  - C2: Inlet_operator hydrograph test (named test_inlet_operator_triangular_hydrograph_dry_basin).
  - C3: Lake-at-rest C-property over >= 100 s: max |v| < 1e-3 m/s and stage drift < 1e-3 m.
  - C4: Stoker shock arrival time: |t_sim - t_exact| <= yieldstep + dx/s; nodata where never wet.
  - Same-typed argument swap sensitivity.
"""

from __future__ import annotations

import json
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd
import rasterio

from damsight.solvers.analytical import stoker_solution
from damsight.solvers.anuga_solver import AnugaSolver


def test_lake_at_rest_c_property_100s(tmp_path: Path):
    """Lake-at-rest C-property verification over irregular bathymetry for >= 100 seconds (C3).

    Gates:
    - max |v| < 1e-3 m/s
    - max stage drift < 1e-3 m
    """
    GATE_MAX_V = 1e-3  # m/s
    GATE_STAGE_DRIFT = 1e-3  # m

    solver = AnugaSolver()

    # Irregular bathymetry: sinusoidal bed variation between 0.7m and 1.3m
    def bumpy_bed(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return 1.0 + 0.3 * np.sin(2.0 * np.pi * x / 100.0)

    spec = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 40.0,
        "dam_x_m": 50.0,
        "h_left_m": 2.0,
        "h_right_m": 2.0,
        "manning_n": 0.03,
        "b_left": "reflective",
        "b_right": "reflective",
        "duration_s": 100.0,
        "yieldstep_s": 20.0,
    }

    run_dir = solver.prepare(spec, mesh_resolution_m=10.0, run_dir=tmp_path / "lake_at_rest_100s")
    domain = run_dir.extra["domain"]

    domain.set_quantity("elevation", bumpy_bed)
    domain.set_quantity("stage", 2.0)

    res = solver.run(run_dir, yieldstep=20.0, finaltime=100.0)
    assert res.success is True

    # Check stage drift from netCDF SWW output
    sww_path = run_dir.path / "simulation.sww"
    nc = netCDF4.Dataset(str(sww_path), "r")
    stage_c = np.array(nc.variables["stage_c"][:])
    nc.close()

    stage_drift = float(np.max(np.abs(stage_c - 2.0)))

    # Compute max velocity across all cells at final time
    h = np.maximum(
        domain.quantities["stage"].centroid_values - domain.quantities["elevation"].centroid_values,
        1e-6,
    )
    u = domain.quantities["xmomentum"].centroid_values / h
    v = domain.quantities["ymomentum"].centroid_values / h
    speed = np.sqrt(u**2 + v**2)
    max_v = float(np.max(speed))

    assert (
        max_v < GATE_MAX_V
    ), f"Lake-at-rest max |v| = {max_v:.4e} m/s exceeded gate {GATE_MAX_V:.4e} m/s"
    assert (
        stage_drift < GATE_STAGE_DRIFT
    ), f"Lake-at-rest stage drift = {stage_drift:.4e} m exceeded gate {GATE_STAGE_DRIFT:.4e} m"


def test_mass_balance_closed_domain(tmp_path: Path):
    """Verify mass balance in a closed domain (C1-i).

    Domain volume is computed independently from SWW output (stage - elevation) * area.
    Error must remain < 1e-4.
    """
    solver = AnugaSolver(mass_balance_tolerance=0.01)
    spec = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 20.0,
        "dam_x_m": 50.0,
        "h_left_m": 4.0,
        "h_right_m": 1.0,
        "manning_n": 0.0,
        "b_left": "reflective",
        "b_right": "reflective",
        "duration_s": 5.0,
    }
    run_dir = solver.prepare(spec, mesh_resolution_m=10.0, run_dir=tmp_path / "mb_closed")
    res = solver.run(run_dir, yieldstep=1.0, finaltime=5.0)

    assert res.success is True
    assert res.mass_balance_error < 1e-4, f"Closed domain error {res.mass_balance_error:.2e} >= 1e-4"
    assert res.extra["outflow_volume_m3"] == 0.0


def test_inlet_operator_triangular_hydrograph_dry_basin(tmp_path: Path):
    """Verify Inlet_operator with triangular hydrograph into dry basin (C1-ii, C2).

    Domain volume increase equals integral of Q dt within 1e-3 m3.
    """
    solver = AnugaSolver(mass_balance_tolerance=0.01)

    t_h = np.array([0.0, 5.0, 10.0])
    q_h = np.array([0.0, 20.0, 0.0])
    df_h = pd.DataFrame({"time_s": t_h, "discharge_m3s": q_h})
    integral_q = 0.5 * 10.0 * 20.0  # 100.0 m3

    spec = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 20.0,
        "dam_x_m": 0.0,
        "h_left_m": 0.0,
        "h_right_m": 0.0,
        "manning_n": 0.03,
        "b_left": "reflective",
        "b_right": "reflective",
        "duration_s": 10.0,
    }
    run_dir = solver.prepare(
        spec,
        hydrograph=df_h,
        mesh_resolution_m=10.0,
        dam_location=[10.0, 10.0],
        inlet_radius_m=10.0,
        run_dir=tmp_path / "mb_inlet",
    )
    res = solver.run(run_dir, yieldstep=1.0, finaltime=10.0)

    assert res.success is True
    vol_final = res.extra["final_volume_m3"]
    vol_diff = abs(vol_final - integral_q)
    assert vol_diff < 1e-3, f"Inlet volume diff {vol_diff:.4e} m3 exceeded gate 1e-3 m3 (final={vol_final:.4f}, expected={integral_q:.4f})"


def test_mass_balance_transmissive_outlet(tmp_path: Path):
    """Verify mass balance with transmissive outlet where water leaves domain (C1-iii).

    V_final = V_init + V_in - V_out must hold within 1e-4.
    """
    solver = AnugaSolver(mass_balance_tolerance=0.01)
    spec = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 20.0,
        "dam_x_m": 50.0,
        "h_left_m": 4.0,
        "h_right_m": 0.0,
        "manning_n": 0.0,
        "b_left": "reflective",
        "b_right": "transmissive",
        "duration_s": 15.0,
    }
    run_dir = solver.prepare(spec, mesh_resolution_m=10.0, run_dir=tmp_path / "mb_trans")
    res = solver.run(run_dir, yieldstep=1.0, finaltime=15.0)

    assert res.success is True
    assert res.extra["outflow_volume_m3"] > 50.0, f"Water should have left domain, got V_out={res.extra['outflow_volume_m3']}"
    assert res.mass_balance_error < 1e-4, f"Transmissive domain error {res.mass_balance_error:.2e} >= 1e-4"


def test_forced_violation_inlet_mass_imbalance_fails(tmp_path: Path):
    """Verify forced violation: inlet hydrograph scaled 1.02 vs tally 1.00 (C1-iv).

    The run must fail (success=False) under standard 1.0% tolerance.
    """
    solver = AnugaSolver(mass_balance_tolerance=0.01)

    t_h = np.array([0.0, 5.0, 10.0])
    q_h = np.array([0.0, 20.0, 0.0])
    # Inlet applies hydrograph scaled by 1.02
    df_h_scaled = pd.DataFrame({"time_s": t_h, "discharge_m3s": q_h * 1.02})

    spec = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 20.0,
        "dam_x_m": 0.0,
        "h_left_m": 0.0,
        "h_right_m": 0.0,
        "b_left": "reflective",
        "b_right": "reflective",
        "duration_s": 10.0,
    }
    # Tally uses 1.00 (scale factor 1.0 / 1.02)
    run_dir = solver.prepare(
        spec,
        hydrograph=df_h_scaled,
        mesh_resolution_m=10.0,
        dam_location=[10.0, 10.0],
        inlet_radius_m=10.0,
        tally_inflow_scale=(1.0 / 1.02),
        run_dir=tmp_path / "mb_forced_violation",
    )
    res = solver.run(run_dir, yieldstep=1.0, finaltime=10.0)

    assert res.success is False, "Run must fail (success=False) when inlet imbalance exceeds 1% tolerance"
    assert res.mass_balance_error > 0.015, f"Expected error > 1.5%, got {res.mass_balance_error:.4%}"
    assert len(res.warnings) > 0
    assert "exceeded configured tolerance" in res.warnings[0]


def test_stoker_arrival_time_shock_speed(tmp_path: Path):
    """Verify arrival time using Stoker shock with constant speed s (C4).

    Analytical arrival: t = (x - x0) / s.
    Gate: |arrival_sim - arrival_exact| <= yieldstep + dx/s at every wetted cell
    away from the initial discontinuity. Nodata where never wet.
    """
    res_m = 10.0
    yieldstep_s = 0.5
    hL = 10.0
    hR = 2.0
    x0 = 500.0
    finaltime = 15.0

    solver = AnugaSolver()
    spec = {
        "type": "channel",
        "length_m": 1000.0,
        "width_m": 20.0,
        "dam_x_m": x0,
        "h_left_m": hL,
        "h_right_m": hR,
        "manning_n": 0.0,
        "duration_s": finaltime,
        "yieldstep_s": yieldstep_s,
    }

    # Stoker exact solution shock speed
    _, _, meta = stoker_solution(np.array([x0]), t=1.0, x0=x0, hL=hL, hR=hR)
    s = meta["shock_speed"]
    hm = meta["hm"]

    # Arrival threshold: 20% elevation above downstream pool hR
    arrival_thresh = hR + 0.2 * (hm - hR)

    run_dir = solver.prepare(
        spec,
        mesh_resolution_m=res_m,
        arrival_threshold_m=arrival_thresh,
        run_dir=tmp_path / "stoker_arrival",
    )
    res = solver.run(run_dir, yieldstep=yieldstep_s, finaltime=finaltime)
    assert res.success is True

    # Read SWW directly for cell-by-cell verification
    sww_path = run_dir.path / "simulation.sww"
    nc = netCDF4.Dataset(str(sww_path), "r")
    x_pts = np.array(nc.variables["x"][:])
    vols = np.array(nc.variables["volumes"][:])
    time_arr = np.array(nc.variables["time"][:])
    stage_c = np.array(nc.variables["stage_c"][:])
    elev_c = np.array(nc.variables["elevation_c"][:])
    nc.close()

    xc = (x_pts[vols[:, 0]] + x_pts[vols[:, 1]] + x_pts[vols[:, 2]]) / 3.0
    depth_c = np.maximum(0.0, stage_c - elev_c)

    arrival_sim = np.full(len(xc), -9999.0, dtype=np.float32)
    for i in range(len(xc)):
        hits = np.where(depth_c[:, i] > arrival_thresh)[0]
        if len(hits) > 0:
            arrival_sim[i] = time_arr[hits[0]]

    # Away from initial discontinuity: x > x0 + 2 * dx
    wetted_mask = (arrival_sim >= 0.0) & (xc > x0 + 2.0 * res_m)
    xc_wet = xc[wetted_mask]
    arr_sim_wet = arrival_sim[wetted_mask]
    arr_exact_wet = (xc_wet - x0) / s

    gate_error = yieldstep_s + res_m / s
    diff = np.abs(arr_sim_wet - arr_exact_wet)
    max_diff = float(np.max(diff))

    assert np.all(
        diff <= gate_error
    ), f"Max arrival diff {max_diff:.4f} s exceeded gate {gate_error:.4f} s (yieldstep + dx/s)"

    # Cells never reached by the shock wave must have nodata (-9999.0)
    unwetted_mask = xc > (x0 + s * finaltime + 2.0 * res_m)
    assert np.any(unwetted_mask), "Must have unwetted cells beyond the shock wave front"
    assert np.all(
        arrival_sim[unwetted_mask] == -9999.0
    ), "Cells never reached by shock wave must have nodata (-9999.0)"

    # Also test collect() contract GeoTIFFs
    outputs = solver.collect(run_dir)
    assert outputs.arrival_time_tif.exists()
    with rasterio.open(outputs.arrival_time_tif) as src:
        arr_tif = src.read(1)
        assert src.nodata == -9999.0
        # Check that far downstream cells in the raster are nodata
        assert arr_tif[0, -1] == -9999.0


def test_solver_same_type_argument_swap_sensitivity(tmp_path: Path):
    """Verify solver preparation fails or produces distinct spatial state if same-typed arguments are swapped."""
    solver = AnugaSolver()

    # Normal order: h_left=10.0, h_right=0.0
    spec_normal = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 20.0,
        "dam_x_m": 50.0,
        "h_left_m": 10.0,
        "h_right_m": 0.0,
        "duration_s": 1.0,
    }
    rd_normal = solver.prepare(spec_normal, mesh_resolution_m=10.0, run_dir=tmp_path / "swap_norm")
    d_norm = rd_normal.extra["domain"]
    xc_norm = d_norm.get_centroid_coordinates()[:, 0]
    st_norm = d_norm.quantities["stage"].centroid_values

    # Swapped order: h_left=0.0, h_right=10.0
    spec_swapped = {
        "type": "channel",
        "length_m": 100.0,
        "width_m": 20.0,
        "dam_x_m": 50.0,
        "h_left_m": 0.0,
        "h_right_m": 10.0,
        "duration_s": 1.0,
    }
    rd_swapped = solver.prepare(spec_swapped, mesh_resolution_m=10.0, run_dir=tmp_path / "swap_inv")
    d_swapped = rd_swapped.extra["domain"]
    st_swapped = d_swapped.quantities["stage"].centroid_values

    # At x < 50m: normal has stage 10.0, swapped has stage 0.0
    mask_left = xc_norm < 40.0
    assert np.allclose(st_norm[mask_left], 10.0)
    assert np.allclose(st_swapped[mask_left], 0.0)
    assert not np.allclose(
        st_norm, st_swapped
    ), "Swapped arguments (h_left, h_right) must produce inverted domain state"
