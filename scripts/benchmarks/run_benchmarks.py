"""Execute Ritter (dry bed) and Stoker (wet bed) analytical benchmarks through AnugaSolver.

Measures front position error and L1 depth profile error across 2 mesh resolutions
and 3 evaluation timestamps. Outputs results JSON and comparison plots.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import netCDF4
import numpy as np

from damsight.solvers.analytical import ritter_solution, stoker_solution
from damsight.solvers.anuga_solver import AnugaSolver


def extract_sww_profile(sww_path: Path, target_time: float) -> tuple[np.ndarray, np.ndarray]:
    """Extract 1D longitudinal depth profile from ANUGA SWW output file at a given time."""
    nc = netCDF4.Dataset(str(sww_path), "r")
    x_pts = np.array(nc.variables["x"][:])
    vols = np.array(nc.variables["volumes"][:])
    time_arr = np.array(nc.variables["time"][:])

    stage_c = np.array(nc.variables["stage_c"][:])
    elev_c = np.array(nc.variables["elevation_c"][:])
    nc.close()

    # Find closest timestep
    time_idx = int(np.argmin(np.abs(time_arr - target_time)))

    # Compute triangle centroids
    xc = (x_pts[vols[:, 0]] + x_pts[vols[:, 1]] + x_pts[vols[:, 2]]) / 3.0

    depth = np.maximum(0.0, stage_c[time_idx] - elev_c)

    # Sort along x axis
    sort_idx = np.argsort(xc)
    return xc[sort_idx], depth[sort_idx]


def run_benchmark_suite(
    output_dir: Path = Path("demo_data/benchmarks"),
    plot_path: Path = Path("docs/SLIDE_FIGURES/benchmark_ritter_stoker.png"),
) -> dict[str, dict]:
    """Run full benchmark suite through AnugaSolver adapter."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_path.parent.mkdir(parents=True, exist_ok=True)

    solver = AnugaSolver()

    resolutions = [20.0, 10.0]  # Coarse vs fine
    timestamps = [5.0, 10.0, 15.0]

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
        "channel_length_m": 1000.0,
        "dam_x_m": 500.0,
        "timestamps_s": timestamps,
        "resolutions_m": resolutions,
        "benchmarks": {},
    }

    _fig, axes = plt.subplots(2, 3, figsize=(15, 9), sharey="row")

    for row_idx, (b_key, b_cfg) in enumerate(benchmarks.items()):
        b_results: dict[str, dict] = {"resolutions": {}}

        for res_m in resolutions:
            run_tmp = output_dir / f"tmp_{b_key}_res_{int(res_m)}"

            spec = {
                "type": "channel",
                "length_m": 1000.0,
                "width_m": 20.0,
                "dam_x_m": 500.0,
                "h_left_m": b_cfg["h_left_m"],
                "h_right_m": b_cfg["h_right_m"],
                "manning_n": 0.0,
                "duration_s": 16.0,
                "yieldstep_s": 1.0,
            }

            # 1. Prepare through adapter
            run_dir = solver.prepare(spec, mesh_resolution_m=res_m, run_dir=run_tmp)

            # 2. Run through adapter
            run_res = solver.run(run_dir, yieldstep=1.0, finaltime=16.0)

            # 3. Collect through adapter
            _ = solver.collect(run_dir)

            res_data: dict[str, dict] = {
                "runtime_s": run_res.runtime_s,
                "mass_balance_error": run_res.mass_balance_error,
                "times": {},
            }

            for col_idx, t_eval in enumerate(timestamps):
                xc_sim, h_sim = extract_sww_profile(run_dir.path / "simulation.sww", t_eval)

                # Analytical exact solution
                if b_key == "ritter":
                    h_exact, _, meta = ritter_solution(xc_sim, t=t_eval, x0=500.0, h0=10.0)
                    exact_front = meta["x_front"]
                    # Simulated front: furthest downstream cell with depth > 0.05 m
                    wet_pts = xc_sim[h_sim > 0.05]
                    sim_front = float(np.max(wet_pts)) if len(wet_pts) > 0 else 500.0
                else:
                    h_exact, _, meta = stoker_solution(xc_sim, t=t_eval, x0=500.0, hL=10.0, hR=2.0)
                    exact_front = meta["x_shock"]
                    # Simulated shock front: location of sharp transition
                    shock_thresh = 2.0 + 0.15 * (meta["hm"] - 2.0)
                    wet_pts = xc_sim[h_sim > shock_thresh]
                    sim_front = float(np.max(wet_pts)) if len(wet_pts) > 0 else 500.0

                l1_error = float(np.mean(np.abs(h_sim - h_exact)))
                front_error = float(abs(sim_front - exact_front))

                res_data["times"][str(t_eval)] = {
                    "l1_depth_error_m": round(l1_error, 4),
                    "exact_front_m": round(float(exact_front), 2),
                    "sim_front_m": round(float(sim_front), 2),
                    "front_position_error_m": round(front_error, 2),
                }

                # Plot on fine resolution
                if res_m == 10.0:
                    ax = axes[row_idx, col_idx]
                    ax.plot(
                        xc_sim,
                        h_exact,
                        "k--",
                        lw=2,
                        label="Exact Analytical",
                    )
                    ax.plot(
                        xc_sim,
                        h_sim,
                        color="#1f77b4" if b_key == "ritter" else "#2ca02c",
                        lw=1.8,
                        label=f"ANUGA (dx={int(res_m)}m)",
                    )
                    ax.axvline(
                        exact_front,
                        color="#d62728",
                        ls=":",
                        alpha=0.8,
                        label=f"Exact Front ({exact_front:.1f}m)",
                    )
                    ax.set_title(
                        f"{b_cfg['name']}\nt = {t_eval:.1f}s | L1 Error: {l1_error:.3f}m",
                        fontsize=10,
                        fontweight="bold",
                    )
                    ax.set_xlabel("x (m)", fontsize=9)
                    if col_idx == 0:
                        ax.set_ylabel("Water Depth h (m)", fontsize=10)
                    ax.grid(True, alpha=0.3)
                    if row_idx == 0 and col_idx == 0:
                        ax.legend(loc="upper right", fontsize=8)

            b_results["resolutions"][f"{int(res_m)}m"] = res_data

        results["benchmarks"][b_key] = b_results

    plt.tight_layout()
    plt.savefig(plot_path, dpi=150)
    plt.close()
    print(f"Benchmark plot saved to: {plot_path}")

    # Save JSON results
    json_path = output_dir / "ritter_stoker_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Benchmark results JSON saved to: {json_path}")

    return results


def main() -> None:
    results = run_benchmark_suite()
    print("\n--- BENCHMARK VALIDATION SUMMARY ---")
    for b_key, b_val in results["benchmarks"].items():
        print(f"\n{b_key.upper()}:")
        for res, r_val in b_val["resolutions"].items():
            print(
                f"  Resolution {res} (Runtime: {r_val['runtime_s']:.2f}s, Mass err: {r_val['mass_balance_error']:.2e}):"
            )
            for t, t_val in r_val["times"].items():
                print(
                    f"    t = {t}s -> L1 Error: {t_val['l1_depth_error_m']:.4f} m | "
                    f"Front Err: {t_val['front_position_error_m']:.2f} m "
                    f"(Sim: {t_val['sim_front_m']:.1f}m, Exact: {t_val['exact_front_m']:.1f}m)"
                )
    print("------------------------------------\n")


if __name__ == "__main__":
    main()
