import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from monegros_ndvi.phenology import calendar_for


BASE_DIR = Path(__file__).resolve().parents[1]


class PhenologyCalendarTests(unittest.TestCase):
    def test_every_dashboard_sequence_has_an_approximate_calendar(self) -> None:
        groups = pd.read_csv(BASE_DIR / "dashboard" / "app_data" / "groups.csv")
        missing = [
            sequence
            for sequence in groups["crop_sequence"].unique()
            if not calendar_for(sequence)
        ]
        self.assertEqual(missing, [])

    def test_phase_windows_are_valid_and_inside_the_dashboard_period(self) -> None:
        groups = pd.read_csv(BASE_DIR / "dashboard" / "app_data" / "groups.csv")
        lower = date(2024, 9, 1)
        upper = date(2025, 10, 31)
        for sequence in groups["crop_sequence"].unique():
            for phase in calendar_for(sequence):
                start = date.fromisoformat(phase["start"])
                end = date.fromisoformat(phase["end"])
                self.assertLessEqual(start, end)
                self.assertGreaterEqual(start, lower)
                self.assertLessEqual(end, upper)


if __name__ == "__main__":
    unittest.main()
