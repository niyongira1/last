"""
Builds the interactive Leaflet map section, real basemap switching, real
toggleable layers, and a working "show me only Priority 1 Critical schools"
filter, all client side, no server needed.

Reads the precomputed files from prepare_leaflet_data.py
(sectors_with_tiers.geojson, schools_with_tiers.json), and the real terrain
hillshade built in build_dashboard.py.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

TIER_COLORS = {
    "Priority 1, Critical": "#b23a48",
    "Priority 2, High": "#d97b4f",
    "Priority 3, Moderate": "#e0b23c",
    "Priority 4, Below Average": "#7fa37f",
    "Priority 5, Adequate": "#3f7d5c",
}


def build_leaflet_section(terrain_uri, terrain_coords):
    with open(os.path.join(DATA_DIR, "sectors_with_tiers.geojson"), encoding="utf-8") as f:
        sectors_geojson = json.load(f)
    with open(os.path.join(DATA_DIR, "schools_with_tiers.json"), encoding="utf-8") as f:
        schools = json.load(f)

    west, north = terrain_coords[0]
    east, _ = terrain_coords[1]
    _, south = terrain_coords[2]

    sectors_json_str = json.dumps(sectors_geojson)
    schools_json_str = json.dumps(schools)
    tier_colors_json_str = json.dumps(TIER_COLORS)

    css = """
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
#leafletMap { height: 660px; border: 1px solid #ccc; border-radius: 4px; }
.sector-label { font-size: 11px; font-weight: 600; color: #1c1c1c; text-shadow: 0 0 3px white, 0 0 3px white, 0 0 3px white; white-space: nowrap; }
.scenario-control, .legend-control { background: white; padding: 10px 12px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.4); font-size: 12.5px; max-width: 240px; }
.scenario-control label { display: block; margin: 3px 0; cursor: pointer; }
.legend-control .swatch { display: inline-block; width: 13px; height: 13px; margin-right: 6px; vertical-align: middle; border: 1px solid #888; }
.legend-control .dot { display: inline-block; width: 11px; height: 11px; border-radius: 50%; margin-right: 6px; vertical-align: middle; border: 1px solid #888; }
.legend-control div { margin: 2px 0; }
.leaflet-control-layers-expanded { max-height: 480px; overflow-y: auto; }
</style>
"""

    div = '<div id="leafletMap"></div>'

    script = f"""
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function() {{
  const SECTORS = {sectors_json_str};
  const SCHOOLS = {schools_json_str};
  const TERRAIN_URI = "{terrain_uri}";
  const TERRAIN_BOUNDS = [[{south}, {west}], [{north}, {east}]];
  const TIER_COLORS = {tier_colors_json_str};

  const map = L.map('leafletMap', {{ center: [-1.45, 29.83], zoom: 10.3 }});

  const streets = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '&copy; OpenStreetMap contributors', maxZoom: 19
  }}).addTo(map);
  const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    attribution: 'Tiles &copy; Esri', maxZoom: 19
  }});
  const terrainBasemap = L.tileLayer('https://{{s}}.tile.opentopomap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: 'Map data: &copy; OpenStreetMap contributors, SRTM | Map style: &copy; OpenTopoMap', maxZoom: 17
  }});
  const light = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO', maxZoom: 19
  }});
  const dark = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO', maxZoom: 19
  }});

  const baseMaps = {{
    "Streets (OpenStreetMap)": streets,
    "Satellite imagery (Esri)": satellite,
    "Terrain (OpenTopoMap)": terrainBasemap,
    "Light / minimal (CartoDB Positron)": light,
    "Dark (CartoDB Dark Matter)": dark,
  }};

  const terrainOverlay = L.imageOverlay(TERRAIN_URI, TERRAIN_BOUNDS, {{ opacity: 0.85 }});

  const sectorBoundaries = L.geoJSON(SECTORS, {{
    style: {{ color: '#2f5d8a', weight: 1.3, fill: false }}
  }});

  const sectorLabels = L.layerGroup();
  SECTORS.features.forEach(function(f) {{
    const marker = L.marker([f.properties.centroid_lat, f.properties.centroid_lon], {{
      icon: L.divIcon({{ className: 'sector-label', html: f.properties.sector, iconSize: [0, 0] }}),
      interactive: false
    }});
    sectorLabels.addLayer(marker);
  }});

  const tierGroups = {{}};
  Object.keys(TIER_COLORS).forEach(function(tier) {{ tierGroups[tier] = L.layerGroup(); }});

  const primaryLayer = L.layerGroup();
  const secondaryLayer = L.layerGroup();
  SCHOOLS.forEach(function(s) {{
    const marker = L.circleMarker([s.lat, s.lon], {{
      radius: s.category === 'Primary' ? 4 : 5,
      color: '#ffffff', weight: 1,
      fillColor: s.category === 'Primary' ? '#1c1c1c' : '#f2d40c',
      fillOpacity: 0.9
    }}).bindPopup('<b>' + s.name + '</b><br>' + s.category + ' school<br>Sector: ' + (s.sector || 'unknown'));
    (s.category === 'Primary' ? primaryLayer : secondaryLayer).addLayer(marker);
  }});

  const criticalSchoolsLayer = L.layerGroup();

  function applyScenario(key) {{
    Object.values(tierGroups).forEach(function(g) {{ g.clearLayers(); }});
    SECTORS.features.forEach(function(f) {{
      const tier = f.properties['tier_' + key];
      const color = TIER_COLORS[tier];
      const layer = L.geoJSON(f, {{
        style: {{ color: '#ffffff', weight: 1.3, fillColor: color, fillOpacity: 0.68 }}
      }}).bindPopup(
        '<b>' + f.properties.sector + '</b><br>Tier: ' + tier + '<br>' +
        'CWAI: ' + f.properties['cwai_' + key] + '<br>' +
        'Composite rank: ' + f.properties['rank_' + key] + ' of 17<br>' +
        'Population (2022): ' + Number(f.properties.Population).toLocaleString()
      );
      tierGroups[tier].addLayer(layer);
    }});

    criticalSchoolsLayer.clearLayers();
    let criticalCount = 0;
    SCHOOLS.forEach(function(s) {{
      if (s['tier_' + key] === 'Priority 1, Critical') {{
        criticalCount++;
        const marker = L.circleMarker([s.lat, s.lon], {{
          radius: 7, color: '#000000', weight: 2,
          fillColor: '#ffffff', fillOpacity: 1
        }}).bindPopup('<b>' + s.name + '</b><br>' + s.category + ' school<br>Sector: ' + s.sector + '<br><b>Priority 1, Critical</b>');
        criticalSchoolsLayer.addLayer(marker);
      }}
    }});
    const countEl = document.getElementById('criticalCount');
    if (countEl) {{ countEl.textContent = criticalCount; }}
  }}

  applyScenario('ahp');

  sectorBoundaries.addTo(map);
  Object.values(tierGroups).forEach(function(g) {{ g.addTo(map); }});
  criticalSchoolsLayer.addTo(map);

  const overlays = {{
    "Sector boundaries": sectorBoundaries,
    "Sector labels": sectorLabels,
    "Real terrain (hillshade)": terrainOverlay,
    "Priority 1, Critical": tierGroups["Priority 1, Critical"],
    "Priority 2, High": tierGroups["Priority 2, High"],
    "Priority 3, Moderate": tierGroups["Priority 3, Moderate"],
    "Priority 4, Below Average": tierGroups["Priority 4, Below Average"],
    "Priority 5, Adequate": tierGroups["Priority 5, Adequate"],
    "Primary schools, all (real)": primaryLayer,
    "Secondary schools, all (real)": secondaryLayer,
    "Schools in Priority 1 Critical sectors only": criticalSchoolsLayer,
  }};

  L.control.layers(baseMaps, overlays, {{ collapsed: false }}).addTo(map);

  const ScenarioControl = L.Control.extend({{
    options: {{ position: 'topright' }},
    onAdd: function() {{
      const div = L.DomUtil.create('div', 'scenario-control');
      div.innerHTML =
        '<b>Weighting scenario</b>' +
        '<label><input type="radio" name="scenario" value="equal"> Equal weight (0.50 / 0.50)</label>' +
        '<label><input type="radio" name="scenario" value="ahp" checked> AHP judgement, adopted (0.33 / 0.67)</label>' +
        '<label><input type="radio" name="scenario" value="strong"> Strong population emphasis (0.17 / 0.83)</label>' +
        '<div style="margin-top:6px;">Real schools in Critical sectors: <b id="criticalCount">-</b></div>';
      L.DomEvent.disableClickPropagation(div);
      div.querySelectorAll('input[name=scenario]').forEach(function(r) {{
        r.addEventListener('change', function(e) {{ applyScenario(e.target.value); }});
      }});
      return div;
    }}
  }});
  map.addControl(new ScenarioControl());

  const LegendControl = L.Control.extend({{
    options: {{ position: 'bottomleft' }},
    onAdd: function() {{
      const div = L.DomUtil.create('div', 'legend-control');
      let rows = '';
      Object.keys(TIER_COLORS).forEach(function(tier) {{
        rows += '<div><span class="swatch" style="background:' + TIER_COLORS[tier] + '"></span>' + tier + '</div>';
      }});
      div.innerHTML = '<b>Priority tier</b>' + rows +
        '<div style="margin-top:6px;"><span class="dot" style="background:#1c1c1c"></span>Primary school (real)</div>' +
        '<div><span class="dot" style="background:#f2d40c"></span>Secondary school (real)</div>' +
        '<div><span class="dot" style="background:#ffffff;border:2px solid black;"></span>School in a Critical sector</div>';
      return div;
    }}
  }});
  map.addControl(new LegendControl());

  applyScenario('ahp');
}})();
</script>
"""

    return css + div + script
