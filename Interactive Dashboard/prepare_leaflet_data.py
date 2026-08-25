"""
Precomputes everything the Leaflet dashboard needs as plain JSON, so the
page itself is static and needs no server side logic.

For every one of the three weighting scenarios (equal, AHP judgement,
strong population emphasis) this works out each sector's priority tier,
then spatially joins the real school points against the real sector
polygons to tag every school with the sector it physically sits in and,
through that, the tier that sector falls into under each scenario. That is
what lets the page answer a question like "show me only the schools inside
a Priority 1 Critical sector" for any of the three weightings, not just one.
"""

import json
import os

import geopandas as gpd
import pandas as pd

from model import load_sector_data, compute_indices, compute_cwai, classify_tiers

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

WEIGHT_SCENARIOS = [
    ("equal", "Equal weight (0.50 / 0.50)", 0.50),
    ("ahp", "AHP judgement, adopted (0.33 / 0.67)", 0.67),
    ("strong", "Strong population emphasis (0.17 / 0.83)", 0.8333),
]

TIER_COLORS = {
    "Priority 1, Critical": "#b23a48",
    "Priority 2, High": "#d97b4f",
    "Priority 3, Moderate": "#e0b23c",
    "Priority 4, Below Average": "#7fa37f",
    "Priority 5, Adequate": "#3f7d5c",
}

SECONDARY_CATEGORIES = ["NINE_TWELVE_YBE_GS", "TVET", "SECONDARY", "TTC"]


def main():
    gdf = gpd.read_file(os.path.join(DATA_DIR, "burera_sectors.geojson"))
    gdf["sector"] = gdf["sector"].str.strip()

    raw = load_sector_data()
    with_indices = compute_indices(raw)

    scenario_tiers = {}
    for key, label, w2 in WEIGHT_SCENARIOS:
        ranked = compute_cwai(with_indices, w2=w2)
        tiered = classify_tiers(ranked)
        scenario_tiers[key] = tiered.set_index("Sector")[["Tier", "CWAI", "Composite_Rank"]]

    for key, label, w2 in WEIGHT_SCENARIOS:
        t = scenario_tiers[key]
        gdf[f"tier_{key}"] = gdf["sector"].map(t["Tier"])
        gdf[f"cwai_{key}"] = gdf["sector"].map(t["CWAI"]).round(3)
        gdf[f"rank_{key}"] = gdf["sector"].map(t["Composite_Rank"])

    centroids = gdf.geometry.centroid
    gdf["centroid_lat"] = centroids.y
    gdf["centroid_lon"] = centroids.x

    merged = gdf.merge(with_indices, left_on="sector", right_on="Sector", how="left")

    sectors_out = json.loads(merged.to_json())
    with open(os.path.join(DATA_DIR, "sectors_with_tiers.geojson"), "w", encoding="utf-8") as f:
        json.dump(sectors_out, f)
    print(f"Wrote sectors_with_tiers.geojson, {len(merged)} sectors")

    schools_df = pd.read_csv(os.path.join(DATA_DIR, "burera_schools.csv"))
    if "District" in schools_df.columns:
        schools_df = schools_df[schools_df["District"].astype(str).str.upper() == "BURERA"]
    schools_df["Category"] = schools_df["school_category"].apply(
        lambda c: "Primary" if c == "PRIMARY" else ("Secondary" if c in SECONDARY_CATEGORIES else "Other")
    )
    schools_df = schools_df[schools_df["Category"] != "Other"].copy()

    schools_gdf = gpd.GeoDataFrame(
        schools_df,
        geometry=gpd.points_from_xy(schools_df["Longitude"], schools_df["Latitude"]),
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(schools_gdf, gdf[["sector", "geometry"]], how="left", predicate="within")
    joined = joined.drop(columns=["geometry", "index_right"])

    for key, label, w2 in WEIGHT_SCENARIOS:
        t = scenario_tiers[key]
        joined[f"tier_{key}"] = joined["sector"].map(t["Tier"])

    schools_records = []
    for row in joined.itertuples():
        rec = {
            "name": row.School_name,
            "category": row.Category,
            "sector": row.sector if isinstance(row.sector, str) else None,
            "lat": row.Latitude,
            "lon": row.Longitude,
        }
        for key, label, w2 in WEIGHT_SCENARIOS:
            rec[f"tier_{key}"] = getattr(row, f"tier_{key}")
        schools_records.append(rec)

    with open(os.path.join(DATA_DIR, "schools_with_tiers.json"), "w", encoding="utf-8") as f:
        json.dump(schools_records, f)
    print(f"Wrote schools_with_tiers.json, {len(schools_records)} schools")

    unmatched = joined["sector"].isna().sum()
    if unmatched:
        print(f"Warning: {unmatched} schools did not fall inside any sector polygon (edge/precision cases)")

    for key, label, w2 in WEIGHT_SCENARIOS:
        n_critical_schools = sum(1 for r in schools_records if r[f"tier_{key}"] == "Priority 1, Critical")
        print(f"Scenario '{label}': {n_critical_schools} real schools sit inside a Priority 1 Critical sector")


if __name__ == "__main__":
    main()
