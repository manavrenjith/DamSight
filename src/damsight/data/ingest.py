"""Master data ingestion pipeline coordinator for DamSight."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString, Point, Polygon

from damsight.config import SiteConfig, is_todo_value, load_site_config
from damsight.data.dem import condition_and_save_dem
from damsight.data.exposure import ingest_population, ingest_vector_exposure
from damsight.data.landcover import generate_landcover_and_manning

logger = logging.getLogger(__name__)


class MissingDatasetError(FileNotFoundError):
    """Raised when an input dataset is missing and cannot be downloaded offline."""


def generate_synthetic_raw_data(raw_dir: Path, target_crs: str = "EPSG:32643") -> dict[str, Path]:
    """Generate tiny synthetic raw datasets for offline testing and demonstration."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    # 1. Synthetic DEM (60x60 grid with slope and a small depression)
    dem_path = raw_dir / "raw_dem.tif"
    height, width = 60, 60
    res = 30.0
    # Center around UTM 43N coordinates (e.g. Morbi region approx 600,000m E, 2,500,000m N)
    x0, y0 = 600000.0, 2500000.0
    transform = from_origin(x0, y0 + height * res, res, res)

    # Base sloping terrain from 80m down to 40m
    x_coords = np.linspace(0, 1, width)
    y_coords = np.linspace(1, 0, height)
    xx, yy = np.meshgrid(x_coords, y_coords)
    dem_data = (80.0 - 40.0 * xx - 10.0 * yy).astype(np.float32)

    # Create artificial depressions to test terrain conditioning
    dem_data[25:28, 25:28] -= 4.5  # 4.5m deep sink
    # Add a single void / nodata cell
    dem_data[5, 5] = -9999.0

    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": target_crs,
        "transform": transform,
        "nodata": -9999.0,
    }
    with rasterio.open(dem_path, "w", **profile) as dst:
        dst.write(dem_data, 1)
    paths["dem"] = dem_path

    # 2. Synthetic Land Cover (ESA WorldCover classes: 30=grass, 40=crop, 50=urban, 80=water)
    lc_path = raw_dir / "raw_worldcover.tif"
    lc_data = np.full((height, width), 40, dtype=np.uint8)  # default cropland
    lc_data[10:20, 10:20] = 50  # urban settlement
    lc_data[28:32, :] = 80  # river channel
    lc_data[40:55, 40:55] = 30  # grassland
    lc_profile = profile.copy()
    lc_profile.update({"dtype": "uint8", "nodata": 255})
    with rasterio.open(lc_path, "w", **lc_profile) as dst:
        dst.write(lc_data, 1)
    paths["landcover"] = lc_path

    # 3. Synthetic WorldPop population raster
    pop_path = raw_dir / "raw_population.tif"
    pop_data = np.zeros((height, width), dtype=np.float32)
    pop_data[10:20, 10:20] = 15.5  # people per cell in urban patch
    pop_profile = profile.copy()
    pop_profile.update({"dtype": "float32", "nodata": -9999.0})
    with rasterio.open(pop_path, "w", **pop_profile) as dst:
        dst.write(pop_data, 1)
    paths["population"] = pop_path

    # 4. Synthetic OSM Roads
    roads_path = raw_dir / "raw_roads.geojson"
    road_geoms = [
        LineString([(x0 + 100, y0 + 100), (x0 + 1500, y0 + 1500)]),
        LineString([(x0 + 500, y0 + 1500), (x0 + 1500, y0 + 500)]),
    ]
    roads_gdf = gpd.GeoDataFrame(
        {
            "id": [1, 2],
            "name": ["Main Highway", "River Road"],
            "type": ["primary", "secondary"],
            "geometry": road_geoms,
        },
        crs=target_crs,
    )
    roads_gdf.to_file(roads_path, driver="GeoJSON")
    paths["roads"] = roads_path

    # 5. Synthetic OSM Buildings
    buildings_path = raw_dir / "raw_buildings.geojson"
    b_geoms = [
        Polygon(
            [
                (x0 + 350, y0 + 350),
                (x0 + 400, y0 + 350),
                (x0 + 400, y0 + 400),
                (x0 + 350, y0 + 400),
            ]
        ),
    ]
    buildings_gdf = gpd.GeoDataFrame(
        {
            "id": [101],
            "name": ["Town Hall"],
            "type": ["civic"],
            "geometry": b_geoms,
        },
        crs=target_crs,
    )
    buildings_gdf.to_file(buildings_path, driver="GeoJSON")
    paths["buildings"] = buildings_path

    # 6. Synthetic OSM Places (Villages)
    places_path = raw_dir / "raw_places.geojson"
    place_geoms = [
        Point(x0 + 450, y0 + 450),
        Point(x0 + 1200, y0 + 800),
    ]
    places_gdf = gpd.GeoDataFrame(
        {
            "id": [201, 202],
            "name": ["Village Alpha", "Village Beta"],
            "type": ["village", "hamlet"],
            "population": [1200, 450],
            "geometry": place_geoms,
        },
        crs=target_crs,
    )
    places_gdf.to_file(places_path, driver="GeoJSON")
    paths["places"] = places_path

    return paths


