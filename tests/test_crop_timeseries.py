"""Numerical tests for parcel-level NDVI aggregation."""

from __future__ import annotations

import unittest

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, box

from analysis.analyze_crop_ndvi import build_parser
from monegros_ndvi.crop_timeseries import (
    aggregate_crop_curves,
    calculate_ndvi,
    split_analysis_units_by_pivots,
)


class CropTimeseriesTests(unittest.TestCase):
    def test_ndvi_formula_and_zero_denominator(self):
        red = np.array([[0.2, 0.0, 0.8]], dtype=np.float32)
        nir = np.array([[0.6, 0.0, 0.2]], dtype=np.float32)
        result = calculate_ndvi(red, nir)
        self.assertAlmostEqual(float(result[0, 0]), 0.5, places=6)
        self.assertTrue(np.isnan(result[0, 1]))
        self.assertAlmostEqual(float(result[0, 2]), -0.6, places=6)

    def test_non_positive_reflectance_is_rejected(self):
        red = np.array([[-1.0]], dtype=np.float32)
        nir = np.array([[2.0]], dtype=np.float32)
        self.assertTrue(np.isnan(calculate_ndvi(red, nir)[0, 0]))

    def test_default_unit_date_coverage_is_eighty_percent(self):
        args = build_parser().parse_args([])
        self.assertEqual(args.minimum_valid_fraction, 0.80)

    def test_confirmed_pivots_split_irrigated_units_and_ignore_candidates(self):
        units = gpd.GeoDataFrame(
            [
                {
                    "unit_id": "U0001",
                    "regime": "R",
                    "product_code": 4,
                    "provincia": 22,
                    "municipio": 1,
                    "poligono": 1,
                    "parcela": 1,
                    "recinto": 1,
                    "clipped_area_ha": 4.0,
                    "analysis_area_ha": 4.0,
                    "geometry": box(0, 0, 200, 200),
                }
            ],
            crs=32630,
        )
        pivots = gpd.GeoDataFrame(
            [
                {
                    "pivot_id": "P01",
                    "status": "confirmed",
                    "geometry": Point(50, 100).buffer(40),
                },
                {
                    "pivot_id": "P08",
                    "status": "candidate_low_confidence",
                    "geometry": Point(150, 100).buffer(40),
                },
            ],
            crs=32630,
        )
        split = split_analysis_units_by_pivots(
            units,
            pivots,
            minimum_area_ha=0.1,
            boundary_buffer_m=0,
        )
        self.assertEqual(set(split["system_class"]), {"pivot", "irrigated_non_pivot"})
        self.assertEqual(set(split.loc[split["system_class"] == "pivot", "pivot_id"]), {"P01"})
        self.assertFalse(split["regime_geometry_conflict"].any())

    def test_dryland_inside_pivot_is_flagged_as_a_regime_conflict(self):
        units = gpd.GeoDataFrame(
            [
                {
                    "unit_id": "U0001",
                    "regime": "S",
                    "product_code": 20,
                    "provincia": 22,
                    "municipio": 1,
                    "poligono": 1,
                    "parcela": 1,
                    "recinto": 1,
                    "clipped_area_ha": 1.0,
                    "analysis_area_ha": 1.0,
                    "geometry": box(0, 0, 100, 100),
                }
            ],
            crs=32630,
        )
        pivots = gpd.GeoDataFrame(
            [
                {
                    "pivot_id": "P01",
                    "status": "confirmed",
                    "geometry": Point(50, 50).buffer(80),
                }
            ],
            crs=32630,
        )
        split = split_analysis_units_by_pivots(
            units,
            pivots,
            minimum_area_ha=0.1,
            boundary_buffer_m=0,
        )
        pivot_piece = split[split["system_class"] == "pivot"].iloc[0]
        self.assertTrue(pivot_piece["regime_geometry_conflict"])

    def test_pivot_fragments_are_collapsed_before_crop_aggregation(self):
        shared = {
            "product_code": 4,
            "crop_name": "Maíz",
            "crop_group": "Cereal",
            "crop_sequence": "Maíz",
            "regime": "R",
            "system_class": "pivot",
        }
        units = gpd.GeoDataFrame(
            [
                {**shared, "unit_id": "A1", "pivot_id": "P01", "geometry": Point(0, 0)},
                {**shared, "unit_id": "A2", "pivot_id": "P01", "geometry": Point(1, 0)},
                {**shared, "unit_id": "A3", "pivot_id": "P02", "geometry": Point(2, 0)},
            ],
            crs=32630,
        )
        observations = pd.DataFrame(
            [
                {**shared, "date": "2025-07-01", "unit_id": "A1", "pivot_id": "P01", "valid_fraction": 1.0, "ndvi_median": 0.1},
                {**shared, "date": "2025-07-01", "unit_id": "A2", "pivot_id": "P01", "valid_fraction": 1.0, "ndvi_median": 0.9},
                {**shared, "date": "2025-07-01", "unit_id": "A3", "pivot_id": "P02", "valid_fraction": 1.0, "ndvi_median": 0.8},
            ]
        )

        curves = aggregate_crop_curves(
            observations,
            units,
            minimum_valid_fraction=0.8,
            minimum_units_per_date=1,
        )

        row = curves.iloc[0]
        self.assertEqual(int(row["total_units"]), 3)
        self.assertEqual(int(row["total_samples"]), 2)
        self.assertEqual(int(row["observed_samples"]), 2)
        self.assertAlmostEqual(float(row["ndvi_median"]), 0.65)


if __name__ == "__main__":
    unittest.main()
