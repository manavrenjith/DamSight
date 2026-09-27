import os
import sys
from pathlib import Path
gdal_data_path = Path(sys.prefix) / "Library" / "share" / "gdal"
if gdal_data_path.exists():
    os.environ["GDAL_DATA"] = str(gdal_data_path)

import rasterio
import numpy as np

with rasterio.open("outputs/site_a/max_depth.tif") as src, rasterio.open("outputs/site_a/arrival_time.tif") as arr_src:
    depth = src.read(1)
    arrival = arr_src.read(1)
    
    # Morbi anchor: 688605.56, 2524469.49
    r_morbi, c_morbi = src.index(688605.56, 2524469.49)
    print(f"Morbi cell (row={r_morbi}, col={c_morbi}): depth={depth[r_morbi, c_morbi]:.2f}m")
    
    # Check east-west transect across Morbi latitude (row r_morbi)
    row_depths = depth[r_morbi, :]
    row_arrs = arrival[r_morbi, :]
    wet_cols = np.where(row_depths > 0.1)[0]
    print(f"Wet columns across Morbi latitude (Y ~= 2524470): {len(wet_cols)}")
    for c in wet_cols:
        x, y = src.xy(r_morbi, c)
        print(f"  Col {c:3d} (X={x:.1f}): Depth = {row_depths[c]:5.2f} m, Arrival = {row_arrs[c]/60:6.1f} min ({row_arrs[c]:.1f} s)")

    # Find the maximum depth anywhere in Morbi city reach (within 2km of anchor)
    rows, cols = np.where(depth > 0.1)
    xs, ys = np.array(rasterio.transform.xy(src.transform, rows, cols))
    dists = np.sqrt((xs - 688605.56)**2 + (ys - 2524469.49)**2)
    morbi_2km_mask = dists <= 2000.0
    if np.any(morbi_2km_mask):
        m_depths = depth[rows[morbi_2km_mask], cols[morbi_2km_mask]]
        m_arrs = arrival[rows[morbi_2km_mask], cols[morbi_2km_mask]]
        max_idx = np.argmax(m_depths)
        print(f"\nMax depth in Morbi 2km radius: {m_depths[max_idx]:.2f} m (Arrival: {m_arrs[max_idx]/60:.1f} min)")
        print(f"Average wet depth in Morbi 2km radius: {np.mean(m_depths):.2f} m")
        print(f"Arrival time range in Morbi 2km radius: {np.min(m_arrs[m_arrs>0])/60:.1f} to {np.max(m_arrs)/60:.1f} min")
