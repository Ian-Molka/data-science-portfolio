# -*- coding: utf-8 -*-
"""
Incident ⟵ County spatial join (left):
- Loads incidents CSV (lat/lon) and a county GeoJSON
- Builds point geometry from lat/lon
- Spatially joins points to counties (intersects, to include border points)
- Keeps ALL incidents; county columns are prefixed with 'county_'
- Outputs CSV (no geometry) and GeoJSON (for QA)

Requires: geopandas, pandas, shapely>=2.0
pip install geopandas shapely pandas
"""

import os
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# ================== USER SETTINGS ==================
INCIDENTS_CSV = r"data/input_file.csv"        # has latitude/longitude columns
COUNTIES_GEOJSON = r"data/counties.geojson"     # your county polygons (GeoJSON/ESRI JSON supported)
OUT_CSV = r"data/output_file.csv"
OUT_GEOJSON = r"data/counties+incident.geojson"

# If your CSV uses different names, set them here; auto-detect also tries common variants.
LAT_COL_HINT = "Latitude"
LON_COL_HINT = "Longitude"

# Predicate: "intersects" is inclusive (captures boundary points).
# You can change to "within" if you want strict point-in-polygon.
PREDICATE = "intersects"
# ====================================================


def detect_lat_lon_columns(df, lat_hint=LAT_COL_HINT, lon_hint=LON_COL_HINT):
    lat_candidates = [lat_hint, "lat", "latitude", "LAT", "Lat", "Y", "y"]
    lon_candidates = [lon_hint, "lon", "longitude", "LONGITUDE", "Lng", "lng", "LON", "Lon", "X", "x"]
    lat = next((c for c in lat_candidates if c in df.columns), None)
    lon = next((c for c in lon_candidates if c in df.columns), None)
    if not lat or not lon:
        raise ValueError(
            "Could not find latitude/longitude columns.\n"
            f"Tried lat={lat_candidates} and lon={lon_candidates}\n"
            f"Columns present: {list(df.columns)}"
        )
    return lat, lon


def derive_county_keys(gdf_county):
    """
    Standardize useful county fields:
      - county_geoid (5-digit FIPS)
      - county_name
      - state_fips
      - county_fips
      - state_abbr (if present)
    Works with common Census/TIGER field names.
    """
    c = gdf_county.copy()

    # Pick name
    if "NAME" in c.columns:
        c["county_name"] = c["NAME"]
    elif "NAMELSAD" in c.columns:
        c["county_name"] = c["NAMELSAD"]
    else:
        # last resort: first name-like column
        name_like = next((col for col in c.columns if "NAME" in col.upper()), None)
        c["county_name"] = c[name_like] if name_like else None

    # State & county FIPS
    state_fp = None
    for cand in ["STATEFP", "STATEFP20", "STATEFP10"]:
        if cand in c.columns:
            state_fp = cand
            break

    county_fp = None
    for cand in ["COUNTYFP", "COUNTYFP20", "COUNTYFP10"]:
        if cand in c.columns:
            county_fp = cand
            break

    # GEOID
    geoid_col = None
    for cand in ["GEOID", "GEOID20", "GEOID10"]:
        if cand in c.columns:
            geoid_col = cand
            break

    if geoid_col:
        c["county_geoid"] = c[geoid_col].astype(str).str.zfill(5)
    elif state_fp and county_fp:
        c["county_geoid"] = c[state_fp].astype(str).str.zfill(2) + c[county_fp].astype(str).str.zfill(3)
    else:
        # leave as None if not available
        c["county_geoid"] = None

    # state_fips / county_fips
    c["state_fips"] = c[state_fp].astype(str).str.zfill(2) if state_fp else None
    c["county_fips"] = c[county_fp].astype(str).str.zfill(3) if county_fp else None

    # state_abbr if available
    st_abbr = None
    for cand in ["STUSPS", "STATEAB", "STATE_ABBR"]:
        if cand in c.columns:
            st_abbr = cand
            break
    c["state_abbr"] = c[st_abbr] if st_abbr else None

    # Prefix all original county attributes to avoid name collisions later
    # but keep the standardized keys unprefixed for convenience.
    rename_map = {col: f"county_{col}" for col in c.columns if col not in ["geometry", "county_geoid",
                                                                          "county_name", "state_fips",
                                                                          "county_fips", "state_abbr"]}
    c = c.rename(columns=rename_map)

    # Keep geometry as-is; return enriched county gdf
    return c


def main():
    # ---- Load incidents ----
    df = pd.read_csv(INCIDENTS_CSV)
    lat_col, lon_col = detect_lat_lon_columns(df, LAT_COL_HINT, LON_COL_HINT)

    # Clean coordinates
    df = df[pd.notnull(df[lat_col]) & pd.notnull(df[lon_col])].copy()
    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
    df = df[pd.notnull(df[lat_col]) & pd.notnull(df[lon_col])]

    gdf_pts = gpd.GeoDataFrame(
        df.copy(),
        geometry=[Point(xy) for xy in zip(df[lon_col], df[lat_col])],
        crs="EPSG:4326"
    )

    # ---- Load counties ----
    counties = gpd.read_file(COUNTIES_GEOJSON)
    if counties.crs is None:
        counties = counties.set_crs("EPSG:4326")
    elif counties.crs.to_string().lower() != "epsg:4326":
        counties = counties.to_crs("EPSG:4326")

    counties_std = derive_county_keys(counties)

    # ---- Spatial join (LEFT) ----
    joined = gpd.sjoin(
        gdf_pts, counties_std,
        how="left",
        predicate=PREDICATE,
        lsuffix="",
        rsuffix="_county"
    )

    # Simple diagnostics
    matched = joined["county_geoid"].notna().sum()
    print(f"Incidents: {len(gdf_pts):,} | Matched to a county: {matched:,} | Unmatched: {len(gdf_pts)-matched:,}")

    # ---- Save outputs ----
    # CSV (drop geometry)
    joined_csv = joined.drop(columns=["geometry"], errors="ignore")
    joined_csv.to_csv(OUT_CSV, index=False)
    print(f"✅ Wrote CSV: {OUT_CSV}")

    # GeoJSON (keep geometry for QA in GIS)
    joined.to_file(OUT_GEOJSON, driver="GeoJSON")
    print(f"✅ Wrote GeoJSON: {OUT_GEOJSON}")

if __name__ == "__main__":
    main()
