"""Empirical breach parameter formulations based on Froehlich (1995, 2008)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class BreachParameters:
    """Calculated empirical breach geometry and timing parameters."""

    breach_width_avg_m: float
    formation_time_s: float
    formation_time_hr: float
    side_slope_z: float  # Z horizontal to 1 vertical
    bottom_width_m: float
    breach_height_m: float
    water_depth_m: float
    reservoir_volume_m3: float
    mode: str  # overtopping | piping
    empirical_peak_qp_m3s: float
    is_natural_dam: bool = False
    parameter_status: str = "verified_formula"  # verified_formula | illustrative
    notes: Optional[str] = None


def froehlich_breach_width(
    reservoir_volume_m3: float,
    breach_height_m: float,
    mode: Literal["overtopping", "piping"] = "overtopping",
) -> float:
    """Calculate average breach width (B_avg) in meters using Froehlich (2008).

    Formula (SI units):
        B_avg = 0.27 * K_o * (V_w ** 0.32) * (h_b ** 0.04)
    Where:
        K_o = 1.3 for overtopping failure
        K_o = 1.0 for piping / seepage failure
        V_w = reservoir volume above breach bottom at time of failure (m^3)
        h_b = height of breach (m)
    """
    if reservoir_volume_m3 <= 0:
        raise ValueError("Reservoir volume must be strictly positive")
    if breach_height_m <= 0:
        raise ValueError("Breach height must be strictly positive")

    k_o = 1.3 if mode.lower() == "overtopping" else 1.0
    b_avg = 0.27 * k_o * (reservoir_volume_m3 ** 0.32) * (breach_height_m ** 0.04)
    return float(b_avg)


def froehlich_formation_time(
    reservoir_volume_m3: float,
    breach_height_m: float,
    g: float = 9.80665,
) -> float:
    """Calculate breach formation time (t_f) in seconds using Froehlich (2008).

    Formula (SI units):
        t_f = 63.2 * sqrt(V_w / (g * h_b^2))
    Where:
        V_w = reservoir volume above breach bottom at time of failure (m^3)
        h_b = height of breach (m)
        g = acceleration due to gravity (m/s^2, default 9.80665)
    """
    if reservoir_volume_m3 <= 0:
        raise ValueError("Reservoir volume must be strictly positive")
    if breach_height_m <= 0:
        raise ValueError("Breach height must be strictly positive")

    ratio = reservoir_volume_m3 / (g * (breach_height_m ** 2))
    t_f = 63.2 * math.sqrt(ratio)
    return float(t_f)


def froehlich_peak_outflow(
    reservoir_volume_m3: float,
    water_depth_m: float,
) -> float:
    """Calculate empirical peak breach outflow (Q_p) in m^3/s using Froehlich (1995).

    Formula (SI units):
        Q_p = 0.607 * (V_w ** 0.295) * (h_w ** 1.24)
    Where:
        V_w = reservoir volume above breach bottom at time of failure (m^3)
        h_w = depth of water above breach invert at time of failure (m)
    """
    if reservoir_volume_m3 <= 0:
        raise ValueError("Reservoir volume must be strictly positive")
    if water_depth_m <= 0:
        raise ValueError("Water depth must be strictly positive")

    q_p = 0.607 * (reservoir_volume_m3 ** 0.295) * (water_depth_m ** 1.24)
    return float(q_p)


def estimate_breach_parameters(
    reservoir_volume_m3: float,
    breach_height_m: float,
    water_depth_m: Optional[float] = None,
    mode: Literal["overtopping", "piping"] = "overtopping",
    side_slope_z: Optional[float] = None,
    is_natural_dam: bool = False,
) -> BreachParameters:
    """Compute complete set of empirical breach parameters.

    If is_natural_dam is True, adjusts formation time and width for unconsolidated
    landslide/blockage material and marks parameters as illustrative.
    """
    h_w = water_depth_m if water_depth_m is not None else breach_height_m

    b_avg = froehlich_breach_width(reservoir_volume_m3, breach_height_m, mode=mode)
    t_f = froehlich_formation_time(reservoir_volume_m3, breach_height_m)
    q_p = froehlich_peak_outflow(reservoir_volume_m3, h_w)

    # Default side slope Z (H:1V): Froehlich (2008) recommends Z=1.0 for overtopping, 0.7 for piping
    if side_slope_z is None:
        z = 1.0 if mode.lower() == "overtopping" else 0.7
    else:
        z = float(side_slope_z)

    # In a trapezoid: B_avg = W_bottom + Z * h_b => W_bottom = B_avg - Z * h_b
    w_bottom = max(0.0, b_avg - z * breach_height_m)

    status = "verified_formula"
    notes = "Standard Froehlich (1995/2008) embankment dam equations."

    if is_natural_dam:
        # Natural blockage / moraine dams feature loose unconsolidated debris.
        # Accelerated erosion factor: formation time is shortened (e.g. 40% of engineered embankment)
        # and width expands by 25%.
        t_f *= 0.40
        b_avg *= 1.25
        w_bottom = max(0.0, b_avg - z * breach_height_m)
        status = "illustrative"
        notes = "Natural dam variant: accelerated erosion in unconsolidated debris (illustrative parameters)."

    return BreachParameters(
        breach_width_avg_m=round(b_avg, 3),
        formation_time_s=round(t_f, 2),
        formation_time_hr=round(t_f / 3600.0, 3),
        side_slope_z=z,
        bottom_width_m=round(w_bottom, 3),
        breach_height_m=breach_height_m,
        water_depth_m=h_w,
        reservoir_volume_m3=reservoir_volume_m3,
        mode=mode,
        empirical_peak_qp_m3s=round(q_p, 2),
        is_natural_dam=is_natural_dam,
        parameter_status=status,
        notes=notes,
    )
