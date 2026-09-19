"""DEM ingestion, reprojection, void detection, and terrain conditioning."""

from __future__ import annotations

import heapq
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import calculate_default_transform, reproject

logger = logging.getLogger(__name__)


@dataclass
class TerrainChangeLog:
    """Record of a single terrain conditioning elevation adjustment."""

    row: int
    col: int
    original_z: float
    conditioned_z: float
    delta_z: float


@dataclass
class TerrainConditioningResult:
    """Summary and details of terrain conditioning."""

    cells_modified: int
    max_fill_m: float
    mean_fill_m: float
    total_volume_m3: float
    carving_applied: bool
    changes: list[TerrainChangeLog] = field(default_factory=list)


def fill_depressions_priority_flood(
    dem: np.ndarray,
    cell_size_m: float,
    max_fill_depth: float,
    nodata: float = -9999.0,
) -> tuple[np.ndarray, TerrainConditioningResult]:
    """Fill depressions in DEM using the Wang & Liu (2006) Priority-Flood algorithm.

    Guarantees monotonic drainage toward domain boundaries while preserving
    deep natural basins that exceed max_fill_depth. Logs every altered cell.
    """
    rows, cols = dem.shape
    filled = dem.copy()
    visited = np.zeros((rows, cols), dtype=bool)
    pq: list[tuple[float, int, int]] = []

    # Initialize priority queue with boundary cells (excluding nodata)
    for r in range(rows):
        for c in (0, cols - 1):
            if filled[r, c] != nodata and not np.isnan(filled[r, c]):
                heapq.heappush(pq, (float(filled[r, c]), r, c))
                visited[r, c] = True

    for c in range(cols):
        for r in (0, rows - 1):
            if not visited[r, c] and filled[r, c] != nodata and not np.isnan(filled[r, c]):
                heapq.heappush(pq, (float(filled[r, c]), r, c))
                visited[r, c] = True

    changes: list[TerrainChangeLog] = []

    # 8-connectivity offsets
    neighbors = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    while pq:
        elev, r, c = heapq.heappop(pq)

        for dr, dc in neighbors:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr, nc]:
                visited[nr, nc] = True
                neighbor_elev = float(filled[nr, nc])

                if neighbor_elev == nodata or np.isnan(neighbor_elev):
                    continue

                if neighbor_elev < elev:
                    fill_delta = elev - neighbor_elev
                    # Only fill if within physical threshold (avoid filling large natural canyons)
                    if fill_delta <= max_fill_depth:
                        new_elev = elev
                        change = TerrainChangeLog(
                            row=nr,
                            col=nc,
                            original_z=round(neighbor_elev, 4),
                            conditioned_z=round(new_elev, 4),
                            delta_z=round(fill_delta, 4),
                        )
                        changes.append(change)
                        filled[nr, nc] = new_elev
                        heapq.heappush(pq, (new_elev, nr, nc))
                    else:
                        heapq.heappush(pq, (neighbor_elev, nr, nc))
                else:
                    heapq.heappush(pq, (neighbor_elev, nr, nc))

    cells_mod = len(changes)
    deltas = [c.delta_z for c in changes] if changes else [0.0]
    max_fill = float(np.max(deltas)) if changes else 0.0
    mean_fill = float(np.mean(deltas)) if changes else 0.0
    cell_area = cell_size_m * cell_size_m
    total_vol = float(np.sum(deltas) * cell_area) if changes else 0.0

    result = TerrainConditioningResult(
        cells_modified=cells_mod,
        max_fill_m=round(max_fill, 4),
        mean_fill_m=round(mean_fill, 4),
        total_volume_m3=round(total_vol, 2),
        carving_applied=False,
        changes=changes,
    )
    return filled, result


def compute_void_cell_pct(arr: np.ndarray, nodata: float = -9999.0) -> float:
    """Calculate percentage of missing/nodata cells in raster."""
    total = arr.size
    if total == 0:
        return 0.0
    voids = np.sum((arr == nodata) | np.isnan(arr))
    return round(float(voids / total) * 100.0, 3)


def condition_and_save_dem(
    raw_dem_path: Path,
    out_dem_path: Path,
    target_crs: str,
    resolution_m: float,
    max_fill_depth: float,
    bbox: tuple[float, float, float, float] | None = None,
    nodata: float = -9999.0,
) -> tuple[np.ndarray, rasterio.Affine, TerrainConditioningResult, dict[str, Any]]:
    """Load DEM, reproject/resample to site grid, condition terrain sinks, and save."""
    out_dem_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(raw_dem_path) as src:
        # Reproject to target CRS and resample
        if bbox is not None and not any(isinstance(x, str) for x in bbox):
            # Projected bounds specified
            minx, miny, maxx, maxy = bbox
            width = max(1, round((maxx - minx) / resolution_m))
            height = max(1, round((maxy - miny) / resolution_m))
            dst_transform = from_bounds(minx, miny, maxx, maxy, width, height)
        else:
            transform, width, height = calculate_default_transform(
                src.crs, target_crs, src.width, src.height, *src.bounds, resolution=resolution_m
            )
            dst_transform = transform

        dst_array = np.full((height, width), nodata, dtype=np.float32)
        src_nodata = src.nodata if src.nodata is not None else nodata

        reproject(
            source=rasterio.band(src, 1),
            destination=dst_array,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=target_crs,
            resampling=Resampling.bilinear,
            src_nodata=src_nodata,
            dst_nodata=nodata,
        )

    # Detect void cells before conditioning
    void_pct = compute_void_cell_pct(dst_array, nodata=nodata)

    # Perform priority-flood depression filling
    conditioned, cond_result = fill_depressions_priority_flood(
        dst_array,
        cell_size_m=resolution_m,
        max_fill_depth=max_fill_depth,
        nodata=nodata,
    )

    # Write conditioned DEM to disk
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": target_crs,
        "transform": dst_transform,
        "nodata": nodata,
        "compress": "deflate",
    }

    with rasterio.open(out_dem_path, "w", **profile) as dst:
        dst.write(conditioned.astype(np.float32), 1)

    valid_mask = (conditioned != nodata) & (~np.isnan(conditioned))
    stats = {
        "min_elevation_m": (
            round(float(np.min(conditioned[valid_mask])), 2) if np.any(valid_mask) else 0.0
        ),
        "max_elevation_m": (
            round(float(np.max(conditioned[valid_mask])), 2) if np.any(valid_mask) else 0.0
        ),
        "mean_elevation_m": (
            round(float(np.mean(conditioned[valid_mask])), 2) if np.any(valid_mask) else 0.0
        ),
        "void_cell_pct": void_pct,
    }

    return conditioned, dst_transform, cond_result, stats
