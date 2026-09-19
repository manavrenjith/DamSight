"""Tests for v2 configuration schema validation, TODO_VERIFY handling, and error cases."""

import warnings
from pathlib import Path
import pytest
from pydantic import ValidationError

from damsight.config import SiteConfig, UnverifiedValueWarning, load_site_config


@pytest.fixture
def valid_v2_verified_config_dict():
    """A fully verified v2 configuration dictionary with concrete numeric values."""
    return {
        "site_id": "site_verified",
        "name": "Machhu-I / Machhu-II Chain (Verified Dataset)",
        "type": "cascade",
        "data_status": {
            "dam_parameters": "verified",
        },
        "crs": "EPSG:32643",
        "aoi": {
            "bbox": [70.85, 22.75, 71.05, 22.95],
        },
        "dams": [
            {
                "id": "machhu_1",
                "role": "upstream",
                "location": [70.85, 22.72],
                "crest_elevation_m": 85.0,
                "dam_height_m": 28.0,
                "reservoir_volume_m3": 85000000.0,
                "stage_storage_csv": "data/site_verified/machhu1_stage_storage.csv",
                "dam_type": "embankment",
                "source": "India-WRIS",
                "verified": True,
            },
            {
                "id": "machhu_2",
                "role": "downstream",
                "location": [70.89, 22.78],
                "crest_elevation_m": 60.5,
                "dam_height_m": 24.3,
                "reservoir_volume_m3": 110000000.0,
                "stage_storage_csv": "data/site_verified/machhu2_stage_storage.csv",
                "dam_type": "embankment",
                "spillway_capacity_m3s": 6100.0,
                "breach_types": ["overtopping", "piping"],
                "source": "India-WRIS / National Register of Large Dams",
                "verified": True,
            },
        ],
        "scenarios": [
            {
                "id": "A1_hindcast_1979",
                "kind": "hindcast",
                "breach_dam": "machhu_2",
                "breach_type": "overtopping",
            },
            {
                "id": "A2_cascade_whatif",
                "kind": "hypothetical",
                "upstream_release_from": "machhu_1",
            },
        ],
        "inputs": {
            "dem": {
                "source": "copernicus_30m",
                "path": None,
            },
            "landcover": "esa_worldcover",
            "population": "worldpop",
            "buildings": "osm",
            "roads": "osm",
        },
        "reference_events": [
            {
                "name": "1979 Failure Extent",
                "type": "historical",
                "extent": "data/site_verified/reference_extent.geojson",
                "source": "CWC Historical Report 1980",
            }
        ],
        "solver": {
            "far_field": "delft3dfm",
            "baseline": "anuga",
            "near_field": "none",
            "mesh_resolution_m": 30.0,
        },
        "ensemble": {
            "n_members": 100,
            "parameters": {
                "breach_width": {"sigma_ln": 0.3},
                "formation_time": {"sigma_ln": 0.4},
                "peak_outflow": {"sigma_ln": 0.3},
                "reservoir_level_m": {"range": [55.0, 61.0]},
            },
        },
        "evacuation": {
            "walking_speed_kmh": 4.0,
            "vehicle_speed_kmh": 30.0,
            "road_closure_depth_m": 0.3,
            "safety_margin_min": 10.0,
        },
    }


def test_valid_v2_verified_config_passes_cleanly(valid_v2_verified_config_dict):
    """Test that a fully verified valid v2 configuration passes without emitting UnverifiedValueWarning."""
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        config = load_site_config(valid_v2_verified_config_dict)

        unverified_warnings = [
            w for w in recorded_warnings if issubclass(w.category, UnverifiedValueWarning)
        ]
        assert len(unverified_warnings) == 0, f"Expected 0 warnings, got: {unverified_warnings}"

    assert config.site_id == "site_verified"
    assert config.type == "cascade"
    assert len(config.dams) == 2
    # Verify backwards-compatible primary dam accessor points to breach dam (machhu_2)
    assert config.dam.id == "machhu_2"
    assert config.dam.dam_height_m == 24.3
    assert config.solver.baseline == "anuga"
    assert config.is_fully_verified is True
    assert len(config.get_unverified_fields()) == 0


def test_site_a_yaml_loads_and_emits_todo_verify_warnings():
    """Test that configs/sites/site_a.yaml loads in v2 and emits UnverifiedValueWarning for TODOs."""
    yaml_path = Path(__file__).resolve().parent.parent / "configs" / "sites" / "site_a.yaml"
    assert yaml_path.exists(), f"Configuration file {yaml_path} does not exist"

    with pytest.warns(UnverifiedValueWarning) as warning_records:
        config = load_site_config(yaml_path)

    # Verify site config object was successfully constructed
    assert config.site_id == "site_a"
    assert config.type == "cascade"
    assert len(config.dams) == 2
    assert config.dams[0].id == "machhu_1"
    assert config.dams[1].id == "machhu_2"
    assert config.dams[1].dam_height_m == "TODO_VERIFY"
    assert config.crs == "TODO_VERIFY"
    assert config.is_fully_verified is False

    # Check that warnings were surfaced for multiple unverified fields
    warning_messages = [str(w.message) for w in warning_records]
    assert any("Site CRS is unverified" in msg for msg in warning_messages)
    assert any("dam_height_m" in msg for msg in warning_messages)
    assert any("reservoir_volume_m3" in msg for msg in warning_messages)


def test_per_value_verified_false_emits_warning(valid_v2_verified_config_dict):
    """Test that setting verified=False in a per-value dict surfaces an UnverifiedValueWarning."""
    valid_v2_verified_config_dict["dams"][1]["dam_height_m"] = {
        "value": 24.3,
        "source": "Unconfirmed local report",
        "verified": False,
    }
    with pytest.warns(UnverifiedValueWarning, match="marked verified=false"):
        config = load_site_config(valid_v2_verified_config_dict)

    assert config.dams[1].dam_height_m == 24.3


def test_data_status_defaulted_allowed(valid_v2_verified_config_dict):
    """Test that data_status allows 'defaulted' badge per v2 specification."""
    valid_v2_verified_config_dict["data_status"]["dam_parameters"] = "defaulted"
    config = load_site_config(valid_v2_verified_config_dict)
    assert config.data_status.dam_parameters == "defaulted"


def test_missing_required_field_dams_fails(valid_v2_verified_config_dict):
    """Test that omitting required 'dams' list raises ValidationError."""
    del valid_v2_verified_config_dict["dams"]
    with pytest.raises(ValidationError) as exc_info:
        load_site_config(valid_v2_verified_config_dict)
    assert "dams" in str(exc_info.value)


def test_missing_dam_height_in_dam_item_fails(valid_v2_verified_config_dict):
    """Test that omitting required dam_height_m in a dam item raises ValidationError."""
    del valid_v2_verified_config_dict["dams"][0]["dam_height_m"]
    with pytest.raises(ValidationError) as exc_info:
        load_site_config(valid_v2_verified_config_dict)
    assert "dam_height_m" in str(exc_info.value)


def test_extra_forbidden_field_fails(valid_v2_verified_config_dict):
    """Test that unexpected extra fields are forbidden by the schema."""
    valid_v2_verified_config_dict["unexpected_custom_key"] = "illegal"
    with pytest.raises(ValidationError) as exc_info:
        load_site_config(valid_v2_verified_config_dict)
    assert "unexpected_custom_key" in str(exc_info.value)
