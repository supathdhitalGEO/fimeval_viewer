#Import necessary libraries
import streamlit as st
from streamlit_folium import st_folium
import folium
import urllib.parse
from folium.features import GeoJson
from branca.element import Element
import datetime as dt

from utilis.ui import inject_globalfont
inject_globalfont(font_size_px=18, sidebar_font_size_px=20)

from utilis.s3_catalog import build_catalog
from utilis.s3_datadownloads import find_json_in_folder, s3_http_url

st.set_page_config(page_title="Interactive FIM Vizualizer", page_icon="🌊", layout="wide")
st.title("Benchmark FIMs")

# Session defaults
if "saved_center" not in st.session_state:
    st.session_state["saved_center"] = [39.8283, -98.5795]
if "saved_zoom" not in st.session_state:
    st.session_state["saved_zoom"] = 5

BUCKET = "sdmlab"
ROOT_PREFIX = "FIM_Database/"

TIER_COLORS = {
    "Tier_1": "#1b9e77",
    "Tier_2": "#d95f02",
    "Tier_3": "#7570b3",
    "Tier_4": "#e7298a",
    "Tier_5": "#66a61e",
}
DEFAULT_TIER_COLOR = "#2c7fb8"

BASEMAPS = {
    "OpenStreetMap": dict(tiles="OpenStreetMap", attr="© OpenStreetMap"),
    "CartoDB Positron": dict(tiles="CartoDB positron", attr="© OpenStreetMap contributors, © CARTO"),
    "Esri WorldTopoMap": dict(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles © Esri — Sources: Esri, HERE, Garmin, FAO, NOAA, and others"
    ),
    "Esri WorldImagery": dict(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles © Esri, Maxar, Earthstar Geographics, GIS User Community"
    ),
}

@st.cache_data(show_spinner=False, ttl=3600)
def cached_find_json(bucket: str, folder: str, tif_filename: str | None):
    """Cache the JSON key discovery per (bucket, folder, tif)."""
    return find_json_in_folder(bucket, folder, tif_filename)

@st.cache_data(show_spinner=False, ttl=3600)
def resolve_urls(bucket: str, s3_key: str | None, file_name: str | None):
    """Given record's s3_key and file_name, return (tif_url, json_url)."""
    tif_url = None
    json_url = None
    if s3_key:
        folder = s3_key.rsplit("/", 1)[0]
        if file_name:
            tif_key = f"{folder}/{file_name}"
            tif_url = s3_http_url(bucket, tif_key)
        json_key = cached_find_json(bucket, folder, file_name)
        if json_key:
            json_url = s3_http_url(bucket, json_key)
    return tif_url, json_url

# Sidebar: cache control and basemap
with st.sidebar:
    st.header("Data")
    if st.button("Reload from AWS S3 Database"):
        build_catalog.clear()   
        cached_find_json.clear()   
        resolve_urls.clear()      
        st.success("Cache cleared. Data will reload now.")

# Cached loads and helpers
with st.spinner("Loading catalog from S3 (cached)…"):
    result = build_catalog(BUCKET, ROOT_PREFIX)

records = result.get("records", [])
load_errors = result.get("errors", [])

if load_errors:
    with st.expander(f"{len(load_errors)} metadata file(s) failed to parse — click for details", expanded=True):
        for key, msg in load_errors[:50]:
            st.markdown(f"- **s3://{BUCKET}/{key}**")
            st.code(msg, language="text")
        if len(load_errors) > 50:
            st.caption(f"...and {len(load_errors)-50} more")

if not records:
    st.warning("No FIM metadata found in S3 (or all JSONs failed to parse). Check bucket/prefix or permissions.")
    st.stop()


# Filters
all_tiers = sorted({r["tier"] for r in records})
dates_all = sorted([r["date_ymd"] for r in records if r["date_ymd"]])
min_date = dt.date.fromisoformat(dates_all[0]) if dates_all else dt.date(2000, 1, 1)
max_date = dt.date.fromisoformat(dates_all[-1]) if dates_all else dt.date.today()

with st.sidebar:
    st.header("Filters")
    with st.form("filters_form", clear_on_submit=False):
        sel_tiers = st.multiselect("Select the Different Tiers", options=all_tiers, default=all_tiers)
        dr = st.date_input("Date range", value=(min_date, max_date),
                           min_value=min_date, max_value=max_date, format="YYYY-MM-DD")
        show_polys = st.checkbox("Show Flood Inundation Mapping Extent", value=st.session_state.get("fim_show", False))
        apply_filters = st.form_submit_button("Apply Filters")
    st.header("Basemap")
    basemap_choice = st.selectbox("Select basemap", list(BASEMAPS.keys()), index=2)

st.session_state["fim_show"] = show_polys

def in_range(r, start_date, end_date):
    if not r["date_ymd"]:
        return False
    d = dt.date.fromisoformat(r["date_ymd"])
    return start_date <= d <= end_date

if isinstance(dr, tuple):
    start_date, end_date = dr
else:
    start_date, end_date = min_date, max_date

filtered = [r for r in records if (r["tier"] in sel_tiers) and in_range(r, start_date, end_date)]

# Map
m = folium.Map(
    location=st.session_state["saved_center"],
    zoom_start=st.session_state["saved_zoom"],
    tiles=None,
    control_scale=True,
    prefer_canvas=True
)

