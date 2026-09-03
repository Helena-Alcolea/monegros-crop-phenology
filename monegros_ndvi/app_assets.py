"""Prepare compact, versionable data assets for the Streamlit portfolio app."""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.request import Request

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

from .crop_timeseries import CLEAR_SCL_CLASSES, discover_scenes
from .download_sentinel2 import (
    CRS_URI_PREFIX,
    PROCESS_URL,
    _open_with_retries,
    acquire_token,
    load_env_file,
)
from .settings import BASE_DIR, DEFAULT_BBOX, DEFAULT_MAX_CATALOG_CLOUD_PERCENT, PipelineError


APP_DATA_DIR = BASE_DIR / "dashboard" / "app_data"
GROUP_COLUMNS = [
    "product_code",
    "crop_name",
    "crop_group",
    "crop_sequence",
    "regime",
    "system_class",
]
SYSTEM_ES = {
    "dryland": "Secano",
    "irrigated_non_pivot": "Regadío sin pivote",
    "pivot": "Pivote central",
}
SYSTEM_EN = {
    "dryland": "Dryland",
    "irrigated_non_pivot": "Irrigated, non-pivot",
    "pivot": "Centre pivot",
}
CROP_EN = {
    "Alfalfa": "Alfalfa",
    "Barbecho tradicional": "Traditional fallow",
    "Cebada": "Barley",
    "Festuca": "Fescue",
    "Guisante": "Pea",
    "Maíz": "Maize",
    "Pastos permanentes de 5 o más años": "Permanent grassland (5+ years)",
    "Trigo blando": "Soft wheat",
    "Triticale": "Triticale",
    "Veza": "Vetch",
    "Yeros": "Bitter vetch",
}
GROUP_COLORS = [
    "#E69F00",
    "#0072B2",
    "#009E73",
    "#CC79A7",
    "#D55E00",
    "#56B4E9",
    "#F0E442",
    "#6A3D9A",
    "#B15928",
    "#1B9E77",
    "#7570B3",
    "#E7298A",
    "#66A61E",
    "#E6AB02",
    "#A6761D",
    "#1F78B4",
    "#FB9A99",
]


RGB_EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{
      bands: ["B02", "B03", "B04", "SCL", "dataMask"],
      units: ["REFLECTANCE", "REFLECTANCE", "REFLECTANCE", "DN", "DN"]
    }],
    mosaicking: "ORBIT",
    output: { bands: 4, sampleType: "AUTO" }
  };
}

function rgba(sample) {
  const gain = 2.5;
  return [gain * sample.B04, gain * sample.B03, gain * sample.B02, sample.dataMask];
}

