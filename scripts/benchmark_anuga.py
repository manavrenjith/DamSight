"""Empirical benchmark for ANUGA simulation on Site A terrain.

Measures wall-clock time, internal ANUGA timesteps, adaptive dt, and peak RAM,
then linearly extrapolates to full 6-hour event.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

# Ensure GDAL_DATA is found
gdal_data_path = Path(sys.prefix) / "Library" / "share" / "gdal"
if gdal_data_path.exists():
    os.environ["GDAL_DATA"] = str(gdal_data_path)

import numpy as np
import pandas as pd
import psutil

from damsight.config import load_site_config
from damsight.solvers.anuga_solver import AnugaSolver


class MemoryMonitor(threading.Thread):
    """Monitors peak RSS memory of the current process and children."""

    def __init__(self, interval_s: float = 0.05):
        super().__init__(daemon=True)
        self.interval_s = interval_s
        self.running = True
        self.peak_bytes = 0
        self.proc = psutil.Process()

    def run(self) -> None:
        while self.running:
            try:
                mem = self.proc.memory_info().rss
                for child in self.proc.children(recursive=True):
                    mem += child.memory_info().rss
                if mem > self.peak_bytes:
                    self.peak_bytes = mem
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            time.sleep(self.interval_s)

    def stop(self) -> float:
        self.running = False
        return self.peak_bytes / (1024 * 1024)


def run_pilot(
    resolution_m: float,
    duration_s: float = 300.0,
    yieldstep_s: float = 20.0,
    cleanup: bool = True,
) -> dict:
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "configs" / "sites" / "site_a.yaml"
    dem_path = project_root / "cache" / "site_a" / "dem.tif"
    manning_path = project_root / "cache" / "site_a" / "manning_n.tif"
    hydrograph_path = project_root / "cache" / "site_a" / "hydrograph.csv"

    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    if not dem_path.exists():
        raise FileNotFoundError(f"DEM not found: {dem_path}")
    if not manning_path.exists():
        raise FileNotFoundError(f"Manning not found: {manning_path}")
    if not hydrograph_path.exists():
        raise FileNotFoundError(f"Hydrograph not found: {hydrograph_path}")

    site_cfg = load_site_config(config_path)
    hydro_df = pd.read_csv(hydrograph_path)

    # Locate downstream dam (Machhu-II)
    target_dam = None
    for d in site_cfg.dams:
        if d.id == "machhu_2" or d.role == "downstream":
            target_dam = d
            break
    if target_dam is None:
        raise ValueError("Machhu-II dam not found in site_a.yaml")

    dam_loc = target_dam.location
    print("=" * 70)
    print(f"PILOT RUN: Resolution = {resolution_m:.1f} m, Duration = {duration_s:.1f} s")
    print(f"Dam: {target_dam.id} at {dam_loc}")
    print("=" * 70)

    mem_monitor = MemoryMonitor(interval_s=0.05)
    mem_monitor.start()

    solver = AnugaSolver(far_field="delft3dfm", baseline="anuga", mass_balance_tolerance=0.05)

    print("\n[1/3] Preparing mesh and domain...")
    t_prep_start = time.time()
    run_dir = solver.prepare(
        site=site_cfg,
        hydrograph=hydro_df,
        mesh_resolution_m=resolution_m,
        boundary_type="transmissive",
        dem_path=dem_path,
        manning_path=manning_path,
        dam_location=dam_loc,
        inlet_radius_m=resolution_m * 1.5,
    )
    t_prep = time.time() - t_prep_start

    domain = run_dir.extra["domain"]
    n_triangles = len(domain)
    nx = run_dir.extra.get("channel_spec", {}).get("nx")
    ny = run_dir.extra.get("channel_spec", {}).get("ny")
    print(f"Mesh prepared in {t_prep:.2f} s:")
    print(f"  Total Triangles: {n_triangles:,}")
    print(f"  Working Directory: {run_dir.path}")

    print(f"\n[2/3] Executing hydrodynamic simulation (0 -> {duration_s:.1f} s, yieldstep={yieldstep_s:.1f} s)...")
    t_sim_start = time.time()
    
    # Custom evolve loop to accurately capture timesteps per yieldstep
    total_steps = 0
    all_min_dts = []
    all_max_dts = []
    
    sww_path = run_dir.path / "simulation.sww"

    for t in domain.evolve(yieldstep=yieldstep_s, finaltime=duration_s):
        steps_this_yield = domain.number_of_steps
        min_dt_yield = domain.recorded_min_timestep
        max_dt_yield = domain.recorded_max_timestep
        
        total_steps += steps_this_yield
        if min_dt_yield < 900.0:
            all_min_dts.append(min_dt_yield)
        if max_dt_yield > 0.0 and max_dt_yield < 900.0:
            all_max_dts.append(max_dt_yield)

        elapsed = time.time() - t_sim_start
        print(f"  [Sim Time {t:6.1f} s / {duration_s:6.1f} s] Yield steps: {steps_this_yield:3d} | Cum steps: {total_steps:5d} | dt: {min_dt_yield:7.4f}s .. {max_dt_yield:7.4f}s | Wall: {elapsed:5.2f}s")

    t_sim = time.time() - t_sim_start
    peak_ram_mb = mem_monitor.stop()

    # Collect volume and mass balance via solver
    # Compute domain volume INDEPENDENTLY from SWW output
    import netCDF4
    if sww_path.exists():
        nc = netCDF4.Dataset(str(sww_path), "r")
        x_pts = np.array(nc.variables["x"][:])
        y_pts = np.array(nc.variables["y"][:])
        vols = np.array(nc.variables["volumes"][:])
        stage_c = np.array(nc.variables["stage_c"][:])
        elev_c = np.array(nc.variables["elevation_c"][:])
        nc.close()

        x0, y0 = x_pts[vols[:, 0]], y_pts[vols[:, 0]]
        x1, y1 = x_pts[vols[:, 1]], y_pts[vols[:, 1]]
        x2, y2 = x_pts[vols[:, 2]], y_pts[vols[:, 2]]
        areas = 0.5 * np.abs(x0 * (y1 - y2) + x1 * (y2 - y0) + x2 * (y0 - y1))

        initial_vol = float(np.sum(np.maximum(0.0, stage_c[0] - elev_c) * areas))
        final_vol = float(np.sum(np.maximum(0.0, stage_c[-1] - elev_c) * areas))
    else:
        initial_vol = float(domain.get_water_volume())
        final_vol = float(domain.get_water_volume())

    inlet_op = run_dir.extra.get("inlet_operator")
    inflow_vol = float(inlet_op.get_total_applied_volume()) if inlet_op is not None else 0.0
    boundary_flux = float(domain.get_boundary_flux_integral())
    expected_vol = initial_vol + inflow_vol + boundary_flux
    norm_vol = max(1.0, max(expected_vol, final_vol))
    mass_balance_error = abs(final_vol - expected_vol) / norm_vol

    global_min_dt = min(all_min_dts) if all_min_dts else yieldstep_s
    global_max_dt = max(all_max_dts) if all_max_dts else yieldstep_s
    mean_dt = duration_s / total_steps if total_steps > 0 else 0.0

    print("\n[3/3] Simulation completed!")
    print(f"  Wall-clock Simulation Time: {t_sim:.2f} s ({t_sim/60.0:.2f} min)")
    print(f"  Total Internal Timesteps: {total_steps:,}")
    print(f"  ANUGA Adaptive dt: min={global_min_dt:.4f} s, max={global_max_dt:.4f} s, mean={mean_dt:.4f} s")
    print(f"  Inflow Volume Applied: {inflow_vol:,.1f} m³")
    print(f"  Peak RAM (RSS): {peak_ram_mb:.1f} MB")
    print(f"  Mass Balance Error: {mass_balance_error:.4%}")

    # Scaling analysis
    wall_per_sim_sec = t_sim / duration_s
    wall_per_step = t_sim / total_steps if total_steps > 0 else 0.0
    wall_per_elem_step_us = (t_sim / (total_steps * n_triangles)) * 1e6 if total_steps > 0 else 0.0

    # 6-hour full event extrapolation (21,600 simulated seconds)
    full_event_s = 21600.0  # 6 hours
    extrap_steps_6hr = full_event_s / mean_dt if mean_dt > 0 else 0
    extrap_sim_time_s = wall_per_sim_sec * full_event_s
    extrap_sim_time_min = extrap_sim_time_s / 60.0
    extrap_sim_time_hr = extrap_sim_time_min / 60.0

    # Also compute conservative extrapolation if peak flood forces dt down to 2.25s
    cfl_peak_dt = 2.25  # seconds
    steps_peak_cfl = full_event_s / cfl_peak_dt
    time_peak_cfl_s = steps_peak_cfl * wall_per_step
    time_peak_cfl_min = time_peak_cfl_s / 60.0

    metrics = {
        "resolution_m": resolution_m,
        "pilot_duration_s": duration_s,
        "pilot_wall_clock_s": t_sim,
        "prep_wall_clock_s": t_prep,
        "triangles": n_triangles,
        "timesteps": total_steps,
        "min_dt_s": global_min_dt,
        "max_dt_s": global_max_dt,
        "mean_dt_s": mean_dt,
        "inflow_vol_m3": inflow_vol,
        "peak_ram_mb": peak_ram_mb,
        "mass_balance_error": mass_balance_error,
        "wall_per_sim_sec": wall_per_sim_sec,
        "wall_per_step_s": wall_per_step,
        "wall_per_elem_step_us": wall_per_elem_step_us,
        "full_6hr_extrap_steps_linear": extrap_steps_6hr,
        "full_6hr_wall_clock_min_linear": extrap_sim_time_min,
        "full_6hr_wall_clock_hr_linear": extrap_sim_time_hr,
        "full_6hr_peak_cfl_dt_s": cfl_peak_dt,
        "full_6hr_wall_clock_min_peak_cfl": time_peak_cfl_min,
        "full_6hr_wall_clock_hr_peak_cfl": time_peak_cfl_min / 60.0,
    }

    print("\n--- Extrapolation to Full 6-Hour Event (21,600 s) ---")
    print(f"  1. Linear from pilot mean dt ({mean_dt:.2f} s): {extrap_sim_time_min:.2f} min ({extrap_sim_time_hr:.2f} hours) [{extrap_steps_6hr:,.0f} steps]")
    print(f"  2. Peak-CFL bounded dt ({cfl_peak_dt:.2f} s):   {time_peak_cfl_min:.2f} min ({time_peak_cfl_min/60.0:.2f} hours) [{steps_peak_cfl:,.0f} steps]")


    if cleanup:
        import shutil
        shutil.rmtree(run_dir.path, ignore_errors=True)

    return metrics


def main():
    parser = argparse.ArgumentParser(description="ANUGA Site A Empirical Timing Benchmark")
    parser.add_argument("--resolution", type=float, default=90.0, help="Mesh resolution in meters")
    parser.add_argument("--duration", type=float, default=300.0, help="Pilot simulated duration in seconds")
    parser.add_argument("--yieldstep", type=float, default=20.0, help="Yieldstep in seconds")
    parser.add_argument("--out-json", type=str, default=None, help="Save metrics to JSON file")
    args = parser.parse_args()

    metrics = run_pilot(
        resolution_m=args.resolution,
        duration_s=args.duration,
        yieldstep_s=args.yieldstep,
    )

    if args.out_json:
        with open(args.out_json, "w") as f:
            json.dump(metrics, f, indent=2)


if __name__ == "__main__":
    main()
