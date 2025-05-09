# Import modules
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import os
import re
from glob import glob
import numpy as np
from scipy.ndimage import gaussian_filter1d as gfd


from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterCrs
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterVectorDestination
from qgis.core import QgsProcessingParameterFeatureSink
from qgis.core import QgsProcessingParameterFile
from qgis.core import QgsExpression
from qgis.core import QgsVectorLayer
from qgis.core import QgsProject
from qgis.core import QgsWkbTypes
from qgis.core import QgsAggregateCalculator
import processing

# Set global font to Calibri and font size to 9pt
plt.rcParams['font.family'] = 'Calibri'
plt.rcParams['font.size'] = 9

class transectlines(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):      
        # Add the parameters
        self.addParameter(QgsProcessingParameterVectorLayer('transect', 'River Centerline', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer('terrain', 'Terrain Layer', defaultValue=None))
        self.addParameter(QgsProcessingParameterFile('ras_folder','RAS Folder Destination', behavior=QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterFile('save_folder','Save Folder Destination', behavior=QgsProcessingParameterFile.Folder))
        
    def processAlgorithm(self, parameters, context, model_feedback):
        # initialize results dictionary
        results = {}
        outputs = {}
        
        # get the RAS and save folder desitination
        ras_folder = parameters['ras_folder']
        save_folder = parameters['save_folder']

        # load the transects
        vlayer = self.parameterAsVectorLayer(parameters, 'transect', context)
        if not vlayer.isValid():
            model_feedback.reportError("Error: Transect vector layer is invalid.")
            return results
        else:
            model_feedback.pushInfo("Transect vector layer loaded successfully.")

        # load the terrain layer
        tlayer = self.parameterAsRasterLayer(parameters, 'terrain', context)
        if not tlayer.isValid():
            model_feedback.reportError("Error: Terrain raster layer is invalid.")
            return results
        else:
            model_feedback.pushInfo("Terrain raster layer loaded successfully.")

        # get all WSE layers in the RAS Folder
        rfolder = os.path.join(ras_folder, 'SB*',"WSE*.tif")
        result_layer = glob(rfolder, recursive=True)
        
        # clean the data for a good image file naming system
        folders = [os.path.basename(os.path.dirname(layer)) for layer in result_layer]
        cleaned_data1 = [re.sub(r'SB - | sb_|_sb|^sb_|^SB_', '', item) for item in folders]
        cleaned_data2 = [re.sub(r'sb_odette', 'Ty. Odette', item) for item in cleaned_data1]
        img_name = [re.sub(r'Post -odette', 'Ty. Odette_post', item) for item in cleaned_data2]
        label_name = [re.sub(r'_post\b', '-Post', item) for item in img_name]
        img_name1 = ['elev'+name+'1' for name in img_name]
        
        # Ensure the save folder exists
        os.makedirs(parameters['save_folder'], exist_ok=True)
        
        # Get the total number of features in the vlayer
        total_features = vlayer.featureCount()
        current_feature = 0
        
        # iterate over each feature in the vlayer
        for feature in vlayer.getFeatures():
            # Check for cancellation
            if model_feedback.isCanceled():
                model_feedback.pushInfo("Operation canceled by the user.")
                break
            
            try:
                current_feature += 1
                
                # Provide feedback about the current feature
                model_feedback.pushInfo(f"Processing feature {current_feature}/{total_features}: {feature['name']}")
                
                # Retrieve the geometry type as a string
                geometry_type_str = QgsWkbTypes.displayString(vlayer.wkbType())
                
                # Create a temporary memory layer for the current feature
                temp_layer = QgsVectorLayer(f"{geometry_type_str}?crs={vlayer.crs().authid()}", "temporary", "memory")
                temp_provider = temp_layer.dataProvider()
                temp_provider.addFeatures([feature])
                temp_layer.updateExtents()
                
                # points along geom
                alg_params = {
                    'INPUT': temp_layer,
                    'DISTANCE':1,
                    'START_OFFSET':0,
                    'END_OFFSET':0,
                    'OUTPUT':'TEMPORARY_OUTPUT'
                }
                outputs['gen_points'] = processing.run("native:pointsalonglines", alg_params, context=context, feedback=model_feedback)
            
                # sample raster values for the terrain elevation
                alg_params = {
                    'INPUT': outputs['gen_points']['OUTPUT'],
                    'RASTERCOPY': tlayer,
                    'COLUMN_PREFIX':'terrain',
                    'OUTPUT':'TEMPORARY_OUTPUT'}
                outputs['sampled'] = processing.run("native:rastersampling", alg_params, context=context, feedback=model_feedback)
                
                # store the values of distance and terrain in a list
                layer = outputs['sampled']['OUTPUT']
                distance = layer.aggregate(QgsAggregateCalculator.ArrayAggregate, 'distance')[0]
                # model_feedback.pushInfo(f"Distance data: {distance}")
                
                terrain = layer.aggregate(QgsAggregateCalculator.ArrayAggregate, 'terrain1')[0]
                # model_feedback.pushInfo(f"Terrain data: {terrain}")
                
                # iterate over each WSE raster maps
                for i, wse in enumerate(result_layer):
                    column_name = 'elev' + img_name[i]

                    # sample raster values for the WSE results
                    alg_params = {
                        'INPUT': outputs['sampled']['OUTPUT'],
                        'RASTERCOPY':wse,
                        'COLUMN_PREFIX': column_name,
                        'OUTPUT':'TEMPORARY_OUTPUT'}
                    outputs['sampled'] = processing.run("native:rastersampling", alg_params, context=context, feedback=model_feedback)

                # get the names of each field in the output
                layer = outputs['sampled']['OUTPUT'].dataProvider()
                field_names = [f.name() for f in layer.fields()]
                # model_feedback.pushInfo(f"Field Names data: {field_names}")
                # model_feedback.pushInfo(f"img_name1 data: {img_name1}")
                # model_feedback.pushInfo(f"img_name data: {img_name}")

                # ----- This section plots the values -----
                
                # save the output in a variable 
                layer = outputs['sampled']['OUTPUT']


                # initialize a color list
                color_list = ['#a6cee3', '#1f78b4', '#b2df8a', '#33a02c', '#fb9a99','#e31a1c', '#fdbf6f', '#ff7f00', '#cab2d6', '#6a3d9a', '#ffff99', '#b15928', '#8dd3c7','#762a83' ]
      
                # initiliaze the figure plot
                fig, ax= plt.subplots(figsize = (5.65,3))

                # plot the terrain elevation
                ax.plot(distance, terrain, label = 'Terrain', color='black', linewidth = 1)

                # iterate over each field name corresponding to img name
                # then plot for each result raster
                for img in field_names:
                    if img in img_name1:
                        i=img_name1.index(img)
                        wse_value = layer.aggregate(QgsAggregateCalculator.ArrayAggregate, img)[0]
                        # model_feedback.pushInfo(f"WSE value for {img}: {layer.aggregate(QgsAggregateCalculator.ArrayAggregate, img)[0]}")
                        ax.plot(distance, wse_value, label= label_name[i], color=color_list[i], linewidth = 0.5)
                    else:
                        model_feedback.reportError(f"Field {img} not found in layer fields. Items of img_name1 {feature['name']}.")
                        
                             
                ax.xlabel('Station (m)')
                ax.ylabel('WSE (m)')
                ax.legend(
                    loc = 'center left',
                    bbox_to_anchor = (1,0.5),
                    fontsize = 7
                )
            
                ax.tight_layout()
                
                # Save the figure
                file_name = feature['name'] + '.png'
                savepath = os.path.join(save_folder, file_name)
                ax.savefig(savepath, dpi=300)
                ax.close()
                
                # Provide feedback after saving the plot
                model_feedback.pushInfo(f"Saved plot for feature '{feature['name']}' at {savepath}")
                
                # Update the progress bar
                progress = int((current_feature / total_features) * 100)
                model_feedback.setProgress(progress)
            
            except Exception as e:
                model_feedback.reportError(f"An error occurred while processing feature '{feature['name']}': {str(e)}")
                continue  # Skip to the next feature
        
        # Final feedback message
        model_feedback.pushInfo("Processing completed.")
               
        return results

    def name(self):
        return 'transectlines'

    def displayName(self):
        return 'transectlines'

    def group(self):
        return ''

    def groupId(self):
        return ''

    def createInstance(self):
        return transectlines()
