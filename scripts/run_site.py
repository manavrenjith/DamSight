"""CLI pipeline entry point for site simulation workflow."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="DamSight Site Workflow Runner")
    parser.add_argument("--site", required=True, help="Site ID (e.g., site_a)")
    parser.add_argument(
        "--stage",
        choices=["ingest", "breach", "run", "ensemble", "surrogate", "evac", "all"],
        default="all",
        help="Pipeline stage to execute",
    )
    args = parser.parse_args()
    print(f"DamSight workflow runner: site={args.site}, stage={args.stage}")
    print("Stage execution not implemented yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
