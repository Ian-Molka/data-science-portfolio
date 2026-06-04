import geopandas as gpd
import pandas as pd

# === File Paths ===
input_file = r"data/input_file.geojson"
output_file = r"data/output_file.geojson"
unmatched_output_file = r"data/unmatched_polygons.geojson"

# === Load GeoJSON
gdf = gpd.read_file(input_file)
print("✅ Loaded GeoJSON")

# === Separate by geometry type
gdf_points = gdf[gdf.geometry.type == 'Point'].copy()
gdf_polygons = gdf[gdf.geometry.type == 'Polygon'].copy()
print(f"📍 Points: {len(gdf_points)} | 🟦 Polygons: {len(gdf_polygons)}")

# === Normalize OBJECTID in points (remove leading zeros)
gdf_points['OBJECTID'] = gdf_points['OBJECTID'].apply(
    lambda x: int(str(x).strip().lstrip('0')) if pd.notnull(x) else None
)

# === Normalize Parking Lot in polygons
gdf_polygons['Parking Lot'] = gdf_polygons['Parking Lot'].astype(str).str.strip()

# === Extract match_id from Parking Lot
def extract_match_id(parking_lot_str):
    if isinstance(parking_lot_str, str) and parking_lot_str.isdigit():
        if len(parking_lot_str) == 5:
            middle_three = parking_lot_str[1:4]
            return str(int(middle_three)) if int(middle_three) < 100 else middle_three
        elif len(parking_lot_str) <= 3:
            return str(int(parking_lot_str))
    return None

gdf_polygons['match_id'] = gdf_polygons['Parking Lot'].apply(extract_match_id)

# === Deduplicate points and prep attributes
gdf_points_unique = gdf_points.drop_duplicates(subset='OBJECTID').copy()
gdf_points_unique = gdf_points_unique.rename(columns={'OBJECTID': 'match_id'})
point_attrs = gdf_points_unique.drop(columns='geometry').copy()
point_attrs = point_attrs.add_suffix('_pt')
point_attrs.rename(columns={'match_id_pt': 'match_id'}, inplace=True)

# === Ensure both match_id columns are string type before merge
gdf_polygons['match_id'] = gdf_polygons['match_id'].astype(str)
point_attrs['match_id'] = point_attrs['match_id'].astype(str)

# === Merge point data into original polygon table (preserve full list)
gdf_polygons_enriched = gdf_polygons.merge(point_attrs, on='match_id', how='left')

# === Propagate key fields across polygons sharing same Parking Lot
fields_to_propagate = ['Direction_pt', 'Direction', 'Zone_pt', 'NAME_pt']
gdf_polygons_enriched[fields_to_propagate] = (
    gdf_polygons_enriched
    .groupby('Parking Lot')[fields_to_propagate]
    .transform(lambda x: x.ffill().bfill())
)

# === Fill OBJECTID from Parking Lot using same logic
gdf_polygons_enriched['OBJECTID'] = gdf_polygons_enriched['Parking Lot'].apply(extract_match_id)

# === Stats
total_polygons = len(gdf_polygons_enriched)
enriched_count = gdf_polygons_enriched['NAME_pt'].notna().sum()
missing_count = total_polygons - enriched_count
unique_ids = gdf_polygons_enriched['match_id'].nunique()
fields_added = gdf_polygons_enriched.filter(like='_pt').columns.tolist()

# === Identify and export unmatched polygons
unmatched = gdf_polygons_enriched[gdf_polygons_enriched['NAME_pt'].isna()].copy()

# === Output summary
print("\n✅ Enrichment complete. Saved to", output_file)
print(f"Enriched polygons: {enriched_count}")
print(f"Unmatched polygons: {missing_count}")
print(f"Unique match_ids in polygons: {unique_ids}")
print(f"Enriched fields copied: {fields_added}")
print("\n🔍 Top unmatched Parking Lot IDs:")
print(unmatched['Parking Lot'].value_counts(dropna=False).head(10))

# === Save unmatched
unmatched.to_file(unmatched_output_file, driver="GeoJSON")
print("🗂️ Unmatched polygons exported to:", unmatched_output_file)

# === Drop match_id column and save final enriched polygons
gdf_polygons_enriched = gdf_polygons_enriched.drop(columns='match_id')
gdf_polygons_enriched.to_file(output_file, driver='GeoJSON')
