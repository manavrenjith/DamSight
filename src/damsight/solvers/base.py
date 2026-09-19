"""Base interfaces and protocols for hydrodynamic solvers."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import pandas as pd


@dataclass
class RunDir:
    """Working directory and configuration for a solver execution."""

    path: Path
    mesh_resolution_m: float
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    """Execution status and metadata resulting from a simulation run."""

    success: bool
    runtime_s: float
    mass_balance_error: float
    warnings: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Outputs:
    """Standard output raster paths adhering to the solver outputs contract."""

    max_depth_tif: Path
    max_velocity_tif: Path
    arrival_time_tif: Path
    hazard_tif: Path
    depth_t_tifs: list[Path] = field(default_factory=list)
    run_meta_json: Path = field(default_factory=Path)


@runtime_checkable
class Solver(Protocol):
    """Protocol defining the lifecycle of a hydrodynamic simulation solver."""

    def prepare(self, site: Any, hydrograph: pd.DataFrame, mesh_resolution_m: float) -> RunDir:
        """Prepare grid, boundary conditions, and configuration in a working directory."""
        ...

    def run(self, run_dir: RunDir) -> RunResult:
        """Execute the hydrodynamic simulation."""
        ...

    def collect(self, run_dir: RunDir) -> Outputs:
        """Collect and validate standardized output rasters."""
        ...
