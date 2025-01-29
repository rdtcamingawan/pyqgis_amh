import rasterio
import numpy as np
import geopandas as gpd
from rasterio import features
from scipy.spatial import cKDTree
import os

# Configuration
base_path = r"C:\Users\richmond\AMH Philippines, Inc\PP23.307 Rockwell and Roll - My Documents\Python\amh_pyqgis\cbnc_tsf3"
input_tiff = os.path.join(base_path,'topo_data.tif')
pt1_shp = os.path.join(base_path,"pt1.shp")
pt2_shp = os.path.join(base_path,"pt2.shp")
poly1_shp = os.path.join(base_path,"poly1.shp")
poly2_shp = os.path.join(base_path,"poly2.shp")
output_dir = r"C:\Users\richmond\AMH Philippines, Inc\PP23.307 Rockwell and Roll - My Documents\Python\amh_pyqgis\cbnc_tsf3"

# Fixed parameters
PT1_ELEV = 39.5             # Fixed spillway elevation
PT2_RANGE = np.arange(40, 43, 0.01)  # 39.5 to 40.5 inclusive

def process_elevation(pt2_elev):
    """Process single elevation scenario"""
    with rasterio.open(input_tiff) as src:
        # Read base elevation data
        existing = src.read(1)
        transform = src.transform
        profile = src.profile.copy()
        nodata = src.nodata

        # Convert to float array
        elev = existing.astype(float)
        elev[elev == nodata] = np.nan

        # Load geometries
        pt1 = gpd.read_file(pt1_shp)
        poly1 = gpd.read_file(poly1_shp)
        # poly2 = gpd.read_file(poly2_shp)

        # Create masks
        def create_mask(poly):
            return features.rasterize(
                poly.geometry,
                out_shape=elev.shape,
                transform=transform,
                fill=0,
                all_touched=True
            ).astype(bool)
        
        mask_slope = create_mask(poly1)
        # mask_flat = create_mask(poly2)

        # Get coordinates grid
        rows, cols = elev.shape
        x_coords, y_coords = np.meshgrid(
            np.arange(cols) * transform[0] + transform[2],
            np.arange(rows) * transform[4] + transform[5]
        )

        # Process slope area (poly1)
        if np.any(mask_slope):
            # Find nearest pt1 for all pixels
            pt1_coords = np.array([[geom.x, geom.y] for geom in pt1.geometry])
            kdtree = cKDTree(pt1_coords)
            _, indices = kdtree.query(np.column_stack([x_coords.ravel(), y_coords.ravel()]))
            
            # Calculate distances
            distances = np.sqrt(
                (x_coords.ravel() - pt1_coords[indices, 0])**2 +
                (y_coords.ravel() - pt1_coords[indices, 1])**2
            ).reshape(rows, cols)

            # Create slope surface
            slope_surface = PT1_ELEV + (pt2_elev - PT1_ELEV) * (distances / distances.max())
            elev = np.where((mask_slope & (elev < slope_surface)), slope_surface, elev)

        # Process flat area (poly2)
        # if np.any(mask_flat):
        #     elev = np.where((mask_flat & (elev < pt2_elev)), pt2_elev, elev)

        # Save output
        output_path = os.path.join(output_dir, 'dp',f"elev_{pt2_elev:.2f}m.tif")
        elev = np.nan_to_num(elev, nan=nodata).astype(rasterio.float32)
        
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(elev, 1)
        print(f"Saved: {output_path}")

# Process all elevation scenarios
for target_elev in PT2_RANGE:
    process_elevation(target_elev)