def run_ingestion(
    site: SiteConfig | Path | str,
    cache_root: Path | None = None,
    allow_synthetic_fallback: bool = False,
    lookup_csv_path: Path | None = None,
) -> dict[str, Any]:
    """Execute complete ingestion pipeline for a site.

    Produces aligned rasters, vector layers, and report.json.
    """
    if isinstance(site, (str, Path)):
        config = load_site_config(site)
    else:
        config = site

    site_id = config.site_id
    if is_todo_value(config.crs):
        if allow_synthetic_fallback:
            target_crs = "EPSG:32643"  # UTM 43N demo reach default
            logger.warning(
                f"Site CRS is unverified ('{config.crs}'). Using fallback CRS '{target_crs}'."
            )
        else:
            raise MissingDatasetError(
                f"Site CRS is unverified ('{config.crs}'). Please specify a valid projected CRS in site config."
            )
    else:
        target_crs = config.crs

    res_m = config.solver.mesh_resolution_m

    base_cache = cache_root or (Path(__file__).resolve().parent.parent.parent.parent / "cache")
    site_cache = base_cache / site_id
    site_cache.mkdir(parents=True, exist_ok=True)
    raw_dir = site_cache / "raw"

    # Determine input sources or check offline availability
    dem_raw_path = (
        Path(config.inputs.dem.path) if config.inputs.dem.path else raw_dir / "raw_dem.tif"
    )
    lc_raw_path = raw_dir / "raw_worldcover.tif"
    pop_raw_path = raw_dir / "raw_population.tif"
    roads_raw_path = raw_dir / "raw_roads.geojson"
    buildings_raw_path = raw_dir / "raw_buildings.geojson"
    places_raw_path = raw_dir / "raw_places.geojson"

    # Offline check: if raw files do not exist
    if not dem_raw_path.exists():
        if allow_synthetic_fallback:
            logger.info(f"Raw inputs missing for {site_id}. Generating synthetic baseline.")
            synth_paths = generate_synthetic_raw_data(raw_dir, target_crs=target_crs)
            dem_raw_path = synth_paths["dem"]
            lc_raw_path = synth_paths["landcover"]
            pop_raw_path = synth_paths["population"]
            roads_raw_path = synth_paths["roads"]
            buildings_raw_path = synth_paths["buildings"]
            places_raw_path = synth_paths["places"]
        else:
            raise MissingDatasetError(
                f"Missing DEM dataset for site '{site_id}'. Offline mode active. "
                f"Please place the GeoTIFF DEM file at: '{dem_raw_path}' "
                f"(Source specified: {config.inputs.dem.source})."
            )

    # 1. Condition DEM and establish master grid profile
    out_dem = site_cache / "dem.tif"
    _dem_arr, _dem_transform, cond_result, elev_stats = condition_and_save_dem(
        raw_dem_path=dem_raw_path,
        out_dem_path=out_dem,
        target_crs=target_crs,
        resolution_m=res_m,
        max_fill_depth=15.0,
    )

    with rasterio.open(out_dem) as src:
        master_profile = src.profile.copy()
        bounds = list(src.bounds)

    # 2. Ingest Land Cover and derive Manning's n
    out_lc = site_cache / "landcover.tif"
    out_manning = site_cache / "manning_n.tif"
    if not lc_raw_path.exists():
        if allow_synthetic_fallback:
            generate_synthetic_raw_data(raw_dir, target_crs=target_crs)
        else:
            raise MissingDatasetError(
                f"Missing ESA WorldCover dataset for site '{site_id}'. "
                f"Please place landcover GeoTIFF at: '{lc_raw_path}'."
            )

    _lc_arr, _manning_arr, manning_stats = generate_landcover_and_manning(
        raw_lc_path=lc_raw_path,
        out_lc_path=out_lc,
        out_manning_path=out_manning,
        dem_profile=master_profile,
        default_manning=0.040,
        lookup_csv_path=lookup_csv_path,
    )

    # 3. Ingest Population raster
    out_pop = site_cache / "population.tif"
    if pop_raw_path.exists():
        _, pop_stats = ingest_population(
            raw_pop_path=pop_raw_path,
            out_pop_path=out_pop,
            dem_profile=master_profile,
        )
    else:
        pop_stats = {"total_population": 0.0, "status": "not_provided"}

    # 4. Ingest Vector Exposures (Roads, Buildings, Places)
    out_roads = site_cache / "roads.geojson"
    out_buildings = site_cache / "buildings.geojson"
    out_places = site_cache / "places.geojson"

    roads_stat = ingest_vector_exposure(
        roads_raw_path if roads_raw_path.exists() else None, out_roads, target_crs
    )
    buildings_stat = ingest_vector_exposure(
        buildings_raw_path if buildings_raw_path.exists() else None, out_buildings, target_crs
    )
    places_stat = ingest_vector_exposure(
        places_raw_path if places_raw_path.exists() else None, out_places, target_crs
    )

    # 5. Compile report.json
    report: dict[str, Any] = {
        "site_id": site_id,
        "data_status": (
            "unverified"
            if (not config.is_fully_verified or allow_synthetic_fallback)
            else config.data_status.dam_parameters
        ),
        "crs": target_crs,
        "resolution_m": res_m,
        "grid_shape": [int(master_profile["height"]), int(master_profile["width"])],
        "bounds": [round(b, 2) for b in bounds],
        "void_cell_pct": elev_stats["void_cell_pct"],
        "elevation_stats": elev_stats,
        "terrain_conditioning": {
            "cells_modified": cond_result.cells_modified,
            "max_fill_m": cond_result.max_fill_m,
            "mean_fill_m": cond_result.mean_fill_m,
            "total_volume_m3": cond_result.total_volume_m3,
            "carving_applied": cond_result.carving_applied,
            "sample_changes": [asdict(c) for c in cond_result.changes[:10]],
        },
        "manning_stats": manning_stats,
        "population_stats": pop_stats,
        "exposure_counts": {
            "roads": roads_stat["count"],
            "buildings": buildings_stat["count"],
            "places": places_stat["count"],
        },
        "datasets_status": {
            "dem": {"status": "ingested", "source": config.inputs.dem.source, "file": str(out_dem)},
            "landcover": {
                "status": "ingested",
                "source": config.inputs.landcover,
                "file": str(out_lc),
            },
            "manning_n": {
                "status": "derived",
                "source": "manning_lookup.csv",
                "file": str(out_manning),
            },
            "population": {
                "status": "ingested" if pop_raw_path.exists() else "empty",
                "file": str(out_pop),
            },
            "roads": {"status": "ingested", "file": str(out_roads)},
            "buildings": {"status": "ingested", "file": str(out_buildings)},
            "places": {"status": "ingested", "file": str(out_places)},
        },
    }

    report_path = site_cache / "report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Ingestion complete for {site_id}. Report saved to {report_path}")
    return report
