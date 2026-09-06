import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=r'C:\\Users\\MACAU\\Desktop\\天池\\work\\photogrammetry\\item_002\\mvs\\scene_textured.obj')
bpy.ops.export_scene.gltf(filepath=r'C:\\Users\\MACAU\\Desktop\\天池\\work\\photogrammetry\\item_002\\mvs\\scene_textured.glb', export_format='GLB')
print('exported', r'C:\\Users\\MACAU\\Desktop\\天池\\work\\photogrammetry\\item_002\\mvs\\scene_textured.glb')
