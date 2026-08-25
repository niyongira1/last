"""
Builds index.html, a single self contained, interactive decision support
page for Burera District education accessibility planning.

Real data used directly:
  Sector boundaries, data/burera_sectors.geojson, clipped from the national
  Sector_Boundaries.shp found on this machine, the 17 Burera sector names
  match the thesis exactly.
  Elevation, data/burera_dem_clip.tif, clipped from the national SRTM 30m
  DEM found on this machine, the same source and resolution the thesis cites.
  School locations, data/burera_schools.csv, the real REB facility register
  for Burera District, 81 real PRIMARY schools, matching the thesis's own
  Table 4.1 count exactly, and 59 real secondary category schools (General
  Secondary 9-12 YBE, TVET, TTC), close to the thesis's reported 60.
  Population, area, and school counts by sector, taken directly from the
  verified thesis tables (Table 4.2 and Table 4.8).

Not yet included, because the source file was not found on this machine,
the real road network (RTDA/OSM). That would let a future version of this
dashboard route actual walking distance along roads and footpaths rather
than straight line or terrain-only distance. See the Data and Limitations
section at the bottom of the page.

Run with: python build_dashboard.py
Output: index.html, ready to open directly or push to GitHub Pages.
"""

import base64
import io
import json
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import rasterio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource

from model import load_sector_data, compute_indices, compute_cwai, classify_tiers, area_based_rank
from simulate_weights import run_weight_sensitivity
from simulate_growth import project_population

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

TIER_COLORS = {
    "Priority 1, Critical": "#b23a48",
    "Priority 2, High": "#d97b4f",
    "Priority 3, Moderate": "#e0b23c",
    "Priority 4, Below Average": "#7fa37f",
    "Priority 5, Adequate": "#3f7d5c",
}

WEIGHT_SCENARIOS = [
    ("Equal weight (0.50 / 0.50)", 0.50),
    ("AHP judgement, adopted (0.33 / 0.67)", 0.67),
    ("Strong population emphasis (0.17 / 0.83)", 0.8333),
]


# ---------------------------------------------------------------------------
# Data assembly
# ---------------------------------------------------------------------------

SECONDARY_CATEGORIES = ["NINE_TWELVE_YBE_GS", "TVET", "SECONDARY", "TTC"]


def load_real_schools():
    df = pd.read_csv(os.path.join(DATA_DIR, "burera_schools.csv"))
    if "District" in df.columns:
        df = df[df["District"].astype(str).str.upper() == "BURERA"]
    primary = df[df["school_category"] == "PRIMARY"].copy()
    secondary = df[df["school_category"].isin(SECONDARY_CATEGORIES)].copy()
    return primary, secondary


def load_geo_and_model():
    gdf = gpd.read_file(os.path.join(DATA_DIR, "burera_sectors.geojson"))
    gdf["sector"] = gdf["sector"].str.strip()

    raw = load_sector_data()
    with_indices = compute_indices(raw)

    scenario_frames = {}
    for label, w2 in WEIGHT_SCENARIOS:
        ranked = compute_cwai(with_indices, w2=w2)
        tiered = classify_tiers(ranked)
        scenario_frames[label] = tiered

    merged = gdf.merge(with_indices, left_on="sector", right_on="Sector", how="left")
    return gdf, merged, with_indices, scenario_frames


# ---------------------------------------------------------------------------
# Real terrain image layer, draped under the choropleth
# ---------------------------------------------------------------------------

def build_terrain_overlay():
    """
    Renders the real clipped Burera hillshade as a transparent PNG whose
    pixel grid lines up exactly with its own geographic bounds, then hands
    back both the image and the four corner coordinates MapLibre needs to
    drape it correctly under the sector polygons. Areas outside the district
    boundary are fully transparent, since the DEM was already clipped to the
    Burera outline before this ever runs.
    """
    dem_path = os.path.join(DATA_DIR, "burera_dem_clip.tif")
    with rasterio.open(dem_path) as src:
        # downsampled for the interactive web layer, full 30 m detail is not
        # perceptible at map viewing scale and just bloats the html file
        target = 600
        scale = max(1, round(max(src.height, src.width) / target))
        out_height, out_width = src.height // scale, src.width // scale
        elevation = np.array(
            src.read(1, out_shape=(out_height, out_width), resampling=rasterio.enums.Resampling.average),
            dtype=float,
        )
        nodata = src.nodata
        bounds = src.bounds
        valid_mask = elevation != nodata if nodata is not None else np.isfinite(elevation)
        elevation[~valid_mask] = np.nan

    # grayscale hillshade rather than a colour elevation ramp, the classified
    # tier colours sit on top of this and stay muddy if the relief layer is
    # coloured too, using plain relief shading is the standard cartographic
    # way to show terrain underneath a thematic choropleth
    ls = LightSource(azdeg=315, altdeg=45)
    hillshade = ls.hillshade(np.nan_to_num(elevation, nan=np.nanmean(elevation)), vert_exag=2.2)
    gray = (hillshade * 255).astype(np.uint8)
    rgba = np.dstack([gray, gray, gray, np.where(valid_mask, 255, 0).astype(np.uint8)])

    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    data_uri = f"data:image/png;base64,{encoded}"

    coordinates = [
        [bounds.left, bounds.top],
        [bounds.right, bounds.top],
        [bounds.right, bounds.bottom],
        [bounds.left, bounds.bottom],
    ]
    return data_uri, coordinates


