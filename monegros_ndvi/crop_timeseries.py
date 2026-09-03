"""Parcel-level Sentinel-2 NDVI extraction for declared PAC crops."""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

os.environ.setdefault("MPLCONFIGDIR", "/tmp/gis_monegros_matplotlib")

import geopandas as gpd
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.patches import Patch
from rasterio.features import geometry_mask
from shapely.geometry import box, mapping

from .settings import DEFAULT_BBOX, EXPECTED_BANDS, PipelineError


SCENE_PATTERN = re.compile(r"^S2L2A_(\d{4}-\d{2}-\d{2})_B04_B08_SCL_10m\.tif$")
CLEAR_SCL_CLASSES = (4, 5)
PROVINCE_CODES = ("0222", "0250")
SYSTEM_LABELS = {
    "dryland": "secano",
    "irrigated_non_pivot": "regadío sin pivote",
    "pivot": "pivote central",
}
SYSTEM_COLORS = {
    "dryland": "#d49a45",
    "irrigated_non_pivot": "#247a4d",
    "pivot": "#2962a3",
}


def discover_scenes(input_dir: Path) -> list[tuple[pd.Timestamp, Path]]:
    scenes: list[tuple[pd.Timestamp, Path]] = []
    for path in sorted(input_dir.glob("S2L2A_*_B04_B08_SCL_10m.tif")):
        match = SCENE_PATTERN.match(path.name)
        if match:
            scenes.append((pd.Timestamp(match.group(1)), path))
    if not scenes:
        raise PipelineError(f"No compatible Sentinel-2 scenes found in {input_dir}.")
    return scenes


def validate_scene_grid(
    scenes: Iterable[tuple[pd.Timestamp, Path]],
) -> tuple[object, object, tuple[int, int]]:
    expected = None
    for _, path in scenes:
        with rasterio.open(path) as dataset:
            signature = (
                dataset.crs,
                dataset.transform,
                dataset.height,
                dataset.width,
                dataset.count,
                dataset.dtypes,
            )
            if dataset.count != len(EXPECTED_BANDS) or set(dataset.dtypes) != {"float32"}:
                raise PipelineError(f"Unexpected band contract in {path.name}.")
            if expected is None:
                expected = signature
            elif signature != expected:
                raise PipelineError(f"Scene grid differs from the first scene: {path.name}.")
    if expected is None:
        raise PipelineError("Cannot determine the Sentinel-2 grid.")
    crs, transform, height, width, _, _ = expected
    return crs, transform, (height, width)


def load_crop_codes(path: Path) -> pd.DataFrame:
    table = pd.read_csv(path)
    required = {"product_code", "crop_name", "crop_group"}
    if not required.issubset(table.columns):
        raise PipelineError(f"Crop-code table lacks columns: {sorted(required - set(table.columns))}")
    table["product_code"] = table["product_code"].astype(int)
    return table


def _find_one(data_dir: Path, pattern: str) -> Path:
    matches = sorted(data_dir.glob(pattern))
    if len(matches) != 1:
        names = ", ".join(item.name for item in matches) or "none"
        raise PipelineError(f"Expected one file matching {pattern!r}; found {names}.")
    return matches[0]


def load_declared_crops(
    data_dir: Path,
    *,
    bbox: tuple[float, float, float, float] = DEFAULT_BBOX,
) -> gpd.GeoDataFrame:
    columns = [
        "provincia",
        "municipio",
        "poligono",
        "parcela",
        "recinto",
        "exp_ano",
        "parc_producto",
        "parc_sistexp",
        "parc_supcult",
        "cultsecun_producto",
        "dn_surface",
    ]
    frames: list[gpd.GeoDataFrame] = []
    for province_code in PROVINCE_CODES:
        source = _find_one(data_dir, f"{province_code}_*_cd_2025_*.gpkg")
        frame = gpd.read_file(
            source,
            layer="cultivo_declarado",
            bbox=bbox,
            columns=columns,
            engine="pyogrio",
            use_arrow=False,
        )
        if frame.crs is None:
            raise PipelineError(f"{source.name} has no coordinate system.")
        if not frame.empty:
            frame = frame.to_crs(4258)
            frame["source_file"] = source.name
            frames.append(frame)
    if not frames:
        raise PipelineError("No declared crops intersect the selected AOI.")

    crops = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True), geometry="geometry", crs="EPSG:4258"
    )
    invalid = ~crops.geometry.is_valid
    if invalid.any():
        crops.loc[invalid, "geometry"] = crops.loc[invalid, "geometry"].make_valid()
    crops = crops[crops.geometry.notna() & ~crops.geometry.is_empty].copy()
    return gpd.clip(crops, gpd.GeoSeries([box(*bbox)], crs=4258), keep_geom_type=True)


