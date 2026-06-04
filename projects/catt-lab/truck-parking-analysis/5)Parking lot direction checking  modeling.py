import pandas as pd
import re
import csv

# === File Paths ===
file_path = r"data/input_file.csv"
output_path = r"data/input_file.csv"

# === Load dataset ===
df = pd.read_csv(file_path, encoding="utf-8")

# === Clean OBJECTID if needed
if 'OBJECTID' in df.columns:
    df['OBJECTID'] = df['OBJECTID'].apply(lambda x: int(float(x)) if pd.notnull(x) else None)

# === Direction abbreviation map
direction_map = {
    'N': ['NORTHBOUND', 'NORTH', 'NB', 'N/B', 'N'],
    'S': ['SOUTHBOUND', 'SOUTH', 'SB', 'S/B', 'S'],
    'E': ['EASTBOUND', 'EAST', 'EB', 'E/B', 'E'],
    'W': ['WESTBOUND', 'WEST', 'WB', 'W/B', 'W']
}
term_to_abbr = {}
for abbr, terms in direction_map.items():
    for term in terms:
        clean = term.replace('/', '').replace('-', '').replace(' ', '').upper()
        term_to_abbr[clean] = abbr

# === Normalize polygon direction to set
def normalize_direction_set(text):
    if not isinstance(text, str):
        return set()
    parts = re.split(r'[/\s\-]+', text.upper())
    return {term_to_abbr.get(part.strip(), None) for part in parts if term_to_abbr.get(part.strip(), None)}

# === Normalize crash direction to single abbreviation
def normalize_direction(text):
    if not isinstance(text, str):
        return None
    clean_text = text.upper().replace('/', '').replace('-', '').replace(' ', '').strip()
    if clean_text == 'U':
        return None
    return term_to_abbr.get(clean_text, None)

# === Normalize direction columns (for all rows, used selectively later)
df['Direction_norm'] = df['Direction'].apply(normalize_direction_set)
crash_fields = ['milepointdirection', 'lanedirection', 'logmile_dir', 'goingdirection']
for col in crash_fields:
    df[f'{col}_norm'] = df[col].apply(normalize_direction)

# === Subset: only analyze direction match for 50m matched and not parking lot
if 'match_50m' in df.columns:
    df_match = df[(df['match_50m'] == 'matched')].copy()
    print(f"🔍 Performing direction analysis on: {len(df_match)} matched rows")
else:
    df_match = df.copy()
    print("⚠️ 'match_50m' column missing. Performing direction analysis on all rows.")

# === Exclude rows where nearest_zone == parking lot
df_match['is_parking_lot'] = df_match['nearest_zone'].str.lower().fillna('') == 'parking lot'
df_match = df_match[~df_match['is_parking_lot']].copy()
print(f"🚫 Excluded parking lot rows. Final direction match set: {len(df_match)} rows")

# === Compare directions
def compare_dirs(crash_val, polygon_set):
    if pd.isna(crash_val) or not polygon_set:
        return 'unknown'
    return 'match' if crash_val in polygon_set else 'mismatch'

for col in crash_fields:
    df_match[f'{col}_to_poly_match'] = df_match.apply(
        lambda row: compare_dirs(row[f'{col}_norm'], row['Direction_norm']), axis=1
    )
    print(f"\n📊 {col} direction match summary:")
    print(df_match[f'{col}_to_poly_match'].value_counts())

# === Step 1: Majority match rule
def majority_direction_match_to_poly(row):
    match_cols = [row[f'{col}_to_poly_match'] == 'match' for col in crash_fields]
    match_count = sum(match_cols)
    unknown_count = sum([row[f'{col}_to_poly_match'] == 'unknown' for col in crash_fields])
    if match_count >= 3:
        return 'match'
    elif match_count == 2 and row['lanedirection_to_poly_match'] == 'match':
        return 'match'
    elif unknown_count == 4:
        return 'unknown'
    else:
        return 'mismatch'

df_match['direction_match_majority_to_poly'] = df_match.apply(majority_direction_match_to_poly, axis=1)
print("\n📊 Step 1: Majority match result:")
print(df_match['direction_match_majority_to_poly'].value_counts())

# === Step 2: Any-match override
def any_direction_match(row):
    return any(row[f'{col}_to_poly_match'] == 'match' for col in crash_fields)

override_mask = df_match['direction_match_majority_to_poly'] == 'mismatch'
df_match.loc[override_mask, 'direction_match_majority_to_poly'] = df_match.loc[override_mask].apply(
    lambda row: 'match' if any_direction_match(row) else 'mismatch',
    axis=1
)

print("\n✅ Step 2: Any-match override applied")
print(df_match['direction_match_majority_to_poly'].value_counts())

# === Merge results back to full dataset
merge_cols = ['vehicleid', 'direction_match_majority_to_poly'] + [f'{col}_to_poly_match' for col in crash_fields]
df = df.merge(df_match[merge_cols], on='vehicleid', how='left')

# === Move narrative to end if exists
if 'narrative' in df.columns:
    narrative_col = df.pop('narrative')
    df['narrative'] = narrative_col

# === Export CSV with clean headers (no quotes in Tableau)
df.to_csv(
    output_path,
    index=False,
    quoting=csv.QUOTE_NONNUMERIC,  # Quote only string values, not headers
    quotechar='"',
    encoding='utf-8',
    lineterminator='\n'
)

print(f"\n💾 Final CSV saved with clean headers: {output_path}")
