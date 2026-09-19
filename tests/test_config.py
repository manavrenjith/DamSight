"""Tests for configuration schema validation, TODO_VERIFY handling, and error cases."""

import warnings
from pathlib import Path
import pytest
from pydantic import ValidationError

from damsight.config import SiteConfig, UnverifiedValueWarning, load_site_config


@pytest.fixture
def valid_verified_config_dict():
    """A fully verified configuration dictionary with concrete numeric values."""
    return {
        "site_id": "site_verified",
        "name": "Machhu-II Dam (Verified Dataset)",
        "type": "dam",
        "data_status": {
            "dam_parameters": "verified",
        },
        "crs": "EPSG:32643",
        "aoi": {
            "bbox": [70.85, 22.75, 71.05, 22.95],
        },
        "dam": {
            "location": [70.89, 22.78],
            "crest_elevation_m": 60.5,
            "dam_height_m": 24.3,
            "reservoir_volume_m3": 110000000.0,
            "stage_storage_csv": "data/site_verified/stage_storage.csv",
            "breach_types": ["overtopping", "piping"],
            "source": "India-WRIS / National Register of Large Dams",
        },
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
                "extent": "data/site_verified/reference_extent.geojson",
                "source": "CWC Historical Report 1980",
            }
        ],
        "solver": {
            "far_field": "anuga",
            "near_field": "none",
            "mesh_resolution_m": 30.0,
        },
        "ensemble": {
            "n_members": 200,
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


def test_valid_verified_config_passes_cleanly(valid_verified_config_dict):
    """Test that a fully verified valid configuration passes without emitting UnverifiedValueWarning."""
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        config = load_site_config(valid_verified_config_dict)

        unverified_warnings = [
            w for w in recorded_warnings if issubclass(w.category, UnverifiedValueWarning)
        ]
        assert len(unverified_warnings) == 0, f"Expected 0 warnings, got: {unverified_warnings}"

    assert config.site_id == "site_verified"
    assert config.dam.dam_height_m == 24.3
    assert config.dam.crest_elevation_m == 60.5
    assert config.is_fully_verified is True
    assert len(config.get_unverified_fields()) == 0


def test_site_a_yaml_loads_and_emits_todo_verify_warnings():
    """Test that configs/sites/site_a.yaml loads properly and emits UnverifiedValueWarning for TODOs."""
    yaml_path = Path(__file__).resolve().parent.parent / "configs" / "sites" / "site_a.yaml"
    assert yaml_path.exists(), f"Configuration file {yaml_path} does not exist"

    with pytest.warns(UnverifiedValueWarning) as warning_records:
        config = load_site_config(yaml_path)

    # Verify site config object was successfully constructed
    assert config.site_id == "site_a"
    assert config.dam.dam_height_m == "TODO_VERIFY"
    assert config.dam.crest_elevation_m == "TODO_VERIFY"
    assert config.dam.reservoir_volume_m3 == "TODO_VERIFY"
    assert config.is_fully_verified is False

    # Check that warnings were surfaced for multiple unverified fields
    warning_messages = [str(w.message) for w in warning_records]
    assert any("dam.dam_height_m" in msg for msg in warning_messages)
    assert any("dam.crest_elevation_m" in msg for msg in warning_messages)
    assert any("dam.reservoir_volume_m3" in msg for msg in warning_messages)

    # Check unverified fields list
    unverified_fields = config.get_unverified_fields()
    assert "dam.dam_height_m" in unverified_fields
    assert "dam.crest_elevation_m" in unverified_fields
    assert "dam.reservoir_volume_m3" in unverified_fields


def test_missing_required_field_site_id_fails(valid_verified_config_dict):
    """Test that omitting top-level required field 'site_id' raises ValidationError."""
    del valid_verified_config_dict["site_id"]
    with pytest.raises(ValidationError) as exc_info:
        load_site_config(valid_verified_config_dict)
    assert "site_id" in str(exc_info.value)


def test_missing_required_field_dam_fails(valid_verified_config_dict):
    """Test that omitting required model 'dam' raises ValidationError."""
    del valid_verified_config_dict["dam"]
    with pytest.raises(ValidationError) as exc_info:
        load_site_config(valid_verified_config_dict)
    assert "dam" in str(exc_info.value)


def test_missing_required_dam_dimension_fails(valid_verified_config_dict):
    """Test that omitting dam.dam_height_m raises ValidationError."""
    del valid_verified_config_dict["dam"]["dam_height_m"]
    with pytest.raises(ValidationError) as exc_info:
        load_site_config(valid_verified_config_dict)
    assert "dam_height_m" in str(exc_info.value)


def test_missing_required_solver_fails(valid_verified_config_dict):
    """Test that omitting required 'solver' section raises ValidationError."""
    del valid_verified_config_dict["solver"]
    with pytest.raises(ValidationError) as exc_info:
        load_site_config(valid_verified_config_dict)
    assert "solver" in str(exc_info.value)


def test_invalid_non_numeric_and_non_todo_field_fails(valid_verified_config_dict):
    """Test that a string that is not a number and not a TODO placeholder raises ValidationError."""
    valid_verified_config_dict["dam"]["dam_height_m"] = "unparseable_string"
    with pytest.raises(ValidationError) as exc_info:
        load_site_config(valid_verified_config_dict)
    assert "dam_height_m" in str(exc_info.value)


def test_invalid_bbox_length_fails(valid_verified_config_dict):
    """Test that bounding box with invalid item count raises ValidationError."""
    valid_verified_config_dict["aoi"]["bbox"] = [70.0, 22.0, 71.0]  # Only 3 elements
    with pytest.raises(ValidationError) as exc_info:
        load_site_config(valid_verified_config_dict)
    assert "bbox" in str(exc_info.value)


def test_extra_forbidden_field_fails(valid_verified_config_dict):
    """Test that unexpected extra fields are forbidden by the schema."""
    valid_verified_config_dict["unexpected_custom_key"] = "illegal"
    with pytest.raises(ValidationError) as exc_info:
        load_site_config(valid_verified_config_dict)
    assert "unexpected_custom_key" in str(exc_info.value)
