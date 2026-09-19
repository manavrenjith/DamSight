"""Configuration schema and loader for DamSight with TODO_VERIFY tracking."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UnverifiedValueWarning(UserWarning):
    """Warning emitted when a configuration value contains a TODO_VERIFY or unverified placeholder."""

    pass


def is_todo_value(val: Any) -> bool:
    """Check if a value is a TODO or unverified placeholder."""
    if isinstance(val, str) and "TODO" in val.upper():
        return True
    return False


def validate_maybe_float(val: Any, field_name: str) -> Union[float, str]:
    """Validate a value that should be a float but may be a TODO_VERIFY marker."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        if is_todo_value(val):
            warnings.warn(
                f"Config field '{field_name}' contains unverified value: '{val}'",
                UnverifiedValueWarning,
                stacklevel=3,
            )
            return val
        try:
            return float(val)
        except ValueError:
            raise ValueError(
                f"Field '{field_name}' value '{val}' is neither a valid number nor a TODO marker"
            )
    raise ValueError(f"Field '{field_name}' expected float or TODO string, got {type(val).__name__}")


def validate_float_list(
    val: Any, field_name: str, expected_len: Optional[int] = None
) -> List[Union[float, str]]:
    """Validate a list of floats that may contain TODO markers."""
    if not isinstance(val, (list, tuple)):
        raise ValueError(f"Field '{field_name}' expected a list, got {type(val).__name__}")
    if expected_len is not None and len(val) != expected_len:
        raise ValueError(f"Field '{field_name}' expected {expected_len} elements, got {len(val)}")

    result = []
    for idx, item in enumerate(val):
        item_field = f"{field_name}[{idx}]"
        result.append(validate_maybe_float(item, item_field))
    return result


class DataStatusConfig(BaseModel):
    """Honesty flags displayed in the UI."""

    model_config = ConfigDict(extra="forbid")
    dam_parameters: Literal["verified", "unverified", "synthetic"] = "unverified"


class AoiConfig(BaseModel):
    """Area of Interest bounding box or polygon."""

    model_config = ConfigDict(extra="forbid")
    bbox: List[Union[float, str]]  # [min_lon, min_lat, max_lon, max_lat]

    @field_validator("bbox", mode="before")
    @classmethod
    def check_bbox(cls, v: Any) -> List[Union[float, str]]:
        return validate_float_list(v, "aoi.bbox", expected_len=4)


class DamConfig(BaseModel):
    """Geotechnical and location attributes for the dam."""

    model_config = ConfigDict(extra="forbid")
    location: List[Union[float, str]]  # [lon, lat]
    crest_elevation_m: Union[float, str]
    dam_height_m: Union[float, str]
    reservoir_volume_m3: Union[float, str]
    stage_storage_csv: Optional[str] = None
    breach_types: List[str] = Field(default_factory=lambda: ["overtopping", "piping"])
    source: Optional[str] = None

    @field_validator("location", mode="before")
    @classmethod
    def check_location(cls, v: Any) -> List[Union[float, str]]:
        return validate_float_list(v, "dam.location", expected_len=2)

    @field_validator("crest_elevation_m", "dam_height_m", "reservoir_volume_m3", mode="before")
    @classmethod
    def check_dimension(cls, v: Any, info: Any) -> Union[float, str]:
        return validate_maybe_float(v, f"dam.{info.field_name}")

    @field_validator("source", mode="after")
    @classmethod
    def check_source(cls, v: Optional[str]) -> Optional[str]:
        if v and is_todo_value(v):
            warnings.warn(
                f"Config field 'dam.source' contains unverified reference: '{v}'",
                UnverifiedValueWarning,
                stacklevel=3,
            )
        return v


class DemInputConfig(BaseModel):
    """Elevation dataset configuration."""

    model_config = ConfigDict(extra="forbid")
    source: str = "copernicus_30m"
    path: Optional[str] = None


class InputsConfig(BaseModel):
    """Base geospatial input layer configurations."""

    model_config = ConfigDict(extra="forbid")
    dem: DemInputConfig
    landcover: str = "esa_worldcover"
    population: str = "worldpop"
    buildings: str = "osm"
    roads: str = "osm"


