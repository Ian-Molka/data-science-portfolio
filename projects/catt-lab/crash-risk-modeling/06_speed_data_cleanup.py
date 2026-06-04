import pandas as pd
from pathlib import Path
import re

# === INPUT / OUTPUT FILES ===
INPUT_FILE  = r"data/input_file.csv"
OUTPUT_FILE = r"data/output_file.csv"

# === Base speed column names you care about ===
BASE_COLS = ["speed_before_15m", "speed_at_crash", "speed_after_15m"]

def parse_suffix(col_name, base):
    """
    Given a column name like 'speed_at_crash.2' and base 'speed_at_crash',
    return the numeric suffix as an int.
    - Return 0 if it is the base column (no suffix).
    - Return None if it doesn't belong to this base.
    """
    if col_name == base:
        return 0
    pattern = re.escape(base) + r'\.(\d+)$'
    m = re.match(pattern, col_name)
    if m:
        return int(m.group(1))
    return None

def main():
    print(f"📂 Loading: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"✅ Loaded dataframe with {df.shape[0]:,} rows and {df.shape[1]:,} columns")

    all_cols_to_drop = []

    for base in BASE_COLS:
        # Find all related columns: base, base.1, base.2, ...
        related_cols = []
        for c in df.columns:
            suffix = parse_suffix(c, base)
            if suffix is not None:
                related_cols.append((c, suffix))

        if not related_cols:
            print(f"\n⚠️ No columns found for base '{base}'. Skipping.")
            continue

        # Sort by suffix descending so we prioritize the "latest" (e.g., .2 over .1 over base)
        related_cols_sorted = sorted(related_cols, key=lambda x: x[1], reverse=True)
        col_order = [c for c, s in related_cols_sorted]

        print(f"\n=== Processing '{base}' ===")
        print(f"  Found related columns (priority order): {col_order}")

        # Ensure base column exists. If not, create it as all NaN.
        if base not in df.columns:
            df[base] = pd.NA

        # Conflate values into base: for each row, take first non-null in priority order
        # (highest suffix first, then fall back)
        base_series = df[base].copy()

        for col in col_order:
            # Skip the base column itself in the loop (we'll overwrite it at the end anyway)
            if col == base:
                continue

            # Use values from this column where base is NaN and this column is not NaN
            mask = base_series.isna() & df[col].notna()
            if mask.any():
                base_series.loc[mask] = df.loc[mask, col]

        # Finally, also allow base itself to keep any values it already had
        df[base] = base_series

        # Mark extra columns (.1, .2, etc.) to be dropped
        extras = [c for c in col_order if c != base]
        all_cols_to_drop.extend(extras)
        print(f"  Will drop extra columns: {extras if extras else 'None'}")

    # Drop all extra columns after processing all bases
    all_cols_to_drop = list(dict.fromkeys(all_cols_to_drop))  # de-duplicate
    if all_cols_to_drop:
        df = df.drop(columns=[c for c in all_cols_to_drop if c in df.columns])
        print(f"\n🧹 Dropped {len(all_cols_to_drop)} extra speed columns: {all_cols_to_drop}")
    else:
        print("\nℹ️ No extra speed columns found to drop.")

    # Save cleaned file
    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\n💾 Cleaned file saved to:\n{OUTPUT_FILE}")
    print(f"📏 Final shape: {df.shape[0]:,} rows × {df.shape[1]:,} columns")

if __name__ == "__main__":
    main()
