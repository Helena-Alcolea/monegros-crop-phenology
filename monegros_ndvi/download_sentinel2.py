#!/usr/bin/env python3
"""Download the Monegros II NDVI-ready Sentinel-2 L2A time series."""

from __future__ import annotations

import json
import math
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from rasterio.warp import transform_bounds

from .settings import (
    BASE_DIR,
    DEFAULT_MAX_CATALOG_CLOUD_PERCENT,
    DEFAULT_RESOLUTION_M,
    EXPECTED_BANDS,
    MANIFEST_NAME,
    TIFF_NAME_TEMPLATE,
    ApiError,
    DataQualityError,
    PipelineError,
)


TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/"
    "protocol/openid-connect/token"
)
STAC_SEARCH_URL = "https://stac.dataspace.copernicus.eu/v1/search"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/process/v1"
CRS_URI_PREFIX = "http://www.opengis.net/def/crs/EPSG/0/"
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
MAX_REQUEST_ATTEMPTS = 4

EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{
      bands: ["B04", "B08", "SCL", "dataMask"],
      units: ["REFLECTANCE", "REFLECTANCE", "DN", "DN"]
    }],
    output: {
      id: "default",
      bands: 4,
      sampleType: "FLOAT32"
    }
  };
}

function evaluatePixel(sample) {
  return [sample.B04, sample.B08, sample.SCL, sample.dataMask];
}
"""


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without exposing or replacing secrets."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def validate_bbox(bbox: tuple[float, float, float, float]) -> None:
    """Validate a small WGS84 rectangle suitable for one UTM grid."""
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180):
        raise PipelineError("Bounding-box longitudes must satisfy -180 <= west < east <= 180.")
    if not (-80 <= south < north <= 84):
        raise PipelineError(
            "Bounding-box latitudes must satisfy -80 <= south < north <= 84 for UTM."
        )
    if south < 0 < north:
        raise PipelineError("The first version does not support an AOI crossing the equator.")
    west_zone = min(60, int(math.floor((west + 180) / 6)) + 1)
    east_zone = min(60, int(math.floor((east + 180) / 6)) + 1)
    if west_zone != east_zone:
        raise PipelineError(
            "The AOI crosses a UTM zone boundary; use a smaller rectangle or a prepared local dataset."
        )


def target_utm_epsg(bbox: tuple[float, float, float, float]) -> int:
    """Return the WGS84 UTM EPSG code for the centre of a validated AOI."""
    west, south, east, north = bbox
    longitude = (west + east) / 2
    latitude = (south + north) / 2
    zone = min(60, int(math.floor((longitude + 180) / 6)) + 1)
    return (32600 if latitude >= 0 else 32700) + zone


def projected_bbox(
    bbox: tuple[float, float, float, float], epsg: int
) -> tuple[float, float, float, float]:
    """Transform the WGS84 rectangle into its enclosing projected bounds."""
    return tuple(
        float(value)
        for value in transform_bounds(
            "EPSG:4326", f"EPSG:{epsg}", *bbox, densify_pts=21
        )
    )


def bbox_geometry(bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    """Create a GeoJSON polygon from west, south, east and north."""
    west, south, east, north = bbox
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [west, south],
                [east, south],
                [east, north],
                [west, north],
                [west, south],
            ]
        ],
    }


def _retry_delay(exc: HTTPError, attempt: int) -> float:
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    try:
        return max(float(retry_after), 1.0) if retry_after else 2.0**attempt
    except ValueError:
        return 2.0**attempt


def _open_with_retries(request: Request, timeout: int):
    last_error: Exception | None = None
    for attempt in range(MAX_REQUEST_ATTEMPTS):
        try:
            return urlopen(request, timeout=timeout)
        except HTTPError as exc:
            last_error = exc
            if exc.code not in RETRYABLE_HTTP_CODES or attempt == MAX_REQUEST_ATTEMPTS - 1:
                detail = exc.read().decode("utf-8", errors="replace")[:1000]
                raise ApiError(
                    f"HTTP {exc.code} from {request.full_url}: {detail}"
                ) from exc
            time.sleep(_retry_delay(exc, attempt))
        except URLError as exc:
            last_error = exc
            if attempt == MAX_REQUEST_ATTEMPTS - 1:
                raise ApiError(
                    f"Could not reach {request.full_url}: {exc.reason}"
                ) from exc
            time.sleep(2.0**attempt)
    raise ApiError(f"Request failed: {last_error}")


def request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Request JSON from a GET or POST endpoint with bounded retries."""
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request = Request(
        url,
        data=body,
        headers=request_headers,
        method="POST" if body is not None else "GET",
    )
    with _open_with_retries(request, timeout=120) as response:
        return json.load(response)


