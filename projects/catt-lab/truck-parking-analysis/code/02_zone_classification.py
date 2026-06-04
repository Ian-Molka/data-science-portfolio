import geopandas as gpd
import pandas as pd
# === File Paths ===
input_file = r"data/input_file.geojson"
output_file = r"data/output_file.geojson"

# === Load GeoJSON ===
gdf = gpd.read_file(input_file)
print(f"✅ Loaded GeoJSON with {len(gdf)} features")

gdf['OBJECTID'] = gdf['OBJECTID'].apply(lambda x: int(str(x).lstrip('0')) if pd.notnull(x) else None)

# === Clean and Normalize Parking Lot column
gdf['Parking Lot'] = gdf['Parking Lot'].astype(str).str.strip()

# === Function to assign Zone based on Parking Lot value
def assign_zone(parking_lot):
    if not parking_lot.isdigit():
        return None
    if len(parking_lot) <= 3:
        return "Parking Lot"
    elif len(parking_lot) == 5:
        last_digit = parking_lot[-1]
        if last_digit == '1':
            return "Upstream"
        elif last_digit == '2':
            return "Upstream: Off-Ramp"
        elif last_digit == '3':
            return "Downstream: On-Ramp"
        elif last_digit == '4':
            return "Downstream"
    return None  # fallback if doesn't meet criteria

# === Assign zones
gdf['Zone'] = gdf['Parking Lot'].apply(assign_zone)

# === Summary
zone_counts = gdf['Zone'].value_counts(dropna=False)
print("\n📊 Zone Assignment Summary:")
print(zone_counts)

# === Save output
gdf.to_file(output_file, driver="GeoJSON")
print(f"\n💾 Saved updated GeoJSON to: {output_file}")
