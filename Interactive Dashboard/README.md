# Burera District Education Accessibility Dashboard

An interactive, browser based decision support tool built alongside the thesis
*Application of Geospatial Techniques in the Assessment of the Spatial
Distribution and Accessibility of Education Facilities in Burera District,
Rwanda*. Open `index.html` in any browser, no server or installation needed
to view it, everything runs client side.

## What is real and what is not

Three spatial layers in this dashboard are real, not illustrative.

**Sector boundaries.** The 17 Burera sector polygons in `data/burera_sectors.geojson`
were clipped from a national Rwanda sector boundary dataset. The sector
names match the thesis exactly, Bungwe, Butaro, Cyanika, Cyeru, Gahunga,
Gatebe, Gitovu, Kagogo, Kinoni, Kinyababa, Kivuye, Nemba, Rugarama,
Rugengabari, Ruhunde, Rusarabuye, Rwerere.

**Elevation.** `data/burera_dem_clip.tif` is clipped from a national 30 metre
SRTM digital elevation model, the same source and resolution the thesis
cites in Section 3.4. The clipped area ranges from roughly 1,744 to 4,119
metres, which includes the volcanic peak on the Uganda border the thesis
describes as part of the Virunga highlands, and both Lake Burera and Lake
Ruhondo are visible in the terrain panel.

**School locations.** `data/burera_schools.csv` is the real Rwanda Basic
Education Board facility register filtered to Burera District, with real
latitude and longitude for every school. Filtering to `school_category ==
PRIMARY` gives 81 schools, matching the thesis's own Table 4.1 total
exactly. Filtering to the General Secondary (9 to 12 YBE), TVET, and TTC
categories, the same combination Table 4.2 of the thesis describes, gives
59 schools, close to the thesis's reported 60. Both are plotted on the map
with legend toggles.

**Population, area, and school counts** by sector are the same verified
figures already published in the thesis, Table 4.2 and Table 4.8.

**Not included.** The road network was not available when this was built.
With an RTDA or OpenStreetMap road layer, this dashboard could be extended
with a genuine point level service area map, routed along real roads,
alongside the sector level view it currently shows. The dashboard states
this limitation on the page itself, in the Data Provenance and Limitations
section.

## What the dashboard does

1. An interactive map of Burera District, real geography, classified into
   the same five priority tiers used throughout the thesis (Critical, High,
   Moderate, Below Average, Adequate), draped over the district's real
   hillshaded terrain. Three buttons above the map let a viewer switch
   between weighting scenarios, from equal weight on school density and
   population, up to the strong population emphasis end of the plausible
   AHP range, and see the map reclassify live. The legend itself is
   clickable, click a tier to hide or show just that priority group.
2. A ranked priority bar chart.
3. A chart showing exactly how each sector's priority rank shifts once
   population is properly weighted in against the thesis's original area
   based ranking.
4. A Monte Carlo simulation, ten thousand redraws of the model's weighting,
   showing which sectors are robustly high priority and which are only high
   priority for a narrow slice of possible weightings.
5. A ten year population growth projection, holding school counts fixed,
   showing which sectors are likely to fall below the district average if
   no new schools are built.
6. The real terrain panel described above.

## Rebuilding it

```
pip install -r requirements.txt
python build_dashboard.py
```

This regenerates `index.html` from `data/burera_sectors.geojson` and
`data/burera_dem_clip.tif`, plus the composite model in `model.py`. If you
have not already extracted those two data files yourself, `extract_real_data.py`
shows exactly how they were produced from the original national datasets,
edit the file paths at the top of that script to point at your own copies of
the national sector boundary shapefile and the national SRTM DEM, then run
it before `build_dashboard.py`.

## Publishing it on GitHub Pages

1. Create a new GitHub repository and push this folder to it.
2. In the repository settings, open the Pages section.
3. Under Build and deployment, choose Deploy from a branch, pick the branch
   you pushed to, and leave the folder as the repository root, since
   `index.html` already sits at the top level.
4. Save. GitHub will publish the page at
   `https://<your-username>.github.io/<repository-name>/` within a minute or
   two.

Because `index.html` is fully self contained, aside from loading the Plotly
library from a CDN, it also works if you just open the file directly in a
browser without any web server at all, which is useful for showing it during
a defence without needing internet access at the venue for anything except
that one script tag.

## Data provenance summary

| Layer | Status | Source |
|---|---|---|
| Sector boundaries | Real | National sector boundary dataset, filtered to Burera |
| Elevation | Real | National 30 m SRTM DEM, clipped to Burera |
| Population, area, school counts | Real, verified | Thesis Table 4.2 and Table 4.8, NISR 2022 Census and REB |
| School point locations | Real | REB facility register, 81 primary and 59 secondary category schools |
| Road network | Not available | Would come from RTDA or OpenStreetMap |
