#!/usr/bin/env python3
"""Build PAC crop units and extract their Sentinel-2 NDVI time series."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/gis_monegros_matplotlib")

from monegros_ndvi.crop_timeseries import (
    aggregate_crop_curves,
    attach_pixel_indices,
    discover_scenes,
    extract_unit_observations,
    load_crop_codes,
    load_declared_crops,
    load_pivot_footprints,
    plot_barley_comparison,
    plot_crop_facets,
    plot_system_map,
    prepare_analysis_units,
    split_analysis_units_by_pivots,
    validate_scene_grid,
    write_report,
)
from monegros_ndvi.settings import (
    BASE_DIR,
    DEFAULT_BBOX,
    DEFAULT_INPUT_DIR,
    DEFAULT_MIN_VALID_FRACTION,
    PipelineError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sentinel-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--sigpac-dir", type=Path, default=BASE_DIR / "data_sigpac" / "raw")
    parser.add_argument("--crop-codes", type=Path, default=BASE_DIR / "data_reference" / "crop_codes_2025.csv")
    parser.add_argument(
        "--pivot-file",
        type=Path,
        default=BASE_DIR / "data_sigpac" / "processed" / "pivot_candidates.gpkg",
    )
    parser.add_argument("--output-dir", type=Path, default=BASE_DIR / "outputs")
    parser.add_argument("--minimum-area-ha", type=float, default=1.0)
    parser.add_argument("--boundary-buffer-m", type=float, default=10.0)
    parser.add_argument("--minimum-pixels", type=int, default=20)
    parser.add_argument(
        "--minimum-valid-fraction",
        type=float,
        default=DEFAULT_MIN_VALID_FRACTION,
    )
    parser.add_argument("--minimum-units-per-date", type=int, default=3)
    return parser


def ensure_project_output(path: Path) -> Path:
    root = BASE_DIR.resolve()
    output = path.expanduser().resolve()
    if output == root or not output.is_relative_to(root):
        raise PipelineError(f"Results must be written inside {root}.")
    return output


def main() -> int:
    args = build_parser().parse_args()
    try:
        output_dir = ensure_project_output(args.output_dir)
        scenes = discover_scenes(args.sentinel_dir)
        target_crs, transform, shape = validate_scene_grid(scenes)
        crop_codes = load_crop_codes(args.crop_codes)
        crops = load_declared_crops(args.sigpac_dir, bbox=DEFAULT_BBOX)
        base_units = prepare_analysis_units(
            crops,
            crop_codes,
            target_crs=target_crs,
            minimum_area_ha=args.minimum_area_ha,
            boundary_buffer_m=0,
        )
        pivots = load_pivot_footprints(args.pivot_file, target_crs=target_crs)
        units = split_analysis_units_by_pivots(
            base_units,
            pivots,
            minimum_area_ha=args.minimum_area_ha,
            boundary_buffer_m=args.boundary_buffer_m,
        )
        units, indices = attach_pixel_indices(
            units,
            transform=transform,
            shape=shape,
            minimum_pixels=args.minimum_pixels,
        )
        if units.empty:
            raise PipelineError("No analysis units remain after spatial filtering.")

        observations = extract_unit_observations(scenes, units, indices)
        curves = aggregate_crop_curves(
            observations,
            units,
            minimum_valid_fraction=args.minimum_valid_fraction,
            minimum_units_per_date=args.minimum_units_per_date,
        )

        processed = BASE_DIR / "data_sigpac" / "processed"
        tables = output_dir / "tables"
        figures = output_dir / "figures"
        processed.mkdir(parents=True, exist_ok=True)
        tables.mkdir(parents=True, exist_ok=True)
        figures.mkdir(parents=True, exist_ok=True)

        units_path = processed / "analysis_units_2025.gpkg"
        if units_path.exists():
            units_path.unlink()
        units.to_file(units_path, layer="analysis_units", driver="GPKG")
        observations.to_csv(tables / "unit_ndvi_timeseries.csv", index=False)
        (
            units.groupby(["system_class", "regime"])
            .agg(
                units=("unit_id", "nunique"),
                analysis_area_ha=("analysis_area_ha", "sum"),
            )
            .reset_index()
            .to_csv(tables / "analysis_unit_summary.csv", index=False)
        )
        curves.assign(date=curves["date"].dt.date).to_csv(
            tables / "crop_ndvi_timeseries.csv", index=False
        )
        plot_crop_facets(curves, figures / "ndvi_by_crop_and_regime.png")
        plot_barley_comparison(curves, figures / "ndvi_barley_regime_comparison.png")
        plot_system_map(units, pivots, scenes, figures / "analysis_units_by_system.png")
        write_report(
            output_dir / "crop_ndvi_analysis_report.json",
            units=units,
            observations=observations,
            curves=curves,
            scene_count=len(scenes),
            parameters={
                "bbox_wgs84": list(DEFAULT_BBOX),
                "minimum_area_ha": args.minimum_area_ha,
                "boundary_buffer_m": args.boundary_buffer_m,
                "minimum_pixels": args.minimum_pixels,
                "confirmed_pivot_ids": pivots["pivot_id"].tolist(),
                "system_classes": ["pivot", "irrigated_non_pivot", "dryland"],
                "pivot_rule": "confirmed footprints only; P08 excluded while low confidence",
                "minimum_valid_fraction_per_unit_date": args.minimum_valid_fraction,
                "minimum_units_per_date": args.minimum_units_per_date,
                "valid_scl_classes": [4, 5],
                "reflectance_quality": "finite B04 and B08 strictly greater than zero",
                "aggregation": (
                    "median of sample-level median NDVI; each non-pivot analysis unit "
                    "is one sample, while PAC fragments are collapsed so each physical "
                    "pivot is one sample; crop sequences and agricultural systems separated"
                ),
                "smoothing": "centred 30-day rolling median",
            },
        )
        print(f"Analysis units: {len(units)}")
        print(f"Unit-date observations: {len(observations)}")
        print(f"Crop-date curve rows: {len(curves)}")
        print(f"Results: {output_dir}")
    except (PipelineError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
