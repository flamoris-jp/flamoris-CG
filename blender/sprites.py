"""Small Blender adapter for alpha-cutout artwork on an upright X/Z plane.

Bottom-center origin, fixed orientation toward -Y. This is not an auto rig,
camera billboard, lip sync system or a Cinema interchange implementation.
"""
def create_sprite(name, image_path, width=1.0, height=1.0, tint=(1.0, 1.0, 1.0)):
    import bpy
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata([(-width/2, 0, 0), (width/2, 0, 0),
                     (width/2, 0, height), (-width/2, 0, height)], [], [(0, 1, 2, 3)])
    mesh.uv_layers.new(name="UVMap")
    for loop, uv in zip(mesh.uv_layers.active.data, [(0,0),(1,0),(1,1),(0,1)]):
        loop.uv = uv
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    material = bpy.data.materials.new(name + "_Artwork")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(str(image_path), check_existing=True)
    emission = nodes.new("ShaderNodeEmission")
    multiply = nodes.new("ShaderNodeVectorMath")
    multiply.operation = "MULTIPLY"
    multiply.inputs[1].default_value = tint
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    output = nodes.new("ShaderNodeOutputMaterial")
    links = material.node_tree.links
    links.new(texture.outputs["Color"], multiply.inputs[0])
    links.new(multiply.outputs["Vector"], emission.inputs["Color"])
    links.new(texture.outputs["Alpha"], mix.inputs[0])
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(emission.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], output.inputs["Surface"])
    obj.data.materials.append(material)
    if hasattr(obj, "visible_shadow"):
        obj.visible_shadow = False
    return obj