def prepare_analysis_units(
    crops: gpd.GeoDataFrame,
    crop_codes: pd.DataFrame,
    *,
    target_crs: object,
    minimum_area_ha: float,
    boundary_buffer_m: float,
) -> gpd.GeoDataFrame:
    if minimum_area_ha <= 0:
        raise PipelineError("Minimum unit area must be positive.")
    if boundary_buffer_m < 0:
        raise PipelineError("Boundary buffer cannot be negative.")

    units = crops.to_crs(target_crs).copy()
    units["product_code"] = pd.to_numeric(units["parc_producto"], errors="coerce").astype("Int64")
    units["secondary_product_code"] = pd.to_numeric(
        units["cultsecun_producto"], errors="coerce"
    ).astype("Int64")
    units["regime"] = units["parc_sistexp"].astype("string")
    units["clipped_area_ha"] = units.geometry.area / 10_000
    units = units[
        units["product_code"].notna()
        & units["regime"].isin(["R", "S"])
        & (units["clipped_area_ha"] >= minimum_area_ha)
    ].copy()

    units = units.merge(crop_codes, on="product_code", how="left")
    units["crop_name"] = units["crop_name"].fillna(
        units["product_code"].map(lambda value: f"Código {int(value)}")
    )
    units["crop_group"] = units["crop_group"].fillna("Sin clasificar")
    secondary_codes = crop_codes[["product_code", "crop_name"]].rename(
        columns={
            "product_code": "secondary_product_code",
            "crop_name": "secondary_crop_name",
        }
    )
    units = units.merge(secondary_codes, on="secondary_product_code", how="left")
    unknown_secondary = units["secondary_product_code"].notna() & units["secondary_crop_name"].isna()
    units.loc[unknown_secondary, "secondary_crop_name"] = units.loc[
        unknown_secondary, "secondary_product_code"
    ].map(lambda value: f"Código {int(value)}")
    units["crop_sequence"] = units["crop_name"]
    has_secondary = units["secondary_product_code"].notna()
    units.loc[has_secondary, "crop_sequence"] = (
        units.loc[has_secondary, "crop_name"]
        + " → "
        + units.loc[has_secondary, "secondary_crop_name"].astype(str)
    )
    if boundary_buffer_m:
        units.geometry = units.geometry.buffer(-boundary_buffer_m)
    units = units[units.geometry.notna() & ~units.geometry.is_empty].copy()
    units["analysis_area_ha"] = units.geometry.area / 10_000
    units = units.sort_values(
        ["product_code", "regime", "provincia", "municipio", "poligono", "parcela", "recinto"]
    ).reset_index(drop=True)
    units.insert(0, "unit_id", [f"U{index:04d}" for index in range(1, len(units) + 1)])
    return units


def load_pivot_footprints(path: Path, *, target_crs: object) -> gpd.GeoDataFrame:
    """Load only the manually confirmed centre-pivot footprints."""
    if not path.exists():
        raise PipelineError(f"Pivot footprint file does not exist: {path}.")
    pivots = gpd.read_file(path, layer="pivot_footprints")
    required = {"pivot_id", "status", "geometry"}
    if not required.issubset(pivots.columns):
        raise PipelineError(
            f"Pivot footprint layer lacks columns: {sorted(required - set(pivots.columns))}"
        )
    if pivots.crs is None:
        raise PipelineError("Pivot footprint layer has no coordinate system.")
    pivots = pivots[pivots["status"] == "confirmed"].copy()
    pivots = pivots[pivots.geometry.notna() & ~pivots.geometry.is_empty].copy()
    if pivots.empty:
        raise PipelineError("No confirmed pivot footprints are available.")
    if pivots["pivot_id"].duplicated().any():
        raise PipelineError("Confirmed pivot identifiers must be unique.")
    return pivots.to_crs(target_crs).sort_values("pivot_id").reset_index(drop=True)


