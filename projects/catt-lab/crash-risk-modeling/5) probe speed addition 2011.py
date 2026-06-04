import pandas as pd
from datetime import timedelta

# === File paths ===
# For each year, just change these three paths to that year's crash & speed files + desired output.
crash_file = r"data/input_file.csv"
ref_speed_file = r"data/ref_speed_file.csv"
output_file = r"data/output_file.csv"


# =========================
# 1) LOAD CRASH FILE
# =========================
print("📥 Loading crash file...")
df_crash = pd.read_csv(crash_file, low_memory=False)
print(f"✅ Crash rows: {len(df_crash)}, columns: {len(df_crash.columns)}")

# =========================
# 1A) CLEAN UP SPEED COLUMNS FOR MULTI-YEAR RUNS
# =========================
base_speed_cols = ['speed_before_15m', 'speed_at_crash', 'speed_after_15m']

# Drop any numbered duplicate speed columns from previous runs (e.g., speed_before_15m.1, .2, etc.)
dup_speed_cols = [
    c for c in df_crash.columns
    if any(c.startswith(col + ".") for col in base_speed_cols)
]

if dup_speed_cols:
    print("🧹 Dropping duplicate speed columns:", dup_speed_cols)
    df_crash = df_crash.drop(columns=dup_speed_cols)

# Ensure the base speed columns exist; if not, create them as all-NA
for col in base_speed_cols:
    if col not in df_crash.columns:
        df_crash[col] = pd.NA

# =========================
# 1B) BUILD TRUE CRASH TIMESTAMP (DATE + TIME)
# =========================
if "crashdate" not in df_crash.columns or "timeofcrash" not in df_crash.columns:
    raise KeyError("Expected 'crashdate' and 'timeofcrash' columns in crash file.")

def normalize_time(s):
    """
    Normalize time strings like:
      '11:30', '1130', '930', '9'  → 'HH:MM'
    Returns None if it can't interpret the value.
    """
    if pd.isna(s):
        return None
    s = str(s).strip()

    # Already HH:MM-ish
    if ':' in s:
        return s

    # Strip non-digits
    s_digits = ''.join(ch for ch in s if ch.isdigit())
    if not s_digits:
        return None

    if len(s_digits) <= 2:         # '9' or '09' -> '09:00'
        h = int(s_digits)
        return f"{h:02d}:00"
    elif len(s_digits) == 3:       # '930' -> '09:30'
        h = int(s_digits[:-2])
        m = int(s_digits[-2:])
        return f"{h:02d}:{m:02d}"
    elif len(s_digits) == 4:       # '1130' -> '11:30'
        h = int(s_digits[:2])
        m = int(s_digits[2:])
        return f"{h:02d}:{m:02d}"
    else:
        return None

df_crash["timeofcrash_norm"] = df_crash["timeofcrash"].apply(normalize_time)

df_crash["crash_timestamp"] = pd.to_datetime(
    df_crash["crashdate"].astype(str) + " " + df_crash["timeofcrash_norm"].astype(str),
    errors="coerce"
)

valid_ts = df_crash["crash_timestamp"].notna().sum()
print(f"🕒 Rows with valid crash_timestamp: {valid_ts} / {len(df_crash)}")
print(df_crash[["crashdate", "timeofcrash", "timeofcrash_norm", "crash_timestamp"]]
      .head(10).to_string(index=False))
print()

# =========================
# 1C) NORMALIZE TMC COLUMN TO 'segment_id'
# =========================
if 'segment_id' in df_crash.columns:
    pass
elif 'tmc_right' in df_crash.columns:
    df_crash = df_crash.rename(columns={'tmc_right': 'segment_id'})
elif 'tmc' in df_crash.columns:
    df_crash = df_crash.rename(columns={'tmc': 'segment_id'})
else:
    raise KeyError(
        "Could not find a TMC column in the crash file. "
        "Expected one of: 'segment_id', 'tmc_right', or 'tmc'."
    )

df_crash['segment_id'] = df_crash['segment_id'].astype(str)
print(f"✅ Unique crash TMCs: {df_crash['segment_id'].nunique()}")

# =========================
# 2) ROUND CRASH TIMES & BUILD YEAR-AWARE KEYS
# =========================
def round_down_15(dt):
    if pd.isna(dt):
        return pd.NaT
    return dt - timedelta(
        minutes=dt.minute % 15,
        seconds=dt.second,
        microseconds=dt.microsecond
    )

df_crash['crash_time_rounded'] = df_crash['crash_timestamp'].apply(round_down_15)

df_crash['t_before'] = df_crash['crash_time_rounded'] - timedelta(minutes=15)
df_crash['t_at']     = df_crash['crash_time_rounded']
df_crash['t_after']  = df_crash['crash_time_rounded'] + timedelta(minutes=15)

# Only keep rows with valid crash_timestamp for key building
valid_mask = df_crash['crash_timestamp'].notna()

df_crash.loc[valid_mask, 't_before_key'] = df_crash.loc[valid_mask, 't_before'].dt.strftime('%Y-%m-%d %H:%M')
df_crash.loc[valid_mask, 't_at_key']     = df_crash.loc[valid_mask, 't_at'].dt.strftime('%Y-%m-%d %H:%M')
df_crash.loc[valid_mask, 't_after_key']  = df_crash.loc[valid_mask, 't_after'].dt.strftime('%Y-%m-%d %H:%M')

