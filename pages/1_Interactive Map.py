import streamlit as st
from streamlit_folium import st_folium
import folium
import urllib.parse
from folium.features import GeoJson, GeoJsonTooltip
from branca.element import Element
import datetime as dt

from utilis.s3_catalog import build_catalog

st.set_page_config(page_title="Interactive FIM Vizualizer", page_icon="🌊", layout="wide")
st.title("Benchmark FIMs")

# Persist view across reruns
st.session_state.setdefault("saved_center", [39.8283, -98.5795])
st.session_state.setdefault("saved_zoom", 5)

# Settings
BUCKET = "sdmlab"
ROOT_PREFIX = "FIM_database_test/"
TIER_COLORS = {
    "Tier_1": "#1b9e77",
    "Tier_2": "#d95f02",
    "Tier_3": "#7570b3",
    "Tier_4": "#e7298a",
    "Tier_5": "#66a61e",
}
DEFAULT_TIER_COLOR = "#2c7fb8"

# Controls
with st.sidebar:
    st.header("Data")
    if st.button("Reload from AWS S3 Database"):
        build_catalog.clear()
        st.success("Cache cleared. Data will reload now.")

# Load
with st.spinner("Loading catalog from S3 (cached)…"):
    records = build_catalog(BUCKET, ROOT_PREFIX)

if not records:
    st.warning("No FIM metadata found in S3. Check bucket/prefix or permissions.")
    st.stop()

# Filters
all_tiers = sorted({r["tier"] for r in records})
dates_all = sorted([r["date_ymd"] for r in records if r["date_ymd"]])
min_date = dt.date.fromisoformat(dates_all[0]) if dates_all else dt.date(2000, 1, 1)
max_date = dt.date.fromisoformat(dates_all[-1]) if dates_all else dt.date.today()

with st.sidebar:
    st.header("Filters")
    sel_tiers = st.multiselect("Select the Different Tiers", options=all_tiers, default=all_tiers)
    dr = st.date_input("Date range", value=(min_date, max_date),
                       min_value=min_date, max_value=max_date, format="YYYY-MM-DD")
    if isinstance(dr, tuple):
        start_date, end_date = dr
    else:
        start_date, end_date = min_date, max_date

    show_polys_checkbox = st.checkbox(
        "Show Flood Inundation Mapping Extent",
        value=st.session_state.get("fim_show", False),
        key="fim_show"
    )
    st.caption("Tip: keep off for national view; turn on after zooming.")

def in_range(r):
    if not r["date_ymd"]:
        return False
    d = dt.date.fromisoformat(r["date_ymd"])
    return start_date <= d <= end_date

filtered = [r for r in records if (r["tier"] in sel_tiers) and in_range(r)]

