# import modules
from glob import glob

# get the point vector layer
vector_path = r'C:\Users\Administrator\AMH Philippines, Inc\NP24.134 Freya Daanbantayan SPP HH - General\06 NP24.134 WORK FILES\HH Files\2 Hydraulic Analysis\HEC-RAS\sample_point.shp'
vlayer = QgsVectorLayer(vector_path, 'vlayer', 'ogr')
if not vlayer.isValid():
    print("Error: Transect vector point layer is invalid.")

# get the ras and save folder
ras_folder = r"C:\Users\Administrator\AMH Philippines, Inc\NP24.134 Freya Daanbantayan SPP HH - General\06 NP24.134 WORK FILES\HH Files\2 Hydraulic Analysis"
save_folder = r"C:\Users\Administrator\AMH Philippines, Inc\NP24.134 Freya Daanbantayan SPP HH - General\06 NP24.134 WORK FILES\HH Files\1 Hydrologic Analysis\GIS Files\Styles\tests\maps"

# get the layer styles
# raster styles
depth_style = r'C:\Users\Administrator\AMH Philippines, Inc\NP24.134 Freya Daanbantayan SPP HH - General\06 NP24.134 WORK FILES\HH Files\1 Hydrologic Analysis\GIS Files\Styles\Depth-for-test.qml'
velocity_style = r"C:\Users\Administrator\AMH Philippines, Inc\NP24.134 Freya Daanbantayan SPP HH - General\06 NP24.134 WORK FILES\HH Files\1 Hydrologic Analysis\GIS Files\Styles\Velocity.qml"
dv_style = r"C:\Users\Administrator\AMH Philippines, Inc\NP24.134 Freya Daanbantayan SPP HH - General\06 NP24.134 WORK FILES\HH Files\1 Hydrologic Analysis\GIS Files\Styles\D_V.qml"
raster_style_list = [depth_style, velocity_style, dv_style]
#vector style
spot_depth = r"C:\Users\Administrator\AMH Philippines, Inc\NP24.134 Freya Daanbantayan SPP HH - General\06 NP24.134 WORK FILES\HH Files\1 Hydrologic Analysis\GIS Files\Styles\spot_depth_style.qml"
spot_velocity = r"C:\Users\Administrator\AMH Philippines, Inc\NP24.134 Freya Daanbantayan SPP HH - General\06 NP24.134 WORK FILES\HH Files\1 Hydrologic Analysis\GIS Files\Styles\spot_velocity_style.qml"
spot_dv = r"C:\Users\Administrator\AMH Philippines, Inc\NP24.134 Freya Daanbantayan SPP HH - General\06 NP24.134 WORK FILES\HH Files\1 Hydrologic Analysis\GIS Files\Styles\spot_dxv_style.qml"
vector_style_list = [spot_depth, spot_velocity, spot_dv]

# list of all results raster keywords
raster_keys = ['Depth', 'Velocity', 'D _ V']

result_raster = {}

for r_key in raster_keys:
    glob_key = f'{r_key}*.tif'
    folder_path = os.path.join(ras_folder, 'SB*', glob_key)
    result_raster[r_key] = glob(folder_path, recursive=True)

# clean the data for file naming
file_list = [re.sub(r'SB - |sb_|SB_', '',os.path.basename(os.path.dirname(f))) for f in result_raster['Depth']]
# file_path = os.path.basename(os.path.dirname(result_raster['Depth'][0]))
# file_name = file_path)
# print(file_list)

# # list of output dictionary
outputs = {}

c = 0
z=0
for key_value, raster_values in result_raster.items():
    for i, item_raster in enumerate(raster_values):
        # add the raster
        rlayer = QgsRasterLayer(item_raster, 'raster', 'gdal')
        QgsProject.instance().addMapLayer(rlayer)
        raster_layer = QgsProject.instance().mapLayersByName('raster')[0]
        
        # set raster layer style
        alg_params = {
            'INPUT': raster_layer,
            'STYLE': raster_style_list[c]
                }
        processing.run("native:setlayerstyle",alg_params )

        # sample raster values
        alg_params = {
            'INPUT': vlayer,
            'RASTERCOPY': item_raster,
            'COLUMN_PREFIX':'elev',
            'OUTPUT':'TEMPORARY_OUTPUT'}
        outputs['sampled'] = processing.run("native:rastersampling", alg_params)
        ptlayer = outputs['sampled']['OUTPUT']

        QgsProject.instance().addMapLayer(ptlayer)
        point_layer = QgsProject.instance().mapLayersByName('Sampled')[0]

        # # set vector layer style
        alg_params = {
            'INPUT': point_layer,
            'STYLE': vector_style_list[c]
                }
        processing.run("native:setlayerstyle",alg_params )

        # save map as image
        save_filename = os.path.join(save_folder, key_value, f"{file_list[i]}.png")
        alg_params = {
            'LAYOUT': key_value,
            'LAYERS':None,
            'DPI':220,
            'GEOREFERENCE':False,
            'INCLUDE_METADATA':True,
            'ANTIALIAS':True,
            'OUTPUT': save_filename
            }
        processing.run("native:printlayouttoimage",alg_params)
        print(f"Printed {key_value} - {file_list[i]}")

        # remove the loaded layers
        QgsProject.instance().removeMapLayer(point_layer.id())
        QgsProject.instance().removeMapLayer(raster_layer.id())
        z+=1
    c+=1

print(f'All maps generated: {z}')

    

