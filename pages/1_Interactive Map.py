from __future__ import annotations
import hashlib
import datetime as dt
from io import BytesIO
from typing import Dict, Any, Iterable, List, Tuple, Optional

import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import mapping

import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.features import GeoJson
from folium.plugins import MarkerCluster
from branca.element import Element

from utilis.ui import inject_globalfont
inject_globalfont(font_size_px=18, sidebar_font_size_px=20)

# Config
BUCKET    = "sdmlab"
CORE_KEY  = "FIM_Database/catalog_core.json"
GPQ_KEY   = "FIM_Database/extents.parquet"  

# Max features to draw at once
BASE_FEATURE_CAP = 10

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

def http_url(key: str) -> str:
    from urllib.parse import quote
    return f"https://{BUCKET}.s3.amazonaws.com/{quote(key, safe='/')}"

# Caching layers
@st.cache_data(show_spinner=False, ttl=86400)
def fetch_json(url: str) -> Dict[str, Any]:
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.json()

@st.cache_resource(show_spinner=False)
def load_extents_gdf(url: str) -> gpd.GeoDataFrame:
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return gpd.read_parquet(BytesIO(r.content))

@st.cache_resource(show_spinner=False)
def load_extents_index(url: str) -> Dict[str, Dict[str, Any]]:
    """
    Cache by URL -> {id: {"tier": str, "site": str, "geom": GeoJSON dict}}
    """
    gdf = load_extents_gdf(url)
    idx: Dict[str, Dict[str, Any]] = {}
    if gdf is None or gdf.empty:
        return idx
    for row in gdf.itertuples(index=False):
        try:
            idx[str(row.id)] = {
                "tier": str(row.tier),
                "site": str(row.site),
                "geom": mapping(row.geometry),
            }
        except Exception:
            continue
    return idx

@st.cache_data(show_spinner=False)
def fingerprint_ids(ids: Iterable[str]) -> str:
    """Stable hash of a set/list of IDs for cache keying."""
    arr = sorted([str(x) for x in ids])
    return hashlib.sha1(("\n".join(arr)).encode("utf-8")).hexdigest()

@st.cache_data(show_spinner=False)
def build_feature_collection(filtered_ids: Iterable[str],
                             extents_idx: Dict[str, Dict[str, Any]],
                             cap: int) -> Dict[str, Any]:
    feats = []
    for rid in filtered_ids:
        info = extents_idx.get(rid)
        if not info:
            continue
        feats.append({
            "type": "Feature",
            "properties": {"tier": info["tier"], "site": info["site"]},
            "geometry": info["geom"],
        })
        if len(feats) >= cap:
            break
    return {"type": "FeatureCollection", "features": feats}

# Page boot
st.set_page_config(page_title="Interactive FIM Vizualizer", page_icon="🌊", layout="wide")
st.title("Benchmark FIMs")

# Session defaults for viewport & control flags
ss = st.session_state
if "saved_center" not in ss:
    ss.saved_center = [39.8283, -98.5795]
if "saved_zoom" not in ss:
    ss.saved_zoom = 5.0
if "last_bounds" not in ss:
    ss.last_bounds = None 
if "fim_show" not in ss:
    ss.fim_show = False
if "filters_changed" not in ss:
    ss.filters_changed = True 
if "map_built_once" not in ss:
    ss.map_built_once = False

# Sidebar: cache control + basemap
with st.sidebar:
    st.header("Data")
    if st.button("Reload Data", use_container_width=True):
        fetch_json.clear()
        load_extents_gdf.clear()
        load_extents_index.clear()
        fingerprint_ids.clear()
        build_feature_collection.clear()
        for k in ("catalog_records", "core_errors", "extents_idx",
                  "polys_cache_key", "feature_collection_cache"):
            ss.pop(k, None)
        ss.filters_changed = True
        st.success("Cache cleared. Data will reload now.")

# Load core catalog
if "catalog_records" not in ss:
    core = fetch_json(http_url(CORE_KEY))
    ss.catalog_records = core.get("records", [])
    ss.core_errors     = core.get("errors", [])

records: List[Dict[str, Any]] = ss.catalog_records
load_errors = ss.get("core_errors", [])

