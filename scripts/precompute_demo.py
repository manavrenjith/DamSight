"""Script to precompute demo assets and save into demo_data/."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Precompute Demo Data for DamSight")
    parser.add_argument("--site", default="site_a", help="Site ID to precompute")
    args = parser.parse_args()
    print(f"Precomputing demo data for {args.site}...")
    print("Precomputation pipeline not implemented yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
