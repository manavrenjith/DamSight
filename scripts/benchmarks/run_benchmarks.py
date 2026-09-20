"""Execute Ritter (dry bed) and Stoker (wet bed) analytical benchmarks through AnugaSolver.

Measures front position error and L1 depth profile error across 3 mesh resolutions
(dx=20m, dx=10m, dx=5m) and 3 evaluation timestamps (5s, 10s, 15s).
Outputs results JSON, validation comparison plot, and gates summary.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import netCDF4
import numpy as np

from damsight.solvers.analytical import ritter_solution, stoker_solution
from damsight.solvers.anuga_solver import AnugaSolver


def extract_sww_profile(sww_path: Path, target_time: float) -> tuple[np.ndarray, np.ndarray, int]:
    """Extract 1D longitudinal depth profile and triangle count from ANUGA SWW output file at target time."""
    nc = netCDF4.Dataset(str(sww_path), "r")
    x_pts = np.array(nc.variables["x"][:])
    vols = np.array(nc.variables["volumes"][:])
    time_arr = np.array(nc.variables["time"][:])
    n_triangles = len(vols)

    stage_c = np.array(nc.variables["stage_c"][:])
    elev_c = np.array(nc.variables["elevation_c"][:])
    nc.close()

    time_idx = int(np.argmin(np.abs(time_arr - target_time)))
    xc = (x_pts[vols[:, 0]] + x_pts[vols[:, 1]] + x_pts[vols[:, 2]]) / 3.0
    depth = np.maximum(0.0, stage_c[time_idx] - elev_c)

    sort_idx = np.argsort(xc)
    return xc[sort_idx], depth[sort_idx], n_triangles


def run_benchmark_suite(
    output_dir: Path = Path("demo_data/benchmarks"),
    plot_path: Path = Path("docs/SLIDE_FIGURES/benchmark_ritter_stoker.png"),
) -> dict[str, dict]:
    """Run full benchmark suite through AnugaSolver adapter adhering to M3a gates."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_path.parent.mkdir(parents=True, exist_ok=True)

    solver = AnugaSolver()

    # Mesh resolutions: dx=20m (coarse), dx/2=10m (fine), dx/4=5m (superfine)
    resolutions = [20.0, 10.0, 5.0]
    timestamps = [5.0, 10.0, 15.0]
    g = 9.80665
    h0 = 10.0
    x0 = 500.0
    channel_len = 1000.0
    channel_width = 20.0
    c0 = np.sqrt(g * h0)

    benchmarks = {
        "ritter": {
            "name": "Ritter (1892) Dry Bed Dam-Break",
            "h_left_m": 10.0,
            "h_right_m": 0.0,
        },
        "stoker": {
            "name": "Stoker (1957) Wet Bed Dam-Break",
            "h_left_m": 10.0,
            "h_right_m": 2.0,
        },
    }

    results: dict[str, dict] = {
        "solver": "anuga",
        "anuga_version": "4.0.0",
        "channel_length_m": channel_len,
        "channel_width_m": channel_width,
        "dam_x_m": x0,
        "h0_m": h0,
        "gravity_m_s2": g,
        "manning_n": 0.0,
        "boundary_types": {
            "top": "reflective",
            "bottom": "reflective",
            "left": "transmissive",
            "right": "transmissive",
        },
        "yieldstep_s": 1.0,
        "timestamps_s": timestamps,
        "resolutions_m": resolutions,
        "benchmarks": {},
    }

    fig, axes = plt.subplots(2, 3, figsize=(15, 9), sharey="row")

    for row_idx, (b_key, b_cfg) in enumerate(benchmarks.items()):
        b_results: dict[str, dict] = {"resolutions": {}}
        h_right = b_cfg["h_right_m"]

        for res_m in resolutions:
            run_tmp = output_dir / f"tmp_{b_key}_res_{int(res_m)}"

            spec = {
                "type": "channel",
                "length_m": channel_len,
                "width_m": channel_width,
                "dam_x_m": x0,
                "h_left_m": b_cfg["h_left_m"],
                "h_right_m": h_right,
                "manning_n": 0.0,
                "b_left": "transmissive",
                "b_right": "transmissive",
                "boundary_type": "transmissive",
                "duration_s": 16.0,
                "yieldstep_s": 1.0,
            }

            # 1. Prepare through adapter
            run_dir = solver.prepare(
                spec,
                mesh_resolution_m=res_m,
                boundary_type="transmissive",
                run_dir=run_tmp,
            )

            # 2. Run through adapter
            run_res = solver.run(run_dir, yieldstep=1.0, finaltime=16.0)

            # 3. Collect through adapter
            _ = solver.collect(run_dir)

            # Extract SWW profile and mesh triangle count
            xc_sample, _, n_triangles = extract_sww_profile(run_dir.path / "simulation.sww", timestamps[0])

            res_data: dict[str, dict] = {
                "runtime_s": round(run_res.runtime_s, 3),
                "mass_balance_error": float(f"{run_res.mass_balance_error:.2e}"),
                "triangle_count": n_triangles,
                "sampling_grid_cells": len(xc_sample),
                "times": {},
            }

            for col_idx, t_eval in enumerate(timestamps):
                xc_sim, h_sim, _ = extract_sww_profile(run_dir.path / "simulation.sww", t_eval)

                # Analytical exact solution
                if b_key == "ritter":
                    h_exact, _, meta = ritter_solution(xc_sim, t=t_eval, x0=x0, h0=h0, g=g)
                    exact_front_tip = meta["x_front"]
                    # Fixed front threshold: furthest cell with depth > 0.01*h0
                    thresh = 0.01 * h0
                    sim_wet = xc_sim[h_sim > thresh]
                    exact_wet = xc_sim[h_exact > thresh]
                else:
                    h_exact, _, meta = stoker_solution(xc_sim, t=t_eval, x0=x0, hL=h0, hR=h_right, g=g)
                    exact_front_tip = meta["x_shock"]
                    # For Stoker, depth starts at h_right; front/shock threshold is h_right + 0.01*(hm - h_right)
                    thresh = h_right + 0.01 * (meta["hm"] - h_right)
                    sim_wet = xc_sim[h_sim > thresh]
                    exact_wet = xc_sim[h_exact > thresh]

                x_sim_front = float(np.max(sim_wet)) if len(sim_wet) > 0 else x0
                x_exact_thresh = float(np.max(exact_wet)) if len(exact_wet) > 0 else x0

                # B4: Front error reported two ways:
                # (i) % of front position [GATE: <= 5% at finest mesh]
                err_front_m = float(abs(x_sim_front - x_exact_thresh))
                err_front_pos_pct = float((err_front_m / x_exact_thresh) * 100.0)

                # (ii) % of distance travelled from x0 [strict metric, reported in JSON & PERFORMANCE.md]
                dist_travelled = abs(x_exact_thresh - x0)
                err_dist_travelled_pct = float(
                    (err_front_m / dist_travelled) * 100.0 if dist_travelled > 0 else 0.0
                )

                # Error against analytical tip (depth = 0) [information only]
                err_against_tip_m = float(abs(x_sim_front - exact_front_tip))

                # L1 Region 1 (Symmetric): Disturbed zone where |x - x0| <= c0 * t
                mask_disturbed = np.abs(xc_sim - x0) <= (c0 * t_eval)
                l1_disturbed_m = float(np.mean(np.abs(h_sim[mask_disturbed] - h_exact[mask_disturbed])))
                l1_disturbed_norm_pct = float((l1_disturbed_m / h0) * 100.0)

                # L1 Region 2: True disturbed region including tip
                # For Ritter: [x0 - c0*t, x0 + 2*c0*t]
                # For Stoker: [x0 - c0*t, x_exact_thresh]
                if b_key == "ritter":
                    mask_true_disturbed = (xc_sim >= (x0 - c0 * t_eval)) & (xc_sim <= (x0 + 2.0 * c0 * t_eval))
                else:
                    mask_true_disturbed = (xc_sim >= (x0 - c0 * t_eval)) & (xc_sim <= x_exact_thresh)
                l1_true_disturbed_m = float(np.mean(np.abs(h_sim[mask_true_disturbed] - h_exact[mask_true_disturbed])))
                l1_true_disturbed_norm_pct = float((l1_true_disturbed_m / h0) * 100.0)

                # Whole-domain L1 norm [information only]: mean_{domain} |h_sim - h_exact| / h0
                l1_whole_m = float(np.mean(np.abs(h_sim - h_exact)))
                l1_whole_norm_pct = float((l1_whole_m / h0) * 100.0)

                # Gate evaluations (at dx=5m)
                gate_front_pass = err_front_pos_pct <= 5.0
                gate_l1_pass = l1_disturbed_norm_pct <= 5.0
                gate_l1_true_pass = l1_true_disturbed_norm_pct <= 5.0

                res_data["times"][str(t_eval)] = {
                    "sim_front_m": round(x_sim_front, 2),
                    "exact_front_thresh_m": round(x_exact_thresh, 2),
                    "exact_front_tip_m": round(exact_front_tip, 2),
                    "front_error_m": round(err_front_m, 2),
                    "front_error_pct_pos": round(err_front_pos_pct, 2),
                    "front_error_pct_dist": round(err_dist_travelled_pct, 2),
                    "front_error_vs_tip_m": round(err_against_tip_m, 2),
                    "gate_front_5pct_pass": gate_front_pass,
                    "l1_disturbed_m": round(l1_disturbed_m, 4),
                    "l1_disturbed_norm_pct": round(l1_disturbed_norm_pct, 2),
                    "l1_true_disturbed_m": round(l1_true_disturbed_m, 4),
                    "l1_true_disturbed_norm_pct": round(l1_true_disturbed_norm_pct, 2),
                    "gate_l1_true_5pct_pass": gate_l1_true_pass,
                    "l1_whole_domain_m": round(l1_whole_m, 4),
                    "l1_whole_domain_norm_pct": round(l1_whole_norm_pct, 2),
                    "gate_l1_5pct_pass": gate_l1_pass,
                }

                # Plot on finest resolution (dx = 5.0 m)
                if res_m == 5.0:
                    ax = axes[row_idx, col_idx]
                    ax.plot(xc_sim, h_exact, "k--", lw=2, label="Exact Analytical")
                    ax.plot(
                        xc_sim,
                        h_sim,
                        color="#1f77b4" if b_key == "ritter" else "#2ca02c",
                        lw=1.8,
                        label=f"ANUGA (dx={int(res_m)}m)",
                    )
                    ax.axvline(
                        x_exact_thresh,
                        color="#d62728",
                        ls=":",
                        lw=1.5,
                        label=f"Front Thresh ({x_exact_thresh:.1f}m)",
                    )
                    ax.axvline(
                        exact_front_tip,
                        color="#7f7f7f",
                        ls="--",
                        lw=1.0,
                        alpha=0.7,
                        label=f"Exact Tip ({exact_front_tip:.1f}m)",
                    )
                    ax.set_title(
                        f"{b_cfg['name']}\nt = {t_eval:.1f}s | L1 Disturbed: {l1_disturbed_norm_pct:.2f}% | Front: {err_front_pos_pct:.2f}%",
                        fontsize=9,
                        fontweight="bold",
                    )
                    ax.set_xlabel("x (m)", fontsize=9)
                    if col_idx == 0:
                        ax.set_ylabel("Water Depth h (m)", fontsize=10)
                    ax.grid(True, alpha=0.3)
                    if row_idx == 0 and col_idx == 0:
                        ax.legend(loc="upper right", fontsize=7)

            b_results["resolutions"][f"{int(res_m)}m"] = res_data
            shutil.rmtree(run_tmp, ignore_errors=True)

        # B5: Convergence audit between resolutions:
        # dx=10m vs dx=20m: error(10) <= error(20)
        # dx=5m vs dx=10m: error(5) <= error(10)
        convergence_audit: dict[str, dict] = {}
        for t_eval in timestamps:
            t_str = str(t_eval)
            e_front_20 = b_results["resolutions"]["20m"]["times"][t_str]["front_error_m"]
            e_front_10 = b_results["resolutions"]["10m"]["times"][t_str]["front_error_m"]
            e_front_5 = b_results["resolutions"]["5m"]["times"][t_str]["front_error_m"]

            e_l1_20 = b_results["resolutions"]["20m"]["times"][t_str]["l1_disturbed_norm_pct"]
            e_l1_10 = b_results["resolutions"]["10m"]["times"][t_str]["l1_disturbed_norm_pct"]
            e_l1_5 = b_results["resolutions"]["5m"]["times"][t_str]["l1_disturbed_norm_pct"]

            front_conv = bool((e_front_10 <= e_front_20) and (e_front_5 <= e_front_10))
            l1_conv = bool((e_l1_10 <= e_l1_20) and (e_l1_5 <= e_l1_10))

            # Observed order: p = log2(e_10 / e_5)
            observed_order_l1 = float(np.log2(e_l1_10 / e_l1_5)) if e_l1_5 > 0 else 1.0

            convergence_audit[t_str] = {
                "front_monotonically_converging": front_conv,
                "l1_monotonically_converging": l1_conv,
                "observed_order_l1": round(observed_order_l1, 2),
                "pass_gate_b5": bool(front_conv and l1_conv),
            }
        b_results["convergence_audit"] = convergence_audit
        results["benchmarks"][b_key] = b_results

    plt.tight_layout()
    plt.savefig(plot_path, dpi=150)
    plt.close()
    print(f"Benchmark plot saved to: {plot_path}")

    # Also save to demo_data/benchmarks/ritter_stoker_comparison.png
    demo_plot = output_dir / "ritter_stoker_comparison.png"
    shutil.copy2(plot_path, demo_plot)

    # Save JSON results
    json_path = output_dir / "ritter_stoker_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Benchmark results JSON saved to: {json_path}")

    return results