def acquire_token(client_id: str, client_secret: str) -> tuple[str, float]:
    """Exchange OAuth client credentials for a reusable short-lived token."""
    form = urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    request = Request(
        TOKEN_URL,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with _open_with_retries(request, timeout=60) as response:
            token_data = json.load(response)
    except ApiError as exc:
        raise ApiError(f"Authentication failed: {exc}") from exc

    if "access_token" not in token_data:
        raise ApiError("Authentication response did not contain an access token.")
    expires_in = int(token_data.get("expires_in", 300))
    return token_data["access_token"], time.monotonic() + max(expires_in - 60, 30)


def search_dates(
    geometry: dict[str, Any],
    start_date: date,
    end_date: date,
    max_cloud_percent: float,
) -> list[dict[str, Any]]:
    """Search every STAC page and keep one catalogue record per UTC date."""
    payload: dict[str, Any] | None = {
        "collections": ["sentinel-2-l2a"],
        "datetime": (
            f"{start_date.isoformat()}T00:00:00Z/"
            f"{end_date.isoformat()}T23:59:59Z"
        ),
        "intersects": geometry,
        "query": {"eo:cloud_cover": {"lte": max_cloud_percent}},
        "sortby": [{"field": "properties.datetime", "direction": "asc"}],
        "limit": 100,
    }
    url = STAC_SEARCH_URL
    features: list[dict[str, Any]] = []

    while url:
        page = request_json(url, payload=payload)
        features.extend(page.get("features", []))
        next_link = next(
            (link for link in page.get("links", []) if link.get("rel") == "next"),
            None,
        )
        if next_link is None:
            break
        url = next_link["href"]
        if next_link.get("method", "GET").upper() == "POST":
            payload = next_link.get("body", payload)
        else:
            payload = None

    # Adjacent tiles can share a date; Process API mosaics that day.
    by_date: dict[str, dict[str, Any]] = {}
    for feature in features:
        properties = feature.get("properties", {})
        timestamp = properties.get("datetime") or properties.get("start_datetime")
        if not timestamp:
            continue
        day = timestamp[:10]
        cloud = float(properties.get("eo:cloud_cover", 100.0))
        current = by_date.get(day)
        if current is None or cloud < current["catalog_cloud_percent"]:
            by_date[day] = {
                "date": day,
                "datetime": timestamp,
                "catalog_cloud_percent": cloud,
                "product_id": feature.get("id"),
            }
    return [by_date[key] for key in sorted(by_date)]


def process_payload(
    bounds: tuple[float, float, float, float],
    epsg: int,
    resolution_m: int,
    scene_date: date,
    max_cloud_percent: float,
) -> dict[str, Any]:
    """Build one daily Sentinel Hub Process API request."""
    next_day = scene_date + timedelta(days=1)
    return {
        "input": {
            "bounds": {
                "bbox": list(bounds),
                "properties": {"crs": f"{CRS_URI_PREFIX}{epsg}"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {
                            "from": f"{scene_date.isoformat()}T00:00:00Z",
                            "to": f"{next_day.isoformat()}T00:00:00Z",
                        },
                        "mosaickingOrder": "leastCC",
                        "maxCloudCoverage": max_cloud_percent,
                    },
                    "processing": {
                        "harmonizeValues": True,
                        "upsampling": "NEAREST",
                        "downsampling": "NEAREST",
                    },
                }
            ],
        },
        "output": {
            "resx": resolution_m,
            "resy": resolution_m,
            "responses": [
                {"identifier": "default", "format": {"type": "image/tiff"}}
            ],
        },
        "evalscript": EVALSCRIPT,
    }