class ReferenceEventConfig(BaseModel):
    """Historical or satellite reference event for validation."""

    model_config = ConfigDict(extra="forbid")
    name: str
    extent: str
    source: Optional[str] = None

    @field_validator("name", "source", mode="after")
    @classmethod
    def check_unverified_text(cls, v: Optional[str], info: Any) -> Optional[str]:
        if v and is_todo_value(v):
            warnings.warn(
                f"Reference event '{info.field_name}' is unverified: '{v}'",
                UnverifiedValueWarning,
                stacklevel=3,
            )
        return v


class SolverConfig(BaseModel):
    """Hydrodynamic solver execution parameters."""

    model_config = ConfigDict(extra="forbid")
    far_field: str = "anuga"
    near_field: str = "none"
    mesh_resolution_m: float = 30.0


class LogNormalParam(BaseModel):
    """Log-normal uncertainty parameter."""

    model_config = ConfigDict(extra="forbid")
    sigma_ln: float


class ReservoirLevelParam(BaseModel):
    """Reservoir initial stage uncertainty bounds."""

    model_config = ConfigDict(extra="forbid")
    range: List[Union[float, str]]

    @field_validator("range", mode="before")
    @classmethod
    def check_range(cls, v: Any) -> List[Union[float, str]]:
        return validate_float_list(v, "ensemble.parameters.reservoir_level_m.range", expected_len=2)


class EnsembleParameters(BaseModel):
    """Uncertainty distributions for Monte Carlo ensemble."""

    model_config = ConfigDict(extra="forbid")
    breach_width: LogNormalParam = Field(default_factory=lambda: LogNormalParam(sigma_ln=0.3))
    formation_time: LogNormalParam = Field(default_factory=lambda: LogNormalParam(sigma_ln=0.4))
    peak_outflow: LogNormalParam = Field(default_factory=lambda: LogNormalParam(sigma_ln=0.3))
    reservoir_level_m: ReservoirLevelParam


class EnsembleConfig(BaseModel):
    """Monte Carlo ensemble configuration."""

    model_config = ConfigDict(extra="forbid")
    n_members: int = 200
    parameters: EnsembleParameters


class EvacuationConfig(BaseModel):
    """Parameters for road cut-off and evacuation feasibility."""

    model_config = ConfigDict(extra="forbid")
    walking_speed_kmh: float = 4.0
    vehicle_speed_kmh: float = 30.0
    road_closure_depth_m: float = 0.3
    safety_margin_min: float = 10.0


class SiteConfig(BaseModel):
    """Master configuration schema for a demo site."""

    model_config = ConfigDict(extra="forbid")

    site_id: str
    name: str
    type: Literal["dam", "natural_blockage", "cascade"] = "dam"
    data_status: DataStatusConfig
    crs: str
    aoi: AoiConfig
    dam: DamConfig
    inputs: InputsConfig
    reference_events: List[ReferenceEventConfig] = Field(default_factory=list)
    solver: SolverConfig
    ensemble: EnsembleConfig
    evacuation: EvacuationConfig

    @field_validator("name", mode="after")
    @classmethod
    def check_site_name(cls, v: str) -> str:
        if is_todo_value(v):
            warnings.warn(
                f"Site name contains placeholder: '{v}'",
                UnverifiedValueWarning,
                stacklevel=3,
            )
        return v

    def get_unverified_fields(self) -> List[str]:
        """Recursively scan model and return dotted paths of unverified fields."""
        unverified: List[str] = []

        def _scan(data: Any, path: str):
            if is_todo_value(data):
                unverified.append(path)
            elif isinstance(data, dict):
                for k, v in data.items():
                    subpath = f"{path}.{k}" if path else k
                    _scan(v, subpath)
            elif isinstance(data, list):
                for idx, v in enumerate(data):
                    _scan(v, f"{path}[{idx}]")
            elif isinstance(data, BaseModel):
                _scan(data.model_dump(), path)

        _scan(self.model_dump(), "")
        return unverified

    @property
    def is_fully_verified(self) -> bool:
        """Return True if no fields contain unverified TODO markers."""
        return len(self.get_unverified_fields()) == 0


def load_site_config(source: Union[str, Path, dict]) -> SiteConfig:
    """Load and validate site configuration from a YAML file or dictionary.

    Surfaces warnings for any unverified values (TODO_VERIFY).
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    elif isinstance(source, dict):
        raw_data = source
    else:
        raise TypeError(f"Expected file path or dictionary, got {type(source).__name__}")

    if not isinstance(raw_data, dict):
        raise ValueError("Configuration data must be a YAML mapping (dictionary)")

    return SiteConfig.model_validate(raw_data)
