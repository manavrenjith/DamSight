"""Script to generate publication-quality breach hydrograph plot saved as PNG."""

import argparse
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

from damsight.breach.froehlich import estimate_breach_parameters
from damsight.breach.hydrograph import StageStorageCurve, generate_breach_hydrograph


def plot_hydrograph(
    reservoir_volume_m3: float = 2.5e7,
    breach_height_m: float = 30.0,
    water_depth_m: float = 27.5,
    crest_elevation_m: float = 85.0,
    mode: str = "overtopping",
    output_png: Path = Path("docs/SLIDE_FIGURES/hydrograph_site_a.png"),
) -> None:
    """Simulate and plot 3-panel breach hydrograph: Q(t), Stage(t), and Cumulative Volume."""
    output_png.parent.mkdir(parents=True, exist_ok=True)

    params = estimate_breach_parameters(
        reservoir_volume_m3=reservoir_volume_m3,
        breach_height_m=breach_height_m,
        water_depth_m=water_depth_m,
        mode=mode,
    )

    stage_storage = StageStorageCurve(
        invert_elevation_m=crest_elevation_m - breach_height_m,
        crest_elevation_m=crest_elevation_m,
        max_volume_m3=reservoir_volume_m3,
    )

    res = generate_breach_hydrograph(
        params=params,
        stage_storage=stage_storage,
        crest_elevation_m=crest_elevation_m,
        dt_s=5.0,
    )

    time_hr = res.time_s / 3600.0
    cum_vol_mcm = np.cumsum(res.discharge_m3s * 5.0) / 1e6
    stored_mcm = reservoir_volume_m3 / 1e6

    fig, axes = plt.subplots(3, 1, figsize=(9, 10), sharex=True)

    # 1. Hydrograph Discharge Q(t)
    ax1 = axes[0]
    ax1.plot(time_hr, res.discharge_m3s, color="#1f77b4", lw=2, label="Hydrograph Outflow Q(t)")
    ax1.axhline(
        params.empirical_peak_qp_m3s,
        color="#d62728",
        ls="--",
        label=f"Froehlich (1995) Empirical Q_p ({params.empirical_peak_qp_m3s:.1f} m³/s)",
    )
    peak_idx = np.argmax(res.discharge_m3s)
    ax1.scatter([time_hr[peak_idx]], [res.peak_discharge_hydrograph_m3s], color="#2ca02c", zorder=5)
    ax1.annotate(
        f"Peak: {res.peak_discharge_hydrograph_m3s:.1f} m³/s\n@ {time_hr[peak_idx]:.2f} hr",
        xy=(time_hr[peak_idx], res.peak_discharge_hydrograph_m3s),
        xytext=(time_hr[peak_idx] + 0.4, res.peak_discharge_hydrograph_m3s * 0.85),
        arrowprops=dict(facecolor="black", shrink=0.05, width=1, headwidth=6),
        fontsize=9,
        fontweight="bold",
    )
    ax1.set_ylabel("Discharge (m³/s)", fontsize=11)
    ax1.set_title("Breach Outflow Hydrograph, Stage Drawdown & Cumulative Volume", fontsize=13, fontweight="bold")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper right", frameon=True)

    # 2. Reservoir Water Surface Stage H(t)
    ax2 = axes[1]
    ax2.plot(time_hr, res.stage_m, color="#ff7f0e", lw=2, label="Reservoir Stage H(t)")
    ax2.plot(time_hr, res.breach_invert_m, color="#8c564b", ls=":", lw=1.5, label="Breach Invert z_b(t)")
    ax2.axhline(crest_elevation_m, color="#7f7f7f", ls="--", alpha=0.7, label=f"Crest ({crest_elevation_m:.1f} m)")
    ax2.axhline(
        crest_elevation_m - breach_height_m,
        color="#bcbd22",
        ls="--",
        alpha=0.7,
        label=f"Final Invert ({(crest_elevation_m - breach_height_m):.1f} m)",
    )
    ax2.set_ylabel("Elevation (m)", fontsize=11)
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="upper right", frameon=True)

    # 3. Cumulative Outflow vs Stored Volume
    ax3 = axes[2]
    ax3.plot(time_hr, cum_vol_mcm, color="#2ca02c", lw=2, label="Cumulative Outflow Volume")
    ax3.axhline(
        stored_mcm,
        color="#000000",
        ls="--",
        lw=1.5,
        label=f"Initial Stored Active Volume ({stored_mcm:.1f} MCM)",
    )
    ax3.set_xlabel("Time since failure (hours)", fontsize=11)
    ax3.set_ylabel("Volume (MCM)", fontsize=11)
    ax3.grid(True, alpha=0.3)
    ax3.legend(loc="lower right", frameon=True)

    plt.tight_layout()
    plt.savefig(output_png, dpi=150)
    plt.close()
    print(f"Hydrograph plot saved to: {output_png}")


def main():
    parser = argparse.ArgumentParser(description="Plot DamSight Breach Hydrograph")
    parser.add_argument("--output", default="docs/SLIDE_FIGURES/hydrograph_site_a.png", help="Output PNG path")
    parser.add_argument("--vw", type=float, default=2.5e7, help="Reservoir volume (m3)")
    parser.add_argument("--hb", type=float, default=30.0, help="Breach height (m)")
    parser.add_argument("--hw", type=float, default=27.5, help="Water depth (m)")
    args = parser.parse_args()

    plot_hydrograph(
        reservoir_volume_m3=args.vw,
        breach_height_m=args.hb,
        water_depth_m=args.hw,
        output_png=Path(args.output),
    )


if __name__ == "__main__":
    main()
