import os
import sys
from pathlib import Path
gdal_data_path = Path(sys.prefix) / "Library" / "share" / "gdal"
if gdal_data_path.exists():
    os.environ["GDAL_DATA"] = str(gdal_data_path)

import rasterio
import numpy as np

with rasterio.open("outputs/site_a/max_depth.tif") as d_src, rasterio.open("outputs/site_a/arrival_time.tif") as a_src:
    depth = d_src.read(1)
    arrival = a_src.read(1)
    
    # We sample transects every 1km northward from Dam (Y=2518500) to Morbi (Y=2524500) to North exit (Y=2534000)
    y_targets = np.linspace(2518500.0, 2533000.0, 15)
    
    print("=" * 80)
    print("HYDRAULIC THALWEG FLOW PATH: ARRIVAL TIME & DEPTH PROFILE")
    print(f"{'Location':<18} | {'Y (m)':<9} | {'Thalweg X (m)':<13} | {'Max Depth (m)':<13} | {'Arrival Time':<20} | {'Status'}")
    print("-" * 80)
    
    prev_arr = 0.0
    violations = 0
    thalweg_points = []
    
    for y in y_targets:
        r, _ = d_src.index(690000.0, y)
        row_depth = depth[r, :]
        row_arr = arrival[r, :]
        wet = np.where((row_depth > 0.5) & (row_arr > 0))[0]
        if len(wet) == 0:
            print(f"Y={y:.0f}: No wet cells")
            continue
        # Thalweg is the maximum depth cell on this river transect
        best_c = wet[np.argmax(row_depth[wet])]
        th_x, th_y = d_src.xy(r, best_c)
        th_d = row_depth[best_c]
        th_a = row_arr[best_c]
        
        status = "OK"
        if th_a < prev_arr:
            status = f"VIOLATION (-{prev_arr - th_a:.1f}s)"
            violations += 1
        prev_arr = th_a
        
        dist_from_dam = (y - 2518500.0) / 1000.0
        loc_label = f"+{dist_from_dam:4.1f}km"
        if dist_from_dam == 0:
            loc_label = "Dam Outlet"
        elif abs(y - 2524470) < 600:
            loc_label = "Morbi Reach"
        elif y > 2532000:
            loc_label = "Near Domain Exit"
            
        print(f"{loc_label:<18} | {y:<9.0f} | {th_x:<13.1f} | {th_d:<13.2f} | {th_a:7.1f}s ({th_a/60:5.1f}min) | {status}")
        thalweg_points.append({
            "y": float(y),
            "x": float(th_x),
            "dist_km": float(dist_from_dam),
            "max_depth_m": float(th_d),
            "arrival_time_s": float(th_a),
            "arrival_time_min": float(th_a / 60.0),
        })

    print("-" * 80)
    print(f"Total Monotonicity Violations along true hydraulic thalweg: {violations}")
