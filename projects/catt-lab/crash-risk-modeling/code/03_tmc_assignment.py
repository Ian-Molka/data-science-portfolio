import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# === File Paths ===
crash_csv = r"data/input_file.csv"
tmc_geojson = r"data/tmc_geojson.geojson"
output_path = r"data/output_file.csv"

# === Load Crash CSV and create GeoDataFrame ===
df_crash = pd.read_csv(crash_csv)
df_crash = df_crash.dropna(subset=['longitude', 'latitude'])  # remove rows without geometry

# Convert to GeoDataFrame
geometry = [Point(xy) for xy in zip(df_crash['longitude'], df_crash['latitude'])]
gdf_crash = gpd.GeoDataFrame(df_crash, geometry=geometry, crs='EPSG:4326')

# === Load TMC GeoJSON ===
gdf_tmc = gpd.read_file(tmc_geojson)
gdf_tmc = gdf_tmc.to_crs('EPSG:4326')

# Optional: simplify TMC data to relevant fields
keep_cols = ['tmc', 'road', 'direction', 'miles', 'geometry']
gdf_tmc = gdf_tmc[[col for col in keep_cols if col in gdf_tmc.columns]]

# === Spatial Join: Find Nearest TMC for Each Crash ===
gdf_crash = gdf_crash.to_crs(epsg=3857)
gdf_tmc = gdf_tmc.to_crs(epsg=3857)

# Find nearest TMC segment for each crash
nearest_tmc = gpd.sjoin_nearest(
    gdf_crash,
    gdf_tmc,
    how='left',
    distance_col='distance_to_tmc'
)

# Convert back to WGS84
nearest_tmc = nearest_tmc.to_crs(epsg=4326)

# === Export Result ===
nearest_tmc.drop(columns='geometry').to_csv(output_path, index=False)
print(f"✅ Output saved to: {output_path}")
