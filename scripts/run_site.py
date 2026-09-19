"""CLI pipeline entry point for site simulation workflow."""

import argparse
import logging
import sys
from pathlib import Path

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
            logger.info(f"Report Summary:\n  CRS: {report['crs']}\n  Grid Shape: {report['grid_shape']}\n  Void Cell Pct: {report['void_cell_pct']}%\n  Depressions Filled: {report['terrain_conditioning']['cells_modified']}")
        except MissingDatasetError as e:
            logger.error(f"Ingestion failed: {e}")
            logger.info("To run with synthetic sample data for offline demo/testing, pass --allow-synthetic.")
            return 1

    if args.stage in ("breach", "run", "ensemble", "surrogate", "evac"):
        logger.info(f"Stage '{args.stage}' not implemented yet.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
