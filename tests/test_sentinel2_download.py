"""Tests for the fixed Monegros II Sentinel-2 download contract."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from monegros_ndvi.download_sentinel2 import (
    EVALSCRIPT,
    download_time_series,
    process_payload,
    project_output_dir,
    target_utm_epsg,
    validate_bbox,
)
from monegros_ndvi.settings import BASE_DIR, DEFAULT_BBOX, EXPECTED_BANDS, PipelineError


class Sentinel2DownloadTests(unittest.TestCase):
    def test_selected_aoi_is_in_northern_utm_zone_30(self):
        validate_bbox(DEFAULT_BBOX)
        self.assertEqual(target_utm_epsg(DEFAULT_BBOX), 32630)

    def test_process_request_preserves_the_four_band_contract(self):
        payload = process_payload(
            (745_000, 4_590_000, 750_000, 4_595_000),
            32630,
            10,
            date(2025, 4, 1),
            60,
        )
        data_filter = payload["input"]["data"][0]["dataFilter"]
        self.assertEqual(payload["input"]["data"][0]["type"], "sentinel-2-l2a")
        self.assertEqual(payload["output"]["resx"], 10)
        self.assertEqual(data_filter["mosaickingOrder"], "leastCC")
        self.assertEqual(EXPECTED_BANDS, ("B04", "B08", "SCL", "dataMask"))
        self.assertIn('sampleType: "FLOAT32"', EVALSCRIPT)

    def test_output_cannot_escape_gis_monegros(self):
        with self.assertRaisesRegex(PipelineError, "GIS_Monegros"):
            project_output_dir(BASE_DIR.parent / "Exercise_1_Helena_Alcolea_Ruiz")

    def test_missing_credentials_fail_without_creating_output(self):
        with tempfile.TemporaryDirectory(dir=BASE_DIR) as temporary:
            output = Path(temporary) / "download"
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("monegros_ndvi.download_sentinel2.BASE_DIR", Path(temporary)),
                patch("monegros_ndvi.download_sentinel2.search_dates") as search,
            ):
                with self.assertRaisesRegex(PipelineError, "SH_CLIENT_ID"):
                    download_time_series(
                        bbox=DEFAULT_BBOX,
                        start_date=date(2025, 1, 1),
                        end_date=date(2025, 1, 31),
                        output_dir=output,
                    )
            search.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
