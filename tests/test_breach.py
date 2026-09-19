"""Unit tests for Froehlich breach parameter equations and hydrograph generation."""

import json
from pathlib import Path
import numpy as np
import pytest

from damsight.breach.froehlich import (
    estimate_breach_parameters,
    froehlich_breach_width,
    froehlich_formation_time,
    froehlich_peak_outflow,
)
from damsight.breach.hydrograph import (
    StageStorageCurve,
    generate_breach_hydrograph,
)


def test_froehlich_worked_examples():
    """(a) Hand-computed worked examples for Froehlich formulas with step-by-step arithmetic.

    =============================================================================
    WORKED EXAMPLE INPUTS (Standard Embankment Failure):
      Reservoir Volume (V_w) = 1.0e7 m^3 (10,000,000 m^3 = 10 MCM)
      Breach Height (h_b)    = 20.0 m
      Water Depth (h_w)      = 20.0 m
      Gravity (g)            = 9.80665 m/s^2

    -----------------------------------------------------------------------------
    1. FROEHLICH (2008) AVERAGE BREACH WIDTH (B_avg):
       Formula: B_avg = 0.27 * K_o * (V_w ^ 0.32) * (h_b ^ 0.04)

       Step 1: Compute V_w ^ 0.32
         V_w ^ 0.32 = (10,000,000) ^ 0.32 = 173.7800828749377

       Step 2: Compute h_b ^ 0.04
         h_b ^ 0.04 = (20.0) ^ 0.04 = 1.1274615024471927

       Step 3a: Overtopping Mode (K_o = 1.3)
         B_avg = 0.27 * 1.3 * 173.7800828749377 * 1.1274615024471927
               = 0.351 * 173.7800828749377 * 1.1274615024471927
               = 68.76203 m

       Step 3b: Piping Mode (K_o = 1.0)
         B_avg = 0.27 * 1.0 * 173.7800828749377 * 1.1274615024471927
               = 0.270 * 173.7800828749377 * 1.1274615024471927
               = 52.89387 m

    -----------------------------------------------------------------------------
    2. FROEHLICH (2008) FORMATION TIME (t_f):
       Formula: t_f = 63.2 * sqrt(V_w / (g * h_b ^ 2))

       Step 1: Compute denominator (g * h_b ^ 2)
         g * h_b ^ 2 = 9.80665 * (20.0 ^ 2) = 9.80665 * 400.0 = 3922.66 m^3/s^2

       Step 2: Compute volume ratio
         V_w / (g * h_b ^ 2) = 10,000,000 / 3922.66 = 2549.2905324448206 s^2

       Step 3: Square root of ratio
         sqrt(2549.2905324448206) = 50.49049942756317 s

       Step 4: Multiply by Froehlich constant 63.2
         t_f = 63.2 * 50.49049942756317 = 3190.99956 seconds (~53.18 minutes)

    -----------------------------------------------------------------------------
    3. FROEHLICH (1995) PEAK DISCHARGE (Q_p):
       Formula: Q_p = 0.607 * (V_w ^ 0.295) * (h_w ^ 1.24)

       Step 1: Compute V_w ^ 0.295
         V_w ^ 0.295 = (10,000,000) ^ 0.295 = 116.14486136979678

       Step 2: Compute h_w ^ 1.24
         h_w ^ 1.24 = (20.0) ^ 1.24 = 41.04944810795498

       Step 3: Multiply by Froehlich coefficient 0.607
         Q_p = 0.607 * 116.14486136979678 * 41.04944810795498
             = 2893.7825 m^3/s
    =============================================================================
    """
    v_w = 1.0e7
    h_b = 20.0
    h_w = 20.0

    # 1. Test Breach Width
    b_overtopping = froehlich_breach_width(v_w, h_b, mode="overtopping")
    assert abs(b_overtopping - 68.7620) < 1e-3, f"Expected ~68.7620 m, got {b_overtopping}"

    b_piping = froehlich_breach_width(v_w, h_b, mode="piping")
    assert abs(b_piping - 52.8938) < 1e-3, f"Expected ~52.8938 m, got {b_piping}"

    # 2. Test Formation Time
    t_f = froehlich_formation_time(v_w, h_b)
    assert abs(t_f - 3191.00) < 1e-2, f"Expected ~3191.00 s, got {t_f}"

    # 3. Test Peak Outflow
    q_p = froehlich_peak_outflow(v_w, h_w)
    assert abs(q_p - 2893.78) < 1e-2, f"Expected ~2893.78 m^3/s, got {q_p}"


