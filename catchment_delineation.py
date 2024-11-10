"""
Model exported as python.
Name : catchment_delineation
Group : 
With QGIS : 33803
"""

from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterCrs
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterVectorDestination
from qgis.core import QgsProcessingParameterFeatureSink
from qgis.core import QgsExpression
import processing


class Catchment_delineation(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterCrs('crs', 'CRS', defaultValue='EPSG:4326'))
        self.addParameter(QgsProcessingParameterRasterLayer('dem', 'DEM', defaultValue=None))
        self.addParameter(QgsProcessingParameterNumber('minimum_area', 'Minimum Area', type=QgsProcessingParameterNumber.Double, minValue=0, maxValue=10000, defaultValue=50000))
        self.addParameter(QgsProcessingParameterVectorLayer('outfall', 'Outfall', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorDestination('Streams', 'Streams', optional=True, type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorDestination('Basin', 'Basin', type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink('Subbasins', 'Subbasins', type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(16, model_feedback)
        results = {}
        outputs = {}

        # fill sinks
        alg_params = {
            '-f': False,
            'GRASS_RASTER_FORMAT_META': None,
            'GRASS_RASTER_FORMAT_OPT': None,
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': None,
            'format': 0,  # grass
            'input': parameters['dem'],
            'areas': QgsProcessing.TEMPORARY_OUTPUT,
            'direction': QgsProcessing.TEMPORARY_OUTPUT,
            'output': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['FillSinks'] = processing.run('grass:r.fill.dir', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # reproject_dem
        alg_params = {
            'DATA_TYPE': 0,  # Use Input Layer Data Type
            'EXTRA': None,
            'INPUT': parameters['dem'],
            'MULTITHREADING': False,
            'NODATA': None,
            'OPTIONS': None,
            'RESAMPLING': 0,  # Nearest Neighbour
            'SOURCE_CRS': None,
            'TARGET_CRS': parameters['crs'],
            'TARGET_EXTENT': None,
            'TARGET_EXTENT_CRS': None,
            'TARGET_RESOLUTION': None,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Reproject_dem'] = processing.run('gdal:warpreproject', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # streams
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
            'basin': QgsProcessing.TEMPORARY_OUTPUT,
            'drainage': QgsProcessing.TEMPORARY_OUTPUT,
            'stream': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Streams'] = processing.run('grass:r.watershed', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # subbasins
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
            'output': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Subbasins'] = processing.run('grass:r.to.vect', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # Reproject Outfall
        alg_params = {
            'CONVERT_CURVED_GEOMETRIES': False,
            'INPUT': parameters['outfall'],
            'OPERATION': None,
            'TARGET_CRS': parameters['crs'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ReprojectOutfall'] = processing.run('native:reprojectlayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        # thin_streams
        alg_params = {
            'GRASS_RASTER_FORMAT_META': None,
            'GRASS_RASTER_FORMAT_OPT': None,
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': None,
            'input': outputs['Streams']['stream'],
            'iterations': 999,
            'output': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Thin_streams'] = processing.run('grass:r.thin', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # stream_vector
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
            'input': outputs['Thin_streams']['output'],
            'type': 0,  # line
            'output': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Stream_vector'] = processing.run('grass:r.to.vect', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        # snapped
        alg_params = {
            'BEHAVIOR': 1,  # Prefer closest point, insert extra vertices where required
            'INPUT': outputs['ReprojectOutfall']['OUTPUT'],
            'REFERENCE_LAYER': outputs['Stream_vector']['output'],
            'TOLERANCE': 200,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Snapped'] = processing.run('native:snapgeometries', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(8)
        if feedback.isCanceled():
            return {}

        # save snapped geom w coordinates
        alg_params = {
            'CALC_METHOD': 0,  # Layer CRS
            'INPUT': outputs['Snapped']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['SaveSnappedGeomWCoordinates'] = processing.run('qgis:exportaddgeometrycolumns', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(9)
        if feedback.isCanceled():
            return {}

        # y_coor
        alg_params = {
            'FIELD_LENGTH': 50,
            'FIELD_NAME': 'y_coor',
            'FIELD_PRECISION': 5,
            'FIELD_TYPE': 0,  # Decimal (double)
            'FORMULA': 'y(@geometry)\n',
            'INPUT': outputs['SaveSnappedGeomWCoordinates']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Y_coor'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(10)
        if feedback.isCanceled():
            return {}

        # x_coor
        alg_params = {
            'FIELD_LENGTH': 50,
            'FIELD_NAME': 'x_coor',
            'FIELD_PRECISION': 5,
            'FIELD_TYPE': 0,  # Decimal (double)
            'FORMULA': 'x(@geometry)\n',
            'INPUT': outputs['SaveSnappedGeomWCoordinates']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['X_coor'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(11)
        if feedback.isCanceled():
            return {}

        # basin
        alg_params = {
            'GRASS_RASTER_FORMAT_META': None,
            'GRASS_RASTER_FORMAT_OPT': None,
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': None,
            'coordinates': QgsExpression('aggregate(\n\tlayer:=  @x_coor_OUTPUT ,\n\taggregate:= \'max\',\n\texpression := "x_coor"\n\n)\n|| \',\' ||\naggregate(\n\tlayer:=  @y_coor_OUTPUT,\n\taggregate:= \'max\',\n\texpression := "y_coor"\n)').evaluate(),
            'input': outputs['Streams']['drainage'],
            'output': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Basin'] = processing.run('grass:r.water.outlet', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(12)
        if feedback.isCanceled():
            return {}

        # basin_vectorized
        alg_params = {
            '-b': False,
            '-s': True,
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
        results['Basin'] = outputs['Basin_vectorized']['output']

        feedback.setCurrentStep(13)
        if feedback.isCanceled():
            return {}

        # Clip
        alg_params = {
            'INPUT': outputs['Subbasins']['output'],
            'OVERLAY': outputs['Basin_vectorized']['output'],
            'OUTPUT': parameters['Subbasins']
        }
        outputs['Clip'] = processing.run('native:clip', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Subbasins'] = outputs['Clip']['OUTPUT']

        feedback.setCurrentStep(14)
        if feedback.isCanceled():
            return {}

        # clip_dem
        alg_params = {
            'ALPHA_BAND': False,
            'CROP_TO_CUTLINE': True,
            'DATA_TYPE': 0,  # Use Input Layer Data Type
            'EXTRA': None,
            'INPUT': parameters['dem'],
            'KEEP_RESOLUTION': False,
            'MASK': outputs['Basin_vectorized']['output'],
            'MULTITHREADING': False,
            'NODATA': None,
            'OPTIONS': None,
            'SET_RESOLUTION': False,
            'SOURCE_CRS': None,
            'TARGET_CRS': parameters['crs'],
            'TARGET_EXTENT': None,
            'X_RESOLUTION': None,
            'Y_RESOLUTION': None,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Clip_dem'] = processing.run('gdal:cliprasterbymasklayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(15)
        if feedback.isCanceled():
            return {}

        # detailed_streams
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
        return results

    def name(self):
        return 'catchment_delineation'

    def displayName(self):
        return 'catchment_delineation'

    def group(self):
        return ''

    def groupId(self):
        return ''

    def createInstance(self):
        return Catchment_delineation()
