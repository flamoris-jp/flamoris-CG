"""Trusted Blender authoring for the source-contour volume experiment.
Run prepare offline, then this builder. No rendering or external asset service.
"""
import base64,json,math
from pathlib import Path


def validate_mesh(data):
    required={'schema_version','keys','faces','uv','front_faces','angles','textures','source_hashes','crop_rects','canonical_scale_pixels','twist_degrees','depth_design','limitations'}
    if set(data)!=required or data['schema_version']!=1:raise ValueError('Unexpected mesh schema')
    keys=data['keys'];faces=data['faces'];uv=data['uv']
    if len(keys)!=2 or not 4<=len(keys[0])<=10000 or len(keys[1])!=len(keys[0]):raise ValueError('Mesh key bounds')
    if not 4<=len(faces)<=20000 or len(uv)!=len(faces):raise ValueError('Face bounds')
    for key in keys:
        for co in key:
            if len(co)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>10 for v in co):raise ValueError('Vertex bounds')
    for face,coords in zip(faces,uv):
        if len(face)!=3 or any(type(v)!=int or not 0<=v<len(keys[0]) for v in face):raise ValueError('Invalid face')
        if len(coords)!=3 or any(len(p)!=2 or any(not math.isfinite(v) or abs(v)>2 for v in p) for p in coords):raise ValueError('UV bounds')
    if len(data['textures'])!=2 or sum(len(s) for s in data['textures'])>2000000:raise ValueError('Texture bounds')
    for s in data['textures']:
        raw=base64.b64decode(s,validate=True)
        if not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('PNG required')
    if not 0<data['front_faces']<len(faces) or len(data['angles'])!=2 or any(not math.isfinite(v) or abs(v)>math.pi for v in data['angles']):raise ValueError('Motion bounds')


def build(data,output):
    validate_mesh(data)
    import bpy,bmesh
    out=Path(output);out.mkdir(exist_ok=False)
    original=bpy.context.scene
    scene=bpy.data.scenes.new('ArtHand_'+out.name[-8:]);objects=scene.collection.objects
    root=bpy.data.objects.new(scene.name+'_ForearmAxis',None);objects.link(root)
    orient=bpy.data.objects.new(scene.name+'_Lift',None);objects.link(orient);root.parent=orient
    mesh=bpy.data.meshes.new(scene.name+'_ClosedSkin');mesh.from_pydata(data['keys'][0],[],data['faces']);mesh.update()
    hand=bpy.data.objects.new(mesh.name,mesh);objects.link(hand);hand.parent=root
    for p in mesh.polygons:p.use_smooth=True
    hand.shape_key_add(name='BackDrawing')
    palm=hand.shape_key_add(name='PalmDrawing')
    for v,co in zip(palm.data,data['keys'][1]):v.co=co
    uv=mesh.uv_layers.new(name='OriginalArtUV')
    for poly,coords in zip(mesh.polygons,data['uv']):
        for loop,co in zip(poly.loop_indices,coords):uv.data[loop].uv=co
        poly.material_index=0 if poly.index<data['front_faces'] else 1
    for view in [0,1]:
        texture_path=out/f'art-{view}.png';texture_path.write_bytes(base64.b64decode(data['textures'][view]))
        image=bpy.data.images.load(str(texture_path),check_existing=False);image.name=scene.name+['_BackArt','_PalmArt'][view];image.pack()
        mat=bpy.data.materials.new(image.name);mat.use_nodes=True;nodes=mat.node_tree.nodes;nodes.clear()
        tex=nodes.new('ShaderNodeTexImage');tex.image=image;tex.interpolation='Linear';tex.extension='EXTEND'
        emission=nodes.new('ShaderNodeEmission');emission.inputs['Strength'].default_value=1
        mix=nodes.new('ShaderNodeMixRGB');mix.name='GrazingArtVisibility';mix.inputs[1].default_value=(.94,.64,.48,1)
        links=mat.node_tree.links;links.new(tex.outputs['Color'],mix.inputs[2]);links.new(mix.outputs[0],emission.inputs['Color'])
        output_node=nodes.new('ShaderNodeOutputMaterial');links.new(emission.outputs['Emission'],output_node.inputs['Surface'])
        mesh.materials.append(mat)
    # The viewer stays on +Z. Negative roll brings the thumb towards the viewer.
    checks=[]
    for frame in range(1,33):
        t=(frame-1)/31
        u=t*t*(3-2*t)
        root.rotation_euler=(-math.pi*u,0,0);root.keyframe_insert(data_path='rotation_euler',frame=frame)
        orient.rotation_euler=(0,0,(1-u)*data['angles'][0]+u*data['angles'][1]);orient.keyframe_insert(data_path='rotation_euler',frame=frame)
        palm.value=u;palm.keyframe_insert(data_path='value',frame=frame)
        # Painted surfaces give way to authored side colour at grazing angles.
        # This avoids projecting ink from an unseen face across the new side.
        exposure=max(0.,min(1.,(abs(math.cos(math.pi*u))-.12)/.40))
        exposure=exposure*exposure*(3-2*exposure)
        for material in mesh.materials:
            factor=material.node_tree.nodes['GrazingArtVisibility'].inputs[0]
            factor.default_value=exposure;factor.keyframe_insert(data_path='default_value',frame=frame)
        checks.append({'frame':frame,'shape':u,'roll_degrees':-180*u,'lift_degrees':math.degrees(orient.rotation_euler.z)})
    camera_data=bpy.data.cameras.new(scene.name+'_Camera');camera=bpy.data.objects.new(camera_data.name,camera_data);objects.link(camera)
    camera.location=(.52,.20,5);camera_data.type='ORTHO';camera_data.ortho_scale=2.25;scene.camera=camera
    scene.world=bpy.data.worlds.new(scene.name+'_World');scene.world.color=(.5,.5,.5)
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8;scene.cycles.use_denoising=False
    scene.render.resolution_x=800;scene.render.resolution_y=600;scene.render.resolution_percentage=100
    scene.render.threads_mode='FIXED';scene.render.threads=2;scene.render.film_transparent=True
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.color_depth='8';scene.render.image_settings.compression=100
    scene.view_settings.view_transform='Standard';scene.render.fps=24;scene.frame_start=1;scene.frame_end=32;scene.frame_set(1)
    metadata={'scene_name':scene.name,'width':800,'height':600,'fps':24,'frame_start':1,'frame_end':32}
    bm=bmesh.new();bm.from_mesh(mesh);bad=sum(not e.is_manifold for e in bm.edges);volume=bm.calc_volume(signed=True);bm.free()
    if bad or volume<=0:raise ValueError('Closed skin topology/normal check failed')
    bpy.data.libraries.write(str(out/'hand.blend'),{scene},fake_user=True,compress=True)
    receipt={'blender_version':bpy.app.version_string,'metadata':metadata,'native_file':str(out/'hand.blend'),'vertices':len(mesh.vertices),'faces':len(mesh.polygons),'nonmanifold_edges':bad,'signed_volume':volume,'original_scene_restored':bpy.context.scene==original,'source_hashes':data['source_hashes'],'rotation':'thumb towards viewer; negative local X roll','original_art_surfaces':True,'rendered':False,'checks':checks,'limitations':data['limitations']}
    (out/'scene.json').write_text(json.dumps(metadata,indent=2));(out/'build-receipt.json').write_text(json.dumps(receipt,indent=2))
    return receipt


if __name__=='__main__':
    import argparse,sys
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('data',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);print(json.dumps(build(json.loads(args.data.read_text()),args.output)))