if load_errors:
    with st.expander(f"{len(load_errors)} metadata issue(s) — click for details", expanded=False):
        for key, msg in load_errors[:50]:
            st.markdown(f"- **{key}**")
            st.code(msg, language="text")
        if len(load_errors) > 50:
            st.caption(f"...and {len(load_errors)-50} more")

if not records:
    st.warning("No records found in catalog_core.json.")
    st.stop()

# Filters
all_tiers = sorted({r.get("tier", "Unknown_Tier") for r in records})
dates_all = sorted([r["date_ymd"] for r in records if (r.get("tier") != "Tier_4") and r.get("date_ymd")])
min_date = dt.date.fromisoformat(dates_all[0]) if dates_all else dt.date(2000, 1, 1)
max_date = dt.date.fromisoformat(dates_all[-1]) if dates_all else dt.date.today()
rp_all   = sorted({r.get("return_period") for r in records if r.get("tier") == "Tier_4" and r.get("return_period") is not None})

with st.sidebar:
    st.header("Filters")
    with st.form("filters_form", clear_on_submit=False):
        sel_tiers = st.multiselect("Select FIM Tiers from Database", options=all_tiers, default=all_tiers)

        show_date_filter = any(t != "Tier_4" for t in sel_tiers)
        if show_date_filter:
            dr = st.date_input(
                "Date range (non-synthetic)",
                value=(min_date, max_date), min_value=min_date, max_value=max_date, format="YYYY-MM-DD"
            )
        else:
            dr = None

        show_rp_filter = ("Tier_4" in sel_tiers) and bool(rp_all)
        if show_rp_filter:
            sel_rps = st.multiselect("Return periods (For synthetic benchark Tier_4, years)", options=rp_all, default=rp_all)
        else:
            sel_rps = None

        show_polys = st.checkbox("Show Flood Inundation Mapping Extent", value=ss.get("fim_show", False))

        apply_filters = st.form_submit_button("Apply Filters", use_container_width=True)

    st.header("Basemap")
    basemap_choice = st.selectbox("Select basemap", list(BASEMAPS.keys()), index=2)

# Persist checkbox selection without triggering redraws until Apply
ss.fim_show = show_polys

# Date range unpack
if isinstance(dr, tuple) and len(dr) == 2:
    start_date, end_date = dr
else:
    start_date, end_date = min_date, max_date

def in_date_range(r) -> bool:
    iso = r.get("date_ymd")
    if not iso:
        return False
    try:
        d = dt.date.fromisoformat(iso)
    except Exception:
        return False
    return (start_date <= d <= end_date)

def pass_filters(r) -> bool:
    rtier = r.get("tier")
    if rtier not in sel_tiers:
        return False
    if rtier == "Tier_4":
        if sel_rps is None:
            return True
        rp = r.get("return_period")
        return (rp in sel_rps) if (rp is not None) else False
    else:
        if dr is None:
            return True
        return in_date_range(r)

# Apply filters only when the user clicks the button
if apply_filters:
    ss.filters_changed = True

filtered = [r for r in records if pass_filters(r)]
filtered_ids = [str(r["id"]) for r in filtered]
ids_key = fingerprint_ids(filtered_ids)

# Extents index
if ss.fim_show and "extents_idx" not in ss:
    ss.extents_idx = load_extents_index(http_url(GPQ_KEY))
extents_idx = ss.get("extents_idx", {}) if ss.fim_show else {}

# Helper: dynamic cap by zoom
def feature_cap_by_zoom(zoom: float) -> int:
    if zoom >= 10:
        return 200
    if zoom >= 8:
        return 120
    if zoom >= 6:
        return 60
    if zoom >= 5:
        return 30
    return BASE_FEATURE_CAP

