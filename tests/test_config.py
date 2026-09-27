"""Tests for v2 configuration schema validation, TODO_VERIFY handling, and error cases."""

import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from damsight.config import (
    UnverifiedValueWarning,
    consume_dam_parameters,
    load_site_config,
)


@pytest.fixture
def valid_v2_verified_config_dict():
    """A synthetic v2 configuration dictionary with concrete numeric values."""
    return {
        "site_id": "site_synthetic",
        "name": "SYNTHETIC_TEST_DAM Cascade (Synthetic Test Dataset)",
        "type": "cascade",
        "data_status": {
            "dam_parameters": "synthetic",
        },
        "crs": "EPSG:32643",
        "aoi": {
            "bbox": [70.85, 22.75, 71.05, 22.95],
        },
        "dams": [
            {
                "id": "SYNTHETIC_TEST_DAM_1",
                "role": "upstream",
                "location": [70.85, 22.72],
                "crest_elevation_m": 85.0,
                "dam_height_m": 28.0,
                "reservoir_volume_m3": 85000000.0,
                "stage_storage_csv": "data/site_synthetic/dam1_stage_storage.csv",
                "dam_type": "embankment",
                "source": "Synthetic fixture",
                "verified": True,
            },
            {
                "id": "SYNTHETIC_TEST_DAM_2",
                "role": "downstream",
                "location": [70.89, 22.78],
                "crest_elevation_m": 60.5,
                "dam_height_m": 24.3,
                "reservoir_volume_m3": 110000000.0,
                "stage_storage_csv": "data/site_synthetic/dam2_stage_storage.csv",
                "dam_type": "embankment",
                "spillway_capacity_m3s": 6100.0,
                "breach_types": ["overtopping", "piping"],
                "source": "Synthetic fixture",
                "verified": True,
            },
        ],
        "scenarios": [
            {
                "id": "A1_hindcast_1979",
                "kind": "hindcast",
                "breach_dam": "SYNTHETIC_TEST_DAM_2",
                "breach_type": "overtopping",
            },
            {
                "id": "A2_cascade_whatif",
                "kind": "hypothetical",
                "upstream_release_from": "SYNTHETIC_TEST_DAM_1",
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
                "name": "Synthetic Reference Event",
                "type": "historical",
                "extent": "data/site_synthetic/reference_extent.geojson",
                "source": "Synthetic benchmark source",
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

    assert config.site_id == "site_synthetic"
    assert config.type == "cascade"
    assert len(config.dams) == 2
    dam2 = config.get_dam("SYNTHETIC_TEST_DAM_2")
    assert dam2.id == "SYNTHETIC_TEST_DAM_2"
    assert dam2.dam_height_m == 24.3
    dam2_inputs = consume_dam_parameters(dam2)
    assert dam2_inputs["dam_height_m"] == 24.3
    assert dam2_inputs["data_status"] == "synthetic"
    assert config.solver.baseline == "anuga"
    assert config.is_fully_verified is True
    assert len(config.get_unverified_fields()) == 0


def test_site_a_yaml_loads_and_emits_todo_verify_warnings():
    """Test that configs/sites/site_a.yaml loads in v2 and emits UnverifiedValueWarning for any TODO or unverified fields."""
    import yaml

    yaml_path = Path(__file__).resolve().parent.parent / "configs" / "sites" / "site_a.yaml"
    assert yaml_path.exists(), f"Configuration file {yaml_path} does not exist"
    raw_yaml = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    raw_text = yaml_path.read_text(encoding="utf-8")
    has_unverified_content = (
        "TODO_VERIFY" in raw_text
        or "verified: false" in raw_text
        or "verified: False" in raw_text
    )

    if has_unverified_content:
        with pytest.warns(UnverifiedValueWarning) as warning_records:
            config = load_site_config(yaml_path)
        assert config.is_fully_verified is False
        warning_messages = [str(w.message) for w in warning_records]

        # Check that warnings were emitted for whichever fields actually contain TODO_VERIFY
        if raw_yaml.get("crs") == "TODO_VERIFY":
            assert any("CRS is unverified" in msg or "crs" in msg.lower() for msg in warning_messages)
        for dam_dict in raw_yaml.get("dams", []):
            for field in ["dam_height_m", "reservoir_volume_m3", "crest_elevation_m"]:
                val = dam_dict.get(field)
                if val == "TODO_VERIFY" or (isinstance(val, dict) and val.get("value") == "TODO_VERIFY"):
                    assert any(field in msg for msg in warning_messages)
    else:
        with warnings.catch_warnings(record=True) as recorded_warnings:
            warnings.simplefilter("always")
            config = load_site_config(yaml_path)
            unverified_warnings = [
                w for w in recorded_warnings if issubclass(w.category, UnverifiedValueWarning)
            ]
            assert len(unverified_warnings) == 0
        assert config.is_fully_verified is True

    # Verify site config object was successfully constructed
    assert config.site_id == "site_a"
    assert config.type == "cascade"
    assert len(config.dams) == 2
    assert config.dams[0].id == "machhu_1"
    assert config.dams[1].id == "machhu_2"



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


# --- RESTORED TESTS (ADAPTED TO V2 SCHEMA) ---


def test_missing_required_field_site_id_fails(valid_v2_verified_config_dict):
    """Test that omitting required site_id raises ValidationError."""
    del valid_v2_verified_config_dict["site_id"]
    with pytest.raises(ValidationError) as exc_info:
        load_site_config(valid_v2_verified_config_dict)
    assert "site_id" in str(exc_info.value)


def test_missing_required_solver_fails(valid_v2_verified_config_dict):
    """Test that omitting required solver configuration block raises ValidationError."""
    del valid_v2_verified_config_dict["solver"]
    with pytest.raises(ValidationError) as exc_info:
        load_site_config(valid_v2_verified_config_dict)
    assert "solver" in str(exc_info.value)


def test_invalid_non_numeric_and_non_todo_field_fails(valid_v2_verified_config_dict):
    """Test that non-numeric, non-TODO strings for float fields raise ValidationError."""
    valid_v2_verified_config_dict["dams"][0]["dam_height_m"] = "invalid_text_value"
    with pytest.raises(ValidationError) as exc_info:
        load_site_config(valid_v2_verified_config_dict)
    assert "neither a valid number nor a TODO marker" in str(exc_info.value)


def test_invalid_bbox_length_fails(valid_v2_verified_config_dict):
    """Test that aoi.bbox with length other than 4 raises ValidationError."""
    valid_v2_verified_config_dict["aoi"]["bbox"] = [70.85, 22.75, 71.05]  # length 3 instead of 4
    with pytest.raises(ValidationError) as exc_info:
        load_site_config(valid_v2_verified_config_dict)
    assert "expected 4 elements" in str(exc_info.value)


# --- ALLOW_UNVERIFIED GUARD & V2 LOGIC TESTS ---


def test_consuming_unverified_physical_value_raises_without_flag(valid_v2_verified_config_dict):
    """Test that consuming a physical config parameter with TODO_VERIFY raises unless allow_unverified=True."""
    valid_v2_verified_config_dict["dams"][0]["dam_height_m"] = "TODO_VERIFY"
    with pytest.warns(UnverifiedValueWarning):
        config = load_site_config(valid_v2_verified_config_dict)

    dam = config.dams[0]
    with pytest.raises(ValueError, match="allow_unverified=True"):
        consume_dam_parameters(dam, allow_unverified=False)


def test_todo_verify_always_raises_even_with_allow_unverified_true(
    valid_v2_verified_config_dict,
):
    """Test that a parameter with TODO_VERIFY always raises ValueError, even with allow_unverified=True."""
    valid_v2_verified_config_dict["dams"][0]["dam_height_m"] = "TODO_VERIFY"
    with pytest.warns(UnverifiedValueWarning):
        config = load_site_config(valid_v2_verified_config_dict)

    dam = config.dams[0]
    with pytest.raises(ValueError, match="TODO_VERIFY"):
        consume_dam_parameters(dam, allow_unverified=True)


def test_per_value_verified_false_takes_unverified_guard_path(valid_v2_verified_config_dict):
    """Test that a {value, source, verified: false} dam value is treated as unverified by the guard."""
    valid_v2_verified_config_dict["dams"][0]["dam_height_m"] = {
        "value": 28.0,
        "source": "Unverified rumor",
        "verified": False,
    }
    with pytest.warns(UnverifiedValueWarning):
        config = load_site_config(valid_v2_verified_config_dict)

    dam = config.dams[0]
    # Without allow_unverified, it raises
    with pytest.raises(ValueError, match="allow_unverified=True"):
        consume_dam_parameters(dam, allow_unverified=False)

    # With allow_unverified=True, it passes and stamps output with data_status=unverified plus sources
    output = consume_dam_parameters(dam, allow_unverified=True)
    assert output["dam_height_m"] == 28.0
    assert output["data_status"] == "unverified"
    assert "Unverified rumor" in output["sources"]


def test_config_dam_requires_explicit_dam_id_when_a2_has_no_breach_dam(
    valid_v2_verified_config_dict,
):
    """Test that config.dam raises ValueError when scenario A2 has no breach_dam, requiring an explicit dam_id."""
    config = load_site_config(valid_v2_verified_config_dict)

    # config.dam requires an explicit dam_id because A2 has no breach_dam
    with pytest.raises(ValueError, match="explicit dam_id is required"):
        _ = config.dam.id

    with pytest.raises(ValueError, match="explicit dam_id is required"):
        _ = config.get_dam()

    # Providing explicit dam_id succeeds
    dam1 = config.get_dam("SYNTHETIC_TEST_DAM_1")
    assert dam1.id == "SYNTHETIC_TEST_DAM_1"

    dam2 = config.dam("SYNTHETIC_TEST_DAM_2")
    assert dam2.id == "SYNTHETIC_TEST_DAM_2"


def test_site_a_data_status_dam_parameters_is_unverified():
    """Test that configs/sites/site_a.yaml has data_status.dam_parameters == 'unverified'."""
    yaml_path = Path(__file__).resolve().parent.parent / "configs" / "sites" / "site_a.yaml"
    with pytest.warns(UnverifiedValueWarning):
        config = load_site_config(yaml_path)

    assert config.data_status.dam_parameters == "unverified"


def test_real_site_a_all_todo_verify_raises_for_both_allow_unverified_flags():
    """Test on real configs/sites/site_a.yaml:
    Scans raw YAML for TODO_VERIFY in required dam fields.
    The guard must raise iff any remain (for both allow_unverified values).
    If none remain and every value carries a source and verified:false,
    it must raise without the flag and return data_status='unverified' (with the sources) with the flag.
    """
    import yaml
    from damsight.breach import get_dam_breach_inputs

    yaml_path = Path(__file__).resolve().parent.parent / "configs" / "sites" / "site_a.yaml"
    raw_yaml = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    with pytest.warns(UnverifiedValueWarning):
        config = load_site_config(yaml_path)

    dam2 = config.get_dam("machhu_2")

    # Find raw dam2 dictionary
    raw_dam2 = next(d for d in raw_yaml.get("dams", []) if d.get("id") == "machhu_2")
    required_fields = ["crest_elevation_m", "dam_height_m", "reservoir_volume_m3"]

    def is_todo(val) -> bool:
        if val == "TODO_VERIFY":
            return True
        if isinstance(val, dict) and val.get("value") == "TODO_VERIFY":
            return True
        return False

    has_todo_in_required = any(is_todo(raw_dam2.get(f)) for f in required_fields)

    if has_todo_in_required:
        # Guard must raise ValueError for BOTH allow_unverified=False and allow_unverified=True
        with pytest.raises(ValueError, match="TODO_VERIFY|allow_unverified=True"):
            get_dam_breach_inputs(dam2, allow_unverified=False)

        with pytest.raises(ValueError, match="TODO_VERIFY"):
            get_dam_breach_inputs(dam2, allow_unverified=True)
    else:
        # If none remain and every value carries a source and verified:false:
        # Must raise without allow_unverified flag
        with pytest.raises(ValueError, match="allow_unverified=True"):
            get_dam_breach_inputs(dam2, allow_unverified=False)

        # With allow_unverified=True, returns data_status="unverified" and sources
        inputs = get_dam_breach_inputs(dam2, allow_unverified=True)
        assert inputs["dam_id"] == "machhu_2"
        assert inputs["data_status"] == "unverified"
        assert "sources" in inputs and len(inputs["sources"]) > 0



def test_unverified_numeric_value_with_source_passes_with_flag_and_returns_source_list():
    """Test on a temporary config with cited numeric values marked verified: false:
    raises without allow_unverified=True, and succeeds with the flag returning data_status='unverified'
    plus the sources list.
    """
    from damsight.breach import get_dam_breach_inputs

    cfg_dict = {
        "site_id": "site_test_unverified",
        "name": "Test Unverified Site",
        "type": "dam",
        "data_status": {"dam_parameters": "unverified"},
        "crs": "EPSG:32643",
        "aoi": {"bbox": [70.0, 22.0, 71.0, 23.0]},
        "dams": [
            {
                "id": "test_dam_unverified",
                "role": "single",
                "location": [70.5, 22.5],
                "crest_elevation_m": {
                    "value": 60.5,
                    "source": "Govt Gazette 1978",
                    "verified": False,
                },
                "dam_height_m": {
                    "value": 24.0,
                    "source": "Govt Gazette 1978",
                    "verified": False,
                },
                "reservoir_volume_m3": {
                    "value": 110000000.0,
                    "source": "Govt Gazette 1978",
                    "verified": False,
                },
                "source": "State Irrigation Dept",
            }
        ],
        "inputs": {
            "dem": {"source": "copernicus_30m"},
            "landcover": "esa_worldcover",
            "population": "worldpop",
            "buildings": "osm",
            "roads": "osm",
        },
        "solver": {"mesh_resolution_m": 30.0},
        "ensemble": {
            "n_members": 10,
            "parameters": {"reservoir_level_m": {"range": [50.0, 60.0]}},
        },
        "evacuation": {},
    }
    with pytest.warns(UnverifiedValueWarning):
        config = load_site_config(cfg_dict)

    dam = config.dams[0]

    # Without allow_unverified, it MUST raise ValueError
    with pytest.raises(ValueError, match="allow_unverified=True"):
        get_dam_breach_inputs(dam, allow_unverified=False)

    # With allow_unverified=True, it succeeds and returns data_status='unverified' + source list
    inputs = get_dam_breach_inputs(dam, allow_unverified=True)
    assert inputs["dam_id"] == "test_dam_unverified"
    assert inputs["dam_height_m"] == 24.0
    assert inputs["reservoir_volume_m3"] == 110000000.0
    assert inputs["crest_elevation_m"] == 60.5
    assert inputs["data_status"] == "unverified"
    assert "Govt Gazette 1978" in inputs["sources"] or "State Irrigation Dept" in inputs["sources"]


def test_dam_breach_inputs_raises_todo_verify_when_any_field_is_todo():
    """Synthetic dam fixture with at least one required field literally TODO_VERIFY, others can be anything.
    Assert ValueError match='TODO_VERIFY' under both allow_unverified=True and allow_unverified=False.
    """
    from damsight.breach import get_dam_breach_inputs

    cfg_dict = {
        "site_id": "site_fixture_todo",
        "name": "Fixture Site with TODO",
        "type": "dam",
        "data_status": {"dam_parameters": "unverified"},
        "crs": "EPSG:32643",
        "aoi": {"bbox": [70.0, 22.0, 71.0, 23.0]},
        "dams": [
            {
                "id": "fixture_dam_todo",
                "role": "single",
                "location": [70.5, 22.5],
                "crest_elevation_m": "TODO_VERIFY",
                "dam_height_m": "TODO_VERIFY",
                "reservoir_volume_m3": {
                    "value": 110000000.0,
                    "source": "Historical Survey 1979",
                    "verified": False,
                },
                "source": "Historical Survey 1979",
            }
        ],
        "inputs": {
            "dem": {"source": "copernicus_30m"},
            "landcover": "esa_worldcover",
            "population": "worldpop",
            "buildings": "osm",
            "roads": "osm",
        },
        "solver": {"mesh_resolution_m": 30.0},
        "ensemble": {
            "n_members": 10,
            "parameters": {"reservoir_level_m": {"range": [50.0, 60.0]}},
        },
        "evacuation": {},
    }
    with pytest.warns(UnverifiedValueWarning):
        config = load_site_config(cfg_dict)

    dam = config.dams[0]

    with pytest.raises(ValueError, match="TODO_VERIFY"):
        get_dam_breach_inputs(dam, allow_unverified=False)

    with pytest.raises(ValueError, match="TODO_VERIFY"):
        get_dam_breach_inputs(dam, allow_unverified=True)


def test_dam_breach_inputs_raises_without_flag_when_fields_are_unverified_numeric():
    """Synthetic dam fixture where all required fields are numeric with verified: false, none TODO_VERIFY.
    Assert ValueError under allow_unverified=False (message should NOT contain 'TODO_VERIFY'), and
    assert successful return with data_status='unverified' under allow_unverified=True,
    checking the returned source list is non-empty.
    """
    from damsight.breach import get_dam_breach_inputs

    cfg_dict = {
        "site_id": "site_fixture_unverified_numeric",
        "name": "Fixture Site Unverified Numeric",
        "type": "dam",
        "data_status": {"dam_parameters": "unverified"},
        "crs": "EPSG:32643",
        "aoi": {"bbox": [70.0, 22.0, 71.0, 23.0]},
        "dams": [
            {
                "id": "fixture_dam_unverified",
                "role": "single",
                "location": [70.5, 22.5],
                "crest_elevation_m": {
                    "value": 60.5,
                    "source": "Historical Report 1979",
                    "verified": False,
                },
                "dam_height_m": {
                    "value": 24.0,
                    "source": "Historical Report 1979",
                    "verified": False,
                },
                "reservoir_volume_m3": {
                    "value": 110000000.0,
                    "source": "Historical Report 1979",
                    "verified": False,
                },
                "source": "Historical Report 1979",
            }
        ],
        "inputs": {
            "dem": {"source": "copernicus_30m"},
            "landcover": "esa_worldcover",
            "population": "worldpop",
            "buildings": "osm",
            "roads": "osm",
        },
        "solver": {"mesh_resolution_m": 30.0},
        "ensemble": {
            "n_members": 10,
            "parameters": {"reservoir_level_m": {"range": [50.0, 60.0]}},
        },
        "evacuation": {},
    }
    with pytest.warns(UnverifiedValueWarning):
        config = load_site_config(cfg_dict)

    dam = config.dams[0]

    with pytest.raises(ValueError) as exc_info:
        get_dam_breach_inputs(dam, allow_unverified=False)
    assert "TODO_VERIFY" not in str(exc_info.value)
    assert "allow_unverified=True" in str(exc_info.value)

    res = get_dam_breach_inputs(dam, allow_unverified=True)
    assert res["dam_id"] == "fixture_dam_unverified"
    assert res["data_status"] == "unverified"
    assert len(res["sources"]) > 0
    assert "Historical Report 1979" in res["sources"]

