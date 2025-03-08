import sys
import re
import os
import h5py
import numpy as np
import pandas as pd
from glob import glob

# Import PySide6 Modules
from PySide6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QPushButton,
    QVBoxLayout, QFileDialog, QLabel, QHBoxLayout,
    QComboBox, QProgressBar
)
from PySide6.QtCore import Qt, QSize

# Import QGIS Modules
import processing
from qgis.core import QgsApplication
from processing.core.Processing import Processing
from qgis.core import (QgsProcessing,
                       QgsCoordinateReferenceSystem,
                       QgsVectorLayer, 
                       QgsRasterLayer,
                       QgsFeatureRequest,
                       QgsProcessing,
                       QgsProcessingAlgorithm,
                       QgsProcessingMultiStepFeedback,
                       QgsProcessingParameterFile,
                       QgsProcessingParameterVectorLayer,
                       QgsProcessingParameterRasterLayer
                       )
# Intialize QGIS
qgs = QgsApplication([], False)
qgs.initQgis()
Processing.initialize()

class Form(QDialog):

    def __init__(self, parent=None):
        super(Form, self).__init__(parent)
        self.setWindowTitle("Extract Flow")

        # Variable to store the selected folder/file path
        self.selected_folder = None
        self.selected_ref_lineshp_file = None
        self.selected_terrain_file = None
        self.selected_field = None # This is the selected field from the combobox

        # Folder selection widgets
        self.folder_label = QLabel('Select RAS Folder: ')
        self.folder_button = QPushButton('...')  # Ellipsis icon
        self.folder_button.setFixedWidth(30)  # Make the button compact

        # Layout for folder selection (label + button)
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(self.folder_label)
        folder_layout.addWidget(self.folder_button)

        # Profile line selection widgets
        self.ref_lineshp_label =  QLabel('Select Profile Line: ')
        self.ref_lineshp_button = QPushButton('...')  # Ellipsis icon
        self.ref_lineshp_button.setFixedWidth(30)

        # Layout for profile file selection (label + button)
        ref_lineshp_layout = QHBoxLayout()
        ref_lineshp_layout.addWidget(self.ref_lineshp_label)
        ref_lineshp_layout.addWidget(self.ref_lineshp_button)   

        # Terrain file selection widgets
        self.terrain_label =  QLabel('Select Terrain: ')
        self.terrain_button = QPushButton('...')  # Ellipsis icon
        self.terrain_button.setFixedWidth(30)

        # Layout for Terrain file selection (label + button)
        terrain_layout = QHBoxLayout()
        terrain_layout.addWidget(self.terrain_label)
        terrain_layout.addWidget(self.terrain_button)     

        # Add a ComboBox
        # This ComboxBox allows users to select what
        # Column name is set for the Station Name
        self.combobox_label = QLabel('Select Field Column') # Label for ComboBox
        self.combobox = QComboBox()
        self.combobox.currentIndexChanged.connect(self.on_combobox_change)
          
        # Layout for ComboBox
        combobox_layout = QHBoxLayout()
        combobox_layout.addWidget(self.combobox_label)
        combobox_layout.addWidget(self.combobox)

        # Create a Compute button
        self.compute_button = QPushButton('Compute')
        self.compute_button.clicked.connect(self.output_flow)

        # Create a Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100) 
        self.progress_bar.setValue(0) 
        self.progress_bar.hide() 

        # Create an Exit button
        self.exit_button = QPushButton('Exit')
        self.exit_button.clicked.connect(self.exit_app)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.addLayout(folder_layout)  
        layout.addLayout(ref_lineshp_layout)
        layout.addLayout(combobox_layout)
        layout.addLayout(terrain_layout)
        layout.addWidget(self.compute_button)
        layout.addWidget(self.progress_bar)  
        layout.addWidget(self.exit_button)  
        
        # Connect signals to slots
        self.folder_button.clicked.connect(self.select_ras_folder)
        self.ref_lineshp_button.clicked.connect(self.select_ref_lineshp_file)
        self.terrain_button.clicked.connect(self.select_terrain_file)


    def select_ras_folder(self):
        # Open a dialog to select a folder
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")

        if folder:  # If a folder is selected
            self.selected_folder = folder
            self.folder_label.setText(f'Selected RAS Folder: {folder}')
        else:
            print('No folder selected.')
    
    def select_ref_lineshp_file(self):
        # Open a Dialog to select the Profile Lines path
        ref_lineshp, _ = QFileDialog.getOpenFileName(self, 
                                                    'Select Profile Line',
                                                    filter='Shapefiles (*.shp)'
                                                    )

        if ref_lineshp:  # If selected a profile line
            self.selected_ref_lineshp_file = ref_lineshp  # Correct variable name
            self.ref_lineshp_label.setText(f'Selected Profile Line: {os.path.basename(ref_lineshp)}')
            self.populate_combobox()  # Repopulate the combobox
        else:
            print('No File Selected')
        
    def select_terrain_file(self):
        # Open a Dialog to select the Profile Lines path
        terrain_file = QFileDialog.getOpenFileName(self, 
                                                  'Select Terain',
                                                  filter = 'Rasters (*.vrt *.tiff *.tif)'
                                                  )

        if terrain_file: # If selected a profile line
            self.selected_terrain_file = terrain_file[0]
            self.terrain_label.setText(f'Selected Terrain: {os.path.basename(terrain_file[0])}')
        else:
            print('No File Selected')

    def populate_combobox(self):
        # Read the Vector Layer
        vlayer = QgsVectorLayer(self.selected_ref_lineshp_file, 'vlayer', 'ogr')
        # Get the field column names
        field_columns = [col.name() for col in vlayer.fields()]
        # Clear the combobox first
        self.combobox.clear()

        # Add the list of field column names to the combobox
        self.combobox.addItems(field_columns)
    
    def on_combobox_change(self, index):
        self.selected_field = self.combobox.currentText()  # Store the selected field

    """
    ----------------------------------------------------------

    The functions below does the flow extraction

    ----------------------------------------------------------

    """

    # Sample Points Along a Line
    def get_lowest_elev(self, station):
        # Read the Reference Line layer into a QgsVectorLayer object
        vlayer = QgsVectorLayer(self.selected_ref_lineshp_file, 'ref_line', 'ogr')

        # Read the Raster Layer into a QgsRasterLayer object
        rlayer = QgsRasterLayer(self.selected_terrain_file, 'rlayer')

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

        # Filter the Reference Line SHP file to get only
        # The current station
        vlayer_iter = vlayer_reprojected['OUTPUT'] # Store the reprojected vlayer to vlayer_iter
        filter_expression = f"\"{self.selected_field}\" = '{station}'" # Filter expression to indicate only the current station is needed
        request = QgsFeatureRequest().setFilterExpression(filter_expression) # Isolates the vector feature matching the feature expression
        memory_layer = vlayer_iter.materialize(request) # Creates a temporary vector layer | only the matching feature

        # Create Points Along Line
        alg_params = {
            'INPUT':memory_layer,
            'DISTANCE':0.001,
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

    # This extract the flow per Reference line
    def flow_extract(self, plan_file):
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
            with np.errstate(divide='ignore', invalid='ignore'):
                ref_max_flow_area_array = np.divide(ref_flow_array, ref_vel_array)
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
            })

        return df
    
    def station_sort_key(self, station_str):
        # Match strings like "Station-1+50" or "Station-0"
        m = re.match(r'Station-(\d+)(?:\+(\d+))?', station_str)
        if m:
            base = int(m.group(1))
            offset = int(m.group(2)) if m.group(2) is not None else 0
            return (base, offset)
        # In case of a non-matching string, push it to the end.
        return (float('inf'), 0)
    
    def output_flow(self):
        # Hide the Compute button and show the progress bar
        self.compute_button.hide()
        self.progress_bar.show()

        # Reset the progress bar
        self.progress_bar.setValue(0)

        # Check if a folder is selected
        if not self.selected_folder:
            print("No folder selected!")
            self.progress_bar.hide()
            self.compute_button.show()
            return

        # Update progress bar (5%)
        self.progress_bar.setValue(5)
        QApplication.processEvents()

        if not self.selected_folder:
            print("No folder selected!")
            return
        
        save_folder = os.path.join(self.selected_folder, "summary.csv")
        save_html = os.path.join(self.selected_folder, "summary.html")
        # Get the RAS Folder and get all .p##.hdf files
        glob_key = os.path.join(self.selected_folder, "*.p*.hdf")
        ras_plan = glob(glob_key, recursive=True)

        # Update progress bar (10%)
        self.progress_bar.setValue(10)
        QApplication.processEvents()

        # Initialize an empty list of DataFrames
        dfs = []
        total_files = len(ras_plan)

        for i, plan in enumerate(ras_plan):
            # Extract flow data from the HDF file
            df_extract = self.flow_extract(plan)
            dfs.append(df_extract)

            # Update progress bar based on the number of files processed
            progress = int((i + 1) / total_files * 50)
            self.progress_bar.setValue(progress)
            QApplication.processEvents()

        # Combine all generated Dataframes
        df_concat = pd.concat(dfs, ignore_index=True)

        # Update progress bar (70%)
        self.progress_bar.setValue(70)
        QApplication.processEvents()

        # Get a Series of all unique values in the Station Column
        df_station = pd.DataFrame(df_concat['Station'].unique(), columns=['Station'])
        # Get the Thalweg
        df_station['Thalweg'] = df_station['Station'].apply(
                                    lambda station:  self.get_lowest_elev(station)
                                )
        
        # Update progress bar (80%)
        self.progress_bar.setValue(80)
        QApplication.processEvents()

        # Merge DataFrames
        df_merge = pd.merge(left=df_concat, right=df_station, on=['Station'])
        # Round off all float type columns to 3 decimal places
        float_cols = df_merge.select_dtypes(include=['float']).columns
        df_merge[float_cols] = df_merge[float_cols].round(3)
        # Sort Values by Station and Flow Scenario
        df_merge.sort_values(by=['Station', 'Flow Scenario'], 
                                key=lambda col: col.apply(self.station_sort_key),
                                inplace=True                                  
                                )
        # Save the DataFrame to CSV and HTML
        df_merge.to_csv(save_folder, index=False)
        df_merge.to_html(save_html, index=False)

        # Update progress bar to 100%
        self.progress_bar.setValue(100)
        QApplication.processEvents()

        # Hide the progress bar and show the Compute button
        self.progress_bar.hide()
        self.compute_button.show()

    def exit_app(self):
        # Exit QGIS
        qgs.exitQgis()
        
        # Close the application when the Exit button is clicked.
        QApplication.quit()


if __name__ == '__main__':
    # Create the Qt Application
    app = QApplication(sys.argv)

    # Create and show the form
    form = Form()
    form.show()

    # Run the main Qt loop
    sys.exit(app.exec())

    
