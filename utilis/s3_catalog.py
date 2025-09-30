from __future__ import annotations
import json, re, datetime as dt
from typing import Dict, List, Any
import boto3
from botocore import UNSIGNED
from botocore.config import Config
import streamlit as st

# CACHED RESOURCES
@st.cache_resource
def _s3_client():
    return boto3.client("s3", config=Config(signature_version=UNSIGNED))

def _extract_ymd(s: str) -> str | None:
    if not s:
        return None
    m = re.search(r"(\d{8})", s)
    return m.group(1) if m else None

# CORE LOGIC
def _list_metadata_objects(bucket: str, root_prefix: str) -> List[str]:
    s3 = _s3_client()
    keys: List[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=root_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith("_metadata.json"):
                keys.append(key)
    return keys

def _fetch_json(bucket: str, key: str) -> Dict[str, Any]:
    s3 = _s3_client()
    resp = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(resp["Body"].read().decode("utf-8"))

@st.cache_data(show_spinner=False)
def build_catalog(bucket: str, root_prefix: str) -> List[Dict[str, Any]]:
    """
    Cached: lists all *_metadata.json under root_prefix (across Tier_*/*),
    fetches and normalizes fields. Cache invalidates only when (bucket, root_prefix) change
    or you manually clear it from the app.
    """
    keys = _list_metadata_objects(bucket, root_prefix)
    out: List[Dict[str, Any]] = []

    for key in keys:
        parts = key.split("/")
        tier = next((p for p in parts if p.lower().startswith("tier_")), None) or "Unknown_Tier"
        site = parts[-2] if len(parts) >= 2 else "Unknown_Site"

        meta = _fetch_json(bucket, key)

        file_name = meta.get("File_Name") or meta.get("File Name")
        res_m    = meta.get("Resolution in meter")
        dtype    = meta.get("Datatype") or meta.get("Data type")
        state    = meta.get("State")
        desc     = meta.get("Description")
        basin    = meta.get("River Basin Name") or meta.get("River Basin")
        source   = meta.get("Source")
        quality  = meta.get("Quality") or tier

        date_raw = meta.get("Date of Flood /Synthetic Flooding Event (return period (years))") or ""
        ymd_compact = _extract_ymd(date_raw) or _extract_ymd(file_name or "")
        date_iso = None
        if ymd_compact:
            try:
                date_iso = dt.datetime.strptime(ymd_compact, "%Y%m%d").date().isoformat()
            except Exception:
                date_iso = None

        # centroid
        lon = lat = None
        centroid = meta.get("Location of the centroid of the flood map") or []
        if isinstance(centroid, list) and len(centroid) >= 2:
            lon, lat = float(centroid[0]), float(centroid[1])
        else:
            ex = meta.get("Extent") or {}
            xmin, ymin, xmax, ymax = ex.get("xmin"), ex.get("ymin"), ex.get("xmax"), ex.get("ymax")
            if all(v is not None for v in (xmin, ymin, xmax, ymax)):
                lon = (float(xmin) + float(xmax)) / 2.0
                lat = (float(ymin) + float(ymax)) / 2.0
        if lon is None or lat is None:
            lon, lat = 0.0, 0.0 

        refs = meta.get("References") or []
        if isinstance(refs, str):
            refs = [refs]

        out.append({
            "tier": tier,
            "site": site,
            "s3_key": key,
            "file_name": file_name,
            "resolution_m": res_m,
            "dtype": dtype,
            "state": state,
            "description": desc,
            "river_basin": basin,
            "source": source,
            "date_raw": date_raw,
            "date_ymd": date_iso,
            "quality": quality,
            "references": refs,
            "centroid_lon": lon,
            "centroid_lat": lat,
            "geometry": meta.get("FIM_Geometry"),
            "extent": meta.get("Extent"),
        })

    return out