def test_outflow_volume_less_than_or_equal_to_stored_volume():
    """(b) Test that total integrated hydrograph outflow volume <= initial stored volume."""
    v_init = 8.5e6  # 8.5 MCM
    h_b = 25.0

    params = estimate_breach_parameters(
        reservoir_volume_m3=v_init,
        breach_height_m=h_b,
        water_depth_m=h_b,
        mode="overtopping",
    )

    stage_storage = StageStorageCurve(
        invert_elevation_m=50.0,
        crest_elevation_m=75.0,
        max_volume_m3=v_init,
    )

    res = generate_breach_hydrograph(
        params=params,
        stage_storage=stage_storage,
        dt_s=5.0,
    )

    # Mass conservation assertions
    assert res.mass_conserved is True
    assert res.total_outflow_volume_m3 <= v_init + 1e-3
    assert res.mass_balance_error_pct < 0.05
    assert res.total_outflow_volume_m3 > 0.90 * v_init  # Vast majority drained


def test_monotonic_reservoir_drawdown():
    """(c) Test that reservoir water level H(t) decreases monotonically over time."""
    v_init = 5.0e6
    h_b = 18.0

    params = estimate_breach_parameters(
        reservoir_volume_m3=v_init,
        breach_height_m=h_b,
        mode="piping",
    )

    res = generate_breach_hydrograph(params=params, dt_s=10.0)

    assert res.drawdown_monotonic is True

    # Confirm delta stage between consecutive steps is non-positive
    stage_diffs = np.diff(res.stage_m)
    assert np.all(stage_diffs <= 1e-7), f"Max stage increase detected: {np.max(stage_diffs)}"


def test_hydrograph_peak_vs_empirical_qp_side_by_side(capsys):
    """(d) Test and report peak from the hydrograph vs empirical Qp side by side."""
    v_init = 1.2e7  # 12 MCM
    h_b = 30.0

    params = estimate_breach_parameters(
        reservoir_volume_m3=v_init,
        breach_height_m=h_b,
        water_depth_m=h_b,
        mode="overtopping",
    )

    res = generate_breach_hydrograph(params=params, dt_s=5.0)

    q_peak_hydrograph = res.peak_discharge_hydrograph_m3s
    q_peak_empirical = res.empirical_peak_qp_m3s

    ratio = q_peak_hydrograph / q_peak_empirical

    # Both values must be positive and within physical hydraulic ratio (0.5 to 1.8)
    assert q_peak_hydrograph > 0.0
    assert q_peak_empirical > 0.0
    assert 0.5 <= ratio <= 1.8

    # Print side-by-side comparison for report visibility
    print(f"\n[BREACH PEAK DISCHARGE COMPARISON]")
    print(f"  Hydrograph Peak Flow (Q_peak):    {q_peak_hydrograph:10.2f} m^3/s")
    print(f"  Froehlich (1995) Empirical (Q_p): {q_peak_empirical:10.2f} m^3/s")
    print(f"  Ratio (Q_peak / Q_p):             {ratio:10.3f}")


def test_natural_dam_illustrative_handling():
    """Verify natural dam variant uses accelerated formation and is marked illustrative."""
    v_init = 4.0e6
    h_b = 15.0

    std_params = estimate_breach_parameters(v_init, h_b, is_natural_dam=False)
    nat_params = estimate_breach_parameters(v_init, h_b, is_natural_dam=True)

    assert nat_params.is_natural_dam is True
    assert nat_params.parameter_status == "illustrative"
    assert "illustrative" in nat_params.notes.lower()
    # Formation time in unconsolidated debris must be faster than engineered embankment
    assert nat_params.formation_time_s < std_params.formation_time_s
    # Breach width in unconsolidated debris is wider
    assert nat_params.breach_width_avg_m > std_params.breach_width_avg_m


def test_hydrograph_file_exports(tmp_path):
    """Test saving hydrograph to CSV and metadata to JSON."""
    v_init = 2.0e6
    h_b = 12.0

    params = estimate_breach_parameters(v_init, h_b)
    res = generate_breach_hydrograph(params=params, dt_s=10.0, total_duration_s=3600.0)

    csv_path = tmp_path / "hydrograph.csv"
    meta_path = tmp_path / "hydrograph_meta.json"

    res.save_csv(csv_path)
    res.save_metadata(meta_path)

    assert csv_path.exists()
    assert meta_path.exists()

    with open(meta_path, "r") as f:
        meta = json.load(f)

    assert "peak_hydrograph_m3s" in meta
    assert "empirical_froehlich_qp_m3s" in meta
    assert meta["mass_conserved"] is True
    assert meta["drawdown_monotonic"] is True
