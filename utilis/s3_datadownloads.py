# utilis/downloads.py
import urllib.parse
import streamlit as st
import boto3

BUCKET = "sdmlab"

# helpers for direct S3 file links
def s3_http_url(bucket: str, key: str) -> str:
    """Build a public-style S3 HTTPS URL (works for public buckets; for private, set proper ACL/CORS or presign)."""
    return f"https://{bucket}.s3.amazonaws.com/{urllib.parse.quote(key, safe='/')}"

def find_json_in_folder(bucket: str, folder: str, tif_filename: str | None) -> str | None:
    """
    Find a metadata .json in the same folder:
    1) Try <tif_basename>.json if tif name is known and exists
    2) Otherwise, return the first .json under the folder
    """
    s3 = boto3.client("s3")
    folder = folder.rstrip("/")

    # Try basename.json next to the tif
    if tif_filename:
        import os as _os
        base = _os.path.splitext(tif_filename)[0]
        candidate = f"{folder}/{base}.json"
        try:
            s3.head_object(Bucket=BUCKET, Key=candidate)
            return candidate
        except Exception:
            pass

    # Fallback: first .json under folder
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=f"{folder}/"):
        for obj in page.get("Contents", []) or []:
            key = obj["Key"]
            if key.endswith("/"):
                continue
            if key.lower().endswith(".json"):
                return key
    return None
