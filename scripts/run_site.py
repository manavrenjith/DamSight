"""CLI pipeline entry point for site simulation workflow."""

import argparse
import logging
import sys
from pathlib import Path

from damsight.breach import (
    StageStorageCurve,
    estimate_breach_parameters,
    generate_breach_hydrograph,
    get_dam_breach_inputs,
)
from damsight.config import load_site_config
from damsight.data.ingest import MissingDatasetError, run_ingestion

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_site")


def main():
    parser = argparse.ArgumentParser(description="DamSight Site Workflow Runner")
    parser.add_argument("--site", required=True, help="Site ID (e.g., site_a)")
    parser.add_argument(
        "--stage",
        choices=["ingest", "breach", "run", "ensemble", "surrogate", "evac", "all"],
        default="all",
        help="Pipeline stage to execute",
    )
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        default=False,
        help="Allow generating synthetic inputs if raw datasets are missing in cache",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "configs" / "sites" / f"{args.site}.yaml"
    if not config_path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        return 1

    config = load_site_config(config_path)

    if args.stage in ("ingest", "all"):
        logger.info(f"Running data ingestion stage for {args.site}...")
        try:
            report = run_ingestion(
                site=config,
                cache_root=project_root / "cache",
                allow_synthetic_fallback=args.allow_synthetic,
            )
            logger.info("Ingestion completed successfully!")
            logger.info(
                f"Report Summary:\n  CRS: {report['crs']}\n  Grid Shape: {report['grid_shape']}\n  Void Cell Pct: {report['void_cell_pct']}%\n  Depressions Filled: {report['terrain_conditioning']['cells_modified']}"
            )
        except MissingDatasetError as e:
            logger.error(f"Ingestion failed: {e}")
            logger.info(
                "To run with synthetic sample data for offline demo/testing, pass --allow-synthetic."
            )
            return 1

    if args.stage in ("breach", "all"):
        logger.info(f"Running breach hydrograph generation for {args.site}...")
        site_cache = project_root / "cache" / args.site
        site_cache.mkdir(parents=True, exist_ok=True)

        # Select dam for breach hydrograph
        target_dam = config.dams[0]
        for d in config.dams:
            if d.role == "downstream" or d.id == "machhu_2":
                target_dam = d
                break

        try:
            dam_inputs = get_dam_breach_inputs(
                target_dam,
                allow_unverified=args.allow_synthetic,
                site=config,
            )
        except ValueError as e:
            logger.error(
                f"Cannot generate breach hydrograph for '{args.site}': {e}."
            )
            return 1

        hb_val = dam_inputs["dam_height_m"]
        vw_val = dam_inputs["reservoir_volume_m3"]
        crest_val = dam_inputs["crest_elevation_m"]

        is_natural = config.type == "natural_blockage"
        breach_params = estimate_breach_parameters(
            reservoir_volume_m3=vw_val,
            breach_height_m=hb_val,
            water_depth_m=hb_val,
            mode=target_dam.breach_types[0] if target_dam.breach_types else "overtopping",
            is_natural_dam=is_natural,
        )

        stage_storage = None
        if target_dam.stage_storage_csv:
            csv_p = project_root / target_dam.stage_storage_csv
            if csv_p.exists():
                stage_storage = StageStorageCurve(
                    invert_elevation_m=crest_val - hb_val,
                    crest_elevation_m=crest_val,
                    max_volume_m3=vw_val,
                    dead_storage_m3=0.0,
                    csv_path=csv_p,
                )

        hydro_res = generate_breach_hydrograph(
            params=breach_params,
            crest_elevation_m=crest_val,
            cd_rect=1.70,
            cd_tri=1.35,
            stage_storage=stage_storage,
            dt_s=5.0,
        )

        out_csv = site_cache / "hydrograph.csv"
        out_meta = site_cache / "hydrograph_meta.json"
        hydro_res.save_csv(out_csv)
        hydro_res.save_metadata(out_meta)

        logger.info("Breach hydrograph generation completed!")
        logger.info(
            f"Breach Parameters Summary:\n  Average Width: {breach_params.breach_width_avg_m:.2f} m\n  Formation Time: {breach_params.formation_time_s:.1f} s ({breach_params.formation_time_hr:.2f} hr)\n  Froehlich (1995) Empirical Qp: {breach_params.empirical_peak_qp_m3s:.1f} m3/s\n  Hydrograph Peak Outflow: {hydro_res.peak_discharge_hydrograph_m3s:.1f} m3/s\n  Ratio (Hydrograph / Qp): {hydro_res.peak_discharge_hydrograph_m3s / breach_params.empirical_peak_qp_m3s:.3f}\n  Mass Balance Conserved: {hydro_res.mass_conserved} (Error: {hydro_res.mass_balance_error_pct:.4f}%)\n  Monotonic Drawdown: {hydro_res.drawdown_monotonic}"
        )

    if args.stage in ("run", "ensemble", "surrogate", "evac"):
        logger.info(f"Stage '{args.stage}' not implemented yet.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