def main() -> None:
    results = run_benchmark_suite()
    print("\n==================== BENCHMARK GATE SUMMARY ====================")
    for b_key, b_val in results["benchmarks"].items():
        print(f"\n--- {b_key.upper()} DAM-BREAK ---")
        for res, r_val in b_val["resolutions"].items():
            print(f"  Resolution {res} (Triangles: {r_val['triangle_count']}, Runtime: {r_val['runtime_s']}s):")
            for t, t_val in r_val["times"].items():
                status_front = "PASS" if t_val["gate_front_5pct_pass"] else "FAIL"
                status_l1 = "PASS" if t_val["gate_l1_5pct_pass"] else "FAIL"
                status_l1_true = "PASS" if t_val["gate_l1_true_5pct_pass"] else "FAIL"
                print(
                    f"    t = {t}s -> Front Err: {t_val['front_error_m']:.2f} m "
                    f"({t_val['front_error_pct_pos']:.2f}% pos [{status_front}], {t_val['front_error_pct_dist']:.2f}% dist, vs tip: {t_val['front_error_vs_tip_m']:.2f} m) | "
                    f"L1 Sym: {t_val['l1_disturbed_norm_pct']:.2f}% [{status_l1}] | "
                    f"L1 True: {t_val['l1_true_disturbed_norm_pct']:.2f}% [{status_l1_true}] (whole: {t_val['l1_whole_domain_norm_pct']:.2f}%)"
                )
        print("  Convergence Audit (B5 Gate):")
        for t, c_val in b_val["convergence_audit"].items():
            status_b5 = "PASS" if c_val["pass_gate_b5"] else "FAIL"
            print(
                f"    t = {t}s -> Front Conv: {c_val['front_monotonically_converging']} | "
                f"L1 Conv: {c_val['l1_monotonically_converging']} | Observed Order: {c_val['observed_order_l1']:.2f} [{status_b5}]"
            )
    print("================================================================\n")


if __name__ == "__main__":
    main()
