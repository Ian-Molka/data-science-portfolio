import pandas as pd
from pathlib import Path

# === File paths ===
crash_file  = r"data/crashes_with_nearest_tmc.csv"
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

# Column in crashes that holds the weather code.
# The script will auto-detect between these common names.
POSSIBLE_WEATHER_CODE_COLS = ["weather_code", "weather_condition", "weather_cond", "weather"]

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
        # keep right side as-is (e.g., '01', '04', '88')
        s = f"{left}.{right}"
    else:
        # pure integer-like; strip leading zeros then pad to 2
        s = s.lstrip("0") or "0"
        s = s.zfill(2)
    return s

# === Load datasets ===
df_crash = pd.read_csv(crash_file)
df_vmt   = pd.read_csv(vmt_file)

# === Find the weather code column (if present) and map to description
weather_col = next((c for c in POSSIBLE_WEATHER_CODE_COLS if c in df_crash.columns), None)
if weather_col is not None:
    # Make a canonical code column for clean joins/mapping
    canon_col = f"{weather_col}_canon"
    df_crash[canon_col] = df_crash[weather_col].apply(canonicalize_code)
    df_crash["weather_description"] = df_crash[canon_col].map(WEATHER_CODE_MAP)
    # Optional sanity check:
    # print(df_crash[[weather_col, canon_col, "weather_description"]].head(20))
else:
    print("⚠️  No weather code column found; skipped code→description mapping.")

# === Rename crash column for merging
if 'tmc_right' in df_crash.columns:
    df_crash = df_crash.rename(columns={'tmc_right': 'segment_id'})
else:
    raise KeyError("❌ 'tmc_right' column not found in crash file.")

# === Merge on segment_id
merged = pd.merge(
    df_crash,
    df_vmt,
    how='left',
    on='segment_id'
)

# === Drop exact duplicates
merged = merged.drop_duplicates()

# === Export to CSV
Path(output_file).parent.mkdir(parents=True, exist_ok=True)
merged.to_csv(output_file, index=False)
print(f"✅ Merged data saved to: {output_file}")
print(f"🧼 Rows after duplicate removal: {len(merged)}")

# Quick report on mapping coverage (only if we found a weather column)
if weather_col is not None:
    total_nonnull = merged[canon_col].notna().sum()
    mapped = merged["weather_description"].notna().sum()
    print(f"🗺️  Weather mapping: {mapped:,}/{total_nonnull:,} non-null codes mapped "
          f"({(mapped/total_nonnull*100 if total_nonnull else 0):.1f}%).")
