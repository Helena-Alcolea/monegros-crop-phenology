#!/usr/bin/env python3
"""Create a focused SIGPAC preview for a pilot area in Monegros II.

The script reads the official provincial GeoPackages without modifying them,
loads only features intersecting a WGS84 bounding box, and writes a comparison
of declared crops (2025) and SIGPAC irrigation coefficients (2026).
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import box


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = BASE_DIR / "data_sigpac" / "raw"
DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs"

# Provisional exploration window around Bujaraloz and Penyalba. It remains
# west of longitude 0 so a later 10 m Sentinel-2 workflow fits UTM zone 30.
DEFAULT_BBOX = (-0.25, 41.42, -0.015, 41.57)

REGIME_COLORS = {
    "R": "#247a4d",
    "S": "#d49a45",
    "Sin dato": "#b8b8b8",
}
REGIME_LABELS = {
    "R": "Regadío declarado",
    "S": "Secano declarado",
    "Sin dato": "Sin dato",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Directory containing the original SIGPAC GeoPackages.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where generated figures and tables are written.",
    )
    parser.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        default=DEFAULT_BBOX,
        help="WGS84 exploration bounds.",
    )
    parser.add_argument(
        "--top-products",
        type=int,
        default=8,
        help="Number of most frequent declared product codes to map.",
    )
    return parser.parse_args()


def validate_bbox(bounds: tuple[float, float, float, float]) -> None:
    west, south, east, north = bounds
    if west >= east or south >= north:
        raise ValueError("The bbox must satisfy WEST < EAST and SOUTH < NORTH.")
    if not (-180 <= west <= 180 and -180 <= east <= 180):
        raise ValueError("Longitudes must be within [-180, 180].")
    if not (-90 <= south <= 90 and -90 <= north <= 90):
        raise ValueError("Latitudes must be within [-90, 90].")


def find_one(data_dir: Path, pattern: str) -> Path:
    matches = sorted(data_dir.glob(pattern))
    if len(matches) != 1:
        names = ", ".join(path.name for path in matches) or "none"
        raise FileNotFoundError(
            f"Expected exactly one file matching {pattern!r}; found: {names}."
        )
    return matches[0]


def read_provincial_layers(
    data_dir: Path,
    *,
    kind: str,
    campaign: int,
    layer: str,
    bbox: tuple[float, float, float, float],
    columns: list[str],
) -> gpd.GeoDataFrame:
    frames: list[gpd.GeoDataFrame] = []
    for province_code in ("0222", "0250"):
        source = find_one(data_dir, f"{province_code}_*_{kind}_{campaign}_*.gpkg")
        frame = gpd.read_file(
            source,
            layer=layer,
            bbox=bbox,
            columns=columns,
            engine="pyogrio",
            use_arrow=False,
        )
        if frame.crs is None:
            raise ValueError(f"{source.name} has no declared coordinate system.")
        frame = frame.to_crs(4258)
        frame["source_file"] = source.name
        frames.append(frame)

    combined = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True),
        geometry="geometry",
        crs="EPSG:4258",
    )
    # A small number of official SIGPAC polygons contain ring defects. Repair
    # them in memory before clipping; the source GeoPackages remain untouched.
    invalid = ~combined.geometry.is_valid
    if invalid.any():
        combined.loc[invalid, "geometry"] = combined.loc[invalid, "geometry"].make_valid()
    combined = combined[combined.geometry.notna() & ~combined.geometry.is_empty].copy()
    clip_geometry = gpd.GeoSeries([box(*bbox)], crs="EPSG:4258")
    return gpd.clip(combined, clip_geometry, keep_geom_type=True)


def prepare_product_groups(
    crops: gpd.GeoDataFrame, top_products: int
) -> tuple[gpd.GeoDataFrame, list[str]]:
    if top_products < 1:
        raise ValueError("--top-products must be at least 1.")
    result = crops.copy()
    code = result["parc_producto"].astype("Int64")
    top_codes = code.value_counts().head(top_products).index.tolist()
    labels = [str(int(item)) for item in top_codes]
    result["product_group"] = code.map(
        lambda value: str(int(value)) if pd.notna(value) and value in top_codes else "Otros/sin dato"
    )
    return result, labels


def map_product_colors(labels: list[str]) -> dict[str, object]:
    palette = plt.get_cmap("tab10")
    colors = {label: palette(index % 10) for index, label in enumerate(labels)}
    colors["Otros/sin dato"] = "#c4c4c4"
    return colors


def add_bounds(axis, bbox: tuple[float, float, float, float]) -> None:
    west, south, east, north = bbox
    axis.set_xlim(west, east)
    axis.set_ylim(south, north)
    latitude = (south + north) / 2
    axis.set_aspect(1 / max(0.1, abs(math.cos(math.radians(latitude)))))
    axis.set_xlabel("Longitud")
    axis.set_ylabel("Latitud")
    axis.grid(color="#dedede", linewidth=0.4, alpha=0.7)


def plot_preview(
    crops: gpd.GeoDataFrame,
    recintos: gpd.GeoDataFrame,
    bbox: tuple[float, float, float, float],
    output: Path,
    top_products: int,
) -> None:
    crop_groups, product_labels = prepare_product_groups(crops, top_products)
    product_colors = map_product_colors(product_labels)

    crop_regime = crops.copy()
    crop_regime["regime"] = crop_regime["parc_sistexp"].fillna("Sin dato")

    recinto_regime = recintos.copy()
    recinto_regime["regime"] = recinto_regime["coef_regadio"].map(
        lambda value: "R" if value == 100 else ("S" if value == 0 else "Sin dato")
    )

    figure, axes = plt.subplots(1, 3, figsize=(19, 7), constrained_layout=True)

    for regime in ("S", "R", "Sin dato"):
        subset = crop_regime[crop_regime["regime"] == regime]
        if not subset.empty:
            subset.plot(
                ax=axes[0],
                color=REGIME_COLORS[regime],
                edgecolor="white",
                linewidth=0.18,
            )
    axes[0].set_title("Cultivo declarado 2025")
    axes[0].legend(
        handles=[
            Patch(facecolor=REGIME_COLORS[key], label=REGIME_LABELS[key])
            for key in ("R", "S", "Sin dato")
        ],
        loc="lower left",
        fontsize=8,
    )

    draw_order = ["Otros/sin dato", *reversed(product_labels)]
    for label in draw_order:
        subset = crop_groups[crop_groups["product_group"] == label]
        if not subset.empty:
            subset.plot(
                ax=axes[1],
                color=product_colors[label],
                edgecolor="white",
                linewidth=0.15,
            )
    axes[1].set_title("Códigos de producto más frecuentes")
    axes[1].legend(
        handles=[
            Patch(facecolor=product_colors[label], label=f"Producto {label}")
            for label in product_labels
        ]
        + [Patch(facecolor=product_colors["Otros/sin dato"], label="Otros/sin dato")],
        loc="lower left",
        fontsize=7,
        ncol=2,
    )

    for regime in ("S", "R", "Sin dato"):
        subset = recinto_regime[recinto_regime["regime"] == regime]
        if not subset.empty:
            subset.plot(
                ax=axes[2],
                color=REGIME_COLORS[regime],
                edgecolor="white",
                linewidth=0.12,
            )
    crop_regime.boundary.plot(ax=axes[2], color="#202020", linewidth=0.12, alpha=0.55)
    axes[2].set_title("Recintos 2026 y límites declarados 2025")
    axes[2].legend(
        handles=[
            Patch(facecolor=REGIME_COLORS["R"], label="Coef. regadío 100"),
            Patch(facecolor=REGIME_COLORS["S"], label="Coef. regadío 0"),
            Patch(facecolor=REGIME_COLORS["Sin dato"], label="Otro/sin dato"),
            Line2D([0], [0], color="#202020", linewidth=1, label="Limite cultivo declarado"),
        ],
        loc="lower left",
        fontsize=8,
    )

    for axis in axes:
        add_bounds(axis, bbox)

    figure.suptitle(
        "SIGPAC — exploración inicial de Monegros II (ventana provisional)",
        fontsize=15,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(figure)


def write_summary(crops: gpd.GeoDataFrame, output: Path) -> None:
    summary = (
        crops.assign(
            parc_sistexp=crops["parc_sistexp"].fillna("Sin dato"),
            parc_producto=crops["parc_producto"].astype("Int64"),
            declared_area_ha=crops["parc_supcult"].fillna(crops["dn_surface"]) / 10_000,
        )
        .groupby(["provincia", "parc_sistexp", "parc_producto"], dropna=False)
        .agg(feature_count=("geometry", "size"), declared_area_ha=("declared_area_ha", "sum"))
        .reset_index()
        .sort_values(["declared_area_ha", "feature_count"], ascending=False)
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output, index=False)


def main() -> int:
    args = parse_args()
    bbox = tuple(args.bbox)
    validate_bbox(bbox)
    if not args.data_dir.is_dir():
        raise FileNotFoundError(f"Data directory does not exist: {args.data_dir}")

    crops = read_provincial_layers(
        args.data_dir,
        kind="cd",
        campaign=2025,
        layer="cultivo_declarado",
        bbox=bbox,
        columns=[
            "dn_oid",
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
        ],
    )
    recintos = read_provincial_layers(
        args.data_dir,
        kind="rec",
        campaign=2026,
        layer="recinto",
        bbox=bbox,
        columns=[
            "dn_oid",
            "provincia",
            "municipio",
            "poligono",
            "parcela",
            "recinto",
            "dn_surface",
            "coef_regadio",
            "uso_sigpac",
        ],
    )
    if crops.empty:
        raise RuntimeError("No declared crops intersect the selected bbox.")
    if recintos.empty:
        raise RuntimeError("No SIGPAC recintos intersect the selected bbox.")

    figure_path = args.output_dir / "figures" / "sigpac_monegros_preview.png"
    table_path = args.output_dir / "tables" / "sigpac_monegros_preview_summary.csv"
    plot_preview(crops, recintos, bbox, figure_path, args.top_products)
    write_summary(crops, table_path)

    print(f"Loaded {len(crops):,} declared-crop polygons and {len(recintos):,} recintos.")
    print(f"Figure: {figure_path}")
    print(f"Summary: {table_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