# Map rendering (no reruns on pan/zoom)
@st.fragment
def render_map():
    # Build the folium map
    m = folium.Map(
        location=ss.saved_center,
        zoom_start=ss.saved_zoom,
        tiles=None,
        control_scale=True,
        prefer_canvas=True
    )
    bm = BASEMAPS[basemap_choice]
    folium.TileLayer(tiles=bm["tiles"], name=basemap_choice, control=False, attr=bm["attr"], show=True).add_to(m)

    # Heavy layers should be created ONLY when filters changed or first draw
    first_draw = not ss.map_built_once
    needs_rebuild = ss.filters_changed

    # Determine current cap based on saved zoom
    current_cap = feature_cap_by_zoom(float(ss.saved_zoom))

    # Build & cache feature collection for polygons when needed
    feature_collection: Optional[Dict[str, Any]] = None
    polys_cache_key = f"{ids_key}|cap={current_cap}|fim={int(ss.fim_show)}"

    if (first_draw or needs_rebuild) and ss.fim_show and extents_idx:
        feature_collection = build_feature_collection(filtered_ids, extents_idx, current_cap)
        ss.feature_collection_cache = feature_collection
        ss.polys_cache_key = polys_cache_key
    else:
        # reuse cached polygons if cache key matches
        if ss.get("polys_cache_key") == polys_cache_key:
            feature_collection = ss.get("feature_collection_cache")

    # Popup builder
    def popup_html(r: dict) -> str:
        tif_url = r.get("tif_url"); json_url = r.get("json_url")
        fields = [
            ("File Name", r.get("file_name")),
            ("Resolution (m)", r.get("resolution_m")),
            ("State", r.get("state")),
            ("Description", r.get("description")),
            ("River Basin Name", r.get("river_basin")),
            ("Source", r.get("source")),
            ("Date", r.get("date_ymd") or r.get("date_raw")),
            ("Return Period (years)", r.get("return_period") if r.get("tier") == "Tier_4" else None),
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

    # Markers (clustered)
    markers_fg = MarkerCluster(
        name="Benchmark FIM Sites",
        show=True,
        disableClusteringAtZoom=10
    )
    # Cap markers by the same dynamic cap
    count = 0
    for r in filtered:
        if count >= current_cap:
            break
        lat = float(r.get("centroid_lat", 0))
        lon = float(r.get("centroid_lon", 0))
        color = TIER_COLORS.get(r.get("tier"), DEFAULT_TIER_COLOR)
        folium.CircleMarker(
            location=[lat, lon],
            radius=8, color="black", weight=1.5, fill=True, fill_color=color, fill_opacity=0.9,
            tooltip=f"{r.get('tier')} — {r.get('site')}",
            popup=folium.Popup(popup_html(r), max_width=500),
        ).add_to(markers_fg)
        count += 1
    markers_fg.add_to(m)

    # Polygons
    if ss.fim_show and feature_collection and feature_collection.get("features"):
        def style_fn(feat):
            t = feat["properties"].get("tier")
            col = TIER_COLORS.get(t, DEFAULT_TIER_COLOR)
            return {"color": col, "weight": 1.0, "fillColor": col, "fillOpacity": 0.5}

        GeoJson(
            data=feature_collection,
            style_function=style_fn,
            smooth_factor=2.0,
            name="Benchmark FIM Extents",
            show=True,
        ).add_to(m)

    #  Legend
    legend_items = "".join(
        f"<div style='display:flex;align-items:center;margin-bottom:6px'>"
        f"<span style='display:inline-block;width:16px;height:16px;background:{TIER_COLORS.get(t, DEFAULT_TIER_COLOR)};"
        f"border:1px solid #000;margin-right:8px'></span>"
        f"<span style='font-size:14px'>{t}</span></div>"
        for t in sorted(set(r.get("tier") for r in filtered))
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

    # CRITICAL
    st_folium(
        m,
        width=None,
        height=720,
        key="fim_map",
        returned_objects=[]
    )

    # After a successful build, clear the flag
    if needs_rebuild or first_draw:
        ss.map_built_once = True
        ss.filters_changed = False

# Map actions
with st.sidebar:
    st.header("Map actions")
    colA, colB = st.columns(2)
    with colA:
        if st.button("Zoom −", use_container_width=True):
            ss.saved_zoom = max(2.0, float(ss.saved_zoom) - 1.0)
            ss.filters_changed = True
    with colB:
        if st.button("Zoom +", use_container_width=True):
            ss.saved_zoom = min(18.0, float(ss.saved_zoom) + 1.0)
            ss.filters_changed = True

    if st.button("Center on USA", use_container_width=True):
        ss.saved_center = [39.8283, -98.5795]
        ss.saved_zoom = 5.0
        ss.filters_changed = True
render_map()
