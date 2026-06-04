import geopandas as gpd
import pandas as pd

# === File Paths ===
zone_file = r"data/Truck_Parking_Polygon_Ready_For_Conflation.geojson"
tmc_file = r"data/MD_tmc_2023.geojson"
vmt_file = r"data/segment_vmt_totals.csv"
output_file = r"data/Truck_Parking_Polygon_Enriched_With_VMT.geojson"

# === Load and project data ===
gdf_zones = gpd.read_file(zone_file).to_crs(epsg=3857)
gdf_tmc = gpd.read_file(tmc_file).to_crs(epsg=3857)
df_vmt = pd.read_csv(vmt_file)

# === Clean VMT column and merge into TMCs ===
df_vmt = df_vmt.rename(columns={'VMT': 'VMT'})  # Rename if needed
if 'tmc' not in gdf_tmc.columns or 'tmc' not in df_vmt.columns:
    raise ValueError("❌ 'tmc' column is required in both TMC GeoJSON and VMT CSV.")

gdf_tmc = gdf_tmc.merge(df_vmt[['tmc', 'VMT']], on='tmc', how='left')
print(f"✅ TMCs with VMT: {gdf_tmc['VMT'].notna().sum()} of {len(gdf_tmc)}")

# === Drop invalid geometries
gdf_zones = gdf_zones[gdf_zones.is_valid]
gdf_tmc = gdf_tmc[gdf_tmc.is_valid]

# === Perform intersection (allow polygon-line intersections)
intersections = gpd.overlay(gdf_zones, gdf_tmc, how='intersection', keep_geom_type=False)

if intersections.empty:
    raise ValueError("❌ No intersections found. Check projections or geometries.")

# === Calculate intersection area
intersections['intersection_area'] = intersections.geometry.area

# === Sort by area and keep only largest TMC per zone
intersections_sorted = intersections.sort_values(by=['OBJECTID', 'intersection_area'], ascending=[True, False])
largest_overlap = intersections_sorted.drop_duplicates(subset='OBJECTID', keep='first')

# === Extract tmc + VMT to assign to zones
vmt_assignment = largest_overlap[['OBJECTID', 'tmc', 'VMT']].copy()

# === Merge back to original zone polygons
gdf_zones = gdf_zones.merge(vmt_assignment, on='OBJECTID', how='left')

# === Reproject and save
gdf_zones = gdf_zones.to_crs(epsg=4326)
gdf_zones.to_file(output_file, driver='GeoJSON')
print(f"\n✅ Final output saved to:\n{output_file}")
print(f"✅ Zones with assigned VMT: {gdf_zones['VMT'].notna().sum()} of {len(gdf_zones)}")
print("🧪 Sample with VMT:")
print(gdf_zones[['OBJECTID', 'Zone', 'tmc', 'VMT']].dropna().head())
