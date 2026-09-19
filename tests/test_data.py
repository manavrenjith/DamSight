"""Tests for data ingestion, grid alignment, terrain conditioning, and offline behaviour."""

import json

import numpy as np
import pytest
import rasterio

from damsight.config import SiteConfig
from damsight.data.dem import (
    compute_void_cell_pct,
    fill_depressions_priority_flood,
)
from damsight.data.ingest import MissingDatasetError, run_ingestion
from damsight.data.landcover import load_manning_lookup


@pytest.fixture
def synthetic_site_config(tmp_path):
    """Create a minimal valid SiteConfig targeting a temporary directory."""
    raw_dict = {
        "site_id": "test_site",
        "name": "Test Site Reach",
        "type": "dam",
        "data_status": {"dam_parameters": "synthetic"},
        "crs": "EPSG:32643",
        "aoi": {"bbox": [600000.0, 2500000.0, 601800.0, 2501800.0]},
        "dams": [
            {
                "id": "dam_1",
                "role": "single",
                "location": [600500.0, 2501000.0],
                "crest_elevation_m": 75.0,
                "dam_height_m": 25.0,
                "reservoir_volume_m3": 5000000.0,
                "stage_storage_csv": None,
                "dam_type": "embankment",
                "breach_types": ["overtopping", "piping"],
                "source": "Synthetic fixture",
            }
        ],
        "scenarios": [
            {
                "id": "scenario_1",
                "kind": "hindcast",
                "breach_dam": "dam_1",
                "breach_type": "overtopping",
            }
        ],
        "inputs": {
            "dem": {"source": "copernicus_30m", "path": None},
            "landcover": "esa_worldcover",
            "population": "worldpop",
            "buildings": "osm",
            "roads": "osm",
        },
        "reference_events": [],
        "solver": {
            "far_field": "delft3dfm",
            "baseline": "anuga",
            "near_field": "none",
            "mesh_resolution_m": 30.0,
        },
        "ensemble": {
            "n_members": 50,
            "parameters": {
                "breach_width": {"sigma_ln": 0.3},
                "formation_time": {"sigma_ln": 0.4},
                "peak_outflow": {"sigma_ln": 0.3},
                "reservoir_level_m": {"range": [65.0, 75.0]},
            },
        },
        "evacuation": {
            "walking_speed_kmh": 4.0,
            "vehicle_speed_kmh": 30.0,
            "road_closure_depth_m": 0.3,
            "safety_margin_min": 10.0,
        },
    }
    return SiteConfig.model_validate(raw_dict)


def test_priority_flood_depression_filling():
    """Test priority-flood depression filling on a small synthetic DEM with known pit."""
    # 5x5 DEM with sloping boundary and an isolated depression at (2, 2)
    dem = np.array(
        [
            [10.0, 10.0, 10.0, 10.0, 10.0],
            [10.0, 8.0, 8.0, 8.0, 10.0],
            [10.0, 8.0, 4.0, 8.0, 10.0],  # Center cell is a pit (4.0m, surrounding is 8.0m)
            [10.0, 8.0, 8.0, 8.0, 10.0],
            [10.0, 10.0, 6.0, 10.0, 10.0],  # (4, 2) is lowest boundary outlet (6.0m)
        ],
        dtype=np.float32,
    )

    filled, result = fill_depressions_priority_flood(dem, cell_size_m=10.0, max_fill_depth=10.0)

    # Pit at (2, 2) should be filled up to 8.0m (its lowest spillway neighbor)
    assert filled[2, 2] == 8.0
    assert result.cells_modified >= 1
    assert result.max_fill_m == 4.0
    assert len(result.changes) >= 1
    assert any(c.row == 2 and c.col == 2 and c.delta_z == 4.0 for c in result.changes)


def test_compute_void_cell_pct():
    """Test void cell percentage calculation."""
    arr = np.array([[1.0, 2.0], [-9999.0, np.nan]], dtype=np.float32)
    void_pct = compute_void_cell_pct(arr, nodata=-9999.0)
    assert void_pct == 50.0


def test_manning_lookup_table():
    """Test loading Manning's n lookup table."""
    lookup = load_manning_lookup()
    assert 10 in lookup  # Tree cover
    assert lookup[10] == 0.120
    assert lookup[50] == 0.150  # Built-up
    assert lookup[80] == 0.025  # Water bodies


def test_offline_missing_dataset_raises_error(synthetic_site_config, tmp_path):
    """Test offline behavior: missing raw files raise MissingDatasetError with actionable message."""
    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    with pytest.raises(MissingDatasetError) as exc_info:
        run_ingestion(
            site=synthetic_site_config,
            cache_root=cache_root,
            allow_synthetic_fallback=False,
        )

    msg = str(exc_info.value)
    assert "Missing DEM dataset" in msg
    assert "Offline mode active" in msg
    assert "Please place" in msg


