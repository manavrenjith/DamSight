"""Configuration schema and loader for DamSight v2 with TODO_VERIFY tracking."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UnverifiedValueWarning(UserWarning):
    """Warning emitted when a configuration value contains a TODO_VERIFY or unverified placeholder."""


def is_todo_value(val: Any) -> bool:
    """Check if a value is a TODO or unverified placeholder."""
    return isinstance(val, str) and "TODO" in val.upper()


def extract_value_and_meta(val: Any) -> tuple[Any, str | None, bool | None]:
    """Unpack value and metadata if structured as a dictionary {value, source, verified}."""
    if isinstance(val, dict) and "value" in val:
        return val["value"], val.get("source"), val.get("verified")
    return val, None, None


def validate_maybe_float(val: Any, field_name: str) -> float | str:
    """Validate a value that should be a float but may be a TODO_VERIFY marker or per-value dict."""
    raw_val, source, verified = extract_value_and_meta(val)

    if verified is False:
        warnings.warn(
            f"Config field '{field_name}' marked verified=false (source: '{source}')",
            UnverifiedValueWarning,
            stacklevel=3,
        )

    if isinstance(raw_val, (int, float)):
        return float(raw_val)
    if isinstance(raw_val, str):
        if is_todo_value(raw_val):
            warnings.warn(
                f"Config field '{field_name}' contains unverified value: '{raw_val}'",
                UnverifiedValueWarning,
                stacklevel=3,
            )
            return raw_val
        try:
            return float(raw_val)
        except ValueError:
            raise ValueError(
                f"Field '{field_name}' value '{raw_val}' is neither a valid number nor a TODO marker"
            )
    raise ValueError(
        f"Field '{field_name}' expected float or TODO string, got {type(raw_val).__name__}"
    )


def validate_float_list(
    val: Any, field_name: str, expected_len: int | None = None
) -> list[float | str]:
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
    dam_parameters: Literal["verified", "unverified", "synthetic", "defaulted"] = "unverified"


class AoiConfig(BaseModel):
    """Area of Interest bounding box or polygon."""

    model_config = ConfigDict(extra="forbid")
    bbox: list[float | str]  # [min_lon, min_lat, max_lon, max_lat]

    @field_validator("bbox", mode="before")
    @classmethod
    def check_bbox(cls, v: Any) -> list[float | str]:
        return validate_float_list(v, "aoi.bbox", expected_len=4)


class DamItemConfig(BaseModel):
    """Geotechnical and operational attributes for a dam in a cascade or single site."""

    model_config = ConfigDict(extra="forbid")
    id: str
    role: str | None = "single"  # upstream | downstream | single | midstream
    location: list[float | str]  # [lon, lat]
    crest_elevation_m: float | str
    dam_height_m: float | str
    reservoir_volume_m3: float | str
    stage_storage_csv: str | None = None
    dam_type: str = "embankment"
    spillway_capacity_m3s: float | str | None = None
    breach_types: list[str] = Field(default_factory=lambda: ["overtopping", "piping"])
    source: str | None = None
    verified: bool | None = None
    unverified_parameters: list[str] = Field(default_factory=list, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def track_unverified(cls, data: Any) -> Any:
        if isinstance(data, dict):
            unverified: list[str] = []
            for key in (
                "crest_elevation_m",
                "dam_height_m",
                "reservoir_volume_m3",
                "spillway_capacity_m3s",
            ):
                raw = data.get(key)
                if (
                    isinstance(raw, dict)
                    and raw.get("verified") is False
                    or isinstance(raw, str)
                    and is_todo_value(raw)
                ):
                    unverified.append(key)
            if data.get("verified") is False:
                unverified.extend(
                    [
                        "crest_elevation_m",
                        "dam_height_m",
                        "reservoir_volume_m3",
                        "spillway_capacity_m3s",
                    ]
                )
            data["unverified_parameters"] = list(set(unverified))
        return data

    def consume_physical_parameter(
        self,
        field_name: str,
        allow_unverified: bool = False,
        fallback_value: float | None = None,
    ) -> tuple[float, str]:
        """Consume a physical parameter, enforcing allow_unverified guard.

        Raises ValueError if unverified and allow_unverified is False.
        Returns (numeric_value, data_status).
        """
        val = getattr(self, field_name)
        is_unverified = (
            is_todo_value(val)
            or (field_name in self.unverified_parameters)
            or (self.verified is False)
        )
        if is_unverified:
            if not allow_unverified:
                raise ValueError(
                    f"Physical parameter '{field_name}' on dam '{self.id}' is unverified ({val}). "
                    "Must pass allow_unverified=True to consume unverified physical values."
                )
            if is_todo_value(val):
                if fallback_value is None:
                    raise ValueError(
                        f"Physical parameter '{field_name}' is placeholder '{val}' and no fallback value was provided."
                    )
                return float(fallback_value), "unverified"
            return float(val), "unverified"
        return float(val), "verified"

    @field_validator("location", mode="before")
    @classmethod
    def check_location(cls, v: Any) -> list[float | str]:
        return validate_float_list(v, "dam.location", expected_len=2)

    @field_validator("crest_elevation_m", "dam_height_m", "reservoir_volume_m3", mode="before")
    @classmethod
    def check_dimension(cls, v: Any, info: Any) -> float | str:
        return validate_maybe_float(v, f"dam.{info.field_name}")

    @field_validator("spillway_capacity_m3s", mode="before")
    @classmethod
    def check_spillway(cls, v: Any) -> float | str | None:
        if v is None:
            return None
        return validate_maybe_float(v, "dam.spillway_capacity_m3s")

    @field_validator("source", mode="after")
    @classmethod
    def check_source(cls, v: str | None) -> str | None:
        if v and is_todo_value(v):
            warnings.warn(
                f"Config field 'dam.source' contains unverified reference: '{v}'",
                UnverifiedValueWarning,
                stacklevel=3,
            )
        return v


class ScenarioConfig(BaseModel):
    """Simulation scenario definition."""

    model_config = ConfigDict(extra="allow")
    id: str
    kind: str = "hindcast"  # hindcast | hypothetical | release | benchmark
    breach_dam: str | None = None
    breach_type: str | None = None
    upstream_release_from: str | None = None


class DemInputConfig(BaseModel):
    """Elevation dataset configuration."""

    model_config = ConfigDict(extra="forbid")
    source: str = "copernicus_30m"
    path: str | None = None


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
    type: str = "historical"  # historical | satellite | benchmark
    extent: str | None = None
    source: str | None = None

    @field_validator("name", "source", mode="after")
    @classmethod
    def check_unverified_text(cls, v: str | None, info: Any) -> str | None:
        if v and is_todo_value(v):
            warnings.warn(
                f"Reference event '{info.field_name}' is unverified: '{v}'",
                UnverifiedValueWarning,
                stacklevel=3,
            )
        return v


class SolverConfig(BaseModel):
    """Hydrodynamic solver execution parameters (v2)."""

    model_config = ConfigDict(extra="forbid")
    far_field: str = "delft3dfm"
    baseline: str = "anuga"
    near_field: str = "none"
    mesh_resolution_m: float = 30.0


class LogNormalParam(BaseModel):
    """Log-normal uncertainty parameter."""

    model_config = ConfigDict(extra="forbid")
    sigma_ln: float


class ReservoirLevelParam(BaseModel):
    """Reservoir initial stage uncertainty bounds."""

    model_config = ConfigDict(extra="forbid")
    range: list[float | str]

    @field_validator("range", mode="before")
    @classmethod
    def check_range(cls, v: Any) -> list[float | str]:
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
    n_members: int = 100
    parameters: EnsembleParameters


class EvacuationConfig(BaseModel):
    """Parameters for road cut-off and evacuation feasibility."""

    model_config = ConfigDict(extra="forbid")
    walking_speed_kmh: float = 4.0
    vehicle_speed_kmh: float = 30.0
    road_closure_depth_m: float = 0.3
    safety_margin_min: float = 10.0


class DamAccessor:
    """Wrapper around dam access providing clear errors when explicit dam_id is required."""

    def __init__(self, site: SiteConfig):
        self._site = site

    def __call__(self, dam_id: str | None = None) -> DamItemConfig:
        return self._site.get_dam(dam_id)

    def __getattr__(self, name: str) -> Any:
        target = self._site.get_dam(dam_id=None)
        return getattr(target, name)


class SiteConfig(BaseModel):
    """Master configuration schema for a demo site (v2)."""

    model_config = ConfigDict(extra="forbid")

    site_id: str
    name: str
    type: Literal["dam", "natural_blockage", "cascade"] = "cascade"
    data_status: DataStatusConfig
    crs: str
    aoi: AoiConfig
    dams: list[DamItemConfig]
    scenarios: list[ScenarioConfig] = Field(default_factory=list)
    inputs: InputsConfig
    reference_events: list[ReferenceEventConfig] = Field(default_factory=list)
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

    @field_validator("crs", mode="after")
    @classmethod
    def check_site_crs(cls, v: str) -> str:
        if is_todo_value(v):
            warnings.warn(
                f"Site CRS is unverified: '{v}'",
                UnverifiedValueWarning,
                stacklevel=3,
            )
        return v

    def get_dam(self, dam_id: str | None = None) -> DamItemConfig:
        """Return dam configuration by dam_id.

        Requires an explicit dam_id if multiple dams are configured and scenarios do not
        unambiguously identify a single breach dam (e.g. scenario A2 has no breach_dam).
        """
        if dam_id is not None:
            for d in self.dams:
                if d.id == dam_id:
                    return d
            raise ValueError(f"Dam with id '{dam_id}' not found in site dams")

        if len(self.dams) == 1:
            return self.dams[0]

        # Multi-dam configuration: check if any scenario lacks breach_dam (e.g. A2)
        has_no_breach_scenario = any(sc.breach_dam is None for sc in self.scenarios)
        if has_no_breach_scenario or len(self.dams) > 1:
            raise ValueError(
                f"Site '{self.site_id}' has multiple dams and scenario (such as A2) has no breach_dam; "
                "explicit dam_id is required via get_dam(dam_id)"
            )
        return self.dams[0]

    @property
    def dam(self) -> DamAccessor:
        """Accessor for primary breach dam; requires explicit dam_id when ambiguous."""
        return DamAccessor(self)

    def get_unverified_fields(self) -> list[str]:
        """Recursively scan model and return dotted paths of unverified fields."""
        unverified: list[str] = []

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


def load_site_config(source: str | Path | dict) -> SiteConfig:
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


def consume_dam_parameters(
    dam: DamItemConfig,
    allow_unverified: bool = False,
    fallbacks: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Consume physical parameters for dam breach/simulation, enforcing allow_unverified guard.

    Raises ValueError if any parameter is unverified and allow_unverified is False.
    Returns dictionary with data_status='unverified' when allow_unverified is True.
    """
    fallbacks = fallbacks or {}
    h_b, s1 = dam.consume_physical_parameter(
        "dam_height_m",
        allow_unverified=allow_unverified,
        fallback_value=fallbacks.get("dam_height_m"),
    )
    v_w, s2 = dam.consume_physical_parameter(
        "reservoir_volume_m3",
        allow_unverified=allow_unverified,
        fallback_value=fallbacks.get("reservoir_volume_m3"),
    )
    crest_z, s3 = dam.consume_physical_parameter(
        "crest_elevation_m",
        allow_unverified=allow_unverified,
        fallback_value=fallbacks.get("crest_elevation_m"),
    )
    status = "unverified" if any(s == "unverified" for s in (s1, s2, s3)) else "verified"
    return {
        "dam_id": dam.id,
        "dam_height_m": h_b,
        "reservoir_volume_m3": v_w,
        "crest_elevation_m": crest_z,
        "data_status": status,
    }
