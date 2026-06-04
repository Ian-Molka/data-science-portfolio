import pandas as pd
import re
import unicodedata

# === Settings ===
INPUT_FILE  = r"data/input_file.csv"
OUTPUT_FILE = r"data/output_file.csv"

RAIL_COL = "Railroad"                    # or "Station"
RACE_COL = "Race and/or Ethnicity"
DATE_COL = "Incident Date_x"
MIN_YEAR = 2019
DROP_UNPARSABLE_DATES = True

# === Canonical mapping for Railroad/Station ===
canon_raw = {
    "amtrak (atk)": "Amtrak",
    "bnsf": "BNSF Railway",
    "bnsf railway (bnsf)": "BNSF Railway",
    "bn": "BNSF Railway",
    "csx": "CSX Transportation",
    "csx transportation (csx)": "CSX Transportation",
    "cs": "CSX Transportation",
    "csx/septa": "CSX Transportation",
    "csx transportation (csx)/fec": "CSX Transportation",
    "florida east cost railroad": "Florida East Coast Railway (FEC)",
    "florida east coast railroad": "Florida East Coast Railway (FEC)",
    "i’m florida east coast railroad": "Florida East Coast Railway (FEC)",
    "florida east coast railway (fec)": "Florida East Coast Railway (FEC)",
    "florida east coast railroad/brightline": "Florida East Coast Railway (FEC)",
    "fec/brightline": "Florida East Coast Railway (FEC)",
    "fec / brightline": "Florida East Coast Railway (FEC)",
    "florida east coast railroad/csx": "Florida East Coast Railway (FEC)",
    "brightline": "Brightline",
    "mbta": "MBTA",
    "mbta fitchburg": "MBTA",
    "montana rail link": "Montana Rail Link",
    "metrolink": "Metrolink",
    "norfolk southern (ns)": "Norfolk Southern",
    "providence & worcester railroad": "Providence & Worcester Railroad",
    "providence worcester ral road": "Providence & Worcester Railroad",
    "sjvr": "San Joaquin Valley Railroad (SJVR)",
    "san joaquin valley railroad": "San Joaquin Valley Railroad (SJVR)",
    "san joaquin railroad": "San Joaquin Valley Railroad (SJVR)",
    "san joaquin railway": "San Joaquin Valley Railroad (SJVR)",
    "san bernardino county": "San Bernardino County Transportation",
    "san bernardino county transporta": "San Bernardino County Transportation",
    "san bernardino county transportation": "San Bernardino County Transportation",
    "tri-rail": "Tri-Rail (SFRTA)",
    "tri rail": "Tri-Rail (SFRTA)",
    "trirail": "Tri-Rail (SFRTA)",
    "tri-rail/brightline": "Tri-Rail (SFRTA)",
    "south florida region railroad": "South Florida Region Railroad/CSX",
    "southern pacific": "Southern Pacific",
    "southern pacific co": "Southern Pacific",
    "southern pacific railroad": "Southern Pacific",
    "southern pacific railroad company": "Southern Pacific",
    "south pacific": "Southern Pacific",
    "south pacific railroad": "Southern Pacific",
    "stillwater central": "Stillwater Central Railroad",
    "still central": "Stillwater Central Railroad",
    "union pacific": "Union Pacific",
    "union pacific (up)": "Union Pacific",
    "up": "Union Pacific",
}

# === Helpers ===
def normalize_text(x: str) -> str:
    x = str(x)
    x = unicodedata.normalize("NFKC", x)
    x = x.strip()
    x = re.sub(r"\s+", " ", x)
    x = re.sub(r"\s*/\s*", "/", x)
    return x

def to_key(x: str) -> str:
    return normalize_text(x).lower()

canon = {to_key(k): v for k, v in canon_raw.items()}

# === Load ===
df = pd.read_csv(INPUT_FILE)

# Use alternate rail column if needed
if RAIL_COL not in df.columns:
    alt = "Station" if RAIL_COL == "Railroad" else "Railroad"
    if alt in df.columns:
        RAIL_COL = alt
    else:
        raise ValueError(f"Neither '{RAIL_COL}' nor '{alt}' found. Available: {list(df.columns)}")

# === Overwrite rail column in place ===
src = df[RAIL_COL].astype(str).fillna("").map(normalize_text)
df[RAIL_COL] = src.map(lambda v: canon.get(to_key(v), v))

# Clean up any helper columns if present
for c in [f"{RAIL_COL}_canonical", f"{RAIL_COL}_original", "primary_rr", "secondary_rr"]:
    if c in df.columns:
        df.drop(columns=c, inplace=True)

# === Date cleaning (preserve time) ===
if DATE_COL in df.columns:
    parsed = pd.to_datetime(df[DATE_COL], errors="coerce", infer_datetime_format=True)
    keep_mask = parsed.dt.year >= MIN_YEAR
    if DROP_UNPARSABLE_DATES:
        df = df[keep_mask.fillna(False)].copy()
        # recompute parsed for the filtered frame and assign back (keeps time)
        parsed = pd.to_datetime(df[DATE_COL], errors="coerce", infer_datetime_format=True)
        df[DATE_COL] = parsed
    else:
        df = df[keep_mask | parsed.isna()].copy()
        parsed = pd.to_datetime(df[DATE_COL], errors="coerce", infer_datetime_format=True)
        df[DATE_COL] = parsed
else:
    print(f"⚠️ Date column '{DATE_COL}' not found — skipping date cleaning.")

# === Race/Ethnicity: keep only three columns ===
if RACE_COL in df.columns:
    df["Race and/or Ethnicity_original"] = df[RACE_COL]
    s = df[RACE_COL].fillna("").astype(str)
    parts = s.str.split(",", n=1)
    df["Race and/or Ethnicity_primary"] = parts.str[0].str.strip()
    df["Race and/or Ethnicity_secondary"] = parts.str[1].fillna("").str.strip()
    df.drop(columns=[RACE_COL], inplace=True)
else:
    print(f"⚠️ Column '{RACE_COL}' not found — skipping Race/Ethnicity split.")

# === Export (format datetime with time) ===
df.to_csv(OUTPUT_FILE, index=False, date_format="%Y-%m-%d %H:%M:%S")
print(f"✅ Saved cleaned file (time preserved in '{DATE_COL}'):\n{OUTPUT_FILE}")
