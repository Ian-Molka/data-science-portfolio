#!/usr/bin/env python3
"""
CMV BASIC FLAG – ALL CRASHES (no VMT, no parking zones)

- Builds a simple CMV flag from vehicle body/make fields
- Keeps ALL crashes
- No spatial operations
- No VMT merge

Author: Ian Molka / CATT Lab
Last Updated: 2025-11-14
"""

from pathlib import Path
import pandas as pd

# ==============================
# CONFIG
# ==============================
CRASH_CSV = Path(
    r"data/input_file.csv"
)

OUTPUT_CSV = Path(
    r"data/output_file.csv"
)

# ==============================
# CMV Flag Helper
# ==============================
def _build_cmv_flag(df: pd.DataFrame) -> pd.Series:
    """
    Simple CMV heuristic based on body/make keywords:
    Flags likely CMVs using:
      TRUCK, TRACTOR, SEMI, BUS, CMV, BOX, DUMP
    """
    candidate_cols = [
        c
        for c in df.columns
        if c.lower()
        in {
            "body_type",
            "vehicle_body_type",
            "make",
            "vehicle_make",
            "vehicle_body_description",
        }
    ]

    # no usable columns → return zeros
    if not candidate_cols:
        return pd.Series(0, index=df.index, dtype="int64")

    patterns = ("TRUCK", "TRACTOR", "SEMI", "BUS", "CMV", "BOX", "DUMP")
    s = pd.Series(0, index=df.index, dtype="int64")

    for col in candidate_cols:
        vals = df[col].astype(str).str.upper()
        s = s | vals.str.contains("|".join(patterns), regex=True, na=False)

    return s.astype(int)


# ==============================
# MAIN
# ==============================
def main():
    print("[1/2] Reading crashes …")
    df = pd.read_csv(CRASH_CSV, low_memory=False)

    print("[2/2] Building cmv_involved flag …")
    df["cmv_involved"] = _build_cmv_flag(df)

    df.to_csv(OUTPUT_CSV, index=False)

    print(f"\n✅ Saved {len(df):,} crashes with cmv_involved flag:\n{OUTPUT_CSV}")

    print("\n📊 cmv_involved breakdown:")
    print(
        df["cmv_involved"]
        .value_counts()
        .rename(index={0: "0 (non-CMV)", 1: "1 (likely CMV)"})
    )


if __name__ == "__main__":
    main()
