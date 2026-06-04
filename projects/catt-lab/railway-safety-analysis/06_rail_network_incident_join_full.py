# -*- coding: utf-8 -*-
"""
Rails LEFT JOIN nearest incidents (within 200 m)
- Keeps ALL rails.
- Each incident (unique row) is matched to its single nearest rail IF within MAX_DISTANCE_M.
- Output has one row per (rail × matched-incident); rails with 0 incidents still appear
  once with NULL incident columns.

Requires:
  pip install geopandas shapely pandas
"""

import os
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# ===================== USER SETTINGS =====================
INCIDENTS_CSV   = r"data/input_file.csv"
TRACKS_GEOJSON  = r"data/NARN_Rail_Lines.geojson"

OUT_GEOJSON     = r"data/Rails_LEFT_join_incidents.geojson"
OUT_CSV         = r"data/Rails_LEFT_join_incidents.csv"

# Incident coordinate column names (auto-detect also tries common variants)
LAT_HINT = "Latitude"
LON_HINT = "Longitude"

# Join behavior:
# - Set to a number to only match incidents within that many meters to a rail.
# - Set to None to ALWAYS assign each incident to its nearest rail (even if far).
MAX_DISTANCE_M = 200
# ========================================================

def detect_lat_lon_columns(df, lat_hint=LAT_HINT, lon_hint=LON_HINT):
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

def to_metric(gdf):
    # Use Web Mercator (EPSG:3857) for distance calculations in meters
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf.to_crs("EPSG:3857")

