"""Land cover ingestion and Manning's n roughness raster generation."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

logger = logging.getLogger(__name__)

DEFAULT_MANNING_LOOKUP_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "manning_lookup.csv"


def load_manning_lookup(csv_path: Optional[Path] = None) -> Dict[int, float]:
    """Load Manning n roughness lookup table from CSV.

    Format: class_code,description,manning_n,source,verified
    """
    path = csv_path or DEFAULT_MANNING_LOOKUP_PATH
    if not path.exists():
        # Fallback to standard WorldCover table if CSV missing
        return {
            10: 0.120,
            20: 0.070,
            30: 0.035,
            40: 0.040,
            50: 0.150,
            60: 0.030,
            70: 0.020,
            80: 0.025,
            90: 0.060,
            95: 0.140,
            100: 0.030,
        }

    lookup: Dict[int, float] = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                code = int(row["class_code"].strip())
                n_val = float(row["manning_n"].strip())
                lookup[code] = n_val
            except (ValueError, KeyError) as e:
                logger.warning(f"Error parsing Manning lookup row {row}: {e}")
    return lookup


def generate_landcover_and_manning(
    raw_lc_path: Path,
    out_lc_path: Path,
    out_manning_path: Path,
    dem_profile: Dict[str, Any],
    lookup_csv_path: Optional[Path] = None,
    default_manning: float = 0.040,
    nodata: float = -9999.0,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """Reproject land cover to match DEM grid and derive Manning's n raster."""
    out_lc_path.parent.mkdir(parents=True, exist_ok=True)
    out_manning_path.parent.mkdir(parents=True, exist_ok=True)

    height = dem_profile["height"]
    width = dem_profile["width"]
    target_crs = dem_profile["crs"]
    dst_transform = dem_profile["transform"]

    manning_table = load_manning_lookup(lookup_csv_path)

    # Reproject landcover to exact DEM grid using nearest neighbor
    lc_aligned = np.full((height, width), 0, dtype=np.uint8)

    with rasterio.open(raw_lc_path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=lc_aligned,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=target_crs,
            resampling=Resampling.nearest,
            dst_nodata=0,
        )

    # Save aligned landcover GeoTIFF
    lc_profile = dem_profile.copy()
    lc_profile.pop("blockxsize", None)
    lc_profile.pop("blockysize", None)
    lc_profile.pop("tiled", None)
    lc_profile.update({
        "count": 1,
        "dtype": "uint8",
        "nodata": 0,
        "compress": "deflate",
    })
    with rasterio.open(out_lc_path, "w", **lc_profile) as dst:
        dst.write(lc_aligned, 1)

    # Derive Manning n
    manning_grid = np.full((height, width), default_manning, dtype=np.float32)
    unmapped_count = 0

    unique_classes = np.unique(lc_aligned)
    for cls in unique_classes:
        cls_int = int(cls)
        mask = (lc_aligned == cls)
        if cls_int in manning_table:
            manning_grid[mask] = manning_table[cls_int]
        else:
            if cls_int != 0:
                unmapped_count += int(np.sum(mask))
            manning_grid[mask] = default_manning

    # Set cells where DEM is nodata to nodata as well
    manning_profile = dem_profile.copy()
    manning_profile.pop("blockxsize", None)
    manning_profile.pop("blockysize", None)
    manning_profile.pop("tiled", None)
    manning_profile.update({
        "count": 1,
        "dtype": "float32",
        "nodata": nodata,
        "compress": "deflate",
    })
    with rasterio.open(out_manning_path, "w", **manning_profile) as dst:
        dst.write(manning_grid, 1)

    stats = {
        "min_manning_n": round(float(np.min(manning_grid)), 4),
        "max_manning_n": round(float(np.max(manning_grid)), 4),
        "mean_manning_n": round(float(np.mean(manning_grid)), 4),
        "unmapped_cells": unmapped_count,
        "classes_present": [int(c) for c in unique_classes if int(c) != 0],
    }

    return lc_aligned, manning_grid, stats
