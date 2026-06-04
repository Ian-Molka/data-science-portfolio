import pandas as pd
from pathlib import Path

# === INPUT / OUTPUT ===
INPUT_FILE  = r"data/input_file.csv"
OUTPUT_FILE = r"data/output_file.csv"

def main():
    print(f"📂 Loading: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)

    if "cmv_inferred" not in df.columns:
        raise KeyError("❌ Column 'cmv_inferred' not found in the dataset.")

    # === FILTER CMV CRASHES ===
    df_cmv = df[df["cmv_inferred"] == True].copy()
    print(f"🚛 CMV crashes found: {len(df_cmv):,}")

    # === EXPORT ===
    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    df_cmv.to_csv(OUTPUT_FILE, index=False)

    print(f"💾 Saved CMV-only dataset to:\n{OUTPUT_FILE}")
    print(f"📊 Output shape: {df_cmv.shape[0]:,} rows × {df_cmv.shape[1]:,} columns")

if __name__ == "__main__":
    main()