def download_tiff(payload: dict[str, Any], token: str, destination: Path) -> None:
    """Download one TIFF atomically so partial files cannot look complete."""
    request = Request(
        PROCESS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "image/tiff",
        },
        method="POST",
    )
    with _open_with_retries(request, timeout=300) as response:
        content = response.read()
    if len(content) < 8 or content[:2] not in (b"II", b"MM"):
        raise ApiError("Process API response is not a valid TIFF file.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(content)
    temporary.replace(destination)


def _manifest_signature(manifest: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "collection",
        "processing_level",
        "reflectance_level",
        "bands",
        "bbox_wgs84",
        "period",
        "resolution_m",
        "target_crs",
    )
    return {key: manifest.get(key) for key in keys}


def _check_existing_dataset(output_dir: Path, expected: dict[str, Any]) -> None:
    manifest_path = output_dir / MANIFEST_NAME
    existing_tiffs = list(output_dir.glob("S2L2A_*_B04_B08_SCL_10m.tif"))
    if existing_tiffs and not manifest_path.exists():
        raise PipelineError(
            f"{output_dir} contains TIFFs but no {MANIFEST_NAME}; use a separate "
            "directory to avoid mixing datasets."
        )
    if manifest_path.exists():
        try:
            current = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError(f"Cannot read existing manifest: {exc}") from exc
        if _manifest_signature(current) != _manifest_signature(expected):
            raise PipelineError(
                "Existing download manifest does not match the requested AOI, "
                "period or product configuration. Use a separate input directory."
            )


def project_output_dir(output_dir: Path) -> Path:
    """Resolve an output path and keep every download inside GIS_Monegros."""
    project_root = BASE_DIR.resolve()
    resolved = output_dir.expanduser().resolve()
    if resolved == project_root or not resolved.is_relative_to(project_root):
        raise PipelineError(
            "Sentinel-2 downloads must be stored in a subdirectory of "
            f"{project_root}."
        )
    return resolved


def download_time_series(
    *,
    bbox: tuple[float, float, float, float],
    start_date: date,
    end_date: date,
    output_dir: Path,
    overwrite: bool = False,
    max_cloud_percent: float = DEFAULT_MAX_CATALOG_CLOUD_PERCENT,
    resolution_m: int = DEFAULT_RESOLUTION_M,
) -> dict[str, Any]:
    """Search and download the complete configured Sentinel-2 time series."""
    validate_bbox(bbox)
    if start_date > end_date:
        raise PipelineError("Start date must be on or before end date.")
    if not 0 <= max_cloud_percent <= 100:
        raise PipelineError("Maximum catalogue cloud percentage must be between 0 and 100.")
    if resolution_m <= 0:
        raise PipelineError("Resolution must be positive.")

    output_dir = project_output_dir(output_dir)
    # The visible filename is easier to edit from graphical file explorers.
    # Keep support for the conventional hidden .env as a fallback.
    load_env_file(BASE_DIR / "CREDENCIALES_COPERNICUS.env")
    load_env_file(BASE_DIR / ".env")
    client_id = os.environ.get("SH_CLIENT_ID")
    client_secret = os.environ.get("SH_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise PipelineError(
            "Set SH_CLIENT_ID and SH_CLIENT_SECRET as environment variables "
            f"or in {BASE_DIR / 'CREDENCIALES_COPERNICUS.env'}."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    epsg = target_utm_epsg(bbox)
    metric_bounds = projected_bbox(bbox, epsg)
    geometry = bbox_geometry(bbox)
    dates = search_dates(geometry, start_date, end_date, max_cloud_percent)
    if not dates:
        raise DataQualityError(
            "The catalogue returned no Sentinel-2 L2A dates for the requested inputs."
        )

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "collection": "sentinel-2-l2a",
        "processing_level": "L2A",
        "reflectance_level": "BOA",
        "bands": list(EXPECTED_BANDS),
        "dtype": "float32",
        "bbox_wgs84": list(bbox),
        "bbox_projected": list(metric_bounds),
        "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "resolution_m": resolution_m,
        "target_crs": f"EPSG:{epsg}",
        "max_catalog_cloud_percent": max_cloud_percent,
        "scene_count": len(dates),
        "scenes": dates,
    }
    _check_existing_dataset(output_dir, manifest)
    (output_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    token = ""
    token_expiry = 0.0
    downloaded = 0
    skipped = 0
    for index, item in enumerate(dates, start=1):
        day = date.fromisoformat(item["date"])
        destination = output_dir / TIFF_NAME_TEMPLATE.format(date=day.isoformat())
        if destination.exists() and not overwrite:
            skipped += 1
            print(f"[{index}/{len(dates)}] Skip existing {destination.name}")
            continue
        if time.monotonic() >= token_expiry:
            token, token_expiry = acquire_token(client_id, client_secret)
        print(f"[{index}/{len(dates)}] Download {day.isoformat()}")
        download_tiff(
            process_payload(
                metric_bounds,
                epsg,
                resolution_m,
                day,
                max_cloud_percent,
            ),
            token,
            destination,
        )
        downloaded += 1

    print(f"Download complete: {downloaded} downloaded, {skipped} skipped.")
    return manifest
