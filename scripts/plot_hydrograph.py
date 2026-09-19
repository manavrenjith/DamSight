"""Script to generate publication-quality synthetic breach hydrograph plot saved as PNG."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from damsight.breach.froehlich import estimate_breach_parameters
from damsight.breach.hydrograph import StageStorageCurve, generate_breach_hydrograph


def plot_hydrograph(
    reservoir_volume_m3: float = 2.5e7,
    breach_height_m: float = 30.0,
    water_depth_m: float = 30.0,
    crest_elevation_m: float = 85.0,
    cd_rect: float = 1.70,
    cd_tri: float = 1.35,
    mode: str = "overtopping",
    output_png: Path = Path("docs/SLIDE_FIGURES/hydrograph_SYNTHETIC_example.png"),
) -> None:
    """Simulate and plot 3-panel breach hydrograph using explicit synthetic inputs.

    Strictly uses synthetic inputs, never reads site_a dam values.
    Stamps 'SYNTHETIC INPUTS, NOT MACHHU-II' plus input values on figure.
    """
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
        dead_storage_m3=0.0,
    )

    res = generate_breach_hydrograph(
        params=params,
        crest_elevation_m=crest_elevation_m,
        cd_rect=cd_rect,
        cd_tri=cd_tri,
        stage_storage=stage_storage,
        dt_s=5.0,
        cutoff_q_ratio=0.01,
    )

    # Compute key hydrograph metrics
    active_vol = res.active_storage_volume_m3
    drained_vol = res.total_outflow_volume_m3
    residual_vol = max(
        0.0, res.remaining_reservoir_volume_m3 - (res.initial_stored_volume_m3 - active_vol)
    )
    residual_frac = residual_vol / active_vol if active_vol > 0 else 0.0
    frac_drained = min(1.0, drained_vol / active_vol) if active_vol > 0 else 0.0
    final_stage = float(res.stage_m[-1])
    first_clamp = res.first_clamp_step

    print("\n--- SYNTHETIC HYDROGRAPH SIMULATION REPORT ---")
    print(
        f"  Residual above-invert volume:            {residual_frac * 100.0:.3f}% ({residual_vol:.1f} / {active_vol:.1f} m³)"
    )
    print(
        f"  Fraction of above-invert storage drained: {frac_drained * 100.0:.2f}% ({drained_vol:.1f} / {active_vol:.1f} m³)"
    )
    print(
        f"  Final stage:                             {final_stage:.2f} m (Invert: {crest_elevation_m - breach_height_m:.2f} m)"
    )
    print(
        f"  First clamp binding step:                {('Step ' + str(first_clamp) + f' (t = {first_clamp * 5.0:.1f} s)') if first_clamp is not None else 'None (0 clamp events)'}"
    )
    print(
        f"  Total steps executed:                    {len(res.time_s)} (Final outflow Q = {res.discharge_m3s[-1]:.4f} m³/s)"
    )
    print(
        f"  Peak outflow:                            {res.peak_discharge_hydrograph_m3s:.1f} m³/s"
    )
    print("----------------------------------------------\n")

    time_hr = res.time_s / 3600.0
    cum_vol_mcm = np.cumsum(res.discharge_m3s * 5.0) / 1e6
    stored_mcm = reservoir_volume_m3 / 1e6

    fig, axes = plt.subplots(3, 1, figsize=(9.5, 11), sharex=True)

    # Prominent disclaimer watermark / banner
    banner_text = (
        "SYNTHETIC INPUTS, NOT MACHHU-II\n"
        f"Inputs: Vw={reservoir_volume_m3 / 1e6:.1f} MCM | hb={breach_height_m:.1f} m | "
        f"hw={water_depth_m:.1f} m | crest={crest_elevation_m:.1f} m | Cd_rect={cd_rect:.2f} | Cd_tri={cd_tri:.2f}"
    )
    fig.text(
        0.5,
        0.965,
        banner_text,
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
        color="#b30000",
        bbox={
            "boxstyle": "round,pad=0.5",
            "facecolor": "#ffe6e6",
            "edgecolor": "#cc0000",
            "lw": 1.5,
        },
    )

    # 1. Hydrograph Discharge Q(t)
    ax1 = axes[0]
    ax1.plot(time_hr, res.discharge_m3s, color="#1f77b4", lw=2, label="Hydrograph Outflow Q(t)")

    # Froehlich empirical Qp comparisons
    qp_30 = 0.607 * (reservoir_volume_m3**0.295) * (breach_height_m**1.24)
    qp_hw = 0.607 * (reservoir_volume_m3**0.295) * (water_depth_m**1.24)
    ratio_30 = res.peak_discharge_hydrograph_m3s / qp_30 if qp_30 > 0 else 0.0

    ax1.axhline(
        qp_30,
        color="#d62728",
        ls="--",
        lw=1.5,
        label=f"Froehlich (1995) Q_p (h_w=30m: {qp_30:.0f} m³/s, ratio={ratio_30:.2f}x)",
    )
    if abs(qp_hw - qp_30) > 10.0:
        ratio_hw = res.peak_discharge_hydrograph_m3s / qp_hw if qp_hw > 0 else 0.0
        ax1.axhline(
            qp_hw,
            color="#9467bd",
            ls=":",
            lw=1.5,
            label=f"Froehlich (1995) Q_p (h_w={water_depth_m:.1f}m: {qp_hw:.0f} m³/s, ratio={ratio_hw:.2f}x)",
        )

    peak_idx = int(np.argmax(res.discharge_m3s))
    ax1.scatter([time_hr[peak_idx]], [res.peak_discharge_hydrograph_m3s], color="#2ca02c", s=40, zorder=5)
    ax1.annotate(
        f"Simulated Peak: {res.peak_discharge_hydrograph_m3s:.1f} m³/s\n"
        f"@ t = {time_hr[peak_idx]:.2f} hr\n"
        f"Ratio to Q_p(30m): {ratio_30:.2f}x",
        xy=(time_hr[peak_idx], res.peak_discharge_hydrograph_m3s),
        xytext=(time_hr[peak_idx] + 0.35, res.peak_discharge_hydrograph_m3s * 0.92),
        arrowprops={"facecolor": "#2ca02c", "edgecolor": "#1b611b", "shrink": 0.05, "width": 1.2, "headwidth": 6},
        fontsize=8.5,
        fontweight="bold",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "#f0fff0", "edgecolor": "#2ca02c", "alpha": 0.95},
    )
    ax1.set_ylabel("Discharge (m³/s)", fontsize=11)
    ax1.set_title(
        "Synthetic Breach Outflow Hydrograph, Stage Drawdown & Volume",
        fontsize=12,
        fontweight="bold",
        pad=15,
    )
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper right", frameon=True, fontsize=8.5)

    # 2. Reservoir Water Surface Stage H(t)
    ax2 = axes[1]
    ax2.plot(time_hr, res.stage_m, color="#ff7f0e", lw=2, label="Reservoir Stage H(t)")
    ax2.plot(
        time_hr, res.breach_invert_m, color="#8c564b", ls=":", lw=1.5, label="Breach Invert z_b(t)"
    )
    ax2.axhline(
        crest_elevation_m,
        color="#7f7f7f",
        ls="--",
        alpha=0.7,
        label=f"Crest ({crest_elevation_m:.1f} m)",
    )
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
        label=f"Initial Active Storage ({stored_mcm:.1f} MCM)",
    )
    ax3.set_xlabel("Time since failure (hours)", fontsize=11)
    ax3.set_ylabel("Volume (MCM)", fontsize=11)
    ax3.grid(True, alpha=0.3)
    ax3.legend(loc="lower right", frameon=True)

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    plt.savefig(output_png, dpi=150)
    plt.close()
    print(f"Hydrograph plot saved to: {output_png}")


def main():
    parser = argparse.ArgumentParser(description="Plot DamSight Synthetic Breach Hydrograph")
    parser.add_argument(
        "--output",
        default="docs/SLIDE_FIGURES/hydrograph_SYNTHETIC_example.png",
        help="Output PNG path",
    )
    parser.add_argument("--vw", type=float, default=2.5e7, help="Reservoir volume (m3)")
    parser.add_argument("--hb", type=float, default=30.0, help="Breach height (m)")
    parser.add_argument("--hw", type=float, default=30.0, help="Water depth (m)")
    parser.add_argument("--crest", type=float, default=85.0, help="Crest elevation (m)")
    args = parser.parse_args()

    plot_hydrograph(
        reservoir_volume_m3=args.vw,
        breach_height_m=args.hb,
        water_depth_m=args.hw,
        crest_elevation_m=args.crest,
        cd_rect=1.70,
        cd_tri=1.35,
        output_png=Path(args.output),
    )


if __name__ == "__main__":
    main()
