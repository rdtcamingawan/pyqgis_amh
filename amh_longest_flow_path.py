from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterCrs
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterVectorDestination
from qgis.core import QgsProcessingParameterFolderDestination
from qgis.core import QgsProcessingParameterFeatureSink
from qgis.core import QgsExpression
from qgis.core import QgsProcessingUtils
from qgis.core import QgsFeatureSink
from qgis.core import QgsWkbTypes
from qgis.core import QgsVectorLayer
from qgis.core import QgsFeature
import processing
import os
import pandas as pd


class generate_cn(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        # Inputs
        self.addParameter(QgsProcessingParameterCrs('crs', 'CRS', defaultValue='EPSG:32651'))
        self.addParameter(QgsProcessingParameterRasterLayer('wbt_dem', 'WBT DEM', defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer('wbt_filled', 'WBT Filled DEM', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('subbasins', 'Subbasins', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('land_cover', 'Land Cover', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('soil_type', 'Soil Type', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
        # Outputs
        self.addParameter(QgsProcessingParameterFeatureSink('curve_number', 'Curve Number', type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue=None))


    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(12, model_feedback)
        results = {}
        outputs = {}
        basin_summary = []
        wbt_file = r"D:\AMH Philippines, Inc\PP23.307 Rockwell and Roll - General\06 NP23.000 WORK FILES\Richmond\My Documents\Python\amh_pyqgis\edc_amacan\lag_time"

        # Reproject Land Cover Layer
        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT':parameters['land_cover'],
            'TARGET_CRS':parameters['crs'],
            'CONVERT_CURVED_GEOMETRIES':False,
            'OUTPUT':'TEMPORARY_OUTPUT'
        }
        outputs['reprojected_lc'] = processing.run('native:reprojectlayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Reproject Soil Layer
        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT':parameters['soil_type'],
            'TARGET_CRS':parameters['crs'],
            'CONVERT_CURVED_GEOMETRIES':False,
            'OUTPUT':'TEMPORARY_OUTPUT'
        }
        outputs['reprojected_soil'] = processing.run('native:reprojectlayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Reproject Outfall Layer
        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # This is the start of watershed characterization
        # all child algorithm output shall be stored in the outputs['scs'] variable
        # this is because they are all temporary output and there I see no need to store it in diffferent variable everytime.
        # So I am just re-writing the outputs['scs'] variable each step.

        #fix geometries
        # fix basins
        alg_params = {
             'INPUT': parameters['subbasins'], 
             'METHOD': 0, 
             'OUTPUT': 'TEMPORARY_OUTPUT'
             }
        outputs['fixed_subbasins'] = processing.run("native:fixgeometries", alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # fix land
        alg_params = {
             'INPUT': outputs['reprojected_lc']['OUTPUT'], 
             'METHOD': 0, 
             'OUTPUT': 'TEMPORARY_OUTPUT'
             }
        outputs['fixed_lc'] = processing.run("native:fixgeometries", alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # fix soil
        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        alg_params = {
             'INPUT': outputs['reprojected_soil']['OUTPUT'], 
             'METHOD': 0, 
             'OUTPUT': 'TEMPORARY_OUTPUT'
             }
        outputs['fixed_soil'] = processing.run("native:fixgeometries", alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        #intersect basin - land cover
        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT': outputs['fixed_lc']['OUTPUT'], 
            'OVERLAY': outputs['fixed_subbasins']['OUTPUT'], # This is the clipped subbasins output
            'INPUT_FIELDS':['class_name'], # This retains the class_name field in the land cover
            'OVERLAY_FIELDS':['name'], # This retains the `name` field in the basins vector
            'OVERLAY_FIELDS_PREFIX':'subbasin',
            'OUTPUT': 'TEMPORARY_OUTPUT'}
        outputs['scs'] = processing.run("native:intersection", alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        #intersect basin - land - soil
        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT': outputs['fixed_soil']['OUTPUT'], 
            'OVERLAY': outputs['scs']['OUTPUT'],
            'INPUT_FIELDS':['descriptio','type'], # This retains the `descriptio` and ` type` in the soil layer input
            'OUTPUT': 'TEMPORARY_OUTPUT'}   
        outputs['scs'] = processing.run("native:intersection", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

        # add retardance coefficient
        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT': outputs['scs'],
            'FIELD_NAME':'class_ret-c',
            'FIELD_TYPE':2,
            'FIELD_LENGTH':255,
            'FIELD_PRECISION':255,
            'FORMULA':
            """
            CASE    
            WHEN "class_name" = 'Built-up' THEN 'Concrete'    
            WHEN "class_name" = 'Inland Water' THEN 'Concrete'    
            WHEN "class_name" = 'Open Forest' THEN 'Closely clipped sod\'    
            WHEN "class_name" = 'Perennial Crop' THEN 'Dense bluegrass turf'    
            WHEN "class_name" = 'Closed Forest' THEN 'Dense bluegrass turf'    
            WHEN "class_name" = 'Brush/Shrubs' THEN 'Closely clipped sod'    
            WHEN "class_name" = 'Grassland' THEN 'Closely clipped sod'    
            WHEN "class_name" = 'Open/Barren' THEN 'Concrete'    
            WHEN "class_name" = 'Mangrove Forest' THEN 'Dense bluegrass turf'    
            WHEN "class_name" = 'Annual Crop' THEN 'Dense bluegrass turf'    
            WHEN "class_name" = 'Marshland Swamp' THEN 'Dense bluegrass turf'    
            WHEN "class_name" = 'Fishpond' THEN 'Concrete'
            END
            """,
            'OUTPUT':'TEMPORARY_OUTPUT'}

        outputs['scs'] = processing.run("native:fieldcalculator", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

        # add runoff coefficient
        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT': outputs['scs'],
            'FIELD_NAME':'class_run-c',
            'FIELD_TYPE':2,
            'FIELD_LENGTH':255,
            'FIELD_PRECISION':255,
            'FORMULA':
            """
            CASE    
            WHEN "class_name" = \'Built-up\' THEN \'AS\'    
            WHEN "class_name" = \'Built-up\' THEN \'CN\'    
            WHEN "class_name" = 'Open/Barren' THEN 'GPF'    
            WHEN "class_name" = \'Grassland\' THEN \'GPA\'   
            WHEN "class_name" = \'Grassland\' THEN \'GPS\'    
            WHEN "class_name" = \'Brush/Shrubs\' THEN \'GFF\'    
            WHEN "class_name" = \'Brush/Shrubs\' THEN \'GFA\'    
            WHEN "class_name" = \'Brush/Shrubs\' THEN \'GFS\'    
            WHEN "class_name" = \'Open Forest\' THEN \'GGF\'    
            WHEN "class_name" = \'Open Forest\' THEN \'GGA\'    
            WHEN "class_name" = \'Open Forest\' THEN \'GGS\'    
            WHEN "class_name" = \'Perennial Crop\' THEN \'CLF\'    
            WHEN "class_name" = \'Perennial Crop\' THEN \'CLA\'    
            WHEN "class_name" = \'Perennial Crop\' THEN \'CLS\'    
            WHEN "class_name" = \'Annual Crop\' THEN \'PRF\'    
            WHEN "class_name" = \'Annual Crop\' THEN \'PRA\'   
            WHEN "class_name" = \'Annual Crop\' THEN \'PRS\'    
            WHEN "class_name" = \'Mangrove Forest\' THEN \'FWF\'    
            WHEN "class_name" = \'Closed Forest\' THEN \'FWA\'    
            WHEN "class_name" = \'Closed Forest\' THEN \'FWS\'
            WHEN "class_name" = \'Inland Water\' THEN \'Water\'
            WHEN "class_name" = \'Marshland/Swamp\' THEN \'Water\'
            WHEN "class_name" = \'Fishpond\' THEN \'Water\'
            END
            """,
            'OUTPUT':'TEMPORARY_OUTPUT'
        }
        outputs['scs'] = processing.run("native:fieldcalculator", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

        # assign HSG value
        feedback.setCurrentStep(8)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT': outputs['scs'],
            'FIELD_NAME':'HSG',
            'FIELD_TYPE':2,
            'FIELD_LENGTH':255,
            'FIELD_PRECISION':0,
            'FORMULA':
                """
                CASE
                WHEN type IN ('Sand', 'Beach Sand', 'Coarse Sand', 'Fine Sand') THEN 'A'
                WHEN type IN ( 'Fine Sandy Loam','Sandy Loam','Loamy Sand', 'Silt Loam') THEN 'B'
                WHEN  type IN ('Loam', 'Clay Loam', 'Silty Clay Loam', 'Gravelly Clay Loam', 'Gravelly Loam','Gravelly Silt Loam','Clay Loam Adobe', 'Sandy Clay Loam') THEN 'C'
                WHEN type IN ('Clay', 'Hydrosol', 'Gravelly Sandy Clay Loam', 'Sandy Clay',  'Filled up soil',  'Mountainous Land', 'Complex', 'Undifferentiated', 'Lava flow') THEN 'D'
                ELSE '-' 
                END
                """,
            'OUTPUT':'TEMPORARY_OUTPUT'}

        outputs['scs'] = processing.run("native:fieldcalculator", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

        #add Manning's N Field
        feedback.setCurrentStep(9)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT': outputs['scs'],
            'FIELD_NAME':'n_value',
            'FIELD_TYPE':0,
            'FIELD_LENGTH':11,
            'FIELD_PRECISION':11,
            'FORMULA': """
                CASE    
                WHEN "class_name" = \'Built-up\' THEN 0.014    
                WHEN "class_name" = \'Inland Water\' THEN 0.035    
                WHEN "class_name" = \'Open Forest\' THEN 0.035    
                WHEN "class_name" = \'Perennial Crop\' THEN 0.045    
                WHEN "class_name" = \'Closed Forest\' THEN 0.12    
                WHEN "class_name" = \'Brush/Shrubs\' THEN 0.05    
                WHEN "class_name" = \'Grassland\' THEN 0.03    
                WHEN "class_name" = \'Open/Barren\' THEN 0.02    
                WHEN "class_name" = \'Mangrove Forest\' THEN 0.035    
                WHEN "class_name" = \'Annual Crop\' THEN 0.045    
                WHEN "class_name" = \'Marshland/Swamp\' THEN 0.035    
                WHEN "class_name" = \'Fishpond\' THEN 0.035    
                ELSE NULL
                END
                """,
            'OUTPUT':'TEMPORARY_OUTPUT'}

        outputs['scs'] = processing.run("native:fieldcalculator", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

        # add ret-c#
        feedback.setCurrentStep(10)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT':outputs['scs'],
            'FIELD_NAME':'ret-c',
            'FIELD_TYPE':0,
            'FIELD_LENGTH':11,
            'FIELD_PRECISION':11,
            'FORMULA':
            """
            CASE
            WHEN "class_ret-c" = 'Concrete' THEN 0.012
            WHEN "class_ret-c" = 'Closely clipped sod' THEN 0.046
            WHEN "class_ret-c" = 'Dense bluegrass turf' THEN 0.06
            ELSE NULL
            END
            """,
            'OUTPUT' : 'TEMPORARY_OUTPUT'
        }
        outputs['scs'] = processing.run("native:fieldcalculator", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

        # add curve number
        feedback.setCurrentStep(11)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT':outputs['scs'],
            'FIELD_NAME':'CN',
            'FIELD_TYPE':2,
            'FIELD_LENGTH':11,
            'FIELD_PRECISION':11,
            'FORMULA':
            """
            CASE    
            WHEN "class_name" = \'Built-up\' AND "HSG" = \'A\' THEN 98    
            WHEN "class_name" = \'Built-up\' AND "HSG" = \'B\' THEN 98    
            WHEN "class_name" = \'Built-up\' AND "HSG" = \'C\' THEN 98    
            WHEN "class_name" = \'Built-up\' AND "HSG" = \'D\' THEN 98    
            WHEN "class_name" = \'Inland Water\' THEN 100    
            WHEN "class_name" = \'Open Forest\' AND "HSG" = \'A\' THEN 36    
            WHEN "class_name" = \'Open Forest\' AND "HSG" = \'B\' THEN 60    
            WHEN "class_name" = \'Open Forest\' AND "HSG" = \'C\' THEN 73   
            WHEN "class_name" = \'Open Forest\' AND "HSG" = \'D\' THEN 79    
            WHEN "class_name" = \'Perennial Crop\' AND "HSG" = \'A\' THEN 72    
            WHEN "class_name" = \'Perennial Crop\' AND "HSG" = \'B\' THEN 81    
            WHEN "class_name" = \'Perennial Crop\' AND "HSG" = \'C\' THEN 88    
            WHEN "class_name" = \'Perennial Crop\' AND "HSG" = \'D\' THEN 91    
            WHEN "class_name" = \'Closed Forest\' AND "HSG" = \'A\' THEN 36    
            WHEN "class_name" = \'Closed Forest\' AND "HSG" = \'B\' THEN 60    
            WHEN "class_name" = \'Closed Forest\' AND "HSG" = \'C\' THEN 73    
            WHEN "class_name" = \'Closed Forest\' AND "HSG" = \'D\' THEN 79    
            WHEN "class_name" = \'Brush/Shrubs\' AND "HSG" = \'A\' THEN 30    
            WHEN "class_name" = \'Brush/Shrubs\' AND "HSG" = \'B\' THEN 58    
            WHEN "class_name" = \'Brush/Shrubs\' AND "HSG" = \'C\' THEN 71    
            WHEN "class_name" = \'Brush/Shrubs\' AND "HSG" = \'D\' THEN 78    
            WHEN "class_name" = \'Grassland\' AND "HSG" = \'A\' THEN 49    
            WHEN "class_name" = \'Grassland\' AND "HSG" = \'B\' THEN 69    
            WHEN "class_name" = \'Grassland\' AND "HSG" = \'C\' THEN 79    
            WHEN "class_name" = \'Grassland\' AND "HSG" = \'D\' THEN 84    
            WHEN "class_name" = \'Open/Barren\' AND "HSG" = \'A\' THEN 68    
            WHEN "class_name" = \'Open/Barren\' AND "HSG" = \'B\' THEN 79    
            WHEN "class_name" = \'Open/Barren\' AND "HSG" = \'C\' THEN 86    
            WHEN "class_name" = \'Open/Barren\' AND "HSG" = \'D\' THEN 89    
            WHEN "class_name" = \'Mangrove Forest\' THEN 100    
            WHEN "class_name" = \'Annual Crop\' AND "HSG" = \'A\' THEN 77    
            WHEN "class_name" = \'Annual Crop\' AND "HSG" = \'B\' THEN 86    
            WHEN "class_name" = \'Annual Crop\' AND "HSG" = \'C\' THEN 91    
            WHEN "class_name" = \'Annual Crop\' AND "HSG" = \'D\' THEN 94    
            WHEN "class_name" = \'Marshland/Swamp\' THEN 100    
            WHEN "class_name" = \'Fishpond\' THEN 100    
            ELSE NULL
            END
            """,
            'OUTPUT':'TEMPORARY_OUTPUT'}
            
        outputs['scs'] = processing.run("native:fieldcalculator", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

        # calculate area of each vector
        feedback.setCurrentStep(12)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT':outputs['scs'],
            'FIELD_NAME':'area_has',
            'FIELD_TYPE':0,
            'FIELD_LENGTH':255,
            'FIELD_PRECISION':255,
            'FORMULA':'$area * 0.0001',
            'OUTPUT':'TEMPORARY_OUTPUT'
            }
        outputs['scs'] = processing.run("native:fieldcalculator", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

        # Write to the final output
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            'curve_number',
            context,
            context.getMapLayer(outputs['scs']).fields(),
            context.getMapLayer(outputs['scs']).wkbType(),
            context.getMapLayer(outputs['scs']).sourceCrs()
        )

        features = context.getMapLayer(outputs['scs']).getFeatures()
        total = 100.0 / context.getMapLayer(outputs['scs']).featureCount() if context.getMapLayer(outputs['scs']).featureCount() else 0

        for current, feature in enumerate(features):
            if feedback.isCanceled():
                break
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            feedback.setProgress(int(current * total))

        results['curve_number'] = dest_id

        # Initialize pandas DataFrame -*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-

        # Create a Vector Layer for outputs['scs'] 
        scs_vector = outputs['scs']
        scs_fields = [f.name() for f in scs_vector.fields()] # Pandas column header
        scs_attrib = [f.attributes() for f in scs_vector.getFeatures()] # Pandas data

        # Save all scs_vector attributes to a Pandas DataFrame
        scs_df = pd.DataFrame(scs_attrib, columns=scs_fields, index=None)

        # convert all necessary columns to numericFormat
        scs_df['area_has'] = pd.to_numeric(scs_df['area_has'], errors='coerce')
        scs_df['CN'] = pd.to_numeric(scs_df['CN'], errors='coerce')
        scs_df['n_value'] = pd.to_numeric(scs_df['n_value'], errors='coerce')

        # Compute for the CN x Area
        scs_df['mult_CN-area'] = scs_df['CN'] * scs_df['area_has']

        # Compute for the Manning's n' x Area
        scs_df['mult_n-area'] = scs_df['n_value'] * scs_df['area_has']

        # WhiteBoxTools Portion --------------------------------------
        wbt_subbasin = outputs['fixed_subbasins']['OUTPUT']
        wbt_dem = parameters['wbt_dem']
        wbt_filled_dem = parameters['wbt_filled']

        # Get geometry type of wbt_subbasin and display as a string
        geometry_type_str = QgsWkbTypes.displayString(wbt_subbasin.wkbType())

        # Create a vector geometry for each feature in wbt_subbasin layer
        for fet in wbt_subbasin.getFeatures(): 
            # create a temporary vector layer
            vl = QgsVectorLayer(f"{geometry_type_str}?crs={wbt_subbasin.crs().authid()}", 'temp', 'memory') 
            pr = vl.dataProvider()
            pr.addAttributes(wbt_subbasin.fields())
            vl.updateFields()
            f = QgsFeature()
            f.setGeometry(fet.geometry())
            f.setAttributes(fet.attributes())
            pr.addFeature(f)
            vl.updateExtents()
            
            # --- WHITEBOXTOOLS ---
            # Clip watershed raster to a feature in the subbasins
            alg_params = {
                'input':wbt_dem,
                'polygons':vl,
                'maintain_dimensions':True,
                'output': os.path.join(wbt_file, 'tempRaster.tif')
                }
            wbt_clip = processing.run("wbt:ClipRasterToPolygon", alg_params, context=context, feedback=feedback)
            
            # calculate for the longest flow path
            alg_params = {
                'dem': wbt_filled_dem,
                'basins': wbt_clip['output'],
                'output': os.path.join(wbt_file, 'tempVector.shp')
                }
            wbt_longestPath = processing.run("wbt:LongestFlowpath", alg_params)

            # Save the longest flow path to a vector layer
            wbt_longestPath = QgsVectorLayer(wbt_longestPath['output'], 'tempPath', 'ogr')
            
            # Get the attributes of the wbt_longestPath
            wbt_LP_head = [f.name() for f in wbt_longestPath.fields()]
            wbt_LP = [f.attributes() for f in wbt_longestPath.getFeatures()]
            
            # save the longest flow path vector to a pandas DataFrame
            df_LP = pd.DataFrame(wbt_LP, columns= wbt_LP_head, index=None)
            
            # get the subbasin number of the current feature
            subbasinNumber = fet.attributes()[0]

            # get the longest flow path, its position and the ave slope of the subbasin
            longestFlowPathPosition = df_LP['LENGTH'].idxmax()
            longestFlowPath = df_LP.loc[longestFlowPathPosition, 'LENGTH']
            aveSlope = df_LP.loc[longestFlowPathPosition, 'AVG_SLOPE']

            """
            INSIDE FILTERED DATAFRAME
            """
            # Get the intersected vector layer
            filtered_df = scs_df[scs_df['subbasin-FID'] == subbasinNumber]

            # get sum of area_has, CN, n_value, ret-c, and run-c
            scs_area = filtered_df['area_has'].sum()
            w_cn = filtered_df['mult_CN-area'].sum() / scs_area # weighted
            w_nValue = filtered_df['mult_n-area'].sum() / scs_area # weighted

            #Compute for the Lag Time
            tc = (60 * ((longestFlowPath * 3.28084) ** 0.8) * ((1000 / w_cn) - 9) ** 0.7) / (1900 * (aveSlope ** 0.5))
            lag_time = max(tc, 5) # Sets the min. tc to 5mins

            # Store all available variables in the subbasin_list
            subbasin_list = [subbasinNumber, scs_area, w_cn, w_nValue, longestFlowPath, aveSlope, lag_time]

            # Append subbasin_list to basin_summary
            basin_summary.append(subbasin_list)

        # Initialize the column header names for the basin summary
        basin_header = ['Subbasin', 'area_has', 'CN', 'n-value', 'flowPath', 'slope', 'lag time'] # Column names for the Basin summary

        basin_df = pd.DataFrame(basin_summary, columns=basin_header, index=None) # save the list as a DataFrame
        basin_df.to_csv(os.path.join(wbt_file, 'basin_summary.csv')) # save the DataFrame as CSV

            
            
        return results 

    def name(self):
        return 'generate_cn'

    def displayName(self):
        return 'generate_cn'

    def group(self):
        return ''

    def groupId(self):
        return ''

    def createInstance(self):
        return generate_cn()
