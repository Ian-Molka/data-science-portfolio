import pandas as pd
import json
from pathlib import Path

# =========================
# File paths (edit if needed)
# =========================
CSV_FILE = r"data/input_file.csv"    # your incidents CSV
GEOJSON_FILE = r"data/NARN_Rail_Lines.geojson"        # the rail lines GeoJSON

OUTPUT_FILE  = r"data/NARN_Rail_Lines export.geojson"  # output GeoJSON with counts
# =========================
# 1) Load incidents CSV and build counts by rail_OBJECTID
# =========================
df = pd.read_csv(CSV_FILE)

if "rail_OBJECTID" not in df.columns:
    raise ValueError("The CSV is missing the 'rail_OBJECTID' column.")

# Normalize to integers (nullable)
df["rail_OBJECTID_clean"] = pd.to_numeric(df["rail_OBJECTID"], errors="coerce").astype("Int64")

# Count incidents per rail id (exclude NaNs from counting)
counts_series = (
    df[df["rail_OBJECTID_clean"].notna()]
      .groupby("rail_OBJECTID_clean")
      .size()
)

# Convert to a plain dict with int keys for fast lookup
incident_counts = {int(k): int(v) for k, v in counts_series.to_dict().items()}

# =========================
# 2) Load GeoJSON and add 'incident_count' to each feature
# =========================
with open(GEOJSON_FILE, "r") as f:
    gj = json.load(f)

# Sanity check
if "features" not in gj or not isinstance(gj["features"], list):
    raise ValueError("Invalid GeoJSON: no 'features' array found.")

added, missing_ids = 0, 0

for feat in gj["features"]:
    props = feat.get("properties", {})
    obj_raw = props.get("OBJECTID", None)

    # Normalize OBJECTID to int if possible
    try:
        obj_id = int(obj_raw) if obj_raw is not None else None
    except (ValueError, TypeError):
        obj_id = None

    # Lookup count; default 0 if no incidents found or invalid id
    count = incident_counts.get(obj_id, 0) if obj_id is not None else 0

    # Add/overwrite count on properties
    props["incident_count"] = int(count)
    feat["properties"] = props
    added += 1
    if obj_id is None:
        missing_ids += 1

# =========================
# 3) Write new GeoJSON (all original fields + incident_count)
# =========================
Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
with open(OUTPUT_FILE, "w") as f:
    json.dump(gj, f)

print(f"✅ Wrote GeoJSON with counts: {OUTPUT_FILE}")
print(f"Features updated: {added} | Features with missing/non-integer OBJECTID: {missing_ids}")
print(f"Unique rail ids with incidents in CSV: {len(incident_counts)}")
