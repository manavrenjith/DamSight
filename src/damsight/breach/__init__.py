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
    get_dam_breach_inputs,
)

__all__ = [
    "BreachParameters",
    "HydrographResult",
    "StageStorageCurve",
    "estimate_breach_parameters",
    "froehlich_breach_width",
    "froehlich_formation_time",
    "froehlich_peak_outflow",
    "generate_breach_hydrograph",
    "get_dam_breach_inputs",
]
