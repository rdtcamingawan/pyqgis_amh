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
from qgis.core import QgsVectorLayer
from qgis.core import QgsRasterLayer
from qgis.core import QgsWkbTypes
from qgis.core import QgsFeature
from decimal import Decimal, getcontext
import processing
import os
import glob
import pandas as pd


class wbt_catchment(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        # Inputs
        self.addParameter(QgsProcessingParameterCrs('crs', 'CRS', defaultValue='EPSG:4326'))
        self.addParameter(QgsProcessingParameterRasterLayer('dem', 'DEM', defaultValue=None))
        self.addParameter(QgsProcessingParameterNumber('minimum_area', 'Minimum Area', type=QgsProcessingParameterNumber.Double, minValue=0, maxValue=10000, defaultValue=50000))
        self.addParameter(QgsProcessingParameterVectorLayer('outfall', 'Outfall', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('land_cover', 'Land Cover', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('soil_type', 'Soil Type', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
        self.addParameter(QgsProcessingParameterFolderDestination('temp_folder', 'Temp Folder')) # Destination Temp Folder for WBT ouptuts
        
    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(31, model_feedback)
        results = {}
        outputs = {}
        wbt_file = parameters['temp_folder']

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}
            
        # reproject_dem
        alg_params = {
            'DATA_TYPE': 0,  
            'EXTRA': None,
            'INPUT': parameters['dem'],
            'MULTITHREADING': False,
            'NODATA': None,
            'OPTIONS': None,
            'RESAMPLING': 0, 
            'SOURCE_CRS': None,
            'TARGET_CRS': parameters['crs'],
            'TARGET_EXTENT': None,
            'TARGET_EXTENT_CRS': None,
            'TARGET_RESOLUTION': None,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Reproject_dem'] = processing.run('gdal:warpreproject', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # Reproject Land Cover Layer
        feedback.setCurrentStep(2)
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
        feedback.setCurrentStep(3)
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
        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT':parameters['outfall'],
            'TARGET_CRS':parameters['crs'],
            'CONVERT_CURVED_GEOMETRIES':False,
            'OUTPUT':'TEMPORARY_OUTPUT'
        }
        outputs['reprojected_outfall'] = processing.run('native:reprojectlayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
                
        # Delineate watershed using WhiteBoxTools
        # delineating using WhiteBoxTools to solve for the 
        # longest flow path which will be used  
        # later in the watershed characterization
        # and rational method computation
        # The watershed and subbasin results shall also be used in the analysis

        # WBT Filled Dem
        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}
        
        alg_params = {
            'dem': outputs['Reproject_dem']['OUTPUT'],
            'fix_flats':True,
            'flat_increment':None,
            'output':os.path.join(wbt_file, 'wbt_filledWandandLiu.tif')
        }
        outputs['filledWangLiu'] = processing.run("wbt:FillDepressionsWangAndLiu", alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # WBT D8 Pointer
        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}
        
        alg_params = {
            'dem':outputs['filledWangLiu']['output'],
            'esri_pntr':False,
            'output': os.path.join(wbt_file, 'wbt_d8pointer.tif')
        }
        outputs['d8Pointer'] = processing.run("wbt:D8Pointer", alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # WBT D8 Flow Accumulation
        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'input': outputs['filledWangLiu']['output'],
            'out_type':0,
            'log':False,
            'clip':False,
            'pntr':False,
            'esri_pntr':False,
            'output':os.path.join(wbt_file, 'wbt_flowaccum.tif')
        }
        outputs['d8FlowAccum'] = processing.run("wbt:D8FlowAccumulation", alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # WBT Extract Streams
        feedback.setCurrentStep(8)
        if feedback.isCanceled():
            return {} 

        alg_params = {
            'flow_accum':outputs['d8FlowAccum']['output'],
            'threshold':10000,
            'zero_background':False,
            'output':os.path.join(wbt_file, 'wbt_streams-raster.tif')
        }
        outputs['wbt_streams'] = processing.run("wbt:ExtractStreams", alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # WBT Raster Streams to Vector
        feedback.setCurrentStep(9)
        if feedback.isCanceled():
            return {}
        
        alg_params = {
            'streams': outputs['wbt_streams']['output'],
            'd8_pntr':outputs['d8Pointer']['output'],
            'esri_pntr':False,
            'output':os.path.join(wbt_file, 'wbt_stream-vector.shp')
        }
        outputs['wbt_exStreams'] = processing.run("wbt:RasterStreamsToVector", alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Streams'] = outputs['wbt_exStreams']['output']

        # WBT Snap Pour Points
        feedback.setCurrentStep(10)
        if feedback.isCanceled():
            return {}
        
        alg_params = {
            'pour_pts': outputs['reprojected_outfall']['OUTPUT'],
            'streams':outputs['wbt_streams']['output'],
            'snap_dist':50,
            'output':os.path.join(wbt_file, 'wbt_snapped_outfall.shp')
        }
        outputs['jenson_snapped'] = processing.run("wbt:JensonSnapPourPoints", alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # WBT Delineate Watershed
        feedback.setCurrentStep(11)
        if feedback.isCanceled():
            return {}
        
        alg_params = {
            'd8_pntr':outputs['d8Pointer']['output'],
            'pour_pts': outputs['jenson_snapped']['output'],
            'esri_pntr':False,
            'output':os.path.join(wbt_file, 'wbt_watershed.tif')
        }
        outputs['wbt_watershed'] = processing.run("wbt:Watershed", alg_params, context=context, feedback=feedback)

        # Convert raster watershed to vector polygon
        feedback.setCurrentStep(12)
        if feedback.isCanceled():
            return {}
        alg_params = {
            'input':outputs['wbt_watershed']['output'],
            'output':os.path.join(wbt_file, 'wbt_vector_basin.shp')   
        }
        outputs['wbt_vector_basin'] = processing.run("wbt:RasterToVectorPolygons",alg_params, context=context, feedback=feedback)
                
        # Delineate the subbasins
        feedback.setCurrentStep(13)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'd8_pntr':outputs['d8Pointer']['output'],
            'streams':outputs['wbt_streams']['output'],
            'esri_pntr':False,
            'output':os.path.join(wbt_file,'subbasins.tif')
        }
        outputs['wbt_subbasins'] = processing.run("wbt:Subbasins", alg_params, context=context, feedback=feedback)

        # Clipped the raster subbasins to the vectorized WBT watershed
        feedback.setCurrentStep(14)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'input': outputs['wbt_subbasins']['output'],
            'polygons':outputs['wbt_vector_basin']['output'],
            'maintain_dimensions':True,
            'output':os.path.join(wbt_file, 'wbt_clipped_subbasins.tif')
        }
        outputs['wbt_clipped_subbasins'] = processing.run("wbt:ClipRasterToPolygon",alg_params, context=context, feedback=feedback)

        # Convert clipped raster subbasins to vector polygon
        feedback.setCurrentStep(15)
        if feedback.isCanceled():
            return {}
        alg_params = {
            'input':outputs['wbt_clipped_subbasins']['output'],
            'output':os.path.join(wbt_file, 'wbt_vector_subbasins.shp')   
        }
        outputs['wbt_vector_subbasins'] = processing.run("wbt:RasterToVectorPolygons",alg_params, context=context, feedback=feedback)
               
        # This is the start of watershed characterization
        # All child algorithm output shall be stored in the outputs['scs'] variable
        # This is because they are all temporary outputs and I see no need to store them in different variables every time.
        # So I am just re-writing the outputs['scs'] variable each step.

        #fix geometries
        # fix basins
        feedback.setCurrentStep(16)
        if feedback.isCanceled():
            return {}
            
        alg_params = {
             'INPUT': outputs['wbt_vector_subbasins']['output'], 
             'METHOD': 0, 
             'OUTPUT': 'TEMPORARY_OUTPUT'
             }
        outputs['fixed_subbasins'] = processing.run("native:fixgeometries", alg_params, context=context, feedback=feedback, is_child_algorithm=True)      

        # fix land
        feedback.setCurrentStep(17)
        if feedback.isCanceled():
            return {}
            
        alg_params = {
             'INPUT': outputs['reprojected_lc']['OUTPUT'], 
             'METHOD': 0, 
             'OUTPUT': 'TEMPORARY_OUTPUT'
             }
        outputs['fixed_lc'] = processing.run("native:fixgeometries", alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # fix soil
        feedback.setCurrentStep(18)
        if feedback.isCanceled():
            return {}

        alg_params = {
             'INPUT': outputs['reprojected_soil']['OUTPUT'], 
             'METHOD': 0, 
             'OUTPUT': 'TEMPORARY_OUTPUT'
        }
        outputs['fixed_soil'] = processing.run("native:fixgeometries", alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        #intersect basin - land cover
        feedback.setCurrentStep(19)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT': outputs['fixed_lc']['OUTPUT'], 
            'OVERLAY': outputs['fixed_subbasins']['OUTPUT'], # This is the clipped subbasins output
            'INPUT_FIELDS':['class_name'], # This retains the class_name field in the land cover
            'OVERLAY_FIELDS':['fid'], # This retains the `name` field in the basins vector
            'OVERLAY_FIELDS_PREFIX':'subbasin-',
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }
        outputs['scs'] = processing.run("native:intersection", alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        #intersect basin - land - soil
        feedback.setCurrentStep(20)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT': outputs['fixed_soil']['OUTPUT'], 
            'OVERLAY': outputs['scs']['OUTPUT'],
            'INPUT_FIELDS':['descriptio','type'], # This retains the `descriptio` and ` type` in the soil layer input
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }   
        outputs['scs'] = processing.run("native:intersection", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

        # add retardance coefficient
        feedback.setCurrentStep(21)
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
        feedback.setCurrentStep(22)
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
        feedback.setCurrentStep(23)
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
        feedback.setCurrentStep(24)
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
        feedback.setCurrentStep(25)
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
        feedback.setCurrentStep(26)
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
        feedback.setCurrentStep(27)
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
        outputs['scs'] = processing.run("native:fieldcalculator", alg_params, context=context, feedback=feedback)['OUTPUT']

        # This part saves the attributes of the outputs['scs'] layer to a pandas DataFrame
        # Saving this to a Pandas DataFrame will allow the code to exit of PyQgis and do Pandas functions instead
        feedback.setCurrentStep(28)
        if feedback.isCanceled():
            return {}
        
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
        scs_df['ret-c'] = pd.to_numeric(scs_df['ret-c'], errors='coerce')

        # Compute for the CN x Area
        scs_df['mult_CN-area'] = scs_df['CN'] * scs_df['area_has']

        # Compute for the Manning's n' x Area
        scs_df['mult_n-area'] = scs_df['n_value'] * scs_df['area_has']

        # Compute for the Retardance Coefficient x Area
        scs_df['mult_retC-area'] = scs_df['ret-c'] * scs_df['area_has']
        
        # Initialize basin_summary list for saving to csv later
        basin_summary = []

        feedback.setCurrentStep(29)
        if feedback.isCanceled():
            return {}
        # Create geometry for WhiteBoxTools
        wbt_subbasin = QgsVectorLayer(outputs['wbt_vector_subbasins']['output'], "wbt_subbasin", 'ogr')
        wbt_dem = QgsRasterLayer(outputs['wbt_watershed']['output'], 'wbt_dem')
        wbt_filled_dem = QgsRasterLayer(outputs['filledWangLiu']['output'], 'wbt_filled_dem')
        
        # Get geometry type of wbt_subbasin and display as a string
        geometry_type_str = QgsWkbTypes.displayString(wbt_subbasin.wkbType())
        
        feedback.setCurrentStep(30)
        if feedback.isCanceled():
            return {}
        # create a vector geometry for each feature in wbt_subbasin layer
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

            # Get the intersected vector layer
            filtered_df = scs_df[scs_df['subbasin-FID'] == subbasinNumber]
            
            # get sum of area_has, CN, n_value, and ret-c
            scs_area = filtered_df['area_has'].sum()
            scs_cn = filtered_df['mult_CN-area'].sum()
            scs_nValue = filtered_df['mult_n-area'].sum()
            scs_retC = filtered_df['mult_retC-area'].sum()
            
            # get the weighted CN, n_value, and retardance coefficient
            w_cn = scs_cn / scs_area
            w_nValue = scs_nValue / scs_area
            w_retC = scs_retC / scs_area

            """


            This section determines which method is applicable for the computation of the time of concentration.
            It will then solves for the appropriate time of concentration. 


            """
            # Define all global variables needed for each rational method functions

            a, d, b = 1666.19, 7.70 ,-0.65
            rc = w_retC	
            c = 0.43
            n = w_nValue
            cn = w_cn
            l, s, area = longestFlowPath * 3.28084, aveSlope/100, scs_area * 0.01
            _threshold = 10e-10

            # Determine what method should be used
            def rational_method(slope, area):
                area_acres = area * 247.105
                if 3 <= slope <= 10 and 1 <= area_acres <= 112:
                    return kirpich(a, d, b, l, s, c, area)
                elif slope > 0 and area_acres < 5:  # Condition for Izzard (1946)
                    return izzard(a, d, b, rc, l, slope, c, area, _threshold)
                elif slope > 0 and area_acres > 112:  # Condition for Federal Aviation Admin. (1970)
                    return faa(a, d, b, rc, l, slope, c, area)
                elif slope >= 0 and area_acres:  # Condition for Kinematic Wave Formulas
                    return kinematic(a, d, b, n, l, slope, c, area, _threshold)
                elif slope <= 2000 and area_acres < 3:  # Condition for SCS Lag Equation (1975)
                    return scs(a, d, b, cn, l, slope, c, area)
                else:
                    return "No applicable method"
            
            def kirpich(a, d, b, length, slope, c, area):
                tc = 0.0078 * length ** 0.77 * slope**-0.385
                i = a * (tc + d)**b
                q = 0.278 * c * i * area
                return q, tc

            def faa(a, d, b, rc, length, slope, c, area):
                slope = slope * 100
                tc = (1.8 * (1.1 - rc) * length**0.5) / slope**0.33
                i = a * (tc + d) **b
                q = 0.278 * c * i * area
                return q, tc

            def scs(a, d, b, cn, length, slope, c, area):
                slope = slope * 100
                tc = (100 * length** 0.8 * ((1000 / cn)-9)**0.7) / (1900 * slope**0.5)
                i = a*(tc+d)**b
                q = 0.278 * c * i * area
                return q, tc
            
            def i_izzard(a, d, b, length, slope, c,i_iter):
                tc = (41.025 * ((0.0007 * i_iter) + c) * length**0.33) / (slope**(1/3) * i_iter**(2/3))
                i_calc_mm = a * (tc + d)**b
                i_calc = i_calc_mm / 10 / 2.54
                return i_calc , i_iter

            def izzard(a, d, b, rc, length, slope, c, area, _threshold):
                lower = 0
                upper = 5000
                solve = (lower + upper) / 2
                threshold = i_izzard(solve)[0] - solve  # Compute initial threshold
                
                while abs(threshold) >= _threshold:        
                    if threshold < 0:
                        upper = solve
                    elif threshold > 0:
                        lower = solve
                    # Update solve based on new bounds
                    solve = (lower + upper) / 2
                    # Recompute threshold with updated solve
                    threshold = i_izzard(solve)[0] - solve

                tc = (41.025 * ((0.0007 * solve) + rc) * length**0.33) / (slope**(1/3) * solve**(2/3))
                i = a * (tc+d) **b
                q = 0.278 * c * i * area
                
                return q, tc

            def i_kinematic(a, d, b, length, slope, n, i_iter):
                # Set precision for calculations
                getcontext().prec = 50  # High precision for critical calculations

                # Convert inputs to Decimal
                a = Decimal(a)
                d = Decimal(d)
                b = Decimal(b)
                length = Decimal(length)
                slope = Decimal(slope)
                n = Decimal(n)
                i_iter = Decimal(i_iter)

                # Perform calculations
                tc = (Decimal("0.94") * (length ** Decimal("0.6") * n ** Decimal("0.6"))) / (
                    i_iter ** Decimal("0.4") * slope ** Decimal("0.33")
                )
                i_calc_mm = a * (tc + d) ** b
                i_calc = i_calc_mm / Decimal("10") / Decimal("2.54")
                return i_calc, i_iter

            def kinematic(a, d, b, n, length, slope, c, area, _threshold):
                # Set precision for calculations
                getcontext().prec = 50

                # Convert inputs to Decimal
                a = Decimal(a)
                d = Decimal(d)
                b = Decimal(b)
                n = Decimal(n)
                length = Decimal(length)
                slope = Decimal(slope)
                c = Decimal(c)
                area = Decimal(area)
                _threshold = Decimal(_threshold)

                lower = Decimal("0")
                upper = Decimal("1000")
                solve = (lower + upper) / Decimal("2")
                threshold = i_kinematic(a, d, b, length, slope, n, solve)[0] - solve

                threshold_plot = []
                while abs(threshold) >= _threshold:
                    if threshold < 0:
                        upper = solve
                    elif threshold > 0:
                        lower = solve
                    solve = (lower + upper) / Decimal("2")
                    threshold = i_kinematic(a, d, b, length, slope, n, solve)[0] - solve
                    threshold_plot.append(threshold)

                tc = (Decimal("0.94") * (length ** Decimal("0.6") * n ** Decimal("0.6"))) / (
                    solve ** Decimal("0.4") * slope ** Decimal("0.33")
                )
                i = a * (tc + d) ** b
                q = Decimal("0.278") * c * i * area

                return float(q), float(tc)

            timeConc = rational_method(slope=aveSlope, area= scs_area * 0.01)[1]
            peakDischarge = rational_method(slope=aveSlope, area= scs_area * 0.01)[0]
            
            # save all data to a list and append to basin_summary list
            subbasin_list = [subbasinNumber, scs_area, w_cn, w_nValue, w_retC, longestFlowPath, aveSlope, timeConc, peakDischarge]
            basin_summary.append(subbasin_list)
        
        feedback.setCurrentStep(31)
        if feedback.isCanceled():
            return {}
        
        basin_header = ['Subbasin', 'area_has', 'CN', 'n-value', 'ret-c', 'LP', 'slope', 'timeOfConc', 'peakQ'] # Column names
        basin_df = pd.DataFrame(basin_summary, columns=basin_header, index=None) # save the list as a DataFrame
        basin_df.to_csv(os.path.join(wbt_file, 'basin_summary.csv')) # save the DataFrame as CSV

        return results

    def name(self):
        return 'wbt_catchment'

    def displayName(self):
        return 'wbt_catchment'

    def group(self):
        return ''

    def groupId(self):
        return ''

    def createInstance(self):
        return wbt_catchment()