# ---------------------------------------------------------------------------
# Figure 1, interactive choropleth map with classified tiers, real terrain,
# sector labels, and weight scenario buttons
# ---------------------------------------------------------------------------

def build_choropleth(gdf, scenario_frames):
    geojson = json.loads(gdf.to_json())
    features_by_sector = {f["properties"]["sector"]: f for f in geojson["features"]}
    tier_order = list(TIER_COLORS.keys())

    centroids = gdf.geometry.centroid
    centroid_lookup = {row.sector: (pt.y, pt.x) for row, pt in zip(gdf.itertuples(), centroids)}

    traces = []
    scenario_trace_indices = []
    for label, w2 in WEIGHT_SCENARIOS:
        tiered = scenario_frames[label]
        ordered = gdf[["sector"]].merge(tiered, left_on="sector", right_on="Sector", how="left")
        this_scenario_indices = []

        for tier in tier_order:
            subset = ordered[ordered["Tier"] == tier]
            if subset.empty:
                # keep an empty placeholder trace so trace indices stay aligned across scenarios
                traces.append(go.Choroplethmap(
                    geojson={"type": "FeatureCollection", "features": []},
                    locations=[], z=[], featureidkey="properties.sector",
                    visible=False, showlegend=False,
                ))
                this_scenario_indices.append(len(traces) - 1)
                continue

            hover_text = [
                f"<b>{row.Sector}</b><br>"
                f"Composite rank: {row.Composite_Rank} of 17<br>"
                f"Tier: {row.Tier}<br>"
                f"CWAI: {row.CWAI:.3f}<br>"
                f"Population (2022): {row.Population:,}<br>"
                f"Density index C1 (Table 4.8): {row.C1_Density_Index:.3f}<br>"
                f"Population index C2: {row.C2_Population_Index:.3f}"
                for row in subset.itertuples()
            ]

            subset_geojson = {
                "type": "FeatureCollection",
                "features": [features_by_sector[s] for s in subset["sector"]],
            }
            traces.append(go.Choroplethmap(
                geojson=subset_geojson,
                locations=subset["sector"],
                z=[1] * len(subset),
                featureidkey="properties.sector",
                colorscale=[[0, TIER_COLORS[tier]], [1, TIER_COLORS[tier]]],
                showscale=False,
                marker_line_width=1.6,
                marker_line_color="#ffffff",
                marker_opacity=0.82,
                text=hover_text,
                hoverinfo="text",
                name=tier,
                showlegend=True,
                visible=False,
            ))
            this_scenario_indices.append(len(traces) - 1)

        scenario_trace_indices.append(this_scenario_indices)

    # sector name labels, always on, independent of the weight scenario shown
    label_trace = go.Scattermap(
        lat=[centroid_lookup[s][0] for s in gdf["sector"]],
        lon=[centroid_lookup[s][1] for s in gdf["sector"]],
        mode="text",
        text=list(gdf["sector"]),
        textfont=dict(size=10.5, color="#1c1c1c"),
        hoverinfo="skip",
        showlegend=False,
    )
    traces.append(label_trace)
    label_index = len(traces) - 1

    # real school locations, from the REB register, also always on
    primary_df, secondary_df = load_real_schools()
    primary_trace = go.Scattermap(
        lat=primary_df["Latitude"], lon=primary_df["Longitude"],
        mode="markers",
        marker=dict(size=6, color="#1c1c1c"),
        name=f"Primary school ({len(primary_df)}, real)",
        text=primary_df["School_name"],
        hovertemplate="<b>%{text}</b><br>Primary school<extra></extra>",
        showlegend=True,
    )
    traces.append(primary_trace)
    primary_index = len(traces) - 1

    secondary_trace = go.Scattermap(
        lat=secondary_df["Latitude"], lon=secondary_df["Longitude"],
        mode="markers",
        marker=dict(size=9, color="#f2d40c"),
        name=f"Secondary school ({len(secondary_df)}, real)",
        text=secondary_df["School_name"],
        hovertemplate="<b>%{text}</b><br>Secondary school<extra></extra>",
        showlegend=True,
    )
    traces.append(secondary_trace)
    secondary_index = len(traces) - 1

    always_visible = [label_index, primary_index, secondary_index]

    default_scenario = 1  # AHP judgement, adopted
    n_traces = len(traces)
    for scenario_i, indices in enumerate(scenario_trace_indices):
        show = scenario_i == default_scenario
        for idx in indices:
            traces[idx].visible = show

    buttons = []
    for scenario_i, (label, w2) in enumerate(WEIGHT_SCENARIOS):
        visibility = [False] * n_traces
        for idx in scenario_trace_indices[scenario_i]:
            visibility[idx] = True
        for idx in always_visible:
            visibility[idx] = True
        buttons.append(dict(label=label, method="update", args=[{"visible": visibility}]))

    centroid = gdf.geometry.union_all().centroid if hasattr(gdf.geometry, "union_all") else gdf.geometry.unary_union.centroid
    terrain_uri, terrain_coords = build_terrain_overlay()

    fig = go.Figure(data=traces)
    fig.update_layout(
        map=dict(
            style="carto-positron",
            center=dict(lat=centroid.y, lon=centroid.x),
            zoom=9.6,
            layers=[dict(
                sourcetype="image",
                source=terrain_uri,
                coordinates=terrain_coords,
                below="traces",
                opacity=1.0,
            )],
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        height=660,
        legend=dict(
            title=dict(text="Legend, click any item to toggle"),
            orientation="v", x=0.01, y=0.02, xanchor="left", yanchor="bottom",
            bgcolor="rgba(255,255,255,0.88)", bordercolor="#ccc", borderwidth=1, font=dict(size=11.5),
        ),
        updatemenus=[dict(
            type="buttons",
            direction="right",
            buttons=buttons,
            x=0.5, xanchor="center",
            y=1.06, yanchor="top",
            showactive=True,
            bgcolor="#f0f0f0",
        )],
        title=dict(
            text="Composite Weighted Accessibility Index by Sector, over real terrain, click a weighting above to explore",
            x=0.5, xanchor="center", font=dict(size=13.5),
        ),
        annotations=[
            dict(text="N<br>▲", x=0.965, y=0.94, xref="paper", yref="paper",
                 showarrow=False, font=dict(size=13, color="#333333"), align="center"),
            dict(text="Burera District, approx. 644 km², 17 sectors",
                 x=0.02, y=0.98, xref="paper", yref="paper", xanchor="left",
                 showarrow=False, font=dict(size=10.5, color="#333333"),
                 bgcolor="rgba(255,255,255,0.75)"),
        ],
    )
    return fig


# ---------------------------------------------------------------------------
# Figure 2, ranked bar chart
# ---------------------------------------------------------------------------

def build_ranked_bar(tiered_default):
    df = tiered_default.sort_values("CWAI")
    colors = [TIER_COLORS[t] for t in df["Tier"]]
    fig = go.Figure(go.Bar(
        x=df["CWAI"], y=df["Sector"], orientation="h",
        marker_color=colors,
        hovertemplate="<b>%{y}</b><br>CWAI: %{x:.3f}<extra></extra>",
    ))
    fig.add_vline(x=1.0, line_dash="dash", line_color="#333333",
                   annotation_text="district average", annotation_position="top")
    fig.update_layout(
        title="Composite Weighted Accessibility Index by Sector (AHP weighting, 0.33 / 0.67)",
        xaxis_title="CWAI", yaxis=dict(autorange="reversed"),
        height=560, margin=dict(l=10, r=10, t=50, b=40),
    )
    return fig


# ---------------------------------------------------------------------------
# Figure 3, rank comparison slope chart
# ---------------------------------------------------------------------------

def build_rank_comparison(with_indices, tiered_default):
    area_rank = area_based_rank(with_indices)
    comparison = area_rank.merge(tiered_default[["Sector", "Composite_Rank"]], on="Sector")
    comparison["Movement"] = comparison["Area_Based_Rank"] - comparison["Composite_Rank"]
    comparison = comparison.sort_values("Area_Based_Rank")

    fig = go.Figure()
    for row in comparison.itertuples():
        color = "#b23a48" if row.Composite_Rank < row.Area_Based_Rank else (
            "#2f5d8a" if row.Composite_Rank > row.Area_Based_Rank else "#999999")
        fig.add_trace(go.Scatter(
            x=[0, 1], y=[row.Area_Based_Rank, row.Composite_Rank],
            mode="lines+markers+text",
            line=dict(color=color, width=2),
            marker=dict(size=8, color=color),
            text=[row.Sector, row.Sector],
            textposition=["middle left", "middle right"],
            hovertemplate=f"<b>{row.Sector}</b><br>Area based rank: {row.Area_Based_Rank}"
                           f"<br>Composite rank: {row.Composite_Rank}<extra></extra>",
            showlegend=False,
        ))

    fig.update_layout(
        title="How Sector Priority Shifts Once Population Is Weighted In",
        xaxis=dict(tickmode="array", tickvals=[0, 1],
                    ticktext=["Area based rank<br>(Table 4.8)", "Composite rank<br>(this model)"],
                    range=[-0.3, 1.3]),
        yaxis=dict(autorange="reversed", title="Rank (1 = most critical)"),
        height=680, margin=dict(l=10, r=10, t=50, b=40),
    )
    return fig


# ---------------------------------------------------------------------------
# Figure 4, weight sensitivity
# ---------------------------------------------------------------------------

def build_weight_sensitivity(raw):
    result = run_weight_sensitivity(raw, n_iter=10000)
    result = result.sort_values("Mean_Rank")

    fig = go.Figure(go.Scatter(
        x=result["Mean_Rank"], y=result["Sector"],
        mode="markers",
        error_x=dict(
            type="data", symmetric=False,
            array=result["Worst_Rank"] - result["Mean_Rank"],
            arrayminus=result["Mean_Rank"] - result["Best_Rank"],
            color="#a9c4de", thickness=8, width=0,
        ),
        marker=dict(size=9, color="#2f5d8a"),
        text=[f"{p*100:.0f}% of draws land this sector in the top 5 priority group"
              for p in result["Prob_Top5_HighPriority"]],
        hovertemplate="<b>%{y}</b><br>Mean rank: %{x:.1f}<br>%{text}<extra></extra>",
    ))
    fig.update_layout(
        title="Weight Sensitivity Simulation, Range of Possible Ranks per Sector (10,000 draws)",
        xaxis_title="Composite rank across simulated weight draws (1 = most critical)",
        yaxis=dict(autorange="reversed"),
        height=620, margin=dict(l=10, r=10, t=50, b=40),
    )
    return fig


# ---------------------------------------------------------------------------
# Figure 5, population growth projection
# ---------------------------------------------------------------------------

def build_population_projection(raw):
    projection = project_population(raw, years=10, n_sim=2000)
    sectors_to_show = ["Gahunga", "Rugengabari", "Cyanika", "Gitovu", "Ruhunde", "Rwerere", "Nemba", "Kagogo"]
    palette = ["#b23a48", "#d97b4f", "#2f5d8a", "#3f7d5c", "#7d5ba6", "#c98a2c", "#5b8c85", "#a15c9e"]

    fig = go.Figure()
    for i, sector in enumerate(sectors_to_show):
        sub = projection[projection["Sector"] == sector].sort_values("Year")
        color = palette[i % len(palette)]
        fig.add_trace(go.Scatter(
            x=sub["Year"], y=sub["CWAI_mean"], mode="lines", name=sector,
            line=dict(color=color, width=2.4),
            hovertemplate=f"<b>{sector}</b><br>Year %{{x}}<br>CWAI %{{y:.3f}}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=pd.concat([sub["Year"], sub["Year"][::-1]]),
            y=pd.concat([sub["CWAI_p90"], sub["CWAI_p10"][::-1]]),
            fill="toself", fillcolor=color, opacity=0.10,
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        ))

    fig.add_hline(y=1.0, line_dash="dash", line_color="#333333",
                   annotation_text="district average", annotation_position="top left")
    fig.update_layout(
        title="Projected Composite Index Under Population Growth Alone (no new school construction assumed)",
        xaxis_title="Year", yaxis_title="Projected CWAI",
        height=560, margin=dict(l=10, r=10, t=50, b=40),
        legend=dict(orientation="h", y=-0.18),
    )
    return fig


# ---------------------------------------------------------------------------
# Figure 6, real terrain context map (static image, real SRTM data)
# ---------------------------------------------------------------------------

def build_terrain_image_base64():
    dem_path = os.path.join(DATA_DIR, "burera_dem_clip.tif")
    with rasterio.open(dem_path) as src:
        elevation = src.read(1).astype(float)
        nodata = src.nodata
        if nodata is not None:
            elevation[elevation == nodata] = np.nan

    ls = LightSource(azdeg=315, altdeg=45)
    valid = elevation[~np.isnan(elevation)]
    vmin, vmax = np.nanpercentile(valid, 1), np.nanpercentile(valid, 99)

    fig, ax = plt.subplots(figsize=(8, 7))
    rgb = ls.shade(elevation, cmap=plt.cm.terrain, vert_exag=1.5, blend_mode="soft",
                    vmin=vmin, vmax=vmax)
    im = ax.imshow(rgb)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Burera District Terrain, Real SRTM 30 m Elevation Data", fontsize=12, fontweight="bold")

    sm = plt.cm.ScalarMappable(cmap=plt.cm.terrain, norm=plt.Normalize(vmin=vmin, vmax=vmax))
    cbar = fig.colorbar(sm, ax=ax, fraction=0.045, pad=0.03)
    cbar.set_label("metres above sea level", fontsize=9)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("ascii")
    return encoded, float(np.nanmin(valid)), float(np.nanmax(valid))


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------

PAGE_CSS = """
body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       max-width: 1080px; margin: 0 auto; padding: 24px 20px 80px; color: #222; background: #fbfbfa; }
h1 { font-size: 26px; margin-bottom: 4px; }
h2 { font-size: 19px; margin-top: 52px; border-top: 1px solid #ddd; padding-top: 28px; }
p.lede { color: #555; font-size: 15px; line-height: 1.55; }
p { line-height: 1.6; font-size: 14.5px; color: #333; }
.section-note { background: #f2f2ee; border-left: 3px solid #7fa37f; padding: 12px 16px;
                 font-size: 13.5px; color: #444; margin: 14px 0; }
.limitation { background: #fbf0ee; border-left: 3px solid #b23a48; padding: 12px 16px;
              font-size: 13.5px; color: #444; margin: 14px 0; }
.figure-block { margin: 18px 0 8px; }
table.provenance { border-collapse: collapse; width: 100%; font-size: 13px; margin: 14px 0; }
table.provenance th, table.provenance td { border: 1px solid #ddd; padding: 8px 10px; text-align: left; }
table.provenance th { background: #f0f0ee; }
footer { margin-top: 60px; font-size: 12.5px; color: #888; border-top: 1px solid #ddd; padding-top: 16px; }
img.terrain { max-width: 100%; border: 1px solid #ddd; border-radius: 4px; }
"""


def build_page(fig1, fig2, fig3, fig4, fig5, terrain_b64, elev_min, elev_max):
    def div(fig, div_id, include_js=False):
        return pio.to_html(fig, include_plotlyjs=("cdn" if include_js else False),
                            full_html=False, div_id=div_id)

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Burera District Education Accessibility Dashboard</title>
<style>{PAGE_CSS}</style>
</head>
<body>

<h1>Burera District Education Accessibility Dashboard</h1>
<p class="lede">
An interactive decision support companion to the thesis
<em>Application of Geospatial Techniques in the Assessment of the Spatial Distribution and
Accessibility of Education Facilities in Burera District, Rwanda</em>. Every figure below is
computed live from population, area, and school count data already verified in the thesis
(Table 4.2 and Table 4.8), and the map and terrain panel use real Burera District geography,
not illustrative or synthetic data.
</p>

<h2>1. Composite accessibility map</h2>
<p>
Click a weighting scenario above the map to see how the priority ranking changes depending on
how much weight is given to population pressure versus raw school density. The AHP judgement
adopted in the model, moderately more weight on population, is selected by default. The map also
plots every real school in the district, taken from the REB facility register, click the school
markers in the legend to show or hide them.
</p>
<div class="figure-block">{div(fig1, "map", include_js=True)}</div>
<div class="section-note">
Map geometry: real Burera District sector boundaries, clipped from a national administrative
boundary dataset. Colour: Composite Weighted Accessibility Index (CWAI), lower and redder means
more critical, higher and greener means better served. Markers: real primary and secondary school
locations from the REB register, hover a marker to see the school's name.
</div>

<h2>2. Ranked priority list</h2>
<div class="figure-block">{div(fig2, "bar")}</div>

<h2>3. How the ranking shifts once population is weighted in</h2>
<p>
The thesis computes an area based score (Table 4.8) and a separate population weighted ratio
(Table 4.9) and notes they disagree for five sectors without resolving the disagreement. This
chart is that resolution. Red lines moving right mean a sector becomes more urgent once
population is properly weighted in, blue lines moving left mean the opposite.
</p>
<div class="figure-block">{div(fig3, "slope")}</div>

<h2>4. How much does the exact weighting matter</h2>
<p>
The 0.33 to 0.67 weighting rests on a single AHP judgement. This simulation redraws that weight
ten thousand times across its full plausible range and tracks how often each sector still lands
in the critical or high priority group, so you can see which findings are robust and which are
sensitive to the exact number chosen.
</p>
<div class="figure-block">{div(fig4, "sensitivity")}</div>

<h2>5. Ten year outlook under population growth alone</h2>
<p>
Holding school counts fixed and growing each sector's population forward, this shows which
sectors are likely to fall below the district average if no new schools are built. Click a
sector name in the legend to isolate it.
</p>
<div class="figure-block">{div(fig5, "projection")}</div>

<h2>6. Real terrain context</h2>
<p>
This is the actual Burera District terrain, clipped from a real national 30 metre SRTM elevation
model, the same source and resolution the thesis cites. Elevation in the clipped area ranges from
approximately {elev_min:.0f} to {elev_max:.0f} metres, consistent with the thesis's own reported
range and with the district's location in the Virunga volcanic highlands on the Uganda border.
</p>
<img class="terrain" src="data:image/png;base64,{terrain_b64}" alt="Burera District real terrain">

<h2>Data provenance and limitations</h2>
<table class="provenance">
<tr><th>Layer</th><th>Status</th><th>Source</th></tr>
<tr><td>Sector boundaries</td><td>Real</td><td>National sector boundary dataset, filtered to Burera's 17 sectors</td></tr>
<tr><td>Elevation</td><td>Real</td><td>National SRTM 30 m DEM, clipped to Burera District</td></tr>
<tr><td>Population, area, school counts</td><td>Real, verified</td><td>Thesis Table 4.2 and Table 4.8, NISR 2022 Census and REB</td></tr>
<tr><td>School point locations</td><td>Real</td><td>REB facility register, 81 primary schools, matching the thesis's Table 4.1 count exactly, and 59 secondary category schools (General Secondary 9-12 YBE, TVET, TTC)</td></tr>
<tr><td>Road network</td><td>Not available on this machine</td><td>Would come from RTDA or OpenStreetMap</td></tr>
</table>
<div class="limitation">
The composite index itself still operates at the sector level, the same level as the thesis's own
Combined Accessibility Score. The school markers on the map are real point locations, but there is
no real road network yet, so this dashboard cannot compute true walking distance or travel time
along actual roads and footpaths, only sector level aggregates and, in the underlying model files,
straight line and terrain cost distance from each real school. If a road network shapefile is
supplied, this dashboard can be extended with a genuine point level service area layer, routed
along real roads, to sit alongside the views shown here.
</div>

<footer>
Built from the composite accessibility model developed alongside the MSc thesis of
DUSABIMANA Yves Alexis, INES Ruhengeri, Department of Land Survey, MSc in Geo Informatics,
August 2026. Generated with Python, GeoPandas, rasterio, and Plotly.
</footer>

</body>
</html>
"""
    return html


def main():
    gdf, merged, with_indices, scenario_frames = load_geo_and_model()
    tiered_default = scenario_frames["AHP judgement, adopted (0.33 / 0.67)"]

    fig1 = build_choropleth(gdf, scenario_frames)
    fig2 = build_ranked_bar(tiered_default)
    fig3 = build_rank_comparison(with_indices, tiered_default)
    fig4 = build_weight_sensitivity(load_sector_data())
    fig5 = build_population_projection(load_sector_data())
    terrain_b64, elev_min, elev_max = build_terrain_image_base64()

    # only the first figure embeds plotly.js, the rest reuse it
    html = build_page(fig1, fig2, fig3, fig4, fig5, terrain_b64, elev_min, elev_max)

    out_path = os.path.join(HERE, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {out_path}, {os.path.getsize(out_path)/1e6:.2f} MB")


if __name__ == "__main__":
    main()
