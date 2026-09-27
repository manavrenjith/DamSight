"""Configuration schema and loader for DamSight v2 with TODO_VERIFY tracking."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator


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
    crest_length_m: float | str | None = None
    catchment_area_km2: float | str | None = None
    peak_inflow_disputed_m3s: dict[str, Any] | str | None = None
    breach_types: list[str] = Field(default_factory=lambda: ["overtopping", "piping"])
    source: str | None = None
    verified: bool | None = None
    unverified_parameters: list[str] = Field(default_factory=list, exclude=True)
    parameter_sources: dict[str, str] = Field(default_factory=dict, exclude=True)
    _site_id: str = PrivateAttr(default="")
    _site_name: str = PrivateAttr(default="")

    @model_validator(mode="before")
    @classmethod
    def track_unverified(cls, data: Any) -> Any:
        if isinstance(data, dict):
            unverified: list[str] = []
            param_sources: dict[str, str] = {}
            dam_src = data.get("source")
            if dam_src and not is_todo_value(str(dam_src)):
                param_sources["_dam"] = str(dam_src)

            for key in (
                "crest_elevation_m",
                "dam_height_m",
                "reservoir_volume_m3",
                "spillway_capacity_m3s",
                "crest_length_m",
                "catchment_area_km2",
            ):
                raw = data.get(key)
                if isinstance(raw, dict):
                    if raw.get("verified") is False:
                        unverified.append(key)
                    field_src = raw.get("source")
                    if field_src and not is_todo_value(str(field_src)):
                        param_sources[key] = str(field_src)
                elif isinstance(raw, str) and is_todo_value(raw):
                    unverified.append(key)

            if data.get("verified") is False:
                unverified.extend(
                    [
                        "crest_elevation_m",
                        "dam_height_m",
                        "reservoir_volume_m3",
                        "spillway_capacity_m3s",
                        "crest_length_m",
                        "catchment_area_km2",
                    ]
                )
            data["unverified_parameters"] = list(set(unverified))
            data["parameter_sources"] = param_sources
        return data

    @property
    def is_synthetic(self) -> bool:
        """Return True if this dam belongs to a synthetic test fixture."""
        s_id = (self._site_id or "").upper()
        s_name = (self._site_name or "").upper()
        d_id = (self.id or "").upper()
        d_source = (self.source or "").upper()
        if "SYNTHETIC" in s_id and "SYNTHETIC" in s_name:
            return True
        return bool(
            "SYNTHETIC" in d_id
            and ("SYNTHETIC" in s_id or "SYNTHETIC" in s_name or "SYNTHETIC" in d_source)
        )

    def consume_physical_parameter(
        self,
        field_name: str,
        allow_unverified: bool = False,
    ) -> tuple[float, str, list[str]]:
        """Consume a physical parameter, enforcing allow_unverified guard.

        Rules:
        a) A value that is TODO_VERIFY always raises ValueError, even with allow_unverified=True.
        b) A numeric value with verified:false and a source passes only with allow_unverified=True;
           the returned metadata carries data_status="unverified" plus the source list.
        c) If synthetic values are needed, they come only from a fixture whose site_id and name
           contain SYNTHETIC, and the returned metadata says data_status="synthetic".
        """
        val = getattr(self, field_name)
        if is_todo_value(val):
            raise ValueError(
                f"Physical parameter '{field_name}' on dam '{self.id}' is a placeholder '{val}' (TODO_VERIFY). "
                "Values marked TODO_VERIFY always raise and cannot be consumed, even with allow_unverified=True."
            )

        is_unverified = (field_name in self.unverified_parameters) or (self.verified is False)
        if is_unverified:
            if not allow_unverified:
                raise ValueError(
                    f"Physical parameter '{field_name}' on dam '{self.id}' is unverified ({val}). "
                    "Must pass allow_unverified=True to consume unverified physical values."
                )
            src = (
                self.parameter_sources.get(field_name)
                or self.parameter_sources.get("_dam")
                or self.source
            )
            if not src or is_todo_value(src):
                raise ValueError(
                    f"Physical parameter '{field_name}' on dam '{self.id}' is marked verified:false but has no valid source citation. "
                    "A numeric value with verified:false requires a cited source to be consumed with allow_unverified=True."
                )
            return float(val), "unverified", [str(src)]

        # Synthetic fixture detection
        if self.is_synthetic:
            sources = [self.source] if self.source and not is_todo_value(self.source) else []
            return float(val), "synthetic", sources

        sources = [self.source] if self.source and not is_todo_value(self.source) else []
        return float(val), "verified", sources

    @field_validator("location", mode="before")
    @classmethod
    def check_location(cls, v: Any) -> list[float | str]:
        return validate_float_list(v, "dam.location", expected_len=2)

    @field_validator(
        "crest_elevation_m",
        "dam_height_m",
        "reservoir_volume_m3",
        "crest_length_m",
        "catchment_area_km2",
        mode="before",
    )
    @classmethod
    def check_dimension(cls, v: Any, info: Any) -> float | str | None:
        if v is None:
            return None
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
    catchment_area_km2: float | str | None = None
    peak_inflow_disputed_m3s: dict[str, Any] | str | None = None

    def model_post_init(self, __context: Any, /) -> None:
        for dam in self.dams:
            dam._site_id = self.site_id
            dam._site_name = self.name

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
    site: SiteConfig | None = None,
) -> dict[str, Any]:
    """Consume physical parameters for dam breach/simulation, enforcing allow_unverified guard.

    Rules:
    a) A value that is TODO_VERIFY always raises, even with allow_unverified=True.
    b) A numeric value with verified:false and a source passes only with allow_unverified=True;
       the returned metadata carries data_status="unverified" plus the source list.
    c) If synthetic values are needed, they come only from a fixture whose site_id and name contain
       SYNTHETIC, and the returned metadata says data_status="synthetic".
    """
    if site is not None:
        dam._site_id = site.site_id
        dam._site_name = site.name

    h_b, s1, src1 = dam.consume_physical_parameter(
        "dam_height_m",
        allow_unverified=allow_unverified,
    )
    v_w, s2, src2 = dam.consume_physical_parameter(
        "reservoir_volume_m3",
        allow_unverified=allow_unverified,
    )
    crest_z, s3, src3 = dam.consume_physical_parameter(
        "crest_elevation_m",
        allow_unverified=allow_unverified,
    )

    all_sources = list(dict.fromkeys(s for s in (src1 + src2 + src3) if s))

    if any(s == "unverified" for s in (s1, s2, s3)):
        status = "unverified"
    elif any(s == "synthetic" for s in (s1, s2, s3)):
        status = "synthetic"
    else:
        status = "verified"

    return {
        "dam_id": dam.id,
        "dam_height_m": h_b,
        "reservoir_volume_m3": v_w,
        "crest_elevation_m": crest_z,
        "data_status": status,
        "sources": all_sources,
    }
