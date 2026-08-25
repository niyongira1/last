"""
Pulls the two real, verifiable spatial layers found on this machine and
clips them down to Burera District, saving small, GitHub friendly copies
into data/. This is run once. Everything downstream in build_dashboard.py
reads only from data/, not from the original D: drive paths, so the
dashboard project is portable and does not depend on any external ArcGIS
project folder existing on someone else's machine.

Source layers, both real, neither synthetic:
  Sector boundaries, D:\\ArcGIS Project\\Data\\Sector_Boundaries\\Sector_Boundaries.shp
    416 sectors nationally, the 17 Burera sector names match the thesis exactly.
  Elevation, D:\\ArcGIS Project\\Data\\Rwanda_SRTM30meters\\Rwanda_SRTM30meters.tif
    National SRTM 30 metre DEM, the same source and resolution the thesis cites.
"""

import json
import os

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask

SECTOR_SHP = r"D:\ArcGIS Project\Data\Sector_Boundaries\Sector_Boundaries.shp"
DEM_TIF = r"D:\ArcGIS Project\Data\Rwanda_SRTM30meters\Rwanda_SRTM30meters.tif"

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def extract_sectors():
    sectors = gpd.read_file(SECTOR_SHP)
    burera = sectors[sectors["district"].str.contains("Burera", case=False, na=False)].copy()
    burera = burera[["sector", "district", "province", "Shape__Are", "Shape__Len", "geometry"]]
    burera = burera.rename(columns={"Shape__Are": "Area_m2_gis", "Shape__Len": "Perimeter_m_gis"})
    burera["sector"] = burera["sector"].str.strip()
    burera = burera.sort_values("sector").reset_index(drop=True)

    out_path = os.path.join(DATA_DIR, "burera_sectors.geojson")
    burera.to_file(out_path, driver="GeoJSON")
    print(f"Wrote {out_path}, {len(burera)} sectors")
    print(sorted(burera["sector"].tolist()))
    return burera


def extract_dem(burera_gdf):
    if hasattr(burera_gdf, "union_all"):
        boundary = burera_gdf.union_all()
    else:
        boundary = burera_gdf.unary_union
    buffered = boundary.buffer(0.01)  # roughly 1 km margin in degrees

    with rasterio.open(DEM_TIF) as src:
        out_image, out_transform = mask(src, [buffered.__geo_interface__], crop=True)
        out_meta = src.meta.copy()
        out_meta.update({
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
            "compress": "lzw",
        })

    out_path = os.path.join(DATA_DIR, "burera_dem_clip.tif")
    with rasterio.open(out_path, "w", **out_meta) as dst:
        dst.write(out_image)

    valid = out_image[out_image != src.nodata] if src.nodata is not None else out_image
    print(f"Wrote {out_path}, shape {out_image.shape}, elevation range "
          f"{np.nanmin(valid):.0f} to {np.nanmax(valid):.0f} metres")


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    burera = extract_sectors()
    extract_dem(burera)
