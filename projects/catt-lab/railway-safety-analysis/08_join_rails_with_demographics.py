# join_rails_with_demographics.py
# ------------------------------------------------------------
# Join rails (GeoJSON) with demographics CSV by Objectid, so
# Tableau reads a single spatial file with all % fields attached.
# ------------------------------------------------------------
import os
import pandas as pd
import geopandas as gpd

# ---------- INPUTS ----------
RAILS_PATH = r"data/input_file.csv"
DEMO_PATH  = r"data/input_file.csv"
# If you only have demographics_all_by_feature.csv, you can also point to that,
# but the *_pct_joinable.csv is ideal since it already has % columns and Objectid.

# ---------- OUTPUT ----------
OUT_GEOJSON = os.path.splitext(RAILS_PATH)[0] + "_joined.geojson"
# Optional: write a CSV of the joined attributes (no geometry)
OUT_ATTR_CSV = os.path.splitext(OUT_GEOJSON)[0] + "_attributes.csv"

# ---------- LOAD ----------
rails = gpd.read_file(RAILS_PATH)
demo  = pd.read_csv(DEMO_PATH, low_memory=False)

# ---------- CLEAN / NORMALIZE KEYS ----------
def ensure_numeric_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("Int64")

# Find rails key
rail_key_candidates = ["Objectid", "OBJECTID", "objectid"]
rail_key = next((c for c in rail_key_candidates if c in rails.columns), None)
if rail_key is None:
    raise KeyError(f"Could not find an Objectid column in rails. Columns: {list(rails.columns)}")

# Find demographics key
demo_key_candidates = ["Objectid", "OBJECTID", "objectid", "feature_id", "Feature Id"]
demo_key = next((c for c in demo_key_candidates if c in demo.columns), None)
if demo_key is None:
    raise KeyError(f"Could not find a join key in demographics. Columns: {list(demo.columns)}")

# Coerce to numeric IDs
rails["_join_id"] = ensure_numeric_series(rails[rail_key])
demo["_join_id"]  = ensure_numeric_series(demo[demo_key])

# Quick diagnostics
missing_rail_ids = rails["_join_id"].isna().sum()
missing_demo_ids = demo["_join_id"].isna().sum()
if missing_rail_ids:
    print(f"[warn] {missing_rail_ids} rail rows have non-numeric/blank Objectid.")
if missing_demo_ids:
    print(f"[warn] {missing_demo_ids} demographic rows have non-numeric/blank Objectid/feature_id.")

# ---------- KEEP ALL DEMOGRAPHIC COLUMNS ----------
demo_reduced = demo.copy()
print(f"[info] Keeping ALL {demo_reduced.shape[1]} demographic columns.")

# ---------- JOIN (Left: rails; Right: demographics) ----------
joined = rails.merge(demo_reduced, on="_join_id", how="left")

# ---------- HOUSEKEEPING ----------
# Provide a clean Objectid column in the output for Tableau
joined["Objectid"] = joined["_join_id"]

# Drop helper
joined = joined.drop(columns=["_join_id"])

# If the original rails also had an Objectid/OBJECTID, drop duplicates to avoid confusion
for dup in ["OBJECTID", "objectid", "Objectid_x", "Objectid_y"]:
    if dup in joined.columns and dup != "Objectid":
        joined = joined.drop(columns=[dup])

# ---------- SAVE ----------
# GeoJSON for Tableau (geometry + attributes)
joined.to_file(OUT_GEOJSON, driver="GeoJSON")
print(f"[ok] Wrote: {OUT_GEOJSON}")

# Also write an attributes CSV (optional, no geometry)
geom_col = joined.geometry.name if hasattr(joined, "geometry") else None
attr_df = joined.drop(columns=[geom_col], errors="ignore") if geom_col else joined.copy()
attr_df.to_csv(OUT_ATTR_CSV, index=False)
print(f"[ok] Wrote: {OUT_ATTR_CSV}")
