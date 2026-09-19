"""Population (WorldPop) and Infrastructure (OSM) exposure ingestion."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

logger = logging.getLogger(__name__)


def ingest_population(
    raw_pop_path: Path,
    out_pop_path: Path,
    dem_profile: Dict[str, Any],
    nodata: float = -9999.0,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Reproject WorldPop population raster to match DEM grid."""
    out_pop_path.parent.mkdir(parents=True, exist_ok=True)

    height = dem_profile["height"]
    width = dem_profile["width"]
    target_crs = dem_profile["crs"]
    dst_transform = dem_profile["transform"]

    pop_aligned = np.full((height, width), 0.0, dtype=np.float32)

    with rasterio.open(raw_pop_path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=pop_aligned,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=target_crs,
            resampling=Resampling.bilinear,
            dst_nodata=0.0,
        )

    # Ensure negative artifacts from bilinear interpolation are eliminated
    pop_aligned = np.clip(pop_aligned, 0.0, None)

    pop_profile = dem_profile.copy()
    pop_profile.pop("blockxsize", None)
    pop_profile.pop("blockysize", None)
    pop_profile.pop("tiled", None)
    pop_profile.update({
        "count": 1,
        "dtype": "float32",
        "nodata": nodata,
        "compress": "deflate",
    })
    with rasterio.open(out_pop_path, "w", **pop_profile) as dst:
        dst.write(pop_aligned, 1)

    total_pop = float(np.sum(pop_aligned))
    stats = {
        "total_population": round(total_pop, 1),
        "max_cell_population": round(float(np.max(pop_aligned)), 1),
    }
    return pop_aligned, stats


def ingest_vector_exposure(
    raw_path: Optional[Path],
    out_path: Path,
    target_crs: str,
    default_geometry_type: str = "LineString",
    bbox: Optional[Tuple[float, float, float, float]] = None,
) -> Dict[str, Any]:
    """Load or transform vector exposure data (roads, buildings, places) to site CRS and save GeoJSON."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if raw_path is not None and raw_path.exists():
        gdf = gpd.read_file(raw_path)
        if gdf.crs != target_crs:
            gdf = gdf.to_crs(target_crs)
        if bbox is not None and len(bbox) == 4 and not any(isinstance(x, str) for x in bbox):
            minx, miny, maxx, maxy = bbox
            gdf = gdf.cx[minx:maxx, miny:maxy]
    else:
        # Create valid empty GeoDataFrame with correct schema
        gdf = gpd.GeoDataFrame(columns=["id", "name", "type", "geometry"], geometry="geometry", crs=target_crs)

    gdf.to_file(out_path, driver="GeoJSON")
    return {
        "count": len(gdf),
        "output_path": str(out_path),
    }
