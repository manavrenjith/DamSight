import os
import sys
from pathlib import Path
gdal_data_path = Path(sys.prefix) / "Library" / "share" / "gdal"
if gdal_data_path.exists():
    os.environ["GDAL_DATA"] = str(gdal_data_path)

import rasterio
import numpy as np
import pandas as pd

def analyze_arrival():
    with rasterio.open("outputs/site_a/arrival_time.tif") as a_src, rasterio.open("outputs/site_a/max_depth.tif") as d_src:
        arr = a_src.read(1)
        dep = d_src.read(1)
        
        dam_x, dam_y = 691350.0, 2518500.0
        
        # 1. 5km point: Southern industrial outskirts of Morbi
        # Let's search thalweg cells with distance ~ 5000m from dam
        rows, cols = np.where((dep > 1.0) & (arr > 0))
        xs, ys = rasterio.transform.xy(d_src.transform, rows, cols)
        xs, ys = np.array(xs), np.array(ys)
        
        # Euclidean distance
        euc_dists = np.sqrt((xs - dam_x)**2 + (ys - dam_y)**2)
        
        # Find deepest cells around Euclidean 5.0km (4.8km to 5.2km)
        mask_5k = (euc_dists >= 4800) & (euc_dists <= 5200) & (ys > dam_y)
        idx_5k = np.argmax(dep[rows[mask_5k], cols[mask_5k]])
        r_5k = rows[mask_5k][idx_5k]
        c_5k = cols[mask_5k][idx_5k]
        x_5k = xs[mask_5k][idx_5k]
        y_5k = ys[mask_5k][idx_5k]
        d_5k = dep[r_5k, c_5k]
        a_5k_s = arr[r_5k, c_5k]
        a_5k_min = a_5k_s / 60.0
        dist_5k_actual = euc_dists[mask_5k][idx_5k]

        # 2. 5km channel-distance point (approx Y = 2523300)
        # Using Y transect at Y=2523500 (approx 5.0km displacement along valley)
        r_chan5, _ = d_src.index(689161.2, 2523500.0)
        wet_chan5 = np.where((dep[r_chan5, :] > 1.0) & (arr[r_chan5, :] > 0))[0]
        c_chan5 = wet_chan5[np.argmax(dep[r_chan5, wet_chan5])]
        x_chan5, y_chan5 = d_src.xy(r_chan5, c_chan5)
        d_chan5 = dep[r_chan5, c_chan5]
        a_chan5_s = arr[r_chan5, c_chan5]
        a_chan5_min = a_chan5_s / 60.0

        # 3. 9km channel point / Morbi City Center reach (Y = 2524714)
        r_morbi, _ = d_src.index(689161.2, 2524714.0)
        wet_morbi = np.where((dep[r_morbi, :] > 1.0) & (arr[r_morbi, :] > 0))[0]
        c_morbi = wet_morbi[np.argmax(dep[r_morbi, wet_morbi])]
        x_morbi, y_morbi = d_src.xy(r_morbi, c_morbi)
        d_morbi = dep[r_morbi, c_morbi]
        a_morbi_s = arr[r_morbi, c_morbi]
        a_morbi_min = a_morbi_s / 60.0

        # Dam toe arrival time (time when water first exceeds 0.1m at dam outlet)
        r_dam, c_dam = d_src.index(dam_x, dam_y)
        a_dam_s = arr[r_dam, c_dam]
        a_dam_min = a_dam_s / 60.0

        # Transit time from Dam Outlet to 5km and to Morbi
        transit_5k_min = a_5k_min - a_dam_min
        transit_morbi_min = a_morbi_min - a_dam_min

        print("=" * 80)
        print("RECONCILIATION OF MORBI ARRIVAL TIME & DISTANCE CHECKPOINTS")
        print("=" * 80)
        print(f"Dam Toe Outlet (0 km):")
        print(f"  Coordinates:        ({dam_x:.1f}, {dam_y:.1f})")
        print(f"  Simulation Arrival: {a_dam_s:.1f} s ({a_dam_min:.1f} min post breach-start)")
        print(f"  Peak Depth:         {dep[r_dam, c_dam]:.2f} m\n")

        print(f"5 km Checkpoint (Morbi Industrial Outskirts):")
        print(f"  Coordinates:        ({x_5k:.1f}, {y_5k:.1f}) [Euclidean dist = {dist_5k_actual:.1f} m]")
        print(f"  Simulation Arrival: {a_5k_s:.1f} s ({a_5k_min:.1f} min post breach-start)")
        print(f"  Wave Transit Time:  {transit_5k_min:.1f} min (from dam toe to 5km)")
        print(f"  Peak Flood Depth:   {d_5k:.2f} m")
        print(f"  Historical Citation: '~20 minutes to Morbi industrial town 5 km below dam' (Wikipedia)\n")

        print(f"~9 km Checkpoint (Morbi City Center / Urban Core Reach):")
        print(f"  Coordinates:        ({x_morbi:.1f}, {y_morbi:.1f}) [~6.6km Euclidean, ~9km channel thalweg]")
        print(f"  Simulation Arrival: {a_morbi_s:.1f} s ({a_morbi_min:.1f} min post breach-start)")
        print(f"  Wave Transit Time:  {transit_morbi_min:.1f} min (from dam toe to Morbi city)")
        print(f"  Peak Flood Depth:   {d_morbi:.2f} m (channel thalweg), 5.11 m (reach average)")
        print(f"  Historical Citation: '~9 km upstream from Morbi' (morbionline.in)\n")

        # Let's inspect the breach hydrograph timing
        hydro = pd.read_csv("cache/site_a/hydrograph.csv")
        # When does discharge start rising significantly?
        q100 = hydro[hydro["discharge_m3s"] >= 100.0].iloc[0]
        q1000 = hydro[hydro["discharge_m3s"] >= 1000.0].iloc[0]
        q_peak = hydro.iloc[hydro["discharge_m3s"].argmax()]

        print("Breach Hydrograph Inception & Surging Timeline:")
        print(f"  Q >= 100 m3/s:      at t = {q100['time_s']:.1f} s ({q100['time_s']/60:.1f} min)")
        print(f"  Q >= 1000 m3/s:     at t = {q1000['time_s']:.1f} s ({q1000['time_s']/60:.1f} min)")
        print(f"  Q_peak (15,008 m3/s): at t = {q_peak['time_s']:.1f} s ({q_peak['time_s']/60:.1f} min)")
        print("-" * 80)

        return {
            "dam": {"x": dam_x, "y": dam_y, "arrival_min": a_dam_min},
            "point_5k": {
                "x": float(x_5k), "y": float(y_5k), "dist_m": float(dist_5k_actual),
                "arrival_min_from_t0": float(a_5k_min),
                "transit_time_from_dam_min": float(transit_5k_min),
                "depth_m": float(d_5k),
            },
            "point_9k_morbi": {
                "x": float(x_morbi), "y": float(y_morbi),
                "arrival_min_from_t0": float(a_morbi_min),
                "transit_time_from_dam_min": float(transit_morbi_min),
                "depth_m": float(d_morbi),
            }
        }

if __name__ == "__main__":
    analyze_arrival()
