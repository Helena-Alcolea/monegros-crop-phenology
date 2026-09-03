# Original SIGPAC/PAC inputs

The multi-gigabyte GeoPackages in this directory are intentionally excluded
from Git. The processing pipeline expects the 2025 declared-crop files for
Huesca (`0222`) and Zaragoza (`0250`) using their original filenames.

The deployed dashboard does not need these sources. It reads the compact,
derived geometries in `dashboard/app_data/units.geojson` instead.
