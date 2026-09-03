#!/usr/bin/env python3
"""Create a summer NDVI diagnostic for delimiting centre-pivot footprints."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/gis_monegros_matplotlib")

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from shapely.geometry import Point

from monegros_ndvi.crop_timeseries import calculate_ndvi, discover_scenes
from monegros_ndvi.settings import BASE_DIR, DEFAULT_BBOX, DEFAULT_INPUT_DIR


START = "2025-06-01"
END = "2025-10-31"
OUTPUT = BASE_DIR / "outputs" / "figures" / "pivot_summer_ndvi_diagnostic.png"
UNIT_OUTPUT = BASE_DIR / "outputs" / "figures" / "pivot_unit_reference.png"
PARCEL_OUTPUT = BASE_DIR / "outputs" / "figures" / "pivot_parcel_reference.png"
PIVOT_OUTPUT = BASE_DIR / "data_sigpac" / "processed" / "pivot_candidates.gpkg"
OVERLAP_OUTPUT = BASE_DIR / "outputs" / "tables" / "pivot_candidate_unit_overlap.csv"

# P01-P02 were fitted on the NDVI diagnostic and then confirmed in SIGPAC.
# P03-P08 were digitised from the three user-reviewed SIGPAC screenshots and
# registered against parcels 506/45, 506/5 and 506/39, respectively.
PIVOT_DEFINITIONS = (
    ("P01", 744780.0, 4596580.0, 320.0, "confirmed", "ndvi_and_sigpac"),
    ("P02", 745440.0, 4596590.0, 340.0, "confirmed", "ndvi_and_sigpac"),
    ("P03", 746025.0, 4596902.0, 227.0, "confirmed", "capture_13-55-59_confirmed"),
    ("P04", 746468.0, 4596745.0, 217.0, "confirmed", "capture_13-55-59_confirmed"),
    ("P05", 745985.0, 4596457.0, 204.0, "confirmed", "capture_13-55-59_confirmed"),
    ("P06", 746397.0, 4596319.0, 212.0, "confirmed", "capture_13-55-59_confirmed"),
    ("P07", 747109.0, 4596520.0, 283.0, "confirmed", "capture_13-56-24"),
    ("P08", 745499.0, 4595993.0, 196.0, "candidate_low_confidence", "capture_13-56-40"),
)

REJECTED_DEFINITIONS = (
    ("old_P03", 746150.0, 4596820.0, 380.0, "rejected_manual_review"),
    ("old_P04", 747550.0, 4596340.0, 250.0, "rejected_manual_review"),
)


def summer_maximum() -> tuple[np.ndarray, rasterio.coords.BoundingBox, object, object]:
    selected = [
        (date, path)
        for date, path in discover_scenes(DEFAULT_INPUT_DIR)
        if START <= date.date().isoformat() <= END
    ]
    if not selected:
        raise RuntimeError("No Sentinel-2 scenes fall inside the summer period.")

    maximum: np.ndarray | None = None
    bounds = None
    crs = None
    transform = None
    for _, path in selected:
        with rasterio.open(path) as dataset:
            red, nir, scl, data_mask = dataset.read()
            bounds = dataset.bounds
            crs = dataset.crs
            transform = dataset.transform
        ndvi = calculate_ndvi(red, nir)
        valid = (data_mask == 1) & np.isin(scl, (4, 5)) & np.isfinite(ndvi)
        current = np.where(valid, ndvi, np.nan)
        maximum = current if maximum is None else np.fmax(maximum, current)

    assert maximum is not None and bounds is not None and crs is not None
    assert transform is not None
    return maximum, bounds, crs, transform


def build_pivot_review(crs: object) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    pivots = gpd.GeoDataFrame(
        [
            {
                "pivot_id": pivot_id,
                "centre_x": centre_x,
                "centre_y": centre_y,
                "radius_m": radius,
                "status": status,
                "source": source,
                "geometry": Point(centre_x, centre_y).buffer(radius, quad_segs=64),
            }
            for pivot_id, centre_x, centre_y, radius, status, source
            in PIVOT_DEFINITIONS
        ],
        geometry="geometry",
        crs=crs,
    )
    rejected = gpd.GeoDataFrame(
        [
            {
                "candidate_id": candidate_id,
                "centre_x": centre_x,
                "centre_y": centre_y,
                "radius_m": radius,
                "status": status,
                "geometry": Point(centre_x, centre_y).buffer(radius, quad_segs=64),
            }
            for candidate_id, centre_x, centre_y, radius, status
            in REJECTED_DEFINITIONS
        ],
        geometry="geometry",
        crs=crs,
    )
    return pivots, rejected


def unit_overlap_table(
    units: gpd.GeoDataFrame,
    pivots: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    rows: list[dict[str, object]] = []
    metadata = ["unit_id", "crop_sequence", "regime", "analysis_area_ha"]
    for pivot in pivots.itertuples():
        areas = units.geometry.intersection(pivot.geometry).area / 10_000
        for index in np.flatnonzero(areas.to_numpy() > 0):
            unit = units.iloc[index]
            overlap = float(areas.iloc[index])
            rows.append(
                {
                    "pivot_id": pivot.pivot_id,
                    "pivot_status": pivot.status,
                    **{column: unit[column] for column in metadata},
                    "overlap_area_ha": overlap,
                    "unit_overlap_fraction": overlap / float(unit.analysis_area_ha),
                }
            )
    return gpd.GeoDataFrame(rows)


def main() -> None:
    ndvi, bounds, crs, _ = summer_maximum()
    units_path = BASE_DIR / "data_sigpac" / "processed" / "analysis_units_2025.gpkg"
    units = gpd.read_file(units_path, layer="analysis_units").to_crs(crs)
    pivots, rejected = build_pivot_review(crs)
    PIVOT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    # This is a generated review file. Recreate it so that obsolete layers from
    # earlier candidate sets cannot survive alongside the current inventory.
    if PIVOT_OUTPUT.exists():
        PIVOT_OUTPUT.unlink()
    pivots.to_file(PIVOT_OUTPUT, layer="pivot_footprints", driver="GPKG")
    rejected.to_file(
        PIVOT_OUTPUT,
        layer="rejected_candidates",
        driver="GPKG",
        mode="a",
    )
    overlaps = unit_overlap_table(units, pivots)
    OVERLAP_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    overlaps.to_csv(OVERLAP_OUTPUT, index=False)

    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
    figure, axes = plt.subplots(1, 2, figsize=(15, 7), constrained_layout=True)
    image = None
    for axis in axes:
        image = axis.imshow(
            ndvi,
            extent=extent,
            origin="upper",
            cmap="RdYlGn",
            vmin=0.05,
            vmax=0.95,
            interpolation="nearest",
        )
        axis.set_aspect("equal")
        axis.set_xlabel("Coordenada UTM este (m)")
        axis.ticklabel_format(style="plain", axis="both", useOffset=False)

    axes[0].set_title("NDVI máximo de verano — señal sin divisiones")
    axes[0].set_ylabel("Coordenada UTM norte (m)")
    axes[1].set_title("La misma señal con unidades PAC superpuestas")
    units.boundary.plot(ax=axes[1], color="#202020", linewidth=0.35, alpha=0.75)
    axes[1].set_ylabel("")
    axes[1].tick_params(labelleft=False)

    confirmed = pivots[pivots["status"] == "confirmed"]
    pending = pivots[pivots["status"] == "pending_manual_confirmation"]
    low_confidence = pivots[pivots["status"] == "candidate_low_confidence"]
    for axis in axes:
        confirmed.boundary.plot(ax=axis, color="#1565c0", linewidth=1.5)
        if not pending.empty:
            pending.boundary.plot(
                ax=axis,
                color="#8e24aa",
                linewidth=1.5,
                linestyle="--",
            )
        low_confidence.boundary.plot(
            ax=axis,
            color="#ff8f00",
            linewidth=1.4,
            linestyle=":",
        )
        rejected.boundary.plot(ax=axis, color="#7f7f7f", linewidth=1.0, linestyle="--")
        for row in pivots.itertuples():
            is_confirmed = row.status == "confirmed"
            is_pending = row.status == "pending_manual_confirmation"
            axis.text(
                row.centre_x,
                row.centre_y,
                row.pivot_id if is_confirmed else (
                    f"{row.pivot_id}*" if is_pending else f"{row.pivot_id}?"
                ),
                ha="center",
                va="center",
                fontsize=8,
                weight="bold",
                color=(
                    "#0d47a1" if is_confirmed else
                    "#6a1b9a" if is_pending else
                    "#e65100"
                ),
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75, "pad": 1.5},
            )
        for row in rejected.itertuples():
            axis.text(
                row.centre_x,
                row.centre_y,
                f"{row.candidate_id} descartado",
                ha="center",
                va="center",
                fontsize=7,
                color="#555555",
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.7, "pad": 1.2},
            )

    assert image is not None
    colourbar = figure.colorbar(image, ax=axes, fraction=0.025, pad=0.02)
    colourbar.set_label("NDVI máximo entre junio y octubre de 2025")
    figure.suptitle(
        "Diagnóstico espacial para delimitar pivotes centrales",
        fontsize=16,
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT, dpi=220, bbox_inches="tight")
    plt.close(figure)

    reference, axis = plt.subplots(figsize=(16, 7), constrained_layout=True)
    axis.imshow(
        ndvi,
        extent=extent,
        origin="upper",
        cmap="RdYlGn",
        vmin=0.05,
        vmax=0.95,
        interpolation="nearest",
    )
    units.boundary.plot(ax=axis, color="#202020", linewidth=0.55, alpha=0.85)
    visible = units[
        (units.geometry.centroid.y >= 4_595_800)
        & (units.geometry.centroid.x >= 744_200)
        & (units.geometry.centroid.x <= 748_000)
    ]
    for row in visible.itertuples():
        point = row.geometry.representative_point()
        axis.text(
            point.x,
            point.y,
            row.unit_id,
            ha="center",
            va="center",
            fontsize=5.5,
            color="#111111",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.7, "pad": 0.7},
        )
    axis.set_xlim(744_200, 748_000)
    axis.set_ylim(4_595_800, 4_597_300)
    axis.set_aspect("equal")
    axis.set_title("Referencia de unidades para geolocalizar las capturas SIGPAC")
    axis.set_xlabel("Coordenada UTM este (m)")
    axis.set_ylabel("Coordenada UTM norte (m)")
    axis.ticklabel_format(style="plain", axis="both", useOffset=False)
    reference.savefig(UNIT_OUTPUT, dpi=240, bbox_inches="tight")
    plt.close(reference)

    recintos_path = BASE_DIR / "data_sigpac" / "raw" / "0222_HUESCA_rec_2026_20251215.gpkg"
    recintos = gpd.read_file(
        recintos_path,
        layer="recinto",
        bbox=DEFAULT_BBOX,
        columns=["municipio", "poligono", "parcela"],
        engine="pyogrio",
        use_arrow=False,
    ).to_crs(crs)
    parcels = recintos.dissolve(by=["municipio", "poligono", "parcela"]).reset_index()
    parcels["parcel_id"] = parcels.apply(
        lambda row: f"{int(row.poligono)}/{int(row.parcela)}", axis=1
    )
    parcel_figure, parcel_axis = plt.subplots(figsize=(16, 8), constrained_layout=True)
    parcel_axis.imshow(
        ndvi,
        extent=extent,
        origin="upper",
        cmap="RdYlGn",
        vmin=0.05,
        vmax=0.95,
        interpolation="nearest",
    )
    parcels.boundary.plot(ax=parcel_axis, color="#d7191c", linewidth=0.7, alpha=0.9)
    visible_parcels = parcels[
        (parcels.geometry.centroid.y >= 4_595_500)
        & (parcels.geometry.centroid.x >= 744_000)
        & (parcels.geometry.centroid.x <= 748_000)
    ]
    for row in visible_parcels.itertuples():
        point = row.geometry.representative_point()
        parcel_axis.text(
            point.x,
            point.y,
            row.parcel_id,
            ha="center",
            va="center",
            fontsize=5.5,
            color="#111111",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 0.7},
        )
    parcel_axis.set_xlim(744_000, 748_000)
    parcel_axis.set_ylim(4_595_500, 4_597_400)
    parcel_axis.set_aspect("equal")
    parcel_axis.set_title("Parcelas SIGPAC 2026 (etiquetas: polígono/parcela)")
    parcel_axis.set_xlabel("Coordenada UTM este (m)")
    parcel_axis.set_ylabel("Coordenada UTM norte (m)")
    parcel_axis.ticklabel_format(style="plain", axis="both", useOffset=False)
    parcel_figure.savefig(PARCEL_OUTPUT, dpi=240, bbox_inches="tight")
    plt.close(parcel_figure)

    print(OUTPUT)
    print(UNIT_OUTPUT)
    print(PARCEL_OUTPUT)
    print(PIVOT_OUTPUT)
    print(OVERLAP_OUTPUT)
    print(pivots.drop(columns="geometry").to_string(index=False))


if __name__ == "__main__":
    main()
