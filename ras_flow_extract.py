import h5py
import os
import pandas as pd
import numpy as np
from glob import glob

# Qgis import modules
import processing
from qgis.core import QgsApplication
from processing.core.Processing import Processing
from qgis.core import (QgsProcessing,
                       QgsCoordinateReferenceSystem,
                       QgsVectorLayer, 
                       QgsRasterLayer,
                       )

# This return the maximum value in a given nd.array
def get_max_list(a_list):
    # Converts the array to a dataframe
    df = pd.DataFrame(a_list)
    max_values = df.max()
    return max_values

# This extract the flow per Reference line
def flow_extract(plan_file):
    ras_hdf_file = plan_file

    # Read the HDF5 File
    with h5py.File(ras_hdf_file, 'r') as f:
        # Get the Flow Title
        # This represents the flow scenario of the plan
        short_id_path = '/Plan Data/Plan Information'
        flow_id = f[short_id_path].attrs['Flow Title'].decode('utf-8')

        # Get the names of the reference line
        ref_name_path = r'/Geometry/Reference Lines/Attributes'
        ref_names = np.array(f[ref_name_path])
        ref_col_names = [x[0].decode('utf-8') for x in ref_names]

        # Get the max discharge per reference lines
        ref_line_path = r'/Results/Unsteady/Output/Output Blocks/DSS Hydrograph Output/Unsteady Time Series/Reference Lines'
        ref_flow_array = f[ref_line_path]['Flow']
        flow_max_values = np.max(ref_flow_array, axis=0)
        ref_flow = flow_max_values.tolist()

        # Get the Max Velocity per Reference Lines
        ref_vel_array = f[ref_line_path]['Velocity']
        vel_max_values = np.max(ref_vel_array, axis=0)
        ref_velocity = vel_max_values.tolist()

        # Compute the Max Flow Area
        # Given by the Eq. Q = A * V; A = Q / V
        ref_max_flow_area_array = np.divide(
                                    ref_flow_array,
                                    ref_vel_array,
                                    )
        ref_max_flow_area = np.nanmax(ref_max_flow_area_array, axis=0).tolist()

        # Get the Max WSE
        ref_wse_array = f[ref_line_path]['Water Surface']
        ref_wse = np.max(ref_wse_array, axis=0).tolist()

        # Compute the EGL
        # Given by the equation: EGL = WSE + V^2 / 2g (g=9.81 m/s^2)
        g = 9.81 * 2 
        vel_head = np.power(ref_vel_array, 2) / g
        egl_array = ref_wse + vel_head
        ref_egl = np.max(egl_array, axis=0).tolist()

        # Create a DataFrame
        df = pd.DataFrame({
            'Station' : ref_col_names,
            'Flow Scenario' : flow_id, 
            'Discharge' : ref_flow,
            'Velocity' : ref_velocity,
            'Flow Area': ref_max_flow_area,
            'WSE': ref_wse,
            'EGL': ref_egl
            # 'Thalweg' : get_lowest_elev()
        })

    return df

# Sample Points Along a Line
def get_lowest_elev(ref_line_vlayer, raster_layer):
    ref_line = ref_line_vlayer

    # Read the Reference Line layer into a QgsVectorLayer object
    vlayer = QgsVectorLayer(ref_line, 'ref_line', 'ogr')

    # Read the Raster Layer into a QgsRasterLayer object
    rlayer = QgsRasterLayer(raster_layer, 'rlayer')

    # Reprojection would be done to ensure that the buffer units is in meters
    # Reproject Reference Line Layer to EPSG:32651
    alg_params = {
        'INPUT':vlayer,
        'TARGET_CRS':QgsCoordinateReferenceSystem('EPSG:32651'),
        'OUTPUT':'TEMPORARY_OUTPUT'
        }
    vlayer_reprojected = processing.run("native:reprojectlayer", alg_params)

    # Reproject Raster Layer
    alg_params = {
        'INPUT':rlayer,
        'SOURCE_CRS':None,
        'TARGET_CRS':QgsCoordinateReferenceSystem('EPSG:32651'),
        'RESAMPLING':0,
        'NODATA':None,
        'TARGET_RESOLUTION':None,
        'OPTIONS':None,
        'DATA_TYPE':0,
        'TARGET_EXTENT':None,
        'TARGET_EXTENT_CRS':None,
        'MULTITHREADING':True,
        'EXTRA':'',
        'OUTPUT':'TEMPORARY_OUTPUT'
    }
    rlayer_reprojected = processing.run("gdal:warpreproject", alg_params)

    # Create Points Along Line
    alg_params = {
        'INPUT':vlayer_reprojected['OUTPUT'],
        'DISTANCE':0.01,
        'START_OFFSET':0,
        'END_OFFSET':0,
        'OUTPUT':'TEMPORARY_OUTPUT'
    }
    vlayer_points = processing.run("native:pointsalonglines", alg_params)

    # Sample Raster Values on Points Along Line
    alg_params = {
        'INPUT': vlayer_points['OUTPUT'],
        'RASTERCOPY': rlayer_reprojected['OUTPUT'],
        'COLUMN_PREFIX':'ELEV',
        'OUTPUT':'TEMPORARY_OUTPUT'
    }
    sampled_points = processing.run("native:rastersampling",alg_params)
    vector_sampled = sampled_points['OUTPUT']

    # Saves the sampled points in a DataFrame
    sampled_fields = [f.name() for f in vector_sampled.fields()] # Gets the column name. Column Header
    sampled_attributes = [f.attributes() for f in vector_sampled.getFeatures()] # Get the values for each row.
    df_sample = pd.DataFrame(sampled_attributes, columns=sampled_fields)

    # Get the lowest elevation
    min_value = df_sample.iloc[:, -1].min()

    return min_value


"""
Inputs from the users are:

1. RAS Folder
2. Reference Line in SHP file Format
"""
# Get Inputs from the user
# Get the RAS Folder and get all .p##.hdf files
# input_ras_folder = input("Paste RAS Folder Path: ").strip().strip('"')
# ras_folder = os.path.normpath(input_ras_folder)

ras_folder = r"C:\Users\richmond\AMH Philippines, Inc\PP23.307 Rockwell and Roll - My Documents\Python\amh_pyqgis\flow_extraction\RAS"
save_folder = os.path.join(ras_folder, "summary.csv")
glob_key = os.path.join(ras_folder, "*.p*.hdf")
ras_plan = glob(glob_key, recursive=True)

# Complete columns for report
x = """
This is the complete column names:

column = [
    'Reference Line',
    'Discharge',
    'Flow Velocity',
    'Flow Area',
    'WSE',
    'EGL',
    'Thalweg',
    'LOB',
    'ROB',
]

"""

dfs = []

for plan in ras_plan:
    df_extract = flow_extract(plan)
    dfs.append(df_extract)

df_concat = pd.concat(dfs, ignore_index=True).sort_values(by=['Station', 'Plan ID'])
df_concat.to_csv(save_folder)

# Exit of QGIS
qgs.exitQgis()