def split_analysis_units_by_pivots(
    units: gpd.GeoDataFrame,
    pivots: gpd.GeoDataFrame,
    *,
    minimum_area_ha: float,
    boundary_buffer_m: float,
) -> gpd.GeoDataFrame:
    """Split declared crops into pivot, irrigated non-pivot and dryland units."""
    if minimum_area_ha <= 0:
        raise PipelineError("Minimum unit area must be positive.")
    if boundary_buffer_m < 0:
        raise PipelineError("Boundary buffer cannot be negative.")
    if units.crs is None or pivots.crs is None:
        raise PipelineError("Analysis units and pivots must have coordinate systems.")
    if units.crs != pivots.crs:
        pivots = pivots.to_crs(units.crs)

    confirmed = pivots[pivots["status"] == "confirmed"].copy()
    if confirmed.empty:
        raise PipelineError("No confirmed pivots are available for splitting units.")
    pivot_union = confirmed.geometry.union_all()
    rows: list[dict[str, object]] = []

    def add_piece(
        source: pd.Series,
        geometry: object,
        *,
        system_class: str,
        pivot_id: str | None,
    ) -> None:
        if geometry is None or geometry.is_empty or geometry.area <= 0:
            return
        attributes = source.drop(labels="geometry").to_dict()
        attributes["parent_unit_id"] = attributes.pop("unit_id")
        attributes["source_clipped_area_ha"] = float(attributes["clipped_area_ha"])
        attributes["system_class"] = system_class
        attributes["pivot_id"] = pivot_id
        attributes["regime_geometry_conflict"] = bool(
            system_class == "pivot" and attributes["regime"] == "S"
        )
        attributes["geometry"] = geometry
        rows.append(attributes)

    for _, unit in units.iterrows():
        for _, pivot in confirmed.iterrows():
            add_piece(
                unit,
                unit.geometry.intersection(pivot.geometry),
                system_class="pivot",
                pivot_id=str(pivot["pivot_id"]),
            )
        outside = unit.geometry.difference(pivot_union)
        add_piece(
            unit,
            outside,
            system_class=("irrigated_non_pivot" if unit["regime"] == "R" else "dryland"),
            pivot_id=None,
        )

    if not rows:
        raise PipelineError("No geometry remains after splitting units by pivots.")
    split = gpd.GeoDataFrame(rows, geometry="geometry", crs=units.crs)
    split = split[split.geometry.notna() & ~split.geometry.is_empty].copy()
    split["split_area_ha"] = split.geometry.area / 10_000
    split = split[split["split_area_ha"] >= minimum_area_ha].copy()
    if boundary_buffer_m:
        split.geometry = split.geometry.buffer(-boundary_buffer_m)
    split = split[split.geometry.notna() & ~split.geometry.is_empty].copy()
    split["clipped_area_ha"] = split["split_area_ha"]
    split["analysis_area_ha"] = split.geometry.area / 10_000
    split["_pivot_sort"] = split["pivot_id"].fillna("")
    split = split.sort_values(
        [
            "product_code",
            "regime",
            "system_class",
            "_pivot_sort",
            "provincia",
            "municipio",
            "poligono",
            "parcela",
            "recinto",
        ]
    ).drop(columns="_pivot_sort").reset_index(drop=True)
    split["unit_id"] = [f"A{index:04d}" for index in range(1, len(split) + 1)]
    columns = ["unit_id", "parent_unit_id", *[
        column for column in split.columns
        if column not in {"unit_id", "parent_unit_id", "geometry"}
    ], "geometry"]
    return split[columns]


