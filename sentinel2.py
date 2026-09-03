#!/usr/bin/env python3
"""Plan or download the Sentinel-2 L2A series for the selected Monegros AOI."""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date
from pathlib import Path

from monegros_ndvi.download_sentinel2 import (
    download_time_series,
    project_output_dir,
    projected_bbox,
    target_utm_epsg,
    validate_bbox,
)
from monegros_ndvi.settings import (
    AOI_NAME,
    DEFAULT_BBOX,
    DEFAULT_END_DATE,
    DEFAULT_INPUT_DIR,
    DEFAULT_MAX_CATALOG_CLOUD_PERCENT,
    DEFAULT_RESOLUTION_M,
    DEFAULT_START_DATE,
    EXPECTED_BANDS,
    PipelineError,
)


def iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use a date in YYYY-MM-DD format.") from exc


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        default=DEFAULT_BBOX,
        help="WGS84 bounds. Defaults to the selected Monegros II AOI.",
    )
    parser.add_argument(
        "--start-date",
        type=iso_date,
        default=DEFAULT_START_DATE,
        help=f"First date (default: {DEFAULT_START_DATE}).",
    )
    parser.add_argument(
        "--end-date",
        type=iso_date,
        default=DEFAULT_END_DATE,
        help=f"Last date (default: {DEFAULT_END_DATE}).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Destination inside this project (default: {DEFAULT_INPUT_DIR}).",
    )
    parser.add_argument(
        "--max-cloud-percent",
        type=float,
        default=DEFAULT_MAX_CATALOG_CLOUD_PERCENT,
        help=(
            "Maximum catalogue cloud cover before pixel-level masking "
            f"(default: {DEFAULT_MAX_CATALOG_CLOUD_PERCENT:g}%%)."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser(
        "plan", help="Show the fixed data contract without accessing the network."
    )
    add_common_arguments(plan_parser)

    download_parser = subparsers.add_parser(
        "download", help="Download one four-band GeoTIFF per available UTC date."
    )
    add_common_arguments(download_parser)
    download_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace files that already exist for this same dataset.",
    )
    return parser


def validate_inputs(args: argparse.Namespace) -> tuple[float, float, float, float]:
    bbox = tuple(args.bbox)
    validate_bbox(bbox)
    if args.start_date > args.end_date:
        raise PipelineError("Start date must be on or before end date.")
    if not 0 <= args.max_cloud_percent <= 100:
        raise PipelineError("Maximum cloud percentage must be between 0 and 100.")
    project_output_dir(args.output_dir)
    return bbox


def show_plan(args: argparse.Namespace, bbox: tuple[float, float, float, float]) -> None:
    epsg = target_utm_epsg(bbox)
    west, south, east, north = projected_bbox(bbox, epsg)
    width = math.ceil((east - west) / DEFAULT_RESOLUTION_M)
    height = math.ceil((north - south) / DEFAULT_RESOLUTION_M)
    uncompressed_mb = width * height * len(EXPECTED_BANDS) * 4 / 1024**2

    print(AOI_NAME)
    print(f"AOI WGS84: {', '.join(f'{value:.6f}' for value in bbox)}")
    print(f"Period: {args.start_date} to {args.end_date}")
    print("Product: Sentinel-2 L2A, bottom-of-atmosphere reflectance")
    print(f"Bands: {', '.join(EXPECTED_BANDS)}")
    print(f"Grid: EPSG:{epsg}, {DEFAULT_RESOLUTION_M} m, about {width} x {height} pixels")
    print(f"Approximate uncompressed size per date: {uncompressed_mb:.1f} MiB")
    print(f"Catalogue cloud filter: <= {args.max_cloud_percent:g}%")
    print(f"Destination: {project_output_dir(args.output_dir)}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        bbox = validate_inputs(args)
        if args.command == "plan":
            show_plan(args, bbox)
        else:
            download_time_series(
                bbox=bbox,
                start_date=args.start_date,
                end_date=args.end_date,
                output_dir=args.output_dir,
                overwrite=args.overwrite,
                max_cloud_percent=args.max_cloud_percent,
                resolution_m=DEFAULT_RESOLUTION_M,
            )
    except PipelineError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
