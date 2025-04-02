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
import processing


class generate_cn(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        # Inputs
        self.addParameter(QgsProcessingParameterCrs('crs', 'CRS', defaultValue='EPSG:32651'))
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
                WHEN "class_name" = 'Brush-Shrubs' THEN 'Closely clipped sod'    
                WHEN "class_name" = 'Grassland' THEN 'Closely clipped sod'    
                WHEN "class_name" = 'Open/Barren' THEN 'Concrete'    
                WHEN "class_name" = 'Mangrove Forest' THEN 'Dense bluegrass turf'    
                WHEN "class_name" = 'Annual Crop' THEN 'Dense bluegrass turf'    
                WHEN "class_name" = 'Marshland Swamp' THEN 'Dense bluegrass turf'    
                WHEN "class_name" = 'Fishpond' THEN 'Concrete'
                WHEN "class_name" = 'Waterway' THEN 'Concrete'
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
                WHEN "class_name" = 'Built-up' THEN 'AS'    
                WHEN "class_name" = 'Built-up' THEN 'CN'    
                WHEN "class_name" = 'Open/Barren' THEN 'GPF'    
                WHEN "class_name" = 'Grassland' THEN 'GPA'   
                WHEN "class_name" = 'Grassland' THEN 'GPS'    
                WHEN "class_name" = 'Brush/Shrubs' THEN 'GFF'    
                WHEN "class_name" = 'Brush/Shrubs' THEN 'GFA'  
                WHEN "class_name" = 'Brush-Shrubs' THEN 'GFA'
                WHEN "class_name" = 'Brush/Shrubs' THEN 'GFS'    
                WHEN "class_name" = 'Open Forest' THEN 'GGF'    
                WHEN "class_name" = 'Open Forest' THEN 'GGA'    
                WHEN "class_name" = 'Open Forest' THEN 'GGS'    
                WHEN "class_name" = 'Perennial Crop' THEN 'CLF'    
                WHEN "class_name" = 'Perennial Crop' THEN 'CLA'    
                WHEN "class_name" = 'Perennial Crop' THEN 'CLS'    
                WHEN "class_name" = 'Annual Crop' THEN 'PRF'    
                WHEN "class_name" = 'Annual Crop' THEN 'PRA'   
                WHEN "class_name" = 'Annual Crop' THEN 'PRS'    
                WHEN "class_name" = 'Mangrove Forest' THEN 'FWF'    
                WHEN "class_name" = 'Closed Forest' THEN 'FWA'    
                WHEN "class_name" = 'Closed Forest' THEN 'FWS'
                WHEN "class_name" = 'Inland Water' THEN 'Water'
                WHEN "class_name" = 'Marshland/Swamp' THEN 'Water'
                WHEN "class_name" = 'Fishpond' THEN 'Water'
                WHEN "class_name" = 'Waterway' THEN 'Water'
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
                    WHEN "class_name" = 'Built-up' THEN 0.014    
                    WHEN "class_name" = 'Inland Water' THEN 0.035    
                    WHEN "class_name" = 'Open Forest' THEN 0.035    
                    WHEN "class_name" = 'Perennial Crop' THEN 0.045    
                    WHEN "class_name" = 'Closed Forest' THEN 0.12    
                    WHEN "class_name" = 'Brush/Shrubs' THEN 0.05
                    WHEN "class_name" = 'Brush-Shrubs' THEN 0.05
                    WHEN "class_name" = 'Grassland' THEN 0.03    
                    WHEN "class_name" = 'Open/Barren' THEN 0.02    
                    WHEN "class_name" = 'Mangrove Forest' THEN 0.035    
                    WHEN "class_name" = 'Annual Crop' THEN 0.045    
                    WHEN "class_name" = 'Marshland/Swamp' THEN 0.035    
                    WHEN "class_name" = 'Fishpond' THEN 0.035 
                    WHEN "class_name" = 'Waterway' THEN 0.035      
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
                WHEN "class_name" = 'Built-up' AND "HSG" = 'A' THEN 98    
                WHEN "class_name" = 'Built-up' AND "HSG" = 'B' THEN 98    
                WHEN "class_name" = 'Built-up' AND "HSG" = 'C' THEN 98    
                WHEN "class_name" = 'Built-up' AND "HSG" = 'D' THEN 98    
                WHEN "class_name" = 'Inland Water' THEN 100    
                WHEN "class_name" = 'Open Forest' AND "HSG" = 'A' THEN 36    
                WHEN "class_name" = 'Open Forest' AND "HSG" = 'B' THEN 60    
                WHEN "class_name" = 'Open Forest' AND "HSG" = 'C' THEN 73   
                WHEN "class_name" = 'Open Forest' AND "HSG" = 'D' THEN 79    
                WHEN "class_name" = 'Perennial Crop' AND "HSG" = 'A' THEN 67    
                WHEN "class_name" = 'Perennial Crop' AND "HSG" = 'B' THEN 78    
                WHEN "class_name" = 'Perennial Crop' AND "HSG" = 'C' THEN 85    
                WHEN "class_name" = 'Perennial Crop' AND "HSG" = 'D' THEN 89    
                WHEN "class_name" = 'Closed Forest' AND "HSG" = 'A' THEN 25    
                WHEN "class_name" = 'Closed Forest' AND "HSG" = 'B' THEN 55    
                WHEN "class_name" = 'Closed Forest' AND "HSG" = 'C' THEN 70    
                WHEN "class_name" = 'Closed Forest' AND "HSG" = 'D' THEN 77    
                WHEN "class_name" = 'Brush/Shrubs' AND "HSG" = 'A' THEN 49    
                WHEN "class_name" = 'Brush/Shrubs' AND "HSG" = 'B' THEN 69   
                WHEN "class_name" = 'Brush/Shrubs' AND "HSG" = 'C' THEN 79    
                WHEN "class_name" = 'Brush/Shrubs' AND "HSG" = 'D' THEN 84
                WHEN "class_name" = 'Grassland' AND "HSG" = 'A' THEN 49
                WHEN "class_name" = 'Grassland' AND "HSG" = 'B' THEN 69    
                WHEN "class_name" = 'Grassland' AND "HSG" = 'C' THEN 79    
                WHEN "class_name" = 'Grassland' AND "HSG" = 'D' THEN 84    
                WHEN "class_name" = 'Open/Barren' AND "HSG" = 'A' THEN 68    
                WHEN "class_name" = 'Open/Barren' AND "HSG" = 'B' THEN 79    
                WHEN "class_name" = 'Open/Barren' AND "HSG" = 'C' THEN 86    
                WHEN "class_name" = 'Open/Barren' AND "HSG" = 'D' THEN 89    
                WHEN "class_name" = 'Mangrove Forest' THEN 100
                WHEN "class_name" = 'Annual Crop' AND "HSG" = 'A' THEN 63
                WHEN "class_name" = 'Annual Crop' AND "HSG" = 'B' THEN 75    
                WHEN "class_name" = 'Annual Crop' AND "HSG" = 'C' THEN 83    
                WHEN "class_name" = 'Annual Crop' AND "HSG" = 'D' THEN 87    
                WHEN "class_name" = 'Marshland/Swamp' THEN 100    
                WHEN "class_name" = 'Fishpond' THEN 100    
                WHEN "class_name" = 'Waterway' THEN 100
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
