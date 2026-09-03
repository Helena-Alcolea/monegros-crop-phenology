#!/usr/bin/env python3
"""Build compact tables, GeoJSON and monthly RGB assets for Streamlit."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from monegros_ndvi.app_assets import (
    APP_DATA_DIR,
    download_monthly_rgb,
    prepare_tabular_assets,
    select_monthly_scenes,
)
from monegros_ndvi.settings import BASE_DIR, DEFAULT_INPUT_DIR, PipelineError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=APP_DATA_DIR)
    parser.add_argument("--download-rgb", action="store_true")
    parser.add_argument("--overwrite-rgb", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        groups = prepare_tabular_assets(
            BASE_DIR / "outputs" / "tables" / "crop_ndvi_timeseries.csv",
            BASE_DIR / "data_sigpac" / "processed" / "analysis_units_2025.gpkg",
            args.output_dir,
        )
        selected = select_monthly_scenes(DEFAULT_INPUT_DIR)
        if args.download_rgb:
            download_monthly_rgb(selected, args.output_dir, overwrite=args.overwrite_rgb)
        print(f"Streamlit groups: {len(groups)}")
        print(f"Representative months: {len(selected)}")
        print(f"Output: {args.output_dir.resolve()}")
    except (PipelineError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
