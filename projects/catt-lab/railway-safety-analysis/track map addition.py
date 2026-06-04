# -*- coding: utf-8 -*-
"""
Incidents (CSV lat/lon) ⟵ nearest NARN Tracks (GeoJSON lines)
- Left spatial join: keeps ALL incidents
- Uses INCIDENT coordinates (not inventory)
- Adds rail_* attributes and distance_m
"""

import os
import re
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# ===================== USER SETTINGS =====================
INCIDENTS_CSV   = r"data/input_file.csv"
TRACKS_GEOJSON  = r"data/NARN_Rail_Lines_US.geojson"
OUT_CSV         = r"data/Incidents_to_NARN_conflation.csv"

# Force specific incident columns (recommended for your file)
LAT_HINT = "Latitude_incident"      # set to None to auto-detect
LON_HINT = "Longitude_incident"     # set to None to auto-detect

# Distance threshold in meters (None = always pick nearest line)
MAX_DISTANCE_M = None
# ========================================================

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

def detect_incident_lat_lon(df: pd.DataFrame, lat_hint: str | None, lon_hint: str | None):
    cols = list(df.columns)

    # Use explicit hints if provided and present
    if lat_hint and lon_hint and lat_hint in df.columns and lon_hint in df.columns:
        print(f"[detect] Using explicit incident columns: lat='{lat_hint}', lon='{lon_hint}'")
        return lat_hint, lon_hint

    # Find latitude-/longitude-like columns
    lat_cands = [c for c in cols if any(tok in _norm(c) for tok in ["lat","latitude","y"])]
    lon_cands = [c for c in cols if any(tok in _norm(c) for tok in ["lon","longitude","x"])]

    if not lat_cands or not lon_cands:
        raise ValueError(f"No latitude/longitude-like columns found. Columns: {cols}")

    # Prefer names containing 'incident'; deprioritize 'inventory'
    def pick(cands):
        inc = [c for c in cands if "incident" in _norm(c)]
        if inc: return inc[0]
        generic = [c for c in cands if "inventory" not in _norm(c)]
        if generic: return generic[0]
        return cands[0]

    lat_col = pick(lat_cands)
    lon_col = pick(lon_cands)
    print(f"[detect] Auto-detected incident lat/lon: '{lat_col}', '{lon_col}'")
    return lat_col, lon_col

def to_metric(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf.to_crs("EPSG:3857")

def main():
    # ---- Load incidents (use INCIDENT coordinates) ----
    df = pd.read_csv(INCIDENTS_CSV)
    lat_col, lon_col = detect_incident_lat_lon(df, LAT_HINT, LON_HINT)

    # Clean/parse coordinates
    df = df[pd.notnull(df[lat_col]) & pd.notnull(df[lon_col])].copy()
    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
    df = df[pd.notnull(df[lat_col]) & pd.notnull(df[lon_col])].copy()

    gdf_pts = gpd.GeoDataFrame(
        df.copy(),
        geometry=[Point(xy) for xy in zip(df[lon_col], df[lat_col])],
        crs="EPSG:4326"
    )

    # ---- Load NARN rails (lines) ----
    if not os.path.exists(TRACKS_GEOJSON):
        raise FileNotFoundError(f"Tracks file not found: {TRACKS_GEOJSON}")
    rails = gpd.read_file(TRACKS_GEOJSON)
    if rails.crs is None:
        rails = rails.set_crs("EPSG:4326")

    rail_id_col = "OBJECTID" if "OBJECTID" in rails.columns else "rail_id"
    if rail_id_col not in rails.columns:
        rails[rail_id_col] = rails.index

    # Reproject to meters for distance
    pts_m   = to_metric(gdf_pts)
    rails_m = to_metric(rails)

    # Nearest join (incident point -> nearest rail line)
    rails_min = rails_m[[rail_id_col, "geometry"]].copy()
    joined = gpd.sjoin_nearest(
        pts_m, rails_min,
        how="left",
        distance_col="distance_m",
        max_distance=MAX_DISTANCE_M  # None => always find nearest
    )

    # Match flag & optional miles
    joined["matched_to_rail"] = joined["distance_m"].notna()
    if "distance_m" in joined.columns:
        joined["distance_mi"] = joined["distance_m"] / 1609.344

    # Normalize rail id naming on the joined frame
    if rail_id_col in joined.columns:
        joined = joined.rename(columns={rail_id_col: f"rail_{rail_id_col}"})
    elif f"{rail_id_col}_right" in joined.columns:
        joined = joined.rename(columns={f"{rail_id_col}_right": f"rail_{rail_id_col}"})

    # Bring all rail attrs (prefixed rail_) into the table
    rails_attr = rails.drop(columns=["geometry"], errors="ignore").copy()
    to_prefix = [c for c in rails_attr.columns if not c.startswith("rail_")]
    rails_attr.rename(columns={c: f"rail_{c}" for c in to_prefix}, inplace=True)

    joined = joined.merge(
        rails_attr,
        left_on=f"rail_{rail_id_col}",
        right_on=f"rail_{rail_id_col}",
        how="left"
    )

    # --- Fix county_GEOID to always be 5 characters (pad with leading zero if needed) ---
    if "county_GEOID" in joined.columns:
        joined["county_GEOID"] = joined["county_GEOID"].astype(str).str.zfill(5)

    # Prepare CSV (drop geometry; keep incident lat/lon)
    out = joined.drop(columns=["geometry"], errors="ignore")

    # Put useful columns first
    front = [lat_col, lon_col, "distance_m", "distance_mi", "matched_to_rail", f"rail_{rail_id_col}"]
    front = [c for c in front if c in out.columns]
    out = out[front + [c for c in out.columns if c not in front]]

    # Save + summary
    out.to_csv(OUT_CSV, index=False)
    n = len(out)
    n_match = int(out["matched_to_rail"].sum()) if "matched_to_rail" in out else 0
    print(f"✅ Wrote: {OUT_CSV}  ({n:,} rows)")
    print(f"   Matches: {n_match:,}  |  Unmatched: {n - n_match:,}")
    print(f"   Using INCIDENT columns: lat='{lat_col}', lon='{lon_col}'")
    if (n - n_match) > 0:
        print("   Example unmatched (first 5):")
        print(out.loc[~out["matched_to_rail"], [lat_col, lon_col]].head())

if __name__ == "__main__":
    main()