function evaluatePixel(samples) {
  const clearClasses = [4, 5, 6];
  for (const sample of samples) {
    if (sample.dataMask === 1 && clearClasses.includes(sample.SCL)) return rgba(sample);
  }
  for (const sample of samples) {
    if (sample.dataMask === 1) return rgba(sample);
  }
  return [0, 0, 0, 0];
}
"""


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def group_id(record: pd.Series | dict[str, Any]) -> str:
    return "-".join(
        [
            str(int(record["product_code"])),
            str(record["regime"]).lower(),
            str(record["system_class"]).replace("_", "-"),
            _slug(str(record["crop_sequence"])),
        ]
    )


def translate_sequence(sequence: str) -> str:
    return " → ".join(CROP_EN.get(item.strip(), item.strip()) for item in sequence.split("→"))


def _peak_record(data: pd.DataFrame) -> tuple[str | None, float | None]:
    usable = data[data["ndvi_median_30d"].notna()]
    if usable.empty:
        return None, None
    row = usable.loc[usable["ndvi_median_30d"].idxmax()]
    return row["date"].date().isoformat(), round(float(row["ndvi_median_30d"]), 3)


def phenology_record(group: pd.DataFrame) -> dict[str, Any]:
    data = group[
        group["curve_valid"]
        & group["ndvi_median_30d"].notna()
        & (group["date"] >= pd.Timestamp("2025-01-01"))
        & (group["date"] <= pd.Timestamp("2025-10-31"))
    ].sort_values("date")
    first_name, *secondary = str(group["crop_sequence"].iloc[0]).split(" → ")
    if secondary:
        first = data[data["date"] < pd.Timestamp("2025-07-01")]
        second = data[data["date"] >= pd.Timestamp("2025-07-01")]
        first_date, first_ndvi = _peak_record(first)
        second_date, second_ndvi = _peak_record(second)
        second_name = " → ".join(secondary)
    else:
        first_date, first_ndvi = _peak_record(data)
        second_date, second_ndvi, second_name = None, None, None
    amplitude = None
    if not data.empty:
        amplitude = round(
            float(data["ndvi_median_30d"].max() - data["ndvi_median_30d"].min()),
            3,
        )
    return {
        "primary_crop_es": first_name,
        "primary_crop_en": CROP_EN.get(first_name, first_name),
        "primary_peak_date": first_date,
        "primary_peak_ndvi": first_ndvi,
        "secondary_crop_es": second_name,
        "secondary_crop_en": CROP_EN.get(second_name, second_name) if second_name else None,
        "secondary_peak_date": second_date,
        "secondary_peak_ndvi": second_ndvi,
        "seasonal_amplitude": amplitude,
    }


def prepare_tabular_assets(
    curves_path: Path,
    units_path: Path,
    output_dir: Path = APP_DATA_DIR,
) -> pd.DataFrame:
    """Write eligible curves, group metadata and a lightweight unit GeoJSON."""
    curves = pd.read_csv(curves_path, parse_dates=["date"])
    eligible = (
        curves.groupby(GROUP_COLUMNS, dropna=False)
        .agg(
            total_units=("total_units", "max"),
            total_samples=("total_samples", "max"),
            valid_dates=("curve_valid", "sum"),
        )
        .reset_index()
    )
    eligible = eligible[
        (eligible["total_samples"] >= 3) & (eligible["valid_dates"] > 0)
    ].copy()
    eligible["group_id"] = eligible.apply(group_id, axis=1)
    eligible = eligible.sort_values(
        ["system_class", "crop_sequence", "regime"], kind="stable"
    ).reset_index(drop=True)
    eligible["color"] = [GROUP_COLORS[index % len(GROUP_COLORS)] for index in range(len(eligible))]
    eligible["system_es"] = eligible["system_class"].map(SYSTEM_ES)
    eligible["system_en"] = eligible["system_class"].map(SYSTEM_EN)
    eligible["crop_sequence_en"] = eligible["crop_sequence"].map(translate_sequence)
    eligible["label_es"] = eligible["crop_sequence"] + " · " + eligible["system_es"]
    eligible["label_en"] = eligible["crop_sequence_en"] + " · " + eligible["system_en"]

    prepared_curves = curves.merge(
        eligible[[*GROUP_COLUMNS, "group_id", "color"]],
        on=GROUP_COLUMNS,
        how="inner",
    )
    prepared_curves = prepared_curves[prepared_curves["curve_valid"]].copy()
    prepared_curves["date"] = prepared_curves["date"].dt.date.astype(str)

    phenology = []
    for key, data in curves.groupby(GROUP_COLUMNS, dropna=False, sort=False):
        key_record = dict(zip(GROUP_COLUMNS, key, strict=True))
        identifier = group_id(key_record)
        if identifier not in set(eligible["group_id"]):
            continue
        phenology.append({"group_id": identifier, **phenology_record(data)})
    phenology_table = pd.DataFrame(phenology)
    eligible = eligible.merge(phenology_table, on="group_id", how="left")

    units = gpd.read_file(units_path, layer="analysis_units")
    units["group_id"] = units.apply(group_id, axis=1)
    units["crop_sequence_en"] = units["crop_sequence"].map(translate_sequence)
    units["system_es"] = units["system_class"].map(SYSTEM_ES)
    units["system_en"] = units["system_class"].map(SYSTEM_EN)
    units = units.to_crs(32630)
    units.geometry = units.geometry.simplify(2.0, preserve_topology=True)
    units = units.to_crs(4326)[
        [
            "unit_id",
            "group_id",
            "crop_sequence",
            "crop_sequence_en",
            "system_class",
            "system_es",
            "system_en",
            "pivot_id",
            "analysis_area_ha",
            "geometry",
        ]
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    prepared_curves.to_csv(output_dir / "curves.csv", index=False)
    eligible.to_csv(output_dir / "groups.csv", index=False)
    (output_dir / "units.geojson").write_text(units.to_json(), encoding="utf-8")
    return eligible


def select_monthly_scenes(input_dir: Path) -> pd.DataFrame:
    """Choose the locally clearest existing NDVI scene in every calendar month."""
    rows: list[dict[str, Any]] = []
    for scene_date, path in discover_scenes(input_dir):
        with rasterio.open(path) as dataset:
            _, _, scl, data_mask = dataset.read()
        clear = (data_mask == 1) & np.isin(scl, (*CLEAR_SCL_CLASSES, 6))
        rows.append(
            {
                "month": scene_date.strftime("%Y-%m"),
                "date": scene_date.date().isoformat(),
                "clear_fraction": float(clear.mean()),
            }
        )
    table = pd.DataFrame(rows)
    selected = table.loc[table.groupby("month")["clear_fraction"].idxmax()].copy()
    return selected.sort_values("month").reset_index(drop=True)


def rgb_process_payload(
    start_date: date,
    end_date: date | None = None,
    *,
    width: int = 1000,
) -> dict[str, Any]:
    """Build a true-colour request; end_date is inclusive when provided."""
    west, south, east, north = DEFAULT_BBOX
    mean_latitude = np.deg2rad((south + north) / 2)
    aspect = ((east - west) * np.cos(mean_latitude)) / (north - south)
    height = max(1, round(width / aspect))
    final_date = end_date or start_date
    return {
        "input": {
            "bounds": {
                "bbox": list(DEFAULT_BBOX),
                "properties": {"crs": f"{CRS_URI_PREFIX}4326"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {
                            "from": f"{start_date.isoformat()}T00:00:00Z",
                            "to": f"{(final_date + timedelta(days=1)).isoformat()}T00:00:00Z",
                        },
                        "mosaickingOrder": "leastCC",
                        "maxCloudCoverage": DEFAULT_MAX_CATALOG_CLOUD_PERCENT,
                    },
                    "processing": {"harmonizeValues": True},
                }
            ],
        },
        "output": {
            "width": width,
            "height": height,
            "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
        },
        "evalscript": RGB_EVALSCRIPT,
    }


def _download_png(payload: dict[str, Any], token: str, destination: Path) -> None:
    request = Request(
        PROCESS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "image/png",
        },
        method="POST",
    )
    with _open_with_retries(request, timeout=300) as response:
        content = response.read()
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise PipelineError("Copernicus did not return a valid monthly RGB PNG.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".png.part")
    temporary.write_bytes(content)
    temporary.replace(destination)


def download_monthly_rgb(
    selected: pd.DataFrame,
    output_dir: Path = APP_DATA_DIR,
    *,
    overwrite: bool = False,
) -> None:
    """Download one compact true-colour image for each selected month."""
    load_env_file(BASE_DIR / "CREDENCIALES_COPERNICUS.env")
    load_env_file(BASE_DIR / ".env")
    client_id = os.environ.get("SH_CLIENT_ID")
    client_secret = os.environ.get("SH_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise PipelineError("Copernicus credentials are required to prepare monthly RGB images.")

    token = ""
    token_expiry = 0.0
    image_dir = output_dir / "monthly_rgb"
    records = []
    for index, row in selected.iterrows():
        destination = image_dir / f"{row['month']}.png"
        if not destination.exists() or overwrite:
            if time.monotonic() >= token_expiry:
                token, token_expiry = acquire_token(client_id, client_secret)
            month_start = date.fromisoformat(f"{row['month']}-01")
            if month_start.month == 12:
                next_month = date(month_start.year + 1, 1, 1)
            else:
                next_month = date(month_start.year, month_start.month + 1, 1)
            print(f"RGB {index + 1}/{len(selected)}: {row['month']} monthly mosaic")
            _download_png(
                rgb_process_payload(month_start, next_month - timedelta(days=1)),
                token,
                destination,
            )
        records.append(
            {
                **row.to_dict(),
                "image": f"monthly_rgb/{destination.name}",
            }
        )
    manifest = {
        "bbox_wgs84": list(DEFAULT_BBOX),
        "selection": "monthly Sentinel-2 L2A mosaic using least cloud cover order",
        "months": records,
    }
    (output_dir / "monthly_rgb.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
