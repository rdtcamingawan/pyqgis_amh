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
import processing
import os
import glob


class grass_catchment(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        # Inputs
        self.addParameter(QgsProcessingParameterCrs('crs', 'CRS', defaultValue='EPSG:4326'))
        self.addParameter(QgsProcessingParameterRasterLayer('dem', 'DEM', defaultValue=None))
        self.addParameter(QgsProcessingParameterNumber('minimum_area', 'Minimum Area', type=QgsProcessingParameterNumber.Double, minValue=0, maxValue=10000, defaultValue=50000))
        self.addParameter(QgsProcessingParameterVectorLayer('outfall', 'Outfall', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('land_cover', 'Land Cover', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('soil_type', 'Soil Type', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
        # Outputs
        self.addParameter(QgsProcessingParameterVectorDestination('Streams', 'Streams', optional=True, type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorDestination('Basin', 'Basin', type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink('Subbasins', 'Subbasins', type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue=None))


    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(28, model_feedback)
        results = {}
        outputs = {}

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
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }
        outputs['Reproject_dem'] = processing.run('gdal:warpreproject', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

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

        alg_params = {
            'INPUT':parameters['outfall'],
            'TARGET_CRS':parameters['crs'],
            'CONVERT_CURVED_GEOMETRIES':False,
            'OUTPUT':'TEMPORARY_OUTPUT'
        }
        outputs['reprojected_outfall'] = processing.run('native:reprojectlayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}
        
        # grass: fill sinks
        alg_params = {
            '-f': False,
            'GRASS_RASTER_FORMAT_META': None,
            'GRASS_RASTER_FORMAT_OPT': None,
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': None,
            'format': 0,  # grass
            'input': outputs['Reproject_dem']['OUTPUT'],
            'areas': 'TEMPORARY_OUTPUT',
            'direction': 'TEMPORARY_OUTPUT',
            'output': 'TEMPORARY_OUTPUT'
        }
        outputs['FillSinks'] = processing.run('grass:r.fill.dir', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        # grass: r.watershed for streams
        alg_params = {
            '-4': False,
            '-a': False,
            '-b': False,
            '-m': False,
            '-s': False,
            'GRASS_RASTER_FORMAT_META': None,
            'GRASS_RASTER_FORMAT_OPT': None,
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': None,
            'blocking': None,
            'convergence': 5,
            'depression': None,
            'disturbed_land': None,
            'elevation': outputs['FillSinks']['output'],
            'flow': None,
            'max_slope_length': None,
            'memory': 300,
            'threshold': parameters['minimum_area'],
            'basin': 'TEMPORARY_OUTPUT',
            'drainage': 'TEMPORARY_OUTPUT',
            'stream': 'TEMPORARY_OUTPUT'
        }
        outputs['Streams'] = processing.run('grass:r.watershed', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # grass: r.to.vect 
        # convert subbasins rasters to vectors
        alg_params = {
            '-b': False,
            '-s': False,
            '-t': False,
            '-v': False,
            '-z': False,
            'GRASS_OUTPUT_TYPE_PARAMETER': 0,  # auto
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': None,
            'GRASS_VECTOR_DSCO': None,
            'GRASS_VECTOR_EXPORT_NOCAT': False,
            'GRASS_VECTOR_LCO': None,
            'column': 'value',
            'input': outputs['Streams']['basin'],
            'type': 2,  # area
            'output': 'TEMPORARY_OUTPUT'
        }
        outputs['Subbasins'] = processing.run('grass:r.to.vect', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        # grass: r.thin
        # thin stream rasters before converting to vector
        # for smoother corners
        alg_params = {
            'GRASS_RASTER_FORMAT_META': None,
            'GRASS_RASTER_FORMAT_OPT': None,
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': None,
            'input': outputs['Streams']['stream'],
            'iterations': 999,
            'output': 'TEMPORARY_OUTPUT'
        }
        outputs['Thin_streams'] = processing.run('grass:r.thin', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(8)
        if feedback.isCanceled():
            return {}

        # grass: r.to.vect
        # convert thinned stream rasters to vector
        alg_params = {
            '-b': False,
            '-s': False,
            '-t': False,
            '-v': False,
            '-z': False,
            'GRASS_OUTPUT_TYPE_PARAMETER': 0,
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': None,
            'GRASS_VECTOR_DSCO': None,
            'GRASS_VECTOR_EXPORT_NOCAT': False,
            'GRASS_VECTOR_LCO': None,
            'column': 'value',
            'input': outputs['Thin_streams']['output'],
            'type': 0,  # line
            'output': 'TEMPORARY_OUTPUT'
        }
        outputs['Stream_vector'] = processing.run('grass:r.to.vect', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(9)
        if feedback.isCanceled():
            return {}
        
        # snap the reprojected outfall
        # to the nearest stream vector
        alg_params = {
            'BEHAVIOR': 1,  # Prefer closest point, insert extra vertices where required
            'INPUT': outputs['reprojected_outfall']['OUTPUT'],
            'REFERENCE_LAYER': outputs['Stream_vector']['output'],
            'TOLERANCE': 200,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }
        outputs['Snapped'] = processing.run('native:snapgeometries', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(10)
        if feedback.isCanceled():
            return {}

        # get the x,y coordinates of the snapped outfall
        # this is in preparation for delineating watershed
        # using the grass: r.water.outlet command
        pt_layer = QgsProcessingUtils.mapLayerFromString(outputs['Snapped']['OUTPUT'], context)
        pt = pt_layer.getGeometry(1).asPoint()

        feedback.setCurrentStep(11)
        if feedback.isCanceled():
            return {}

        # grass: r.water.outlet
        # delineate the watershed
        alg_params = {
            'GRASS_RASTER_FORMAT_META': None,
            'GRASS_RASTER_FORMAT_OPT': None,
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': None,
            'coordinates': f'{pt.x()}, {pt.y()}',
            'input': outputs['Streams']['drainage'],
            'output': 'TEMPORARY_OUTPUT'
        }
        outputs['Basin'] = processing.run('grass:r.water.outlet', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(12)
        if feedback.isCanceled():
            return {}

        # grass: r.to.vect
        # convert basin raster to vector
        alg_params = {
            '-b': False,
            '-s': False,
            '-t': False,
            '-v': False,
            '-z': False,
            'GRASS_OUTPUT_TYPE_PARAMETER': 0,  # auto
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': None,
            'GRASS_VECTOR_DSCO': None,
            'GRASS_VECTOR_EXPORT_NOCAT': False,
            'GRASS_VECTOR_LCO': None,
            'column': 'value',
            'input': outputs['Basin']['output'],
            'type': 2,  # area
            'output': parameters['Basin']
        }
        outputs['Basin_vectorized'] = processing.run('grass:r.to.vect', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        
        feedback.setCurrentStep(13)
        if feedback.isCanceled():
            return {}
            
        # fix geometries
        # fix subbasins geometry
        alg_params = {
            'INPUT': outputs['Subbasins']['output'],
            'METHOD':1,
            'OUTPUT':'TEMPORARY_OUTPUT'}
        outputs['fixed_subbasins'] = processing.run("native:fixgeometries", alg_params, context = context, feedback=feedback)
        
        feedback.setCurrentStep(14)
        if feedback.isCanceled():
            return {}
        
        # fix basin geometry
        alg_params = {'INPUT': outputs['Basin_vectorized']['output'],
            'METHOD':1,
            'OUTPUT':'TEMPORARY_OUTPUT'}
        outputs['fixed_basins'] = processing.run("native:fixgeometries", alg_params, context = context, feedback=feedback)
        results['Basin'] = outputs['fixed_basins']['OUTPUT']
        
        feedback.setCurrentStep(15)
        if feedback.isCanceled():
            return {}

        # clip the subbasins to only the basin extents
        alg_params = {
            'INPUT': outputs['fixed_subbasins']['OUTPUT'],
            'OVERLAY': outputs['fixed_basins']['OUTPUT'],
            'OUTPUT': parameters['Subbasins']
        }
        outputs['Clip'] = processing.run('native:clip', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Subbasins'] = outputs['Clip']['OUTPUT']
        
        # create a name field for the cliped subbasins
        alg_params = {
            'INPUT': outputs['Clip']['OUTPUT'],
            'FIELD_NAME':'name',
            'FIELD_TYPE':2,
            'FIELD_LENGTH':255,
            'FIELD_PRECISION':255,
            'FORMULA':'@row_number',
            'OUTPUT':'TEMPORARY_OUTPUT'
            }
        outputs['clipped_subbasins'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(16)
        if feedback.isCanceled():
            return {}

        # clip the input dem
        # to be used for grass: r.stream.extract
        alg_params = {
            'ALPHA_BAND': False,
            'CROP_TO_CUTLINE': True,
            'DATA_TYPE': 0,  # Use Input Layer Data Type
            'EXTRA': None,
            'INPUT': parameters['dem'],
            'KEEP_RESOLUTION': False,
            'MASK': outputs['fixed_basins']['OUTPUT'],
            'MULTITHREADING': False,
            'NODATA': None,
            'OPTIONS': None,
            'SET_RESOLUTION': False,
            'SOURCE_CRS': None,
            'TARGET_CRS': parameters['crs'],
            'TARGET_EXTENT': None,
            'X_RESOLUTION': None,
            'Y_RESOLUTION': None,
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }
        outputs['Clip_dem'] = processing.run('gdal:cliprasterbymasklayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        
        feedback.setCurrentStep(17)
        if feedback.isCanceled():
            return {}

        # grass: r.stream.extract
        # extract vector streams
        # using this command allows for a more detailed stream resolution without
        # repeating the r.watershed -> r.to.vect command
        # this simply divides the input threshold by 100 for the stream resolution
        alg_params = {
            'GRASS_OUTPUT_TYPE_PARAMETER': 2,  # line
            'GRASS_RASTER_FORMAT_META': None,
            'GRASS_RASTER_FORMAT_OPT': None,
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': None,
            'GRASS_VECTOR_DSCO': None,
            'GRASS_VECTOR_EXPORT_NOCAT': False,
            'GRASS_VECTOR_LCO': None,
            'accumulation': None,
            'd8cut': None,
            'depression': None,
            'elevation': outputs['Clip_dem']['OUTPUT'],
            'memory': 300,
            'mexp': 0,
            'stream_length': 0,
            'threshold': QgsExpression(' @minimum_area /100').evaluate(),
            'stream_vector': parameters['Streams']
        }
        outputs['Detailed_streams'] = processing.run('grass:r.stream.extract', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Streams'] = outputs['Detailed_streams']['stream_vector']

        # This is the start of watershed characterization
        # all child algorithm output shall be stored in the outputs['scs'] variable
        # this is because they are all temporary output and there I see no need to store it in diffferent variable everytime.
        # So I am just re-writing the outputs['scs'] variable each step.

        #fix geometries
        # fix basins
        alg_params = {
             'INPUT': outputs['clipped_subbasins']['OUTPUT'], 
             'METHOD': 0, 
             'OUTPUT': 'TEMPORARY_OUTPUT'
             }
        outputs['fixed_subbasins'] = processing.run("native:fixgeometries", alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(18)
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
        feedback.setCurrentStep(19)
        if feedback.isCanceled():
            return {}

        alg_params = {
             'INPUT': outputs['reprojected_soil']['OUTPUT'], 
             'METHOD': 0, 
             'OUTPUT': 'TEMPORARY_OUTPUT'
             }
        outputs['fixed_soil'] = processing.run("native:fixgeometries", alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        #intersect basin - land cover
        feedback.setCurrentStep(20)
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
        feedback.setCurrentStep(21)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'INPUT': outputs['fixed_soil']['OUTPUT'], 
            'OVERLAY': outputs['scs']['OUTPUT'],
            'INPUT_FIELDS':['descriptio','type'], # This retains the `descriptio` and ` type` in the soil layer input
            'OUTPUT': 'TEMPORARY_OUTPUT'}   
        outputs['scs'] = processing.run("native:intersection", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

        # add retardance coefficient
        feedback.setCurrentStep(22)
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
        feedback.setCurrentStep(23)
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
        feedback.setCurrentStep(24)
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
        feedback.setCurrentStep(25)
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
        feedback.setCurrentStep(26)
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
        feedback.setCurrentStep(27)
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
        feedback.setCurrentStep(28)
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
        outputs['scs'] = processing.runAndLoadResults("native:fieldcalculator", alg_params, context=context, feedback=feedback)['OUTPUT']
            
        return results 

    def name(self):
        return 'grass_catchment'

    def displayName(self):
        return 'grass_catchment'

    def group(self):
        return ''

    def groupId(self):
        return ''

    def createInstance(self):
        return grass_catchment()
