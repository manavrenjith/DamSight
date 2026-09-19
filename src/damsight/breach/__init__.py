"""Breach parameter estimation and hydrograph generation module."""

from damsight.breach.froehlich import (
    BreachParameters,
    estimate_breach_parameters,
    froehlich_breach_width,
    froehlich_formation_time,
    froehlich_peak_outflow,
)
from damsight.breach.hydrograph import (
    HydrographResult,
    StageStorageCurve,
    generate_breach_hydrograph,
)

__all__ = [
    "froehlich_breach_width",
    "froehlich_formation_time",
    "froehlich_peak_outflow",
    "estimate_breach_parameters",
    "BreachParameters",
    "StageStorageCurve",
    "HydrographResult",
    "generate_breach_hydrograph",
]