def attach_pixel_indices(
    units: gpd.GeoDataFrame,
    *,
    transform: object,
    shape: tuple[int, int],
    minimum_pixels: int,
) -> tuple[gpd.GeoDataFrame, dict[str, np.ndarray]]:
    if minimum_pixels < 1:
        raise PipelineError("Minimum pixel count must be at least one.")
    indices: dict[str, np.ndarray] = {}
    pixel_counts: list[int] = []
    keep: list[bool] = []
    for row in units.itertuples():
        mask = geometry_mask(
            [mapping(row.geometry)],
            out_shape=shape,
            transform=transform,
            invert=True,
            all_touched=False,
        )
        selected = np.flatnonzero(mask)
        pixel_counts.append(int(selected.size))
        accepted = selected.size >= minimum_pixels
        keep.append(accepted)
        if accepted:
            indices[row.unit_id] = selected
    result = units.copy()
    result["analysis_pixel_count"] = pixel_counts
    result = result.loc[keep].copy().reset_index(drop=True)
    return result, indices


def calculate_ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    denominator = nir + red
    result = np.full(red.shape, np.nan, dtype=np.float32)
    # Zero or negative surface reflectance can occur after atmospheric
    # correction/clipping. Treat it as invalid so it cannot create NDVI=1
    # artefacts over dense summer crops.
    valid = (
        np.isfinite(red)
        & np.isfinite(nir)
        & (red > 0)
        & (nir > 0)
        & (np.abs(denominator) > 1e-8)
    )
    np.divide(nir - red, denominator, out=result, where=valid)
    np.clip(result, -1, 1, out=result)
    return result


def extract_unit_observations(
    scenes: list[tuple[pd.Timestamp, Path]],
    units: gpd.GeoDataFrame,
    pixel_indices: dict[str, np.ndarray],
) -> pd.DataFrame:
    metadata = units.set_index("unit_id")[
        [
            "product_code",
            "crop_name",
            "crop_group",
            "secondary_product_code",
            "secondary_crop_name",
            "crop_sequence",
            "regime",
            "system_class",
            "pivot_id",
            "regime_geometry_conflict",
            "parent_unit_id",
            "source_clipped_area_ha",
            "split_area_ha",
            "clipped_area_ha",
            "analysis_area_ha",
            "analysis_pixel_count",
        ]
    ].to_dict("index")
    rows: list[dict[str, object]] = []
    for scene_number, (scene_date, path) in enumerate(scenes, start=1):
        with rasterio.open(path) as dataset:
            red, nir, scl, data_mask = dataset.read()
        ndvi = calculate_ndvi(red, nir).ravel()
        quality = (
            (data_mask == 1)
            & np.isin(scl, CLEAR_SCL_CLASSES)
            & np.isfinite(ndvi.reshape(red.shape))
        ).ravel()
        for unit_id, selected in pixel_indices.items():
            usable = selected[quality[selected]]
            values = ndvi[usable]
            record: dict[str, object] = {
                "date": scene_date.date().isoformat(),
                "unit_id": unit_id,
                **metadata[unit_id],
                "valid_pixel_count": int(values.size),
                "valid_fraction": float(values.size / selected.size),
                "ndvi_mean": np.nan,
                "ndvi_median": np.nan,
                "ndvi_q25": np.nan,
                "ndvi_q75": np.nan,
            }
            if values.size:
                record.update(
                    ndvi_mean=float(np.mean(values)),
                    ndvi_median=float(np.median(values)),
                    ndvi_q25=float(np.quantile(values, 0.25)),
                    ndvi_q75=float(np.quantile(values, 0.75)),
                )
            rows.append(record)
        if scene_number == 1 or scene_number % 20 == 0 or scene_number == len(scenes):
            print(f"NDVI zonal statistics: {scene_number}/{len(scenes)} scenes")
    return pd.DataFrame(rows)


