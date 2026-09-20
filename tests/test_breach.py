"""Comprehensive unit tests for Froehlich breach parameter equations and hydrograph generation."""

import json

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
    """(a) Hand-computed worked examples for Froehlich formulas with step-by-step independent arithmetic.

    =============================================================================
    WORKED EXAMPLE 1 (Equal Height and Depth: hb = hw = 20.0 m):
      Reservoir Volume (V_w) = 1.0e7 m^3 (10,000,000 m^3 = 10 MCM)
      Breach Height (h_b)    = 20.0 m
      Water Depth (h_w)      = 20.0 m
      Gravity (g)            = 9.80665 m/s^2

    -----------------------------------------------------------------------------
    1. FROEHLICH (2008) AVERAGE BREACH WIDTH (B_avg):
       Formula: B_avg = 0.27 * K_o * (V_w ^ 0.32) * (h_b ^ 0.04)

       Step 1: Compute V_w ^ 0.32
         V_w ^ 0.32 = (10,000,000) ^ 0.32 = 173.7800828749377

       Step 2: Compute h_b ^ 0.04  (20 ^ 0.04 = 1.127304, rounded to 1.12730)
         h_b ^ 0.04 = (20.0) ^ 0.04 = 1.127304394081711

       Step 3a: Overtopping Mode (K_o = 1.3)
         B_avg = 0.27 * 1.3 * 173.7800828749377 * 1.127304394081711
               = 0.351 * 173.7800828749377 * 1.127304394081711
               = 68.76203 m

       Step 3b: Piping Mode (K_o = 1.0)
         B_avg = 0.27 * 1.0 * 173.7800828749377 * 1.127304394081711
               = 0.270 * 173.7800828749377 * 1.127304394081711
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

    b_overtopping = froehlich_breach_width(v_w, h_b, mode="overtopping")
    assert abs(b_overtopping - 68.7620) < 1e-3

    b_piping = froehlich_breach_width(v_w, h_b, mode="piping")
    assert abs(b_piping - 52.8938) < 1e-3

    t_f = froehlich_formation_time(v_w, h_b)
    assert abs(t_f - 3191.00) < 1e-2

    q_p = froehlich_peak_outflow(v_w, h_w)
    assert abs(q_p - 2893.78) < 1e-2


def test_froehlich_worked_example_unequal_hb_hw():
    """(a) Hand-computed worked example with hb != hw (e.g. Vw=2.5e7 m^3, hb=30.0 m, hw=27.5 m).

    =============================================================================
    WORKED EXAMPLE 2 (Independent Calculator Verification with hb != hw):
      Reservoir Volume (V_w) = 2.5e7 m^3 (25,000,000 m^3 = 25 MCM)
      Breach Height (h_b)    = 30.0 m
      Water Depth (h_w)      = 27.5 m  (Reservoir partially drawn down below crest)
      Gravity (g)            = 9.80665 m/s^2

    Step 1: Breach Width (Overtopping, K_o = 1.3)
      V_w ^ 0.32 = 25,000,000 ^ 0.32 = 232.99188916435534
      h_b ^ 0.04 = 30.0 ^ 0.04       = 1.1457367676485573
      B_avg = 0.27 * 1.3 * 232.991889 * 1.145737 = 93.6985 m

    Step 2: Breach Width (Piping, K_o = 1.0)
      B_avg = 0.27 * 1.0 * 232.991889 * 1.145737 = 72.0758 m

    Step 3: Formation Time (t_f)
      g * h_b ^ 2 = 9.80665 * 900.0 = 8825.985 m^3/s^2
      Ratio = 25,000,000 / 8825.985 = 2832.545 s^2
      sqrt(Ratio) = 53.22166 s
      t_f = 63.2 * 53.22166 = 3363.6089 s (~56.06 min)

    Step 4: Peak Outflow Q_p (depends on hw = 27.5 m, NOT hb = 30.0 m)
      V_w ^ 0.295 = 25,000,000 ^ 0.295 = 152.1921676102556
      h_w ^ 1.24  = 27.5 ^ 1.24        = 60.92177388018944
      Q_p = 0.607 * 152.192168 * 60.921774 = 5627.9928 m^3/s

    Step 5: Argument Swap Sensitivity Audit (AGENTS.md Rule 1)
      If hb and hw were mistakenly swapped, Q_p would use h_b=30.0 m:
      h_b ^ 1.24 = 30.0 ^ 1.24 = 67.862578
      Q_p_swapped = 0.607 * 152.192168 * 67.862578 = 6269.1888 m^3/s
      Delta = |6269.19 - 5627.99| = 641.20 m^3/s (~11.4% error)
    =============================================================================
    """
    v_w = 2.5e7
    h_b = 30.0
    h_w = 27.5

    # 1. Breach Width
    b_ov = froehlich_breach_width(v_w, h_b, mode="overtopping")
    assert abs(b_ov - 93.6985) < 1e-3, f"Expected 93.6985 m, got {b_ov}"

    b_pip = froehlich_breach_width(v_w, h_b, mode="piping")
    assert abs(b_pip - 72.0758) < 1e-3, f"Expected 72.0758 m, got {b_pip}"

    # 2. Formation Time
    t_f = froehlich_formation_time(v_w, h_b)
    assert abs(t_f - 3363.61) < 1e-2, f"Expected 3363.61 s, got {t_f}"

    # 3. Peak Outflow with hw
    q_p = froehlich_peak_outflow(v_w, h_w)
    assert abs(q_p - 5627.99) < 1e-2, f"Expected 5627.99 m^3/s, got {q_p}"

    # 4. Swap sensitivity test: verify that passing swapped argument produces different result
    q_p_swapped = froehlich_peak_outflow(v_w, h_b)
    assert abs(q_p_swapped - 6269.19) < 1e-2
    assert abs(q_p - q_p_swapped) > 600.0


def test_mass_conservation_and_clamp_binding():
    """(b)(i) Mass conservation: total outflow <= stored, clamp never binds before recession tail."""
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
        dead_storage_m3=0.0,
    )

    res = generate_breach_hydrograph(
        params=params,
        crest_elevation_m=75.0,
        cd_rect=1.70,
        cd_tri=1.35,
        stage_storage=stage_storage,
        dt_s=5.0,
    )

    # Outflow volume <= stored volume
    assert res.mass_conserved is True
    assert res.total_outflow_volume_m3 <= v_init + 1e-3
    assert res.mass_balance_error_pct < 0.05
    assert res.total_outflow_volume_m3 > 0.90 * v_init

    # (i) Assert that the min() clamp NEVER bound before the recession tail
    assert (
        res.clamp_active_before_recession == 0
    ), f"Clamp bound {res.clamp_active_before_recession} times before the recession tail!"


def test_dead_storage_never_drained():
    """(b)(ii) Test with dead storage below breach invert showing drawdown never removes it."""
    v_active = 6.0e6  # 6.0 MCM above breach invert
    v_dead = 2.0e6  # 2.0 MCM dead storage below invert
    v_total = v_active + v_dead
    h_b = 20.0
    invert_z = 50.0
    crest_z = 70.0
    bed_z = 35.0  # reservoir bottom 15m below breach invert

    params = estimate_breach_parameters(
        reservoir_volume_m3=v_active,
        breach_height_m=h_b,
        water_depth_m=h_b,
        mode="overtopping",
    )

    stage_storage = StageStorageCurve(
        invert_elevation_m=invert_z,
        crest_elevation_m=crest_z,
        max_volume_m3=v_total,
        dead_storage_m3=v_dead,
        bed_elevation_m=bed_z,
    )

    res = generate_breach_hydrograph(
        params=params,
        crest_elevation_m=crest_z,
        cd_rect=1.70,
        cd_tri=1.35,
        stage_storage=stage_storage,
        dt_s=5.0,
    )

    # 1. Total outflow must not exceed active storage
    assert res.total_outflow_volume_m3 <= v_active + 1e-3

    # 2. Dead storage must remain completely untouched in the reservoir
    assert res.remaining_reservoir_volume_m3 >= v_dead - 1e-3
    assert abs(res.remaining_reservoir_volume_m3 - v_dead) < 10.0  # within 10 m^3

    # 3. Water stage never draws down below breach invert elevation
    final_stage = res.stage_m[-1]
    assert final_stage >= invert_z - 1e-3


def test_dt_convergence():
    """(b)(iii) Test dt convergence: peak and total volume change < 2% between dt and dt/2."""
    v_init = 1.0e7
    h_b = 22.0

    params = estimate_breach_parameters(
        reservoir_volume_m3=v_init,
        breach_height_m=h_b,
        water_depth_m=h_b,
        mode="overtopping",
    )

    # Run with dt = 10.0 s
    res_dt1 = generate_breach_hydrograph(
        params=params,
        crest_elevation_m=100.0,
        cd_rect=1.70,
        cd_tri=1.35,
        dt_s=10.0,
    )

    # Run with dt/2 = 5.0 s
    res_dt2 = generate_breach_hydrograph(
        params=params,
        crest_elevation_m=100.0,
        cd_rect=1.70,
        cd_tri=1.35,
        dt_s=5.0,
    )

    # Relative difference in peak discharge
    peak_diff_pct = (
        abs(res_dt1.peak_discharge_hydrograph_m3s - res_dt2.peak_discharge_hydrograph_m3s)
        / res_dt2.peak_discharge_hydrograph_m3s
        * 100.0
    )

    # Relative difference in total volume
    vol_diff_pct = (
        abs(res_dt1.total_outflow_volume_m3 - res_dt2.total_outflow_volume_m3)
        / res_dt2.total_outflow_volume_m3
        * 100.0
    )

    assert peak_diff_pct < 2.0, f"Peak discharge dt convergence error {peak_diff_pct:.3f}% >= 2.0%"
    assert vol_diff_pct < 2.0, f"Total volume dt convergence error {vol_diff_pct:.3f}% >= 2.0%"


def test_monotonic_reservoir_drawdown():
    """(c) Test that reservoir water level H(t) decreases monotonically over time."""
    v_init = 5.0e6
    h_b = 18.0

    params = estimate_breach_parameters(
        reservoir_volume_m3=v_init,
        breach_height_m=h_b,
        mode="piping",
    )

    res = generate_breach_hydrograph(
        params=params,
        crest_elevation_m=100.0,
        cd_rect=1.70,
        cd_tri=1.35,
        dt_s=10.0,
    )

    assert res.drawdown_monotonic is True
    stage_diffs = np.diff(res.stage_m)
    assert np.all(stage_diffs <= 1e-7), f"Max stage increase detected: {np.max(stage_diffs)}"


def test_hydrograph_peak_vs_empirical_qp_side_by_side(capsys):
    """(d) Assert 0.5 <= Q_peak/Qp <= 2.0 and print the inputs used side by side."""
    v_init = 1.2e7  # 12 MCM
    h_b = 30.0
    h_w = 30.0
    mode = "overtopping"
    dam_type = "embankment"
    dt_s = 5.0
    cd_rect = 1.70
    cd_tri = 1.35

    params = estimate_breach_parameters(
        reservoir_volume_m3=v_init,
        breach_height_m=h_b,
        water_depth_m=h_w,
        mode=mode,
        dam_type=dam_type,
    )

    res = generate_breach_hydrograph(
        params=params,
        crest_elevation_m=100.0,
        cd_rect=cd_rect,
        cd_tri=cd_tri,
        dt_s=dt_s,
    )

    q_peak_hydrograph = res.peak_discharge_hydrograph_m3s
    q_peak_empirical = res.empirical_peak_qp_m3s
    ratio = q_peak_hydrograph / q_peak_empirical

    # Print inputs and results side by side
    print("\n=======================================================")
    print("BREACH PEAK DISCHARGE COMPARISON & INPUT AUDIT (TEST D)")
    print("=======================================================")
    print("Inputs Used:")
    print(f"  Reservoir Active Volume (V_w):   {v_init:.1e} m³ ({v_init/1e6:.1f} MCM)")
    print(f"  Breach Height (h_b):             {h_b:.1f} m")
    print(f"  Water Depth (h_w):               {h_w:.1f} m")
    print(f"  Breach Mode:                     {mode}")
    print(f"  Dam Type:                        {dam_type}")
    print(f"  Time Step (dt):                  {dt_s:.1f} s")
    print(f"  Weir Coefficients:               Cd_rect={cd_rect}, Cd_tri={cd_tri}")
    print("-------------------------------------------------------")
    print("Discharge Comparison:")
    print(f"  Hydrograph Peak Outflow (Q_peak): {q_peak_hydrograph:10.2f} m³/s")
    print(f"  Froehlich (1995) Empirical (Q_p): {q_peak_empirical:10.2f} m³/s")
    print(f"  Ratio (Q_peak / Q_p):             {ratio:10.3f}")
    print("=======================================================\n")

    # Assert bounded ratio per specification
    assert 0.5 <= ratio <= 2.0, f"Ratio {ratio:.3f} outside [0.5, 2.0]"


def test_natural_dam_illustrative_handling():
    """Verify natural dam variant uses factors 0.40 and 1.25 and carries parameter_status=illustrative."""
    v_init = 4.0e6
    h_b = 15.0

    std_params = estimate_breach_parameters(v_init, h_b, is_natural_dam=False)
    nat_params = estimate_breach_parameters(v_init, h_b, is_natural_dam=True)

    assert nat_params.is_natural_dam is True
    assert nat_params.parameter_status == "illustrative"
    assert "invented placeholder, no source" in nat_params.notes.lower()

    # Exact factor checks
    assert abs(nat_params.formation_time_s - 0.40 * std_params.formation_time_s) < 0.05
    assert abs(nat_params.breach_width_avg_m - 1.25 * std_params.breach_width_avg_m) < 0.05

    # Check hydrograph metadata reflects illustrative status
    res = generate_breach_hydrograph(
        params=nat_params,
        crest_elevation_m=100.0,
        cd_rect=1.70,
        cd_tri=1.35,
    )
    assert res.is_natural_dam is True


def test_non_embankment_dam_type_raises_error():
    """Test that non-embankment dam types (e.g. arch, concrete gravity) raise ValueError."""
    v_init = 1.0e7
    h_b = 25.0

    # SYNTHETIC_TEST_DAM (arch)
    with pytest.raises(ValueError, match="only for embankment dams"):
        estimate_breach_parameters(v_init, h_b, dam_type="arch")

    # SYNTHETIC_TEST_DAM (masonry gravity)
    with pytest.raises(ValueError, match="only for embankment dams"):
        froehlich_breach_width(v_init, h_b, dam_type="masonry_gravity")

    with pytest.raises(ValueError, match="only for embankment dams"):
        froehlich_formation_time(v_init, h_b, dam_type="concrete_gravity")

    with pytest.raises(ValueError, match="only for embankment dams"):
        froehlich_peak_outflow(v_init, h_b, dam_type="buttress")


def test_hydrograph_file_exports(tmp_path):
    """Test saving hydrograph to CSV and metadata to JSON."""
    v_init = 2.0e6
    h_b = 12.0

    params = estimate_breach_parameters(v_init, h_b)
    res = generate_breach_hydrograph(
        params=params,
        crest_elevation_m=100.0,
        cd_rect=1.70,
        cd_tri=1.35,
        dt_s=10.0,
        total_duration_s=3600.0,
    )

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
    assert meta["parameter_status"] == "verified_formula"
    assert "clamp_active_before_recession" in meta




def test_hydrograph_recession_limb_decays_without_discontinuity():
    """Verify that breach discharge Q(t) decays smoothly without discontinuities after peak."""
    v_init = 2.5e7  # 25 MCM
    h_b = 30.0
    h_w = 27.5
    crest_z = 85.0
    cd_rect = 1.70
    cd_tri = 1.35
    dt_s = 5.0

    params = estimate_breach_parameters(
        reservoir_volume_m3=v_init,
        breach_height_m=h_b,
        water_depth_m=h_w,
        mode="overtopping",
    )
    res = generate_breach_hydrograph(
        params=params,
        crest_elevation_m=crest_z,
        cd_rect=cd_rect,
        cd_tri=cd_tri,
        dt_s=dt_s,
    )

    peak_idx = int(np.argmax(res.discharge_m3s))
    q_recession = res.discharge_m3s[peak_idx:]
    peak_q = res.peak_discharge_hydrograph_m3s

    # Ensure run was extended until Q < 1% of peak
    assert res.discharge_m3s[-1] < 0.01 * peak_q

    # Check that after peak, Q decays monotonically without sudden upward spikes
    diffs = np.diff(q_recession)
    assert np.all(
        diffs <= 1e-6
    ), f"Found upward spike in recession limb: max diff = {np.max(diffs)}"

    # Continuity: step-to-step drop relative to peak must be small (< 1% per step dt)
    max_step_drop = float(np.max(np.abs(diffs)))
    max_step_drop_rel = max_step_drop / peak_q
    assert (
        max_step_drop_rel < 0.01
    ), f"Discontinuity detected: step drop {max_step_drop:.2f} m3/s ({max_step_drop_rel*100:.2f}% of peak)"


def test_hydrograph_tail_asymptotic_recession_and_clamp_invariance():
    """Verify asymptotic recession:
    1. For every step after peak where Q[i] >= 0.01*peak, Q[i+1] >= 0.85*Q[i].
    2. Residual above-invert volume < 1% of initial stored active volume.
    3. Zero clamp bindings after peak while Q >= 0.01*peak.
    """
    v_init = 2.5e7  # 25 MCM
    h_b = 30.0
    h_w = 27.5
    crest_z = 85.0
    cd_rect = 1.70
    cd_tri = 1.35
    dt_s = 5.0

    params = estimate_breach_parameters(
        reservoir_volume_m3=v_init,
        breach_height_m=h_b,
        water_depth_m=h_w,
        mode="overtopping",
    )
    res = generate_breach_hydrograph(
        params=params,
        crest_elevation_m=crest_z,
        cd_rect=cd_rect,
        cd_tri=cd_tri,
        dt_s=dt_s,
    )

    peak_q = res.peak_discharge_hydrograph_m3s
    peak_idx = int(np.argmax(res.discharge_m3s))
    threshold_q = 0.01 * peak_q

    # 1. Smooth recession test: for every step after peak where Q[i] >= 0.01*peak, Q[i+1] >= 0.85*Q[i]
    for i in range(peak_idx, len(res.discharge_m3s) - 1):
        q_curr = res.discharge_m3s[i]
        q_next = res.discharge_m3s[i + 1]
        if q_curr >= threshold_q:
            ratio = q_next / q_curr
            assert (
                ratio >= 0.85
            ), f"Step {i} (t={res.time_s[i]}s): Q[i+1]/Q[i] = {ratio:.4f} < 0.85 (Q[i]={q_curr:.2f}, Q[i+1]={q_next:.2f})"

    # 2. Residual above-invert volume < 1% of stored active volume
    residual_vol = res.remaining_reservoir_volume_m3 - (
        res.initial_stored_volume_m3 - res.active_storage_volume_m3
    )
    residual_pct = (residual_vol / res.active_storage_volume_m3) * 100.0
    assert (
        residual_pct < 1.0
    ), f"Residual above-invert volume {residual_pct:.3f}% is not < 1.0% of active storage ({residual_vol:.1f} m3)"

    # 3. Zero clamp bindings after peak while Q >= 0.01*peak
    assert (
        res.clamp_active_steps == 0
    ), f"Found {res.clamp_active_steps} clamp bindings during recession!"


def test_breach_bottom_width_clamped_to_zero_when_b_avg_less_than_z_times_hb():
    """Verify that when Froehlich B_avg < Z * h_b, bottom width clamps to 0.0 (forming triangular notch).

    Worked calculation:
      V_w = 1.0e6 m3, h_b = 40.0 m, overtopping (K_o = 1.3, Z = 1.0)
      B_avg = 0.27 * 1.3 * (1.0e6 ^ 0.32) * (40.0 ^ 0.04) ≈ 33.816 m
      Z * h_b = 1.0 * 40.0 = 40.0 m
      B_avg - Z * h_b = 33.816 - 40.0 = -6.184 m <= 0
      Expected bottom_width_m = 0.0 m.
    Routing then proceeds cleanly using purely triangular weir flow.
    """
    v_w = 1.0e6
    h_b = 40.0
    crest_z = 85.0
    cd_rect = 1.70
    cd_tri = 1.35

    params = estimate_breach_parameters(
        reservoir_volume_m3=v_w,
        breach_height_m=h_b,
        water_depth_m=h_b,
        mode="overtopping",
    )

    # 1. Assert theoretical invariants
    assert params.breach_width_avg_m < params.side_slope_z * h_b
    assert params.bottom_width_m == 0.0, f"Expected bottom width 0.0 m, got {params.bottom_width_m}"

    # 2. Simulate hydrograph: triangular weir flow
    res = generate_breach_hydrograph(
        params=params,
        crest_elevation_m=crest_z,
        cd_rect=cd_rect,
        cd_tri=cd_tri,
        dt_s=5.0,
    )

    assert res.peak_discharge_hydrograph_m3s > 0.0
    assert res.mass_conserved is True
    assert res.drawdown_monotonic is True
    assert np.all(res.breach_width_m == 0.0), "Breach bottom width must remain 0.0 throughout"
    assert res.total_outflow_volume_m3 > 0.95 * v_w

