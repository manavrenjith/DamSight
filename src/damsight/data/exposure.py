"""Population (WorldPop) and Infrastructure (OSM) exposure ingestion."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

logger = logging.getLogger(__name__)


def compute_raster_cell_area_m2(
    crs: Any,
    transform: rasterio.Affine,
    shape: tuple[int, int],
) -> np.ndarray:
    """Compute per-cell ground area in square meters for projected or geographic grids."""
    rows, cols = shape
    is_geo = getattr(crs, "is_geographic", False) if crs else False
    if not is_geo and crs is not None:
        crs_str = str(crs).upper()
        if "4326" in crs_str or "WGS 84" in crs_str or "CRS84" in crs_str:
            is_geo = True

    dx = abs(transform[0])
    dy = abs(transform[4])

    if is_geo:
        # WGS-84 reference ellipsoid approx meters per degree
        row_indices = np.arange(rows)
        center_lats = transform[3] + (row_indices + 0.5) * transform[4]
        m_per_deg_lat = 111132.92
        m_per_deg_lon = 111412.84 * np.cos(np.radians(center_lats))
        row_areas = (dx * m_per_deg_lon) * (dy * m_per_deg_lat)
        return np.repeat(row_areas[:, np.newaxis], cols, axis=1).astype(np.float32)
    else:
        area = float(dx * dy)
        return np.full((rows, cols), area, dtype=np.float32)


def ingest_population(
    raw_pop_path: Path,
    out_pop_path: Path,
    dem_profile: dict[str, Any],
    nodata: float = -9999.0,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Reproject WorldPop population raster to match DEM grid while conserving absolute count.

    WorldPop rasters store population COUNT per cell (an extensive quantity), not density.
    Reprojecting count directly with standard interpolators (e.g. bilinear) scales the domain sum
    by the area ratio of the grids (e.g. inflating 1km to 30m by ~1111x).

    This function converts source counts to ground density (persons / m²), reprojects density
    to the target DEM grid, and integrates density back into counts per destination cell
    (count = density * dst_cell_area_m2), exactly conserving population count.
    """
    out_pop_path.parent.mkdir(parents=True, exist_ok=True)

    height = dem_profile["height"]
    width = dem_profile["width"]
    target_crs = dem_profile["crs"]
    dst_transform = dem_profile["transform"]

    pop_aligned = np.full((height, width), nodata, dtype=np.float32)

    with rasterio.open(raw_pop_path) as src:
        src_data = src.read(1)
        src_nodata = src.nodata if src.nodata is not None else nodata

        # Calculate source and destination cell areas in m²
        src_areas = compute_raster_cell_area_m2(src.crs, src.transform, (src.height, src.width))
        dst_areas = compute_raster_cell_area_m2(target_crs, dst_transform, (height, width))

        # Convert source counts to population density (persons / m²)
        valid_src = (src_data != src_nodata) & (~np.isnan(src_data))
        density_src = np.full_like(src_data, src_nodata, dtype=np.float32)
        density_src[valid_src] = src_data[valid_src] / src_areas[valid_src]

        density_aligned = np.full((height, width), nodata, dtype=np.float32)
        reproject(
            source=density_src,
            destination=density_aligned,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=target_crs,
            resampling=Resampling.bilinear,
            src_nodata=src_nodata,
            dst_nodata=nodata,
        )

    # Convert destination density back to population counts per cell
    valid_mask = (density_aligned != nodata) & (~np.isnan(density_aligned))
    # Eliminate negative interpolation artifacts only on valid cells; keep zeros and nodata distinct
    pop_aligned[valid_mask] = np.clip(
        density_aligned[valid_mask] * dst_areas[valid_mask], 0.0, None
    )

    pop_profile = dem_profile.copy()
    pop_profile.pop("blockxsize", None)
    pop_profile.pop("blockysize", None)
    pop_profile.pop("tiled", None)
    pop_profile.update(
        {
            "count": 1,
            "dtype": "float32",
            "nodata": nodata,
            "compress": "deflate",
        }
    )
    with rasterio.open(out_pop_path, "w", **pop_profile) as dst:
        dst.write(pop_aligned, 1)

    total_pop = float(np.sum(pop_aligned[valid_mask])) if np.any(valid_mask) else 0.0
    max_pop = float(np.max(pop_aligned[valid_mask])) if np.any(valid_mask) else 0.0
    stats = {
        "total_population": round(total_pop, 1),
        "max_cell_population": round(max_pop, 4),
        "void_cells": int(np.sum(~valid_mask)),
    }
    return pop_aligned, stats


def ingest_vector_exposure(
    raw_path: Path | None,
    out_path: Path,
    target_crs: str,
    default_geometry_type: str = "LineString",
    bbox: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
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
        gdf = gpd.GeoDataFrame(
            columns=["id", "name", "type", "geometry"], geometry="geometry", crs=target_crs
        )

    gdf.to_file(out_path, driver="GeoJSON")
    return {
        "count": len(gdf),
        "output_path": str(out_path),
    }