def main():
    print(f"Using GeoPandas {gpd.__version__}")

    # ---- Load incidents ----
    inc_df = pd.read_csv(INCIDENTS_CSV)
    lat_col, lon_col = detect_lat_lon_columns(inc_df, LAT_HINT, LON_HINT)

    # Create a guaranteed-unique row key for incidents
    row_id_col = "__inc_rowid__"
    inc_df[row_id_col] = range(len(inc_df))

    # Optional human ID (may be non-unique)
    orig_inc_id_col = "Report ID" if "Report ID" in inc_df.columns else None

    # Clean coords
    inc_df = inc_df[pd.notnull(inc_df[lat_col]) & pd.notnull(inc_df[lon_col])].copy()
    inc_df[lat_col] = pd.to_numeric(inc_df[lat_col], errors="coerce")
    inc_df[lon_col] = pd.to_numeric(inc_df[lon_col], errors="coerce")
    inc_df = inc_df[pd.notnull(inc_df[lat_col]) & pd.notnull(inc_df[lon_col])]

    # Dtypes for safety
    if orig_inc_id_col:
        inc_df[orig_inc_id_col] = inc_df[orig_inc_id_col].astype(str)

    gdf_pts = gpd.GeoDataFrame(
        inc_df.copy(),
        geometry=[Point(xy) for xy in zip(inc_df[lon_col], inc_df[lat_col])],
        crs="EPSG:4326"
    )

    # ---- Load rails ----
    if not os.path.exists(TRACKS_GEOJSON):
        raise FileNotFoundError(f"Tracks file not found: {TRACKS_GEOJSON}")
    rails = gpd.read_file(TRACKS_GEOJSON)
    if rails.crs is None:
        rails = rails.set_crs("EPSG:4326")

    # Stable rail ID
    rail_id_col = "OBJECTID" if "OBJECTID" in rails.columns else "rail_id"
    if rail_id_col not in rails.columns:
        rails[rail_id_col] = rails.index

    # Deduplicate rails by ID (guardrail)
    before_dupe = len(rails)
    rails = rails.drop_duplicates(subset=[rail_id_col])
    after_dupe = len(rails)
    if after_dupe < before_dupe:
        print(f"Deduped rails on {rail_id_col}: {before_dupe} → {after_dupe}")

    # ---- Project to meters for distances ----
    pts_m   = to_metric(gdf_pts)
    rails_m = to_metric(rails)

    # ---- Step 1: Assign each incident (row) to its NEAREST rail (within threshold) ----
    pairs = gpd.sjoin_nearest(
        pts_m[[row_id_col, lat_col, lon_col, "geometry"]],
        rails_m[[rail_id_col, "geometry"]],
        how="left",
        distance_col="distance_m",
        max_distance=MAX_DISTANCE_M  # None -> always assign nearest
    ).drop(columns=["geometry"], errors="ignore")

    # Keep only incidents that actually matched (within threshold if set)
    pairs["matched_to_rail"] = pairs["distance_m"].notna()
    pairs = pairs[pairs["matched_to_rail"]].copy()

    # ---- Sanity checks (by row) ----
    total_inc_valid = len(gdf_pts)
    total_pairs = len(pairs)
    unique_rows_matched = pairs[row_id_col].nunique()
    print("— SANITY CHECKS —")
    print(f"Incidents with valid coords: {total_inc_valid:,}")
    print(f"Matched incident→rail pairs: {total_pairs:,}")
    print(f"Unique incident rows matched: {unique_rows_matched:,}")
    if total_pairs != unique_rows_matched:
        # Enforce 1-nearest per row just in case
        pairs = pairs.sort_values("distance_m").drop_duplicates(subset=[row_id_col], keep="first")
        total_pairs = len(pairs)
        unique_rows_matched = pairs[row_id_col].nunique()
        print(f"   → Enforced 1-nearest per row. Pairs now: {total_pairs:,}")

    # Optional: show if 'Report ID' is non-unique
    if orig_inc_id_col:
        dup_ids = inc_df[orig_inc_id_col].duplicated(keep=False).sum()
        print(f"Non-unique '{orig_inc_id_col}' rows: {dup_ids:,}")

    # ---- Step 2: Prepare rail base (ALL rails, with rail_* prefixes) ----
    rails_geom  = rails_m[[rail_id_col, "geometry"]].copy()
    rails_attrs = rails.drop(columns=["geometry"], errors="ignore").copy().add_prefix("rail_")

    # Handy padded county FIPS if present
    if "rail_STCNTYFIPS" not in rails_attrs.columns and "STCNTYFIPS" in rails.columns:
        rails_attrs["rail_STCNTYFIPS"] = rails["STCNTYFIPS"]
    if "rail_STCNTYFIPS" in rails_attrs.columns:
        rails_attrs["rail_county_fips_5"] = rails_attrs["rail_STCNTYFIPS"].astype(str).str.zfill(5)

    rails_base = rails_geom.merge(
        rails_attrs,
        left_on=rail_id_col,
        right_on=f"rail_{rail_id_col}" if f"rail_{rail_id_col}" in rails_attrs.columns else rail_id_col,
        how="left",
        validate="one_to_one"
    )
    # (Optional) drop the duplicated rail key from attrs if present
    dup_key = f"rail_{rail_id_col}"
    if dup_key in rails_base.columns:
        rails_base.drop(columns=[dup_key], inplace=True)

    # ---- Step 3: Attach incident columns WITHOUT any 'inc_' prefix ----
    # Keep only the join key + rail + distance in pairs
    pairs_slim = pairs[[row_id_col, rail_id_col, "distance_m"]].copy()

    # Use original incident columns (no renaming)
    inc_attrs = gdf_pts.drop(columns=["geometry"], errors="ignore").copy()

    # Guard: avoid accidental name clash with the rail id
    if rail_id_col in inc_attrs.columns:
        inc_attrs.rename(columns={rail_id_col: f"{rail_id_col}_incident"}, inplace=True)

    # Join incident attributes by the unique row key (one-to-one)
    pairs_full = pairs_slim.merge(
        inc_attrs,
        on=row_id_col,
        how="left",
        validate="one_to_one"
    )

    # Rails LEFT JOIN pairs (so rails with 0 incidents remain, with incident cols NULL)
    rails_left = rails_base.merge(
        pairs_full,
        on=rail_id_col,
        how="left",
        validate="one_to_many"     # a rail can have many matched incidents
    )

    # Flag showing whether this row corresponds to a matched incident
    rails_left["has_incident_within_threshold"] = rails_left["distance_m"].notna()

    # ---- Reproject back to EPSG:4326 for GeoJSON and save outputs ----
    rails_left_gdf = gpd.GeoDataFrame(rails_left, geometry="geometry", crs="EPSG:3857").to_crs("EPSG:4326")

    if OUT_GEOJSON:
        rails_left_gdf.to_file(OUT_GEOJSON, driver="GeoJSON")
    if OUT_CSV:
        rails_left_nogeo = pd.DataFrame(rails_left_gdf.drop(columns=["geometry"]))
        rails_left_nogeo.to_csv(OUT_CSV, index=False)

    # ---- Final counts + expectation check ----
    total_rails = rails[rail_id_col].nunique()
    rails_with_inc = pairs[rail_id_col].nunique()
    rails_without_inc = total_rails - rails_with_inc
    expected_rows = rails_without_inc + len(pairs)  # rails (0-incidents) + one row per matched incident
    actual_rows = len(rails_left_gdf)

    print("\n— OUTPUT SUMMARY —")
    print(f"Rails total                       : {total_rails:,}")
    print(f"Rails with ≥1 incident ≤{MAX_DISTANCE_M} m : {rails_with_inc:,}")
    print(f"Rails with 0 incidents            : {rails_without_inc:,}")
    print(f"Matched incident→rail pairs       : {len(pairs):,}")
    print(f"Expected output rows              : {expected_rows:,}")
    print(f"Actual output rows                : {actual_rows:,}")
    if expected_rows != actual_rows:
        print("WARNING: Row count mismatch. This usually means duplicate rail IDs slipped in somewhere.")

    print(f"\n✅ Wrote GeoJSON: {OUT_GEOJSON}" if OUT_GEOJSON else "\nℹ️ Skipped GeoJSON")
    print(f"✅ Wrote CSV    : {OUT_CSV}" if OUT_CSV else "ℹ️ Skipped CSV")

if __name__ == "__main__":
    main()
