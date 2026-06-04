import pandas as pd
from pathlib import Path

# === File paths ===
crash_file  = r"data/\crashes_with_nearest_tmc.csv"
vmt_file    = r"data/segment_vmt_totals.csv"
output_file = r"data/crash_with_vmt_conflated.csv"

# === Weather code → description mapping (from your screenshot)
WEATHER_CODE_MAP = {
    "00":   "N/A",
    "02":   "FOGGY",
    "03":   "RAINING",
    "05":   "SEVERE WINDS",
    "06.01":"CLEAR",
    "07.01":"CLOUDY",
    "08.04":"SNOW",
    "09.04":"SLEET",
    "10.04":"BLOWING SNOW",
    "11.88":"BLOWING SAND, SOIL, DIRT",
    "12.04":"WINTRY MIX",
    "88":   "OTHER",
    "99":   "UNKNOWN",
}

# Possible weather code column names in crash file
POSSIBLE_WEATHER_CODE_COLS = ["weather_code", "weather_condition", "weather_cond", "weather"]

# Possible crash-side TMC/segment key columns
POSSIBLE_TMC_COLS = [
    "segment_id",
    "tmc_right",
    "tmc_left",
    "tmc",
    "tmc_code",
    "nearest_tmc",
    "matched_tmc",
]

def canonicalize_code(x):
    """
    Robustly normalize codes so they match the mapping keys:
    - Integers are zero-padded to 2 digits (e.g., 2 -> '02')
    - Decimal codes are zero-padded on the left side (e.g., '6.01' -> '06.01')
    - Strings like '02', '06.01' are preserved
    """
    if pd.isna(x):
        return None
    s = str(x).strip()
    if s == "":
        return None
    # drop trailing .0 for int-like values read as floats
    if s.endswith(".0"):
        s = s[:-2]
    if "." in s:
        left, right = s.split(".", 1)
        left = left.zfill(2)
        s = f"{left}.{right}"
    else:
        s = s.lstrip("0") or "0"
        s = s.zfill(2)
    return s

# === Load datasets ===
df_crash = pd.read_csv(crash_file, low_memory=False)
df_vmt   = pd.read_csv(vmt_file, low_memory=False)

# === Weather mapping (if we find a weather column) ===
weather_col = next((c for c in POSSIBLE_WEATHER_CODE_COLS if c in df_crash.columns), None)
if weather_col is not None:
    canon_col = f"{weather_col}_canon"
    df_crash[canon_col] = df_crash[weather_col].apply(canonicalize_code)
    df_crash["weather_description"] = df_crash[canon_col].map(WEATHER_CODE_MAP)
else:
    canon_col = None
    print("⚠️  No weather code column found; skipped code→description mapping.")

# === Detect crash-side segment/TMC key and normalize to 'segment_id' ===
crash_tmc_col = next((c for c in POSSIBLE_TMC_COLS if c in df_crash.columns), None)

if crash_tmc_col is None:
    raise KeyError(
        "❌ Could not find any TMC/segment column in crash file.\n"
        f"Tried: {POSSIBLE_TMC_COLS}\n"
        f"Available columns: {list(df_crash.columns)}"
    )

if crash_tmc_col != "segment_id":
    print(f"🔑 Using crash column '{crash_tmc_col}' as segment key → renaming to 'segment_id'")
    df_crash = df_crash.rename(columns={crash_tmc_col: "segment_id"})
else:
    print("🔑 Using existing 'segment_id' column in crash file as merge key")

# === Ensure VMT table has a matching key ===
if "segment_id" not in df_vmt.columns:
    # You can extend this logic if your VMT file ever uses a different name
    raise KeyError(
        "❌ VMT file must contain 'segment_id' column for merging.\n"
        f"VMT columns: {list(df_vmt.columns)}"
    )

# === Merge on segment_id ===
merged = pd.merge(
    df_crash,
    df_vmt,
    how='left',
    on='segment_id'
)

# === Drop exact duplicates ===
merged = merged.drop_duplicates()

# === Export to CSV ===
Path(output_file).parent.mkdir(parents=True, exist_ok=True)
merged.to_csv(output_file, index=False)
print(f"✅ Merged data saved to: {output_file}")
print(f"🧼 Rows after duplicate removal: {len(merged)}")

# Quick report on weather mapping coverage (only if we found a weather column)
if weather_col is not None and canon_col is not None:
    total_nonnull = merged[canon_col].notna().sum()
    mapped = merged["weather_description"].notna().sum()
    pct = (mapped / total_nonnull * 100) if total_nonnull else 0
    print(f"🗺️  Weather mapping: {mapped:,}/{total_nonnull:,} non-null codes mapped ({pct:.1f}%).")

print(merged.head(20))            # Shows first 20 rows
print(merged[['segment_id','VMT']].head(20))  # Show only key columns
