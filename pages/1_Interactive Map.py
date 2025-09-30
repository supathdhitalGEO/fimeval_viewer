import streamlit as st
from streamlit_folium import st_folium
import folium

st.set_page_config(page_title="Map", page_icon="", layout="wide")
st.title("Benchmark FIMs")

# Basemaps with attributions
BASEMAPS = {
    "OpenStreetMap": {
        "tiles": "OpenStreetMap",
        "attr": "© OpenStreetMap contributors",
        "max_zoom": 19,
    },
    "CartoDB Positron": {
        "tiles": "CartoDB positron",
        "attr": "© OpenStreetMap contributors, © CARTO",
        "max_zoom": 20,
    },
    "Esri Hillshade": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}",
        "attr": "Tiles © Esri",
        "max_zoom": 20,
    },
    "Esri WorldImagery": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr": "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
        "max_zoom": 20,
    },
    "USGS USImageryTopo": {
        "tiles": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryTopo/MapServer/tile/{z}/{y}/{x}",
        "attr": "USGS Imagery Topo",
        "max_zoom": 16,
    },
}

# Centered on continental US
m = folium.Map(location=[39.8283, -98.5795], zoom_start=5, tiles=None, control_scale=True)

# Added all basemaps, showing OpenStreetMap by default
for name, cfg in BASEMAPS.items():
    folium.TileLayer(
        tiles=cfg["tiles"],
        name=name,
        attr=cfg["attr"],
        max_zoom=cfg["max_zoom"],
        overlay=False,
        show=(name == "OpenStreetMap"),
    ).add_to(m)

# Added basemap switcher
folium.LayerControl(collapsed=False).add_to(m)

# Render map
st_folium(m, width=None, height=720)
