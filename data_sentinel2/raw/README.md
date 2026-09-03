# Sentinel-2 raw inputs

The downloader writes one GeoTIFF per available UTC date in this directory.
Every file contains `B04`, `B08`, `SCL` and `dataMask`, in that order, on the
same 10 m UTM grid. `catalog_manifest.json` records the exact AOI, period,
product settings and catalogue results.

Do not place manual True Color or Level-1C exports here.
