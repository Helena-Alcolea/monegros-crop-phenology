"""Tests for compact Streamlit data preparation."""

from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from monegros_ndvi.app_assets import phenology_record, rgb_process_payload, translate_sequence


class AppAssetTests(unittest.TestCase):
    def test_double_crop_phenology_uses_two_seasonal_windows(self):
        group = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-04-20", "2025-05-01", "2025-08-10", "2025-09-01"]),
                "curve_valid": [True, True, True, True],
                "ndvi_median_30d": [0.8, 0.6, 0.7, 0.9],
                "crop_sequence": ["Cebada → Maíz"] * 4,
            }
        )
        result = phenology_record(group)
        self.assertEqual(result["primary_peak_date"], "2025-04-20")
        self.assertEqual(result["secondary_peak_date"], "2025-09-01")
        self.assertEqual(result["primary_crop_en"], "Barley")
        self.assertEqual(result["secondary_crop_en"], "Maize")

    def test_rgb_request_covers_the_complete_month(self):
        payload = rgb_process_payload(date(2025, 7, 1), date(2025, 7, 31))
        time_range = payload["input"]["data"][0]["dataFilter"]["timeRange"]
        self.assertEqual(time_range["from"], "2025-07-01T00:00:00Z")
        self.assertEqual(time_range["to"], "2025-08-01T00:00:00Z")
        self.assertEqual(payload["output"]["width"], 1000)

    def test_crop_sequences_are_translated_term_by_term(self):
        self.assertEqual(translate_sequence("Guisante → Maíz"), "Pea → Maize")


if __name__ == "__main__":
    unittest.main()
