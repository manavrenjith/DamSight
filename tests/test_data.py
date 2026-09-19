"""Tests for data ingestion, grid alignment, terrain conditioning, and offline behaviour."""

import json
from pathlib import Path
import numpy as np
import pytest
import rasterio

from damsight.config import SiteConfig, load_site_config
from damsight.data.dem import (
    compute_void_cell_pct,
    fill_depressions_priority_flood,
)
from damsight.data.ingest import MissingDatasetError, generate_synthetic_raw_data, run_ingestion
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
            [10.0,  8.0,  8.0,  8.0, 10.0],
            [10.0,  8.0,  4.0,  8.0, 10.0],  # Center cell is a pit (4.0m, surrounding is 8.0m)
            [10.0,  8.0,  8.0,  8.0, 10.0],
            [10.0, 10.0,  6.0, 10.0, 10.0],  # (4, 2) is lowest boundary outlet (6.0m)
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
    report = run_ingestion(
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
    with rasterio.open(dem_path) as dem_src, \
         rasterio.open(lc_path) as lc_src, \
         rasterio.open(manning_path) as man_src, \
         rasterio.open(pop_path) as pop_src:

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
