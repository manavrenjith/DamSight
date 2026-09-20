"""ANUGA shallow-water 2D hydrodynamic solver adapter.

Implements the Solver protocol (prepare, run, collect) with inflow hydrograph,
Manning n roughness, mass-balance monitoring, and standardized GeoTIFF exports.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from scipy.interpolate import griddata

from damsight.solvers.base import Outputs, RunDir, RunResult

logger = logging.getLogger(__name__)

ANUGA_AVAILABLE = False
ANUGA_VERSION = "unknown"
try:
    import sys

    import anuga

    ANUGA_AVAILABLE = True
    raw_ver = getattr(anuga, "__version__", "4.0.0")
    if "unknown" in raw_ver or raw_ver.startswith("0.0.0"):
        conda_meta = Path(sys.prefix) / "conda-meta"
        matches = list(conda_meta.glob("anuga-*.json"))
        if matches:
            parts = matches[0].stem.split("-")
            raw_ver = parts[1] if len(parts) >= 2 else "4.0.0"
        else:
            raw_ver = "4.0.0"
    ANUGA_VERSION = raw_ver
except ImportError:
    anuga = None  # type: ignore


class AnugaSolver:
    """Hydrodynamic shallow-water solver adapter wrapping ANUGA."""

    def __init__(
        self,
        far_field: str = "delft3dfm",
        baseline: str = "anuga",
        mass_balance_tolerance: float = 0.05,
    ) -> None:
        if not ANUGA_AVAILABLE:
            raise RuntimeError(
                "ANUGA is not installed or importable. Check environment or install via conda-forge."
            )
        self.far_field = far_field
        self.baseline = baseline
        self.mass_balance_tolerance = mass_balance_tolerance

    def prepare(
        self,
        site: Any,
        hydrograph: pd.DataFrame | None = None,
        mesh_resolution_m: float = 30.0,
        run_dir: Path | None = None,
        boundary_type: str | None = None,
        **kwargs: Any,
    ) -> RunDir:
        """Prepare working directory, mesh, bathymetry, roughness, and boundary conditions.

        Supports both real/synthetic geospatial site configurations and analytical benchmark specifications.
        boundary_type is a required parameter (no default).
        """
        # Enforce required boundary_type with no default
        resolved_b_type = boundary_type
        if resolved_b_type is None and "boundary_type" in kwargs:
            resolved_b_type = kwargs.pop("boundary_type")
        if resolved_b_type is None and isinstance(site, dict) and "boundary_type" in site:
            resolved_b_type = site.get("boundary_type")

        if resolved_b_type is None:
            raise ValueError(
                "boundary_type is a required argument with no default (e.g. 'transmissive' or 'reflective')."
            )

        if run_dir is None:
            import tempfile

            run_dir_path = Path(tempfile.mkdtemp(prefix="anuga_run_"))
        else:
            run_dir_path = Path(run_dir)
            run_dir_path.mkdir(parents=True, exist_ok=True)

        extra: dict[str, Any] = {
            "site": site,
            "hydrograph": hydrograph,
            "boundary_type": resolved_b_type,
            "kwargs": kwargs,
        }

        # Case 1: Analytical rectangular channel specification
        if isinstance(site, dict) and site.get("type") == "channel":
            length_m = float(site.get("length_m", 1000.0))
            width_m = float(site.get("width_m", 20.0))
            dam_x_m = float(site.get("dam_x_m", 500.0))
            h_left_m = float(site.get("h_left_m", 10.0))
            h_right_m = float(site.get("h_right_m", 0.0))
            manning_n = float(site.get("manning_n", 0.0))
            duration_s = float(site.get("duration_s", 20.0))
            yieldstep_s = float(site.get("yieldstep_s", 1.0))
            crs = str(site.get("crs", "EPSG:32643"))

            nx = max(2, round(length_m / mesh_resolution_m))
            ny = max(1, round(width_m / mesh_resolution_m))

            domain = anuga.rectangular_cross_domain(
                nx, ny, len1=length_m, len2=width_m, origin=(0.0, 0.0)
            )
            domain.set_name("simulation")
            domain.set_datadir(str(run_dir_path))
            domain.set_quantity("elevation", 0.0)
            domain.set_quantity("friction", manning_n)

            # Initial stage piecewise function
            def initial_stage(x: np.ndarray, y: np.ndarray) -> np.ndarray:
                return np.where(x <= dam_x_m, h_left_m, h_right_m)

            domain.set_quantity("stage", initial_stage)

            # Boundary conditions: reflective side walls, transmissive ends
            b_left = site.get("b_left", resolved_b_type)
            b_right = site.get("b_right", resolved_b_type)
            boundary_map = {
                "bottom": anuga.Reflective_boundary(domain),
                "top": anuga.Reflective_boundary(domain),
                "left": (
                    anuga.Transmissive_boundary(domain)
                    if b_left == "transmissive"
                    else anuga.Reflective_boundary(domain)
                ),
                "right": (
                    anuga.Transmissive_boundary(domain)
                    if b_right == "transmissive"
                    else anuga.Reflective_boundary(domain)
                ),
            }
            domain.set_boundary(boundary_map)

            # Inflow Hydrograph via Inlet Operator (for channel spec)
            if hydrograph is not None and not hydrograph.empty:
                dam_loc = kwargs.get("dam_location", [dam_x_m, width_m / 2.0])
                dam_x, dam_y = float(dam_loc[0]), float(dam_loc[1])
                inlet_radius = float(kwargs.get("inlet_radius_m", mesh_resolution_m * 1.5))
                region = anuga.Region(domain, center=[dam_x, dam_y], radius=inlet_radius)

                time_arr = hydrograph["time_s"].to_numpy()
                flow_arr = hydrograph["discharge_m3s"].to_numpy()

                def q_func_channel(t: float) -> float:
                    return float(np.interp(t, time_arr, flow_arr, left=0.0, right=0.0))

                inlet_op = anuga.Inlet_operator(domain, region, Q=q_func_channel)
                extra["inlet_operator"] = inlet_op

            extra["domain"] = domain
            extra["channel_spec"] = {
                "length_m": length_m,
                "width_m": width_m,
                "dam_x_m": dam_x_m,
                "h_left_m": h_left_m,
                "h_right_m": h_right_m,
                "duration_s": duration_s,
                "yieldstep_s": yieldstep_s,
                "crs": crs,
                "nx": nx,
                "ny": ny,
            }
            extra["grid_spec"] = {
                "crs": crs,
                "bounds": [0.0, 0.0, length_m, width_m],
                "resolution": mesh_resolution_m,
            }

        # Case 2: Geospatial site DEM & landcover simulation
        else:
            dem_path: Path | None = None
            if hasattr(site, "inputs") and hasattr(site.inputs, "dem") and site.inputs.dem.path:
                dem_path = Path(site.inputs.dem.path)
            elif isinstance(site, dict) and "dem_path" in site:
                dem_path = Path(site["dem_path"])
            elif kwargs.get("dem_path"):
                dem_path = Path(kwargs["dem_path"])

            if dem_path is None or not dem_path.exists():
                raise FileNotFoundError(f"DEM raster file not found for site: {dem_path}")

            with rasterio.open(dem_path) as dem_src:
                dem_bounds = dem_src.bounds
                dem_crs = dem_src.crs.to_string() if dem_src.crs else "EPSG:32643"
                dem_transform = dem_src.transform
                dem_shape = (dem_src.height, dem_src.width)
                dem_nodata = dem_src.nodata or -9999.0

            x_len = dem_bounds.right - dem_bounds.left
            y_len = dem_bounds.top - dem_bounds.bottom
            nx = max(2, round(x_len / mesh_resolution_m))
            ny = max(2, round(y_len / mesh_resolution_m))

            domain = anuga.rectangular_cross_domain(
                nx,
                ny,
                len1=x_len,
                len2=y_len,
                origin=(dem_bounds.left, dem_bounds.bottom),
            )
            domain.set_name("simulation")
            domain.set_datadir(str(run_dir_path))

            centroids = domain.get_centroid_coordinates()

            with rasterio.open(dem_path) as dem_src:
                sampled_elev = np.array([val[0] for val in dem_src.sample(centroids)])
            # Clean nodata values if any
            valid_elev = np.where(
                sampled_elev == dem_nodata,
                np.nanmean(sampled_elev[sampled_elev != dem_nodata]),
                sampled_elev,
            )
            domain.set_quantity("elevation", valid_elev, location="centroids")

            # Friction: sample from Manning raster if available
            manning_path = kwargs.get("manning_path")
            if manning_path and Path(manning_path).exists():
                with rasterio.open(manning_path) as man_src:
                    sampled_manning = np.array([val[0] for val in man_src.sample(centroids)])
                domain.set_quantity("friction", sampled_manning, location="centroids")
            else:
                default_n = float(kwargs.get("manning_n", 0.035))
                domain.set_quantity("friction", default_n)

            # Stage: initial water depth (dry bed by default)
            init_depth = float(kwargs.get("initial_depth_m", 0.0))
            domain.set_quantity("stage", valid_elev + init_depth, location="centroids")

            # Inflow Hydrograph via Inlet Operator
            inlet_op = None
            if hydrograph is not None and not hydrograph.empty:
                dam_loc = kwargs.get("dam_location")
                if dam_loc is None and hasattr(site, "dams") and site.dams:
                    dam_loc = site.dams[0].location

                if dam_loc is not None:
                    # dam_loc can be [lon, lat] or [x, y]
                    dam_x, dam_y = float(dam_loc[0]), float(dam_loc[1])
                    inlet_radius = float(kwargs.get("inlet_radius_m", mesh_resolution_m * 1.5))
                    region = anuga.Region(domain, center=[dam_x, dam_y], radius=inlet_radius)

                    time_arr = hydrograph["time_s"].to_numpy()
                    flow_arr = hydrograph["discharge_m3s"].to_numpy()

                    def q_func(t: float) -> float:
                        return float(np.interp(t, time_arr, flow_arr, left=0.0, right=0.0))

                    inlet_op = anuga.Inlet_operator(domain, region, Q=q_func)
                    extra["inlet_operator"] = inlet_op

            # Boundaries
            b_type = resolved_b_type
            b_op = (
                anuga.Transmissive_boundary(domain)
                if b_type == "transmissive"
                else anuga.Reflective_boundary(domain)
            )
            domain.set_boundary(
                {
                    "left": b_op,
                    "right": b_op,
                    "bottom": b_op,
                    "top": b_op,
                }
            )

            extra["domain"] = domain
            extra["grid_spec"] = {
                "crs": dem_crs,
                "bounds": [dem_bounds.left, dem_bounds.bottom, dem_bounds.right, dem_bounds.top],
                "transform": dem_transform,
                "shape": dem_shape,
                "nodata": dem_nodata,
                "resolution": mesh_resolution_m,
            }

        # Save any tally scaling or arrival parameters in extra
        if "tally_inflow_scale" in kwargs:
            extra["tally_inflow_scale"] = float(kwargs["tally_inflow_scale"])
        if "arrival_threshold_m" in kwargs:
            extra["arrival_threshold_m"] = float(kwargs["arrival_threshold_m"])

        return RunDir(path=run_dir_path, mesh_resolution_m=mesh_resolution_m, extra=extra)

    def run(
        self,
        run_dir: RunDir,
        yieldstep: float = 1.0,
        finaltime: float | None = None,
    ) -> RunResult:
        """Execute simulation, monitor mass balance, and verify pass threshold."""
        domain = run_dir.extra.get("domain")
        if domain is None:
            raise ValueError("RunDir contains no prepared ANUGA domain instance")

        # Determine duration
        if finaltime is None:
            channel_spec = run_dir.extra.get("channel_spec", {})
            finaltime = float(channel_spec.get("duration_s", 20.0))

        start_time = time.time()

        # Evolve domain
        for _ in domain.evolve(yieldstep=yieldstep, finaltime=finaltime):
            pass

        runtime_s = time.time() - start_time

        # Compute domain volume INDEPENDENTLY from SWW output (stage - elevation, times cell area)
        sww_path = run_dir.path / "simulation.sww"
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

        # Mass conservation accounting: V_final = V_init + V_in - V_out
        inlet_op = run_dir.extra.get("inlet_operator")
        inflow_vol = float(inlet_op.get_total_applied_volume()) if inlet_op is not None else 0.0

        # Tally scale allows forced violation testing:
        # e.g., inlet applied hydrograph scaled by 1.02 while tally uses 1.00
        tally_scale = float(run_dir.extra.get("tally_inflow_scale", 1.0))
        tally_inflow_vol = inflow_vol * tally_scale

        # Boundary net flux (negative = outflow leaving domain, positive = inflow entering domain)
        boundary_flux = float(domain.get_boundary_flux_integral())
        outflow_vol = -min(0.0, boundary_flux)

        expected_vol = initial_vol + tally_inflow_vol + boundary_flux
        norm_vol = max(1.0, max(expected_vol, final_vol))
        mass_balance_error = abs(final_vol - expected_vol) / norm_vol

        warnings_list: list[str] = []
        success = True

        if mass_balance_error > self.mass_balance_tolerance:
            success = False
            msg = (
                f"Mass balance error ({mass_balance_error:.4%}) exceeded configured "
                f"tolerance ({self.mass_balance_tolerance:.4%}). V_init={initial_vol:.1f} m3, "
                f"V_inflow={tally_inflow_vol:.1f} m3, V_outflow={outflow_vol:.1f} m3, "
                f"V_final={final_vol:.1f} m3, V_expected={expected_vol:.1f} m3"
            )
            warnings_list.append(msg)
            logger.warning(msg)

        result = RunResult(
            success=success,
            runtime_s=runtime_s,
            mass_balance_error=mass_balance_error,
            warnings=warnings_list,
            extra={
                "initial_volume_m3": initial_vol,
                "inflow_volume_m3": inflow_vol,
                "tally_inflow_volume_m3": tally_inflow_vol,
                "outflow_volume_m3": outflow_vol,
                "boundary_flux_integral": boundary_flux,
                "expected_volume_m3": expected_vol,
                "final_volume_m3": final_vol,
                "finaltime_s": finaltime,
            },
        )
        run_dir.extra["run_result"] = result
        return result

    def collect(self, run_dir: RunDir) -> Outputs:
        """Collect and validate standardized output rasters adhering to the outputs contract."""
        sww_path = run_dir.path / "simulation.sww"
        if not sww_path.exists():
            raise FileNotFoundError(f"Simulation output SWW file not found: {sww_path}")

        nc = netCDF4.Dataset(str(sww_path), "r")
        x_pts = np.array(nc.variables["x"][:])
        y_pts = np.array(nc.variables["y"][:])
        vols = np.array(nc.variables["volumes"][:])
        time_arr = np.array(nc.variables["time"][:])

        stage_c = np.array(nc.variables["stage_c"][:])  # (timesteps, n_triangles)
        elev_c = np.array(nc.variables["elevation_c"][:])
        xmom_c = np.array(nc.variables["xmomentum_c"][:])
        ymom_c = np.array(nc.variables["ymomentum_c"][:])
        nc.close()

        # Compute triangle centroid coordinates
        xc = (x_pts[vols[:, 0]] + x_pts[vols[:, 1]] + x_pts[vols[:, 2]]) / 3.0
        yc = (y_pts[vols[:, 0]] + y_pts[vols[:, 1]] + y_pts[vols[:, 2]]) / 3.0
        points = np.column_stack([xc, yc])

        # Depth time series
        depth_c = np.maximum(0.0, stage_c - elev_c)  # (timesteps, n_triangles)

        # Velocity & Hazard time series
        speed_c = np.zeros_like(depth_c)
        for k in range(len(time_arr)):
            d_k = depth_c[k]
            u_k = xmom_c[k] / np.maximum(d_k, 1e-4)
            v_k = ymom_c[k] / np.maximum(d_k, 1e-4)
            speed_c[k] = np.where(d_k > 0.005, np.sqrt(u_k**2 + v_k**2), 0.0)

        hazard_c = depth_c * speed_c

        # Peak quantities across all timesteps
        max_depth_vals = np.max(depth_c, axis=0)
        max_velocity_vals = np.max(speed_c, axis=0)
        max_hazard_vals = np.max(hazard_c, axis=0)

        # Arrival time: first time depth exceeds threshold; nodata if never
        arrival_thresh = float(run_dir.extra.get("arrival_threshold_m", 0.1))
        arrival_time_vals = np.full(len(xc), -9999.0, dtype=np.float32)
        exceed_mask = depth_c > arrival_thresh  # (timesteps, n_triangles)
        for tri_idx in range(len(xc)):
            idx_hits = np.where(exceed_mask[:, tri_idx])[0]
            if len(idx_hits) > 0:
                arrival_time_vals[tri_idx] = float(time_arr[idx_hits[0]])

        # Determine target raster grid
        grid_spec = run_dir.extra.get("grid_spec", {})
        bounds = grid_spec.get("bounds", [xc.min(), yc.min(), xc.max(), yc.max()])
        crs = grid_spec.get("crs", "EPSG:32643")
        nodata_val = float(grid_spec.get("nodata", -9999.0))
        res_m = float(run_dir.mesh_resolution_m)

        if "transform" in grid_spec and "shape" in grid_spec:
            transform = grid_spec["transform"]
            height, width = grid_spec["shape"]
            cols, rows = np.meshgrid(np.arange(width), np.arange(height))
            gx, gy = rasterio.transform.xy(transform, rows, cols, offset="center")
            grid_x = np.array(gx)
            grid_y = np.array(gy)
        else:
            x_min, y_min, x_max, y_max = bounds
            width = max(2, round((x_max - x_min) / res_m))
            height = max(2, round((y_max - y_min) / res_m))
            transform = from_origin(x_min, y_max, res_m, res_m)
            cols, rows = np.meshgrid(np.arange(width), np.arange(height))
            gx, gy = rasterio.transform.xy(transform, rows, cols, offset="center")
            grid_x = np.array(gx)
            grid_y = np.array(gy)

        # Interpolate onto regular grid
        interp_depth = griddata(
            points, max_depth_vals, (grid_x, grid_y), method="linear", fill_value=0.0
        ).reshape(height, width)
        interp_velocity = griddata(
            points, max_velocity_vals, (grid_x, grid_y), method="linear", fill_value=0.0
        ).reshape(height, width)
        interp_hazard = griddata(
            points, max_hazard_vals, (grid_x, grid_y), method="linear", fill_value=0.0
        ).reshape(height, width)
        interp_arrival = griddata(
            points, arrival_time_vals, (grid_x, grid_y), method="nearest", fill_value=nodata_val
        ).reshape(height, width)

        # Clean unwetted cells in arrival time
        interp_arrival = np.where(interp_depth <= arrival_thresh, nodata_val, interp_arrival)

        # Write standard GeoTIFF contract rasters
        max_depth_tif = run_dir.path / "max_depth.tif"
        max_velocity_tif = run_dir.path / "max_velocity.tif"
        arrival_time_tif = run_dir.path / "arrival_time.tif"
        hazard_tif = run_dir.path / "hazard.tif"

        raster_meta = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 1,
            "dtype": "float32",
            "crs": crs,
            "transform": transform,
            "nodata": nodata_val,
        }

        for path, data_arr in [
            (max_depth_tif, interp_depth),
            (max_velocity_tif, interp_velocity),
            (arrival_time_tif, interp_arrival),
            (hazard_tif, interp_hazard),
        ]:
            with rasterio.open(path, "w", **raster_meta) as dst:
                dst.write(data_arr.astype(np.float32), 1)

        # Generate run_meta.json
        run_result: RunResult | None = run_dir.extra.get("run_result")
        runtime_s = run_result.runtime_s if run_result else 0.0
        mass_error = run_result.mass_balance_error if run_result else 0.0
        warns = run_result.warnings if run_result else []

        run_meta_json = run_dir.path / "run_meta.json"
        meta_data: dict[str, Any] = {
            "solver": "anuga",
            "version": ANUGA_VERSION,
            "install_method": "conda-forge",
            "mesh_resolution_m": run_dir.mesh_resolution_m,
            "boundary_type": run_dir.extra.get("boundary_type"),
            "runtime_s": runtime_s,
            "mass_balance_error": mass_error,
            "warnings": warns,
        }
        if "arrival_threshold_m" in run_dir.extra:
            meta_data["arrival_threshold_m"] = float(run_dir.extra["arrival_threshold_m"])

        with open(run_meta_json, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, indent=2)

        return Outputs(
            max_depth_tif=max_depth_tif,
            max_velocity_tif=max_velocity_tif,
            arrival_time_tif=arrival_time_tif,
            hazard_tif=hazard_tif,
            run_meta_json=run_meta_json,
        )
