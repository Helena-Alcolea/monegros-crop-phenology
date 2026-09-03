#!/usr/bin/env python3
"""Shared settings for the Monegros II Sentinel-2 workflow."""

from __future__ import annotations

from datetime import date
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = BASE_DIR / "data_sentinel2" / "raw"
DEFAULT_OUTPUT_DIR = BASE_DIR / "ndvi_results"

AOI_NAME = "Monegros II — regadío, secano y pivotes"
DEFAULT_BBOX = (-0.078535, 41.455348, -0.020767, 41.492320)
DEFAULT_START_DATE = date(2024, 9, 1)
DEFAULT_END_DATE = date(2025, 10, 31)

EXPECTED_BANDS = ("B04", "B08", "SCL", "dataMask")
VALID_SCL_CLASSES = (4, 5)
VEGETATION_SCL_CLASS = 4

DEFAULT_NDVI_THRESHOLD = 0.45
DEFAULT_MIN_VEGETATED_DATES = 5
DEFAULT_MIN_VALID_FRACTION = 0.80
DEFAULT_MIN_COMPONENT_AREA_HA = 10.0
DEFAULT_COMPONENT_MODE = "largest"
COMPONENT_MODES = ("largest", "all")

DEFAULT_RESOLUTION_M = 10
DEFAULT_MAX_CATALOG_CLOUD_PERCENT = 60.0
DEFAULT_SMOOTHING_WINDOW_DAYS = 30
SMOOTHING_WINDOWS_DAYS = (15, 30, 45)
SEASONAL_MONTHS = (1, 4, 7, 10)
MAX_SENSITIVITY_PANELS = 64

TIFF_NAME_TEMPLATE = "S2L2A_{date}_B04_B08_SCL_10m.tif"
TIFF_NAME_GLOB = "S2L2A_*_B04_B08_SCL_10m.tif"
MANIFEST_NAME = "catalog_manifest.json"


class PipelineError(RuntimeError):
    """A user-facing pipeline error that does not require a traceback."""


class InputValidationError(PipelineError):
    """An error caused by missing or incompatible local input rasters."""


class DataQualityError(PipelineError):
    """An error caused by insufficient usable satellite observations."""


class ApiError(PipelineError):
    """An error returned by a Copernicus API or authentication service."""
