"""Physically consistent breach hydrograph generator using level-pool routing."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from damsight.breach.froehlich import BreachParameters


class StageStorageCurve:
    """Represents a reservoir elevation-volume (stage-storage) relationship."""

    def __init__(
        self,
        invert_elevation_m: float,
        crest_elevation_m: float,
        max_volume_m3: float,
        csv_path: Optional[Union[str, Path]] = None,
        power_law_exponent: float = 2.0,
    ):
        self.invert_elevation_m = float(invert_elevation_m)
        self.crest_elevation_m = float(crest_elevation_m)
        self.max_volume_m3 = float(max_volume_m3)
        self.height_m = max(0.1, self.crest_elevation_m - self.invert_elevation_m)
        self.p = float(power_law_exponent)

        self.stages: Optional[np.ndarray] = None
        self.volumes: Optional[np.ndarray] = None

        if csv_path is not None and Path(csv_path).exists():
            self._load_from_csv(Path(csv_path))

    def _load_from_csv(self, path: Path) -> None:
        """Load stage-storage table from CSV."""
        df = pd.read_csv(path)
        # Expect columns stage_m (or elevation_m) and volume_m3
        stage_col = [c for c in df.columns if "stage" in c.lower() or "elev" in c.lower()][0]
        vol_col = [c for c in df.columns if "vol" in c.lower()][0]
        sorted_df = df.sort_values(by=stage_col)
        self.stages = sorted_df[stage_col].to_numpy(dtype=float)
        self.volumes = sorted_df[vol_col].to_numpy(dtype=float)

    def volume_to_stage(self, volume_m3: float) -> float:
        """Compute reservoir water stage for a given storage volume."""
        v = max(0.0, min(volume_m3, self.max_volume_m3))
        if self.volumes is not None and self.stages is not None:
            return float(np.interp(v, self.volumes, self.stages))

        # Default parametric power law: V(H) = V_max * ((H - z_inv) / h)^p
        # => H = z_inv + h * (V / V_max) ** (1 / p)
        frac = v / self.max_volume_m3
        stage = self.invert_elevation_m + self.height_m * (frac ** (1.0 / self.p))
        return float(stage)

    def stage_to_volume(self, stage_m: float) -> float:
        """Compute storage volume for a given reservoir water stage."""
        h = max(0.0, stage_m - self.invert_elevation_m)
        if self.volumes is not None and self.stages is not None:
            return float(np.interp(stage_m, self.stages, self.volumes))

        frac = min(1.0, h / self.height_m)
        vol = self.max_volume_m3 * (frac ** self.p)
        return float(vol)


@dataclass
class HydrographResult:
    """Breach hydrograph simulation results and comparison metrics."""

    time_s: np.ndarray
    discharge_m3s: np.ndarray
    stage_m: np.ndarray
    volume_m3: np.ndarray
    breach_width_m: np.ndarray
    breach_invert_m: np.ndarray

    peak_discharge_hydrograph_m3s: float
    empirical_peak_qp_m3s: float
    time_to_peak_s: float
    total_outflow_volume_m3: float
    initial_stored_volume_m3: float
    mass_conserved: bool
    mass_balance_error_pct: float
    drawdown_monotonic: bool
    is_natural_dam: bool

    def to_dataframe(self) -> pd.DataFrame:
        """Export time series to pandas DataFrame."""
        return pd.DataFrame({
            "time_s": self.time_s,
            "discharge_m3s": np.round(self.discharge_m3s, 3),
            "stage_m": np.round(self.stage_m, 3),
            "volume_m3": np.round(self.volume_m3, 1),
            "breach_width_m": np.round(self.breach_width_m, 3),
            "breach_invert_m": np.round(self.breach_invert_m, 3),
        })

    def save_csv(self, path: Union[str, Path]) -> None:
        """Save hydrograph time series to CSV."""
        df = self.to_dataframe()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)

    def save_metadata(self, path: Union[str, Path]) -> None:
        """Save simulation metadata and comparison metrics to JSON."""
        meta = {
            "peak_hydrograph_m3s": round(self.peak_discharge_hydrograph_m3s, 2),
            "empirical_froehlich_qp_m3s": round(self.empirical_peak_qp_m3s, 2),
            "time_to_peak_s": round(self.time_to_peak_s, 1),
            "time_to_peak_min": round(self.time_to_peak_s / 60.0, 2),
            "total_outflow_volume_m3": round(self.total_outflow_volume_m3, 1),
            "initial_stored_volume_m3": round(self.initial_stored_volume_m3, 1),
            "mass_conserved": self.mass_conserved,
            "mass_balance_error_pct": round(self.mass_balance_error_pct, 4),
            "drawdown_monotonic": self.drawdown_monotonic,
            "is_natural_dam": self.is_natural_dam,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)


def generate_breach_hydrograph(
    params: BreachParameters,
    stage_storage: Optional[StageStorageCurve] = None,
    total_duration_s: Optional[float] = None,
    dt_s: float = 10.0,
    crest_elevation_m: float = 100.0,
    cd_rect: float = 1.70,
    cd_tri: float = 1.35,
) -> HydrographResult:
    """Generate physically consistent outflow hydrograph through growing trapezoidal breach.

    Simulates broad-crested weir flow coupled with reservoir drawdown (level-pool routing).
    Strictly guarantees:
        1. Outflow volume <= Initial stored volume
        2. Monotonic reservoir stage drawdown
    """
    v_init = params.reservoir_volume_m3
    h_b = params.breach_height_m
    t_f = max(dt_s, params.formation_time_s)
    z_crest = crest_elevation_m
    z_bottom = z_crest - h_b

    if stage_storage is None:
        stage_storage = StageStorageCurve(
            invert_elevation_m=z_bottom,
            crest_elevation_m=z_crest,
            max_volume_m3=v_init,
        )
    else:
        z_crest = stage_storage.crest_elevation_m
        z_bottom = z_crest - h_b

    # Simulation runs until reservoir drained or specified duration
    duration = total_duration_s or max(t_f * 3.5, 7200.0)
    n_steps = int(math.ceil(duration / dt_s)) + 1

    time_arr = np.zeros(n_steps, dtype=np.float32)
    q_arr = np.zeros(n_steps, dtype=np.float32)
    stage_arr = np.zeros(n_steps, dtype=np.float32)
    vol_arr = np.zeros(n_steps, dtype=np.float32)
    width_arr = np.zeros(n_steps, dtype=np.float32)
    invert_arr = np.zeros(n_steps, dtype=np.float32)

    curr_vol = v_init
    curr_stage = stage_storage.volume_to_stage(curr_vol)

    final_w = params.bottom_width_m
    side_z = params.side_slope_z

    for i in range(n_steps):
        t = i * dt_s
        time_arr[i] = t
        stage_arr[i] = curr_stage
        vol_arr[i] = curr_vol

        # Breach expansion phase [0, t_f]
        frac_formed = min(1.0, t / t_f)
        # Linear/sigmoidal breach bottom incision from z_crest down to z_bottom
        z_b = z_crest - (h_b * frac_formed)
        # Bottom width growth from 0 up to final_w
        w_b = final_w * frac_formed

        invert_arr[i] = z_b
        width_arr[i] = w_b

        # Head of water above current breach invert
        h_water = max(0.0, curr_stage - z_b)

        if h_water > 0.0 and curr_vol > 0.0:
            # Broad-crested trapezoidal weir flow:
            # Rectangular component: Cd1 * W_b * h^(1.5)
            # Triangular sides component: Cd2 * Z * h^(2.5)
            q_weir = cd_rect * w_b * (h_water ** 1.5) + cd_tri * side_z * (h_water ** 2.5)

            # Mass conservation clamp: cannot drain more than available volume in interval dt
            max_drain_vol = curr_vol
            actual_drain_vol = min(max_drain_vol, q_weir * dt_s)
            actual_q = actual_drain_vol / dt_s

            curr_vol = max(0.0, curr_vol - actual_drain_vol)
            curr_stage = stage_storage.volume_to_stage(curr_vol)
        else:
            actual_q = 0.0

        q_arr[i] = actual_q

    # Calculate metrics
    peak_q = float(np.max(q_arr))
    time_to_peak = float(time_arr[np.argmax(q_arr)])
    total_outflow = float(np.sum(q_arr * dt_s))
    mass_err_pct = abs(total_outflow - (v_init - curr_vol)) / v_init * 100.0
    mass_conserved = total_outflow <= (v_init + 1e-4)

    # Monotonicity check on stage drawdown
    stage_diffs = np.diff(stage_arr)
    drawdown_monotonic = bool(np.all(stage_diffs <= 1e-6))

    return HydrographResult(
        time_s=time_arr,
        discharge_m3s=q_arr,
        stage_m=stage_arr,
        volume_m3=vol_arr,
        breach_width_m=width_arr,
        breach_invert_m=invert_arr,
        peak_discharge_hydrograph_m3s=peak_q,
        empirical_peak_qp_m3s=params.empirical_peak_qp_m3s,
        time_to_peak_s=time_to_peak,
        total_outflow_volume_m3=total_outflow,
        initial_stored_volume_m3=v_init,
        mass_conserved=mass_conserved,
        mass_balance_error_pct=mass_err_pct,
        drawdown_monotonic=drawdown_monotonic,
        is_natural_dam=params.is_natural_dam,
    )
