import pandas as pd

# === File path ===
file_path = r"data/input_file.csv"

# === Load CSV ===
df = pd.read_csv(file_path, dtype=str)   # read as strings to avoid numeric formatting issues

# === Make sure the column exists ===
if "tmc" not in df.columns:
    raise KeyError("❌ The column 'tmc' was not found in the CSV file.")

# === Extract unique values ===
unique_tmcs = (
    df["tmc"]
    .dropna()
    .astype(str)
    .str.strip()
    .unique()
)

# === Sort them numerically/lexicographically ===
unique_tmcs = sorted(unique_tmcs)

# === Print comma-separated list ===
comma_list = ",".join(unique_tmcs)
print("Comma-separated list of all unique tmcs:")
print(comma_list)
