import pandas as pd

# === File paths ===
file1 = r"data/input_file.csv"     
file2 = r"data/input_file.csv"    
output_file = r"data/output_file.csv"
# === Load the files ===
# Automatically detect if CSV or Excel
def load_file(path):
    if path.lower().endswith(".csv"):
        return pd.read_csv(path)
    elif path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported file type: {path}")

df1 = load_file(file1)
df2 = load_file(file2)

print(f"✅ Loaded {len(df1)} rows from file1")
print(f"✅ Loaded {len(df2)} rows from file2")

# === Ensure Report ID exists in both files ===
if 'Report ID' not in df1.columns:
    raise KeyError("'Report ID' column not found in first file")
if 'Report ID' not in df2.columns:
    raise KeyError("'Report ID' column not found in second file")

# === Merge the files ===
# inner join = keep only matching Report ID values
merged_df = pd.merge(df1, df2, on='Report ID', how='inner')

print(f"🔍 Merged file has {len(merged_df)} rows (matching Report ID)")

# === Save the result ===
merged_df.to_csv(output_file, index=False)
print(f"💾 Output saved to: {output_file}")