def aggregate_crop_curves(
    observations: pd.DataFrame,
    units: gpd.GeoDataFrame,
    *,
    minimum_valid_fraction: float,
    minimum_units_per_date: int,
) -> pd.DataFrame:
    if not 0 < minimum_valid_fraction <= 1:
        raise PipelineError("Minimum valid fraction must be in (0, 1].")
    if minimum_units_per_date < 1:
        raise PipelineError("Minimum units per date must be positive.")

    group_columns = [
        "product_code",
        "crop_name",
        "crop_group",
        "crop_sequence",
        "regime",
        "system_class",
    ]
    unit_totals = (
        units.groupby(group_columns, dropna=False)["unit_id"]
        .nunique()
        .rename("total_units")
    )
    sample_units = units.copy()
    sample_units["sample_id"] = sample_units["unit_id"]
    is_pivot = sample_units["system_class"] == "pivot"
    sample_units.loc[is_pivot, "sample_id"] = sample_units.loc[is_pivot, "pivot_id"]
    sample_totals = (
        sample_units.groupby(group_columns, dropna=False)["sample_id"]
        .nunique()
        .rename("total_samples")
    )
    accepted = observations[
        observations["ndvi_median"].notna()
        & (observations["valid_fraction"] >= minimum_valid_fraction)
    ].copy()
    accepted["sample_id"] = accepted["unit_id"]
    is_pivot = accepted["system_class"] == "pivot"
    accepted.loc[is_pivot, "sample_id"] = accepted.loc[is_pivot, "pivot_id"]

    # A declared PAC unit can be split into several pieces by a centre-pivot
    # footprint. Collapse those pieces first so that every physical pivot has
    # the same weight in the crop/system curve. Outside pivots, sample_id is
    # simply the original analysis-unit identifier.
    samples = (
        accepted.groupby(["date", *group_columns, "sample_id"], dropna=False)
        .agg(sample_ndvi=("ndvi_median", "median"))
        .reset_index()
    )
    curves = (
        samples.groupby(["date", *group_columns], dropna=False)
        .agg(
            observed_samples=("sample_id", "nunique"),
            ndvi_median=("sample_ndvi", "median"),
            ndvi_q25=("sample_ndvi", lambda values: values.quantile(0.25)),
            ndvi_q75=("sample_ndvi", lambda values: values.quantile(0.75)),
        )
        .reset_index()
        .merge(unit_totals.reset_index(), on=group_columns, how="left")
        .merge(sample_totals.reset_index(), on=group_columns, how="left")
    )
    curves["date"] = pd.to_datetime(curves["date"])
    curves["observed_sample_fraction"] = (
        curves["observed_samples"] / curves["total_samples"]
    )
    required = np.maximum(
        minimum_units_per_date,
        np.ceil(curves["total_samples"] * 0.5).astype(int),
    )
    curves["curve_valid"] = curves["observed_samples"] >= required
    curves["ndvi_median_30d"] = np.nan

    pieces: list[pd.DataFrame] = []
    for _, group in curves.groupby(group_columns, sort=False):
        group = group.sort_values("date").copy()
        valid = group["curve_valid"]
        rolling = (
            group.loc[valid].set_index("date")["ndvi_median"]
            .rolling("30D", center=True, min_periods=2)
            .median()
        )
        group.loc[valid, "ndvi_median_30d"] = rolling.to_numpy()
        pieces.append(group)
    return pd.concat(pieces, ignore_index=True).sort_values(group_columns + ["date"])


def _plot_group(axis, data: pd.DataFrame, color: str) -> None:
    data = data[data["curve_valid"]].sort_values("date")
    axis.fill_between(
        data["date"], data["ndvi_q25"], data["ndvi_q75"], color=color, alpha=0.18
    )
    axis.plot(data["date"], data["ndvi_median"], "o", color=color, markersize=2.5, alpha=0.45)
    axis.plot(data["date"], data["ndvi_median_30d"], color=color, linewidth=2)