def test_ingestion_grid_alignment_and_report(synthetic_site_config, tmp_path):
    """Test full ingestion pipeline with synthetic data, checking raster alignment and report.json."""
    cache_root = tmp_path / "cache"
    _report = run_ingestion(
        site=synthetic_site_config,
        cache_root=cache_root,
        allow_synthetic_fallback=True,
    )

    site_cache = cache_root / synthetic_site_config.site_id
    dem_path = site_cache / "dem.tif"
    lc_path = site_cache / "landcover.tif"
    manning_path = site_cache / "manning_n.tif"
    pop_path = site_cache / "population.tif"
    report_path = site_cache / "report.json"

    assert dem_path.exists()
    assert lc_path.exists()
    assert manning_path.exists()
    assert pop_path.exists()
    assert report_path.exists()

    # Verify identical raster geometry and CRS
    with (
        rasterio.open(dem_path) as dem_src,
        rasterio.open(lc_path) as lc_src,
        rasterio.open(manning_path) as man_src,
        rasterio.open(pop_path) as pop_src,
    ):

        # Check CRS
        assert dem_src.crs.to_string() == synthetic_site_config.crs
        assert lc_src.crs.to_string() == synthetic_site_config.crs
        assert man_src.crs.to_string() == synthetic_site_config.crs
        assert pop_src.crs.to_string() == synthetic_site_config.crs

        # Check Shape (Height, Width)
        assert dem_src.shape == lc_src.shape
        assert dem_src.shape == man_src.shape
        assert dem_src.shape == pop_src.shape

        # Check Affine Transform & Resolution
        assert dem_src.transform == lc_src.transform
        assert dem_src.transform == man_src.transform
        assert dem_src.transform == pop_src.transform
        assert dem_src.res == (30.0, 30.0)

        # Check Bounds
        assert dem_src.bounds == lc_src.bounds
        assert dem_src.bounds == man_src.bounds

    # Check report.json contents
    with open(report_path, "r", encoding="utf-8") as f:
        rep = json.load(f)

    assert rep["site_id"] == "test_site"
    assert rep["crs"] == "EPSG:32643"
    assert rep["resolution_m"] == 30.0
    assert "void_cell_pct" in rep
    assert "terrain_conditioning" in rep
    assert rep["terrain_conditioning"]["cells_modified"] >= 0
    assert "manning_stats" in rep
    assert "datasets_status" in rep


def test_population_zeros_preserved_and_exact_void_count(tmp_path):
    """Test that source raster carrying its own nodata (-99999.0) plus valid zeros (0.0) is correctly reprojected:
    voids (-99999.0) -> dst_nodata (-9999.0), valid zeros (0.0) preserved without corruption.

    On m2-candidate exposure.py (dst_nodata=0.0, no src_nodata), voids were turned into 0.0,
    causing assert np.sum(aligned == -9999.0) == 20 to fail by assertion (got 0 != 20).
    """
    from damsight.data.exposure import ingest_population

    raw_pop_path = tmp_path / "raw_pop.tif"
    out_pop_path = tmp_path / "aligned_pop.tif"

    # 10x10 raster: 50 populated cells (10.0), 30 valid zeros (0.0), 20 real voids (-99999.0)
    data = np.full((10, 10), 10.0, dtype=np.float32)
    data[0:3, :] = 0.0  # 30 cells of valid zero population
    data[8:10, :] = -99999.0  # 20 cells of real voids in source

    transform = rasterio.transform.from_origin(600000.0, 2501800.0, 30.0, 30.0)
    raw_profile = {
        "driver": "GTiff",
        "count": 1,
        "dtype": "float32",
        "width": 10,
        "height": 10,
        "crs": "EPSG:32643",
        "transform": transform,
        "nodata": -99999.0,  # Source raster carries -99999.0 nodata
    }
    with rasterio.open(raw_pop_path, "w", **raw_profile) as dst:
        dst.write(data, 1)

    dem_profile = {
        "driver": "GTiff",
        "count": 1,
        "dtype": "float32",
        "width": 10,
        "height": 10,
        "crs": "EPSG:32643",
        "transform": transform,
        "nodata": -9999.0,  # Destination DEM grid carries -9999.0 nodata
    }

    aligned, stats = ingest_population(
        raw_pop_path=raw_pop_path,
        out_pop_path=out_pop_path,
        dem_profile=dem_profile,
        nodata=-9999.0,
    )

    # Check valid zeros preserved
    valid_zero_count = int(np.sum(aligned == 0.0))
    assert valid_zero_count == 30, f"Expected 30 valid zeros preserved, got {valid_zero_count}"

    # Check source voids (-99999.0) mapped to destination nodata (-9999.0)
    void_count = int(np.sum(aligned == -9999.0))
    assert void_count == 20, f"Expected 20 real voids (-9999.0), got {void_count}"
    assert stats["void_cells"] == 20

    # Check void percentage is 20.0%
    void_pct = (void_count / aligned.size) * 100.0
    assert void_pct == 20.0

    # Verify no GDAL 1.4013e-45 corruption
    assert not np.any((aligned > 0.0) & (aligned < 1e-30))
