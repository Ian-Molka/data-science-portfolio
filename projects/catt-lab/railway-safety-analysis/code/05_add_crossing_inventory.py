# conflate_incidents_to_inventory_spatial_only.py
# pip install geopandas pandas shapely pyogrio

import pandas as pd
import geopandas as gpd
from geopandas.array import GeometryDtype
import numpy as np

# ====== CONFIG =======================================================
# Incidents (LEFT)
INCIDENTS_CSV      = r"data/input_file.csv"
INCIDENTS_GEOJSON  = None  # set INCIDENTS_CSV=None to use GeoJSON

INCIDENT_ID_COL = "Incident Key"
INC_LAT_COL     = "Latitude"
INC_LON_COL     = "Longitude"

# Inventory (RIGHT)
INVENTORY_CSV  = r"data/inventory_file.csv"
INV_LAT_COL    = "Latitude"
INV_LON_COL    = "Longitude"

# Distance threshold (0.5 miles)
HALF_MILE_METERS = 1609.344  # 804.672 m
METERS_PER_MILE  = 1609.344

# If present, use one of these IDs to break ties deterministically:
INVENTORY_ID_CANDIDATES = [
    "DOT_Number", "DOT Number", "Crossing ID", "CrossingID", "XingID",
    "InventoryID", "FRAARCID", "FRFRANODE", "ID"
]

# Outputs
BASE = r"data/Incidents_spatial_only_0p5mi"
OUTPUT_GEOJSON        = BASE + ".geojson"
OUTPUT_CSV            = BASE + ".csv"
OUTPUT_UNMATCHED_CSV  = BASE + "_unmatched.csv"
# ====================================================================

def csv_to_points(path, lat_col, lon_col, prefix=None):
    """Load CSV safely, coerce lat/lon, return GeoDataFrame (EPSG:4326)."""
    df = pd.read_csv(path, dtype=str, low_memory=False)

    for col in ["index_left", "index_right", "index_l", "index_r"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
    df = df.dropna(subset=[lat_col, lon_col])

    if prefix:
        df = df.rename(columns={lat_col: f"{lat_col}_{prefix}", lon_col: f"{lon_col}_{prefix}"})
        lat_col = f"{lat_col}_{prefix}"
        lon_col = f"{lon_col}_{prefix}"

    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[lon_col], df[lat_col]), crs="EPSG:4326")


def load_incidents(csv_path=None, geojson_path=None):
    if geojson_path:
        g = gpd.read_file(geojson_path)
        if g.crs is None:
            g = g.set_crs(epsg=4326)
    else:
        g = csv_to_points(csv_path, INC_LAT_COL, INC_LON_COL, prefix="incident")

    if INCIDENT_ID_COL not in g.columns:
        g[INCIDENT_ID_COL] = g.index.astype(str)
    return g


def demote_extra_geometry_columns(gdf: gpd.GeoDataFrame, keep_geom_name: str = "geometry") -> gpd.GeoDataFrame:
    """Convert any extra geometry-typed columns to WKT so GeoJSON save sees only one geometry."""
    out = gdf.copy()
    for col in out.columns:
        if col == keep_geom_name:
            continue
        if isinstance(out[col].dtype, GeometryDtype):
            out[col] = gpd.GeoSeries(out[col], crs=out.crs).to_wkt()
    return out


def pick_inventory_id_col(df):
    """Find a stable inventory ID column (plain or '_inv' suffixed) for tie-breaking."""
    for c in INVENTORY_ID_CANDIDATES:
        if c in df.columns:
            return c
        if f"{c}_inv" in df.columns:
            return f"{c}_inv"
    return None