def plot_crop_facets(curves: pd.DataFrame, output: Path) -> None:
    preferred = [
        (5, "S", "Cebada", "dryland"),
        (5, "R", "Cebada → Maíz", "pivot"),
        (5, "R", "Cebada → Maíz", "irrigated_non_pivot"),
        (4, "R", "Maíz", "pivot"),
        (4, "R", "Maíz", "irrigated_non_pivot"),
        (13, "S", "Triticale", "dryland"),
        (60, "R", "Alfalfa", "irrigated_non_pivot"),
        (40, "R", "Guisante → Maíz", "irrigated_non_pivot"),
    ]
    selected: list[pd.DataFrame] = []
    selected_keys: set[tuple[int, str, str, str]] = set()
    for code, regime, sequence, system_class in preferred:
        group = curves[
            (curves["product_code"] == code)
            & (curves["regime"] == regime)
            & (curves["crop_sequence"] == sequence)
            & (curves["system_class"] == system_class)
        ]
        if not group.empty and int(group["total_samples"].max()) >= 3:
            selected.append(group)
            selected_keys.add((code, regime, sequence, system_class))
    candidates = (
        curves.groupby(
            ["product_code", "regime", "crop_sequence", "system_class"],
            dropna=False,
        )["total_samples"]
        .max()
        .sort_values(ascending=False)
    )
    for key, unit_count in candidates.items():
        if len(selected) >= 8:
            break
        if int(unit_count) < 3 or key in selected_keys:
            continue
        code, regime, sequence, system_class = key
        selected.append(
            curves[
                (curves["product_code"] == code)
                & (curves["regime"] == regime)
                & (curves["crop_sequence"] == sequence)
                & (curves["system_class"] == system_class)
            ]
        )
        selected_keys.add(key)
    if not selected:
        raise PipelineError("No crop/system group has enough units for plotting.")

    figure, axes = plt.subplots(4, 2, figsize=(15, 13), sharex=True, sharey=True, constrained_layout=True)
    for axis, group in zip(axes.flat, selected):
        system_class = str(group["system_class"].iloc[0])
        _plot_group(axis, group, SYSTEM_COLORS[system_class])
        crop = str(group["crop_sequence"].iloc[0])
        samples = int(group["total_samples"].max())
        label = SYSTEM_LABELS[system_class]
        sample_label = "pivotes" if system_class == "pivot" else "unidades"
        axis.set_title(f"{crop} — {label} ({samples} {sample_label})")
        axis.grid(color="#dddddd", linewidth=0.5, alpha=0.65)
        axis.set_ylim(-0.1, 0.95)
        axis.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    for axis in axes.flat[len(selected):]:
        axis.set_visible(False)
    for axis in axes[:, 0]:
        axis.set_ylabel("NDVI")
    figure.suptitle("Dinámica NDVI por cultivo y sistema agrícola — campaña PAC 2025", fontsize=16)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(figure)


def plot_barley_comparison(curves: pd.DataFrame, output: Path) -> None:
    figure, axis = plt.subplots(figsize=(12, 6), constrained_layout=True)
    comparisons = (
        ("S", "Cebada", "dryland", "Cebada de secano"),
        ("R", "Cebada", "pivot", "Pivote: cebada"),
        (
            "R",
            "Cebada → Maíz",
            "irrigated_non_pivot",
            "Regadío sin pivote: cebada → maíz",
        ),
    )
    for regime, sequence, system_class, label in comparisons:
        group = curves[
            (curves["product_code"] == 5)
            & (curves["regime"] == regime)
            & (curves["crop_sequence"] == sequence)
            & (curves["system_class"] == system_class)
        ]
        if group.empty:
            continue
        valid = group[group["curve_valid"]].sort_values("date")
        axis.fill_between(
            valid["date"], valid["ndvi_q25"], valid["ndvi_q75"],
            color=SYSTEM_COLORS[system_class], alpha=0.14,
        )
        axis.plot(
            valid["date"], valid["ndvi_median_30d"], color=SYSTEM_COLORS[system_class],
            linewidth=2.4, label=f"{label} (n={int(group['total_samples'].max())})",
        )
    axis.set_title("Dinámica de cebada según sistema y secuencia declarada")
    axis.set_ylabel("NDVI")
    axis.set_xlabel("Fecha")
    axis.set_ylim(-0.1, 0.95)
    axis.grid(color="#dddddd", linewidth=0.5, alpha=0.65)
    axis.legend()
    axis.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(figure)