# Build the set of (segment_id, key) combos we actually need
keys_before = list(zip(df_crash.loc[valid_mask, 'segment_id'], df_crash.loc[valid_mask, 't_before_key']))
keys_at     = list(zip(df_crash.loc[valid_mask, 'segment_id'], df_crash.loc[valid_mask, 't_at_key']))
keys_after  = list(zip(df_crash.loc[valid_mask, 'segment_id'], df_crash.loc[valid_mask, 't_after_key']))

needed_keys = {
    (seg, key)
    for seg, key in keys_before + keys_at + keys_after
    if pd.notna(key)
}

print(f"🎯 Unique (TMC, year+time-bin) combos needed: {len(needed_keys)}")

# Represent keys as "segment_id|key" strings for fast filtering
needed_key_strings = {f"{seg}|{key}" for seg, key in needed_keys}

# =========================
# 3) STREAM THE BIG READINGS FILE IN CHUNKS & KEEP ONLY NEEDED ROWS
# =========================
chunk_size = 500_000  # adjust smaller if memory is still tight
agg_chunks = []

usecols = ['tmc_code', 'measurement_tstamp', 'speed']  # adjust if names differ

print("⏳ Scanning probe readings in chunks and keeping only needed (TMC, year+time-bin)...")

for i, chunk in enumerate(pd.read_csv(ref_speed_file,
                                      usecols=usecols,
                                      chunksize=chunk_size)):
    print(f"  • Chunk {i+1}: raw rows = {len(chunk)}")

    # Rename tmc_code -> segment_id and ensure string type
    chunk = chunk.rename(columns={'tmc_code': 'segment_id'})
    chunk['segment_id'] = chunk['segment_id'].astype(str)

    # Parse timestamp & speed
    chunk['measurement_tstamp'] = pd.to_datetime(chunk['measurement_tstamp'],
                                                 errors='coerce')
    chunk['speed'] = pd.to_numeric(chunk['speed'], errors='coerce')

    # Drop rows with missing essentials
    chunk = chunk.dropna(subset=['measurement_tstamp', 'speed'])

    # Build year-aware time key aligned with crash keys
    chunk['time_key'] = chunk['measurement_tstamp'].dt.strftime('%Y-%m-%d %H:%M')

    # Combined segment + time key
    chunk['seg_time_key'] = chunk['segment_id'] + "|" + chunk['time_key']

    # Keep only rows whose (segment_id, time_key) we actually need
    chunk = chunk[chunk['seg_time_key'].isin(needed_key_strings)]

    print(f"    ↳ kept rows matching crash TMC/year+time bins: {len(chunk)}")

    if chunk.empty:
        continue

    # Aggregate mean speed for this reduced chunk
    chunk_agg = (
        chunk.groupby(['segment_id', 'time_key'], as_index=False)
             .agg({'speed': 'mean'})
    )
    agg_chunks.append(chunk_agg)

# =========================
# 4) BUILD MASTER SPEED TABLE & MERGE
# =========================
if not agg_chunks:
    print("⚠️ No matching probe data found for any crash TMC/year+time bins.")
    # Still save crash file with empty speed columns so script completes cleanly
    df_crash['speed_data_available'] = False
    df_crash.to_csv(output_file, index=False)
    print(f"📝 Output (with empty speed columns) saved to: {output_file}")
else:
    # Combine all chunk-level aggregations and aggregate again
    speed_key = pd.concat(agg_chunks, ignore_index=True)
    speed_key = (
        speed_key.groupby(['segment_id', 'time_key'], as_index=False)
                 .agg({'speed': 'mean'})
    )

    print(f"✅ Final speed_key rows (TMC, year+time-bin): {len(speed_key)}")

    def merge_speed(df, time_key_col, out_col):
        """
        Merge speed_key into df on (segment_id, time_key) and
        fill/append into the existing out_col without creating duplicate columns.
        """
        merged = df.merge(
            speed_key,  # ['segment_id','time_key','speed']
            left_on=['segment_id', time_key_col],
            right_on=['segment_id', 'time_key'],
            how='left'
        ).drop(columns=['time_key'])

        # Put new speeds in a temporary column
        tmp_col = f"{out_col}_new"
        merged = merged.rename(columns={'speed': tmp_col})

        # If out_col already exists, keep existing values and only fill NaNs with new ones
        if out_col in merged.columns:
            merged[out_col] = merged[out_col].combine_first(merged[tmp_col])
            merged = merged.drop(columns=[tmp_col])
        else:
            # First-time creation: rename temp to out_col
            merged = merged.rename(columns={tmp_col: out_col})

        return merged

    # Merge in speeds, filling existing blanks only
    df_crash = merge_speed(df_crash, 't_before_key', 'speed_before_15m')
    df_crash = merge_speed(df_crash, 't_at_key',     'speed_at_crash')
    df_crash = merge_speed(df_crash, 't_after_key',  'speed_after_15m')

    # Flag rows where any speed value exists
    df_crash['speed_data_available'] = df_crash[
        ['speed_before_15m', 'speed_at_crash', 'speed_after_15m']
    ].notna().any(axis=1)

    # =========================
    # 5) SAVE RESULT
    # =========================
    df_crash.to_csv(output_file, index=False)
    print("🎉 Probe speed conflation (year + month/day/time, targeted) complete.")
    print(f"   Output: {output_file}")
    print("   Crashes with any speed data:",
          int(df_crash['speed_data_available'].sum()),
          "of", len(df_crash))
