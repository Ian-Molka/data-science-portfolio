import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import csv

# === File Paths ===
csv_file = r"data/crash_vehicle_events_joined_described.csv"
geojson_file = r"data/Truck_Parking_Polygon_Enriched_With_VMT.geojson"
output_file = r"data/conflated_crashes_with_tmc_parking2test.csv"

# === Load crash points ===
df_points = pd.read_csv(csv_file)
if 'OBJECTID' in df_points.columns:
    df_points['OBJECTID'] = df_points['OBJECTID'].apply(lambda x: int(str(x).lstrip('0')) if pd.notnull(x) else None)

df_points = df_points.dropna(subset=['latitude', 'longitude']).copy()
df_points['geometry'] = df_points.apply(lambda row: Point(row['longitude'], row['latitude']), axis=1)
gdf_points = gpd.GeoDataFrame(df_points, geometry='geometry', crs="EPSG:4326")

# === Load truck parking polygons ===
gdf_polygons = gpd.read_file(geojson_file)
gdf_polygons = gdf_polygons[gdf_polygons.geometry.is_valid & ~gdf_polygons.geometry.is_empty].copy()

# === Reproject to EPSG:3857 for distance-based buffering
gdf_points_m = gdf_points.to_crs(epsg=3857)
gdf_polygons_m = gdf_polygons.to_crs(epsg=3857)

# === Step 1: Filter crashes within 3 miles (≈4800 meters)
buffer_3m = gdf_points_m.copy()
buffer_3m['geometry'] = buffer_3m.geometry.buffer(4800)
joined_3m = gpd.sjoin(buffer_3m, gdf_polygons_m, how="inner", predicate="intersects")
valid_ids = set(joined_3m['vehicleid'])

filtered_points = gdf_points[gdf_points['vehicleid'].isin(valid_ids)].copy()
filtered_points = filtered_points.drop_duplicates(subset='vehicleid')
filtered_points_m = filtered_points.to_crs(epsg=3857)

# === Step 2: Match at 0m, 25m, and 50m buffers
for buffer_size in [0, 25, 50]:
    temp = filtered_points_m.copy()
    if buffer_size > 0:
        temp['geometry'] = temp.geometry.buffer(buffer_size)
    joined = gpd.sjoin(temp, gdf_polygons_m[['geometry']], how='inner', predicate='intersects')
    matched_ids = set(joined['vehicleid'])
    filtered_points[f"match_{buffer_size}m"] = filtered_points['vehicleid'].apply(
        lambda vid: "matched" if vid in matched_ids else "unmatched"
    )

# === Flag if matched in any buffer
filtered_points["in_zone"] = filtered_points.apply(
    lambda row: any(row[f"match_{m}m"] == "matched" for m in [0, 25, 50]),
    axis=1
)

# === Step 3: CMV Involvement Flag
cmv_body_types = {
    "TRUCK - CARGO VAN/LIGHT 2 AXLES (OVER 10,000LBS (4,536 KG))",
    "TRUCK - TRACTOR",
    "TRUCK - OTHER LIGHT (10,000LBS (4,536KG) OR LESS)",
    "TRUCK - MEDIUM/HEAVY 3 AXLES (OVER 10,000LBS (4,536KG)",
    "FIRE VEHICLE/NON EMERGENCY",
    "FARM VEHICLE"
}
filtered_points["cmv_involved"] = filtered_points["vehicle_body_description"].apply(
    lambda x: str(x).strip() in cmv_body_types if pd.notna(x) else False
)

# === Step 4: Nearest zone (within 50m) with attributes
buffer_50m = filtered_points_m.copy()
buffer_50m['geometry'] = buffer_50m.geometry.buffer(50)
joined_50m = gpd.sjoin(buffer_50m, gdf_polygons_m, how='inner', predicate='intersects')

crash_geom_by_vid = (
    filtered_points_m.drop_duplicates(subset='vehicleid')
    .set_index('vehicleid')['geometry']
)
joined_50m['crash_geom'] = joined_50m['vehicleid'].map(crash_geom_by_vid)
joined_50m['distance'] = joined_50m.apply(lambda row: row['crash_geom'].distance(row['geometry']), axis=1)

nearest = joined_50m.sort_values('distance').drop_duplicates('vehicleid')
polygon_fields = [col for col in gdf_polygons.columns if col != 'geometry']
merge_fields = ['vehicleid'] + polygon_fields

filtered_points = filtered_points.merge(nearest[merge_fields], on='vehicleid', how='left')

# === Rename Zone -> nearest_zone
if 'Zone' in filtered_points.columns:
    filtered_points.rename(columns={'Zone': 'nearest_zone'}, inplace=True)

# === Step 5: Flag if in special zone with 20m buffer
gdf_polygons_m['Zone_clean'] = gdf_polygons_m['Zone'].str.lower().str.strip()
special_zones = ['upstream: off-ramp', 'downstream: on-ramp', 'parking lot']
zones_for_buffer = gdf_polygons_m[gdf_polygons_m['Zone_clean'].isin(special_zones)].copy()
zones_for_buffer['geometry'] = zones_for_buffer.geometry.buffer(20)

zone_buffer_match = gpd.sjoin(filtered_points_m, zones_for_buffer[['geometry']], how='inner', predicate='intersects')
matched_ids_20m = zone_buffer_match['vehicleid'].drop_duplicates()
filtered_points['in_20m_special_zone'] = filtered_points['vehicleid'].isin(matched_ids_20m)

# === Export final CSV
filtered_points.to_csv(
    output_file,
    index=False,
    quoting=csv.QUOTE_NONNUMERIC,  # Quotes only string values
    quotechar='"',
    encoding='utf-8',
    lineterminator='\n'
)

print("\n✅ Final labeled file created with in_zone flag.")
print(f"📄 Output: {output_file}")