def plot_system_map(
    units: gpd.GeoDataFrame,
    pivots: gpd.GeoDataFrame,
    scenes: list[tuple[pd.Timestamp, Path]],
    output: Path,
) -> None:
    """Map final analysis units over the maximum valid summer NDVI signal."""
    summer = [
        path
        for date, path in scenes
        if pd.Timestamp("2025-06-01") <= date <= pd.Timestamp("2025-10-31")
    ]
    if not summer:
        raise PipelineError("No summer scenes are available for the system map.")
    maximum: np.ndarray | None = None
    bounds = None
    raster_crs = None
    for path in summer:
        with rasterio.open(path) as dataset:
            red, nir, scl, data_mask = dataset.read()
            bounds = dataset.bounds
            raster_crs = dataset.crs
        ndvi = calculate_ndvi(red, nir)
        valid = (data_mask == 1) & np.isin(scl, CLEAR_SCL_CLASSES) & np.isfinite(ndvi)
        current = np.where(valid, ndvi, np.nan)
        maximum = current if maximum is None else np.fmax(maximum, current)
    assert maximum is not None and bounds is not None and raster_crs is not None

    mapped_units = units.to_crs(raster_crs)
    mapped_pivots = pivots.to_crs(raster_crs)
    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
    figure, axis = plt.subplots(figsize=(13, 8), constrained_layout=True)
    axis.imshow(
        maximum,
        extent=extent,
        origin="upper",
        cmap="Greys",
        vmin=0.05,
        vmax=0.95,
        interpolation="nearest",
        alpha=0.72,
    )
    for system_class in ("dryland", "irrigated_non_pivot", "pivot"):
        subset = mapped_units[mapped_units["system_class"] == system_class]
        subset.plot(
            ax=axis,
            facecolor=SYSTEM_COLORS[system_class],
            edgecolor=SYSTEM_COLORS[system_class],
            linewidth=0.45,
            alpha=0.42,
        )
    mapped_pivots.boundary.plot(ax=axis, color="#144b7a", linewidth=1.0, alpha=0.9)
    conflicts = mapped_units[mapped_units["regime_geometry_conflict"]]
    if not conflicts.empty:
        conflicts.boundary.plot(ax=axis, color="#c62828", linewidth=2.0)
    handles = [
        Patch(facecolor=SYSTEM_COLORS[key], alpha=0.55, label=SYSTEM_LABELS[key])
        for key in ("dryland", "irrigated_non_pivot", "pivot")
    ]
    if not conflicts.empty:
        handles.append(
            Patch(
                facecolor="none",
                edgecolor="#c62828",
                linewidth=2.0,
                label="conflicto régimen declarado/geometría",
            )
        )
    axis.legend(handles=handles, loc="lower left", framealpha=0.9)
    axis.set_title("Unidades agrícolas finales por sistema — campaña PAC 2025")
    axis.set_xlabel("Coordenada UTM este (m)")
    axis.set_ylabel("Coordenada UTM norte (m)")
    axis.ticklabel_format(style="plain", axis="both", useOffset=False)
    axis.set_aspect("equal")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(figure)


def write_report(
    path: Path,
    *,
    units: gpd.GeoDataFrame,
    observations: pd.DataFrame,
    curves: pd.DataFrame,
    scene_count: int,
    parameters: dict[str, object],
) -> None:
    groups = (
        units.groupby(["product_code", "crop_sequence", "regime", "system_class"])
        .agg(units=("unit_id", "nunique"), analysis_area_ha=("analysis_area_ha", "sum"))
        .reset_index()
        .sort_values("analysis_area_ha", ascending=False)
    )
    systems = (
        units.groupby(["system_class", "regime"])
        .agg(units=("unit_id", "nunique"), analysis_area_ha=("analysis_area_ha", "sum"))
        .reset_index()
        .sort_values(["system_class", "regime"])
    )
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scene_count": scene_count,
        "analysis_unit_count": len(units),
        "unit_observation_count": len(observations),
        "valid_curve_row_count": int(curves["curve_valid"].sum()),
        "regime_geometry_conflict_count": int(units["regime_geometry_conflict"].sum()),
        "parameters": parameters,
        "systems": systems.to_dict(orient="records"),
        "groups": groups.to_dict(orient="records"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