def main():
    # Load layers
    incidents = load_incidents(INCIDENTS_CSV, INCIDENTS_GEOJSON)           # EPSG:4326
    inventory = csv_to_points(INVENTORY_CSV, INV_LAT_COL, INV_LON_COL, prefix="inventory")  # EPSG:4326

    # Reproject to meters for distance calc
    inc_m = incidents.to_crs(3857)
    inv_m = inventory.to_crs(3857)

    # Spatial nearest join within 0.5 mile (may return ties = multiple rows per incident)
    joined_m = gpd.sjoin_nearest(
        inc_m, inv_m,
        how="left",
        lsuffix="inc", rsuffix="inv",
        distance_col="distance_m",
        max_distance=HALF_MILE_METERS
    )

    # Back to WGS84
    joined = joined_m.to_crs(4326)

    # Distance in miles
    joined["distance_mi"] = (joined["distance_m"] / METERS_PER_MILE).round(3)

    # Carry inventory lon/lat if present
    if "Longitude_inventory" in joined.columns and "Latitude_inventory" in joined.columns:
        joined["inventory_lon"] = pd.to_numeric(joined["Longitude_inventory"], errors="coerce")
        joined["inventory_lat"] = pd.to_numeric(joined["Latitude_inventory"], errors="coerce")

    # Optional inventory WKT via index_right
    if "index_right" in joined.columns:
        inv_wkt_map = inventory.geometry.to_wkt()
        joined["inventory_wkt"] = joined["index_right"].map(inv_wkt_map)

    # ---------- NEW: collapse to ONE closest crossing per incident ----------
    rows_before = len(joined)

    inv_id_col = pick_inventory_id_col(joined)
    sort_cols = ["distance_m"]
    # Stable tie-breakers: prefer a real inventory ID, then index_right if available
    if inv_id_col:
        sort_cols.append(inv_id_col)
    if "index_right" in joined.columns:
        sort_cols.append("index_right")

    # Sort and drop duplicates to keep a single closest row per incident
    joined = joined.sort_values(sort_cols).drop_duplicates(subset=[INCIDENT_ID_COL], keep="first")

    rows_after = len(joined)
    collapsed_ties = rows_before - rows_after
    # -----------------------------------------------------------------------

    # Final GeoDataFrame (incident geometry only). Demote any extra geometry cols (paranoia).
    g = gpd.GeoDataFrame(joined, geometry="geometry", crs="EPSG:4326")
    g = demote_extra_geometry_columns(g, keep_geom_name="geometry")

    # Save outputs
    g.to_file(OUTPUT_GEOJSON, driver="GeoJSON")
    g.drop(columns=["geometry"], errors="ignore").to_csv(OUTPUT_CSV, index=False)

    # Report + unmatched list
    total_inc = len(incidents)
    matched   = g["distance_m"].notna().sum()
    unmatched = total_inc - matched
    pct       = (matched / total_inc * 100.0) if total_inc else 0.0

    # Unmatched IDs file
    if INCIDENT_ID_COL in g.columns:
        unmatched_ids = g.loc[g["distance_m"].isna(), INCIDENT_ID_COL].astype(str).tolist()
    else:
        left_ids = set(incidents[INCIDENT_ID_COL].astype(str))
        matched_ids = set(g.loc[g["distance_m"].notna(), INCIDENT_ID_COL].astype(str)) if INCIDENT_ID_COL in g.columns else set()
        unmatched_ids = sorted(left_ids - matched_ids)
    pd.DataFrame({INCIDENT_ID_COL: unmatched_ids}).to_csv(OUTPUT_UNMATCHED_CSV, index=False)

    # Distance stats (meters & miles) for matched
    d_m  = pd.to_numeric(g.loc[g["distance_m"].notna(), "distance_m"], errors="coerce")
    d_mi = pd.to_numeric(g.loc[g["distance_mi"].notna(), "distance_mi"], errors="coerce")
    dist_stats_m  = (d_m.min() if not d_m.empty else np.nan,
                     d_m.median() if not d_m.empty else np.nan,
                     d_m.mean() if not d_m.empty else np.nan,
                     d_m.max() if not d_m.empty else np.nan)
    dist_stats_mi = (d_mi.min() if not d_mi.empty else np.nan,
                     d_mi.median() if not d_mi.empty else np.nan,
                     d_mi.mean() if not d_mi.empty else np.nan,
                     d_mi.max() if not d_mi.empty else np.nan)

    # Console report
    print(f"✅ Saved GeoJSON: {OUTPUT_GEOJSON}")
    print(f"✅ Saved CSV:     {OUTPUT_CSV}")
    print(f"🕳️  Unmatched ID list: {OUTPUT_UNMATCHED_CSV}")
    print("---- Spatial Match Report (0.5 mile, one-per-incident) ----")
    print(f"Tie rows collapsed:     {collapsed_ties}")
    print(f"Matched within 0.5 mi:  {matched}")
    print(f"Total incidents:        {total_inc}")
    print(f"Unmatched:              {unmatched}")
    print(f"Percent matched:        {pct:.1f}%")
    print("Distance (m)   — min / median / mean / max: {:.2f} / {:.2f} / {:.2f} / {:.2f}".format(*[x if pd.notna(x) else float('nan') for x in dist_stats_m]))
    print("Distance (mi)  — min / median / mean / max: {:.3f} / {:.3f} / {:.3f} / {:.3f}".format(*[x if pd.notna(x) else float('nan') for x in dist_stats_mi]))


if __name__ == "__main__":
    main()