bm = BASEMAPS[basemap_choice]
folium.TileLayer(tiles=bm["tiles"], name=basemap_choice, control=False, attr=bm["attr"], show=True).add_to(m)

def popup_html(r: dict) -> str:
    # Resolve URLs via cached helper
    tif_url, json_url = resolve_urls(BUCKET, r.get("s3_key"), r.get("file_name"))

    fields = [
        ("File Name", r.get("file_name")),
        ("Resolution (m)", r.get("resolution_m")),
        ("State", r.get("state")),
        ("Description", r.get("description")),
        ("River Basin Name", r.get("river_basin")),
        ("Source", r.get("source")),
        ("Date", r.get("date_ymd") or r.get("date_raw")),
        ("Quality", r.get("quality")),
    ]
    rows = "".join(
        f"<tr><th style='text-align:left;vertical-align:top;padding-right:8px'>{k}</th>"
        f"<td style='text-align:left'>{'' if v is None else v}</td></tr>"
        for k, v in fields
    )

    refs = r.get("references") or []
    refs_html = ""
    if refs:
        refs_html = "<div style='margin-top:6px'><b>References</b><div style='margin:4px 0;padding-left:12px'>"
        for ref in refs:
            refs_html += f"<div style='margin-bottom:6px'>{ref}</div>"
        refs_html += "</div></div>"

    # Two download buttons
    buttons_html = ""
    if tif_url:
        buttons_html += f"""
        <a href="{tif_url}" target="_blank" rel="noopener"
           style="text-decoration:none;display:inline-block;background:#2563eb;color:#fff;
                  padding:8px 10px;border-radius:6px;font-weight:600;margin-right:8px;">
          ⬇ Download Benchmark FIM (.tif)
        </a>"""
    if json_url:
        buttons_html += f"""
        <a href="{json_url}" target="_blank" rel="noopener"
           style="text-decoration:none;display:inline-block;background:#059669;color:#fff;
                  padding:8px 10px;border-radius:6px;font-weight:600;">
          ⬇ Download Metadata (.json)
        </a>"""

    return f"""
    <div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif; font-size:13px; max-width:420px">
        <table>{rows}</table>
        {'<hr style="margin:6px 0" />' if refs_html or buttons_html else ''}
        {refs_html}
        {buttons_html}
    </div>
    """


markers_fg = folium.FeatureGroup(name="Benchmark FIM Sites", show=True)
for r in filtered:
    color = TIER_COLORS.get(r["tier"], DEFAULT_TIER_COLOR)
    folium.CircleMarker(
        location=[r["centroid_lat"], r["centroid_lon"]],
        radius=8, color="black", weight=1.5, fill=True, fill_color=color, fill_opacity=0.9,
        tooltip=f"{r['tier']} — {r['site']}",
        popup=folium.Popup(popup_html(r), max_width=500),
    ).add_to(markers_fg)
markers_fg.add_to(m)

if st.session_state["fim_show"]:
    polys_fg = folium.FeatureGroup(name="Benchmark FIM Extents", show=True)
    for r in filtered:
        geom = r.get("geometry")
        if not geom:
            continue
        color = TIER_COLORS.get(r["tier"], DEFAULT_TIER_COLOR)
        gj = GeoJson(
            data={"type": "Feature", "properties": {"tier": r["tier"], "site": r["site"]}, "geometry": geom},
            style_function=lambda feat, col=color: {"color": col, "weight": 1.0, "fillColor": col, "fillOpacity": 0.5},
            smooth_factor=0.8,
            tooltip=folium.GeoJsonTooltip(fields=[], aliases=[]),
        )
        gj.add_child(folium.Popup(popup_html(r), max_width=520))
        gj.add_to(polys_fg)
    polys_fg.add_to(m)

# Legend
legend_items = "".join(
    f"<div style='display:flex;align-items:center;margin-bottom:6px'>"
    f"<span style='display:inline-block;width:16px;height:16px;background:{TIER_COLORS.get(t, DEFAULT_TIER_COLOR)};"
    f"border:1px solid #000;margin-right:8px'></span>"
    f"<span style='font-size:14px'>{t}</span></div>"
    for t in sorted(set(r["tier"] for r in filtered))
)
legend_html = f"""
<div style="position:fixed; z-index:9999; bottom:20px; right:20px; background:rgba(255,255,255,0.95);
            padding:12px 14px; border-radius:10px; box-shadow:0 2px 6px rgba(0,0,0,0.3);">
  <div style="font-weight:600; font-size:14px; margin-bottom:8px">FIM Tiers</div>
  {legend_items if legend_items else '<div style="font-size:13px;color:#666">No FIMs with this filter in any Tier</div>'}
</div>
"""
m.get_root().html.add_child(Element(legend_html))

folium.LayerControl(collapsed=False).add_to(m)

ret = st_folium(m, width=None, height=720, key="fim_map")

# persist viewport after applying filters
if apply_filters and isinstance(ret, dict):
    c = ret.get("center"); z = ret.get("zoom")
    if isinstance(c, dict) and ("lat" in c) and ("lng" in c) and isinstance(z, (int, float)):
        st.session_state["saved_center"] = [float(c["lat"]), float(c["lng"])]
        st.session_state["saved_zoom"] = float(z)