# Basemap
BASEMAPS = {
    "OpenStreetMap": {"tiles": "OpenStreetMap", "attr": "© OpenStreetMap contributors", "max_zoom": 19},
    "CartoDB Positron": {"tiles": "CartoDB positron", "attr": "© OpenStreetMap contributors, © CARTO", "max_zoom": 20},
    "Esri WorldTopoMap": {"tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
                          "attr": "Tiles © Esri — Source: Esri, HERE, Garmin, FAO, NOAA, and others", "max_zoom": 20},
    "Esri WorldImagery": {"tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                          "attr": "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community", "max_zoom": 20},
}
basemap_choice = st.selectbox("Basemap", list(BASEMAPS.keys()), index=2)
cfg = BASEMAPS[basemap_choice]

# Build fresh map each run (keeps things stable); preserve view from session_state
m = folium.Map(
    location=st.session_state["saved_center"],
    zoom_start=st.session_state["saved_zoom"],
    tiles=None,
    control_scale=True,
    prefer_canvas=True
)
folium.TileLayer(
    tiles=cfg["tiles"], name=basemap_choice, attr=cfg["attr"],
    max_zoom=cfg["max_zoom"], overlay=False, show=True
).add_to(m)

def popup_html(r: dict) -> str:
    tif_url = None
    file_name = r.get("file_name")
    s3_key = r.get("s3_key")
    if file_name and s3_key:
        folder = s3_key.rsplit("/", 1)[0]
        tif_path = f"{folder}/{file_name}"
        tif_url = f"https://{BUCKET}.s3.amazonaws.com/{urllib.parse.quote(tif_path, safe='/')}"
    fields = [
        ("File Name", file_name),
        ("Resolution (m)", r.get("resolution_m")),
        ("State", r.get("state")),
        ("Description", r.get("description")),
        ("River Basin Name", r.get("river_basin")),
        ("Source", r.get("source")),
        ("Date", r.get("date_ymd") or r.get("date_raw")),
        ("Quality", r.get("quality")),
    ]
    refs = r.get("references") or []
    refs_html = "<ul>" + "".join(f"<li>{ref}</li>" for ref in refs) + "</ul>" if refs else ""
    rows = "".join(
        f"<tr><th style='text-align:left;vertical-align:top;padding-right:8px'>{k}</th>"
        f"<td style='text-align:left'>{'' if v is None else v}</td></tr>"
        for k, v in fields
    )
    download_html = ""
    if tif_url:
        download_html = f"""
        <div style="margin-top:10px">
          <a href="{tif_url}" target="_blank" rel="noopener noreferrer"
             style="text-decoration:none;display:inline-block;background:#2563eb;color:#fff;
                    padding:8px 10px;border-radius:6px;font-weight:600;">
            ⬇ Download FIM Benchmark Data (.tif)
          </a>
        </div>
        """
    return f"""
      <div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif; font-size:13px; max-width:420px">
        <table>{rows}</table>
        {'<hr style="margin:6px 0 6px 0" />' if refs_html or download_html else ''}
        {('<b>References</b>' + refs_html) if refs_html else ''}
        {download_html}
      </div>
    """

# Centroid markers (lightweight)
for r in filtered:
    color = TIER_COLORS.get(r["tier"], DEFAULT_TIER_COLOR)
    folium.CircleMarker(
        location=[r["centroid_lat"], r["centroid_lon"]],
        radius=8, color="black", weight=1.5, fill=True, fill_color=color, fill_opacity=0.9,
        tooltip=f"{r['tier']} — {r['site']}",
        popup=folium.Popup(popup_html(r), max_width=500),
    ).add_to(m)

# Polygons
if show_polys_checkbox:
    for r in filtered:
        geom = r.get("geometry")
        if not geom:
            continue
        color = TIER_COLORS.get(r["tier"], DEFAULT_TIER_COLOR)
        gj = GeoJson(
            data={"type": "Feature", "properties": {"tier": r["tier"], "site": r["site"]}, "geometry": geom},
            name=f"{r['tier']} — {r['site']}",
            style_function=lambda feat, col=color: {"color": col, "weight": 1.0, "fillColor": col, "fillOpacity": 0.5},
            smooth_factor=0.8,
        )
        gj.add_child(folium.Popup(popup_html(r), max_width=520))
        gj.add_to(m)

# Legend
legend_items = "".join(
    f"<div style='display:flex;align-items:center;margin-bottom:6px'>"
    f"<span style='display:inline-block;width:16px;height:16px;background:{TIER_COLORS.get(t, DEFAULT_TIER_COLOR)};"
    f"border:1px solid #000;margin-right:8px'></span>"
    f"<span style='font-size:14px'>{t}</span></div>"
    for t in sel_tiers
)
legend_html = f"""
<div style="position:fixed; z-index:9999; bottom:20px; right:20px; background:rgba(255,255,255,0.95);
            padding:12px 14px; border-radius:10px; box-shadow:0 2px 6px rgba(0,0,0,0.3);">
  <div style="font-weight:600; font-size:14px; margin-bottom:8px">FIM Tiers</div>
  {legend_items if legend_items else '<div style="font-size:13px;color:#666">No tiers selected</div>'}
</div>
"""
m.get_root().html.add_child(Element(legend_html))

# Render (use a constant key; dynamic keys can cause white iframe)
ret = st_folium(m, width=None, height=720, key="fim_map")

# Persist view (tiny threshold avoids jitter)
if isinstance(ret, dict):
    c = ret.get("center"); z = ret.get("zoom")
    if isinstance(c, dict) and ("lat" in c) and ("lng" in c):
        lat_new, lng_new = c["lat"], c["lng"]
        lat_old, lng_old = st.session_state["saved_center"]
        if abs(lat_new - lat_old) > 1e-3 or abs(lng_new - lng_old) > 1e-3:
            st.session_state["saved_center"] = [lat_new, lng_new]
    if isinstance(z, (int, float)):
        if abs(z - st.session_state["saved_zoom"]) > 0.1:
            st.session_state["saved_zoom"] = z

