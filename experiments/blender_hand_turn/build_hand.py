"""Author a small real Blender hand-turn scene; save a new native snapshot only.
No rendering subprocess, runtime/service mutation or external assets.
"""
import json
import math
from pathlib import Path


def build(output):
    import bpy
    import bmesh
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    original_scene=bpy.context.scene
    scene=bpy.data.scenes.new('HandTurnLab_'+out.name[-8:])
    collection=scene.collection
    def material(name,color,rough=.7):
        m=bpy.data.materials.new(scene.name+'_'+name);m.diffuse_color=(*color,1);m.use_nodes=True
        shader=m.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(*color,1);shader.inputs['Roughness'].default_value=rough
        return m
    skin=material('Skin',(.88,.53,.34));nail=material('Nail',(.98,.78,.64),.45);crease=material('Crease',(.30,.105,.055));coat=material('Cuff',(.87,.88,.93));lining=material('Lining',(.025,.03,.045))
    root=bpy.data.objects.new(scene.name+'_RotateLongAxis',None);collection.objects.link(root)
    authored=[]
    def mesh_object(name,verts,faces,mat):
        mesh=bpy.data.meshes.new(scene.name+'_'+name);mesh.from_pydata(verts,[],faces);mesh.update()
        bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
        obj=bpy.data.objects.new(mesh.name,mesh);collection.objects.link(obj);obj.parent=root;obj.data.materials.append(mat)
        for p in mesh.polygons:p.use_smooth=True
        authored.append(obj);return obj
    def loft(name,centers,widths,depths,mat,segments=28):
        verts=[];faces=[]
        for i,c in enumerate(centers):
            tangent=Vector(centers[min(i+1,len(centers)-1)])-Vector(centers[max(0,i-1)])
            tangent.normalize();vertical=Vector((0,0,1));side=vertical.cross(tangent).normalized();up=tangent.cross(side).normalized()
            for j in range(segments):
                a=2*math.pi*j/segments
                p=Vector(c)+side*(widths[i]*math.cos(a))+up*(depths[i]*math.sin(a));verts.append(tuple(p))
        for i in range(len(centers)-1):
            for j in range(segments):
                k=(j+1)%segments;faces.append((i*segments+j,i*segments+k,(i+1)*segments+k,(i+1)*segments+j))
        faces.extend([tuple(range(segments-1,-1,-1)),tuple((len(centers)-1)*segments+j for j in range(segments))])
        return mesh_object(name,verts,faces,mat)
    def ellipsoid(name,center,scale,mat):
        bm=bmesh.new();bmesh.ops.create_uvsphere(bm,u_segments=24,v_segments=16,radius=1)
        verts=[tuple(Vector(center)+Vector((v.co.x*scale[0],v.co.y*scale[1],v.co.z*scale[2]))) for v in bm.verts]
        for i,v in enumerate(bm.verts):v.index=i
        faces=[tuple(v.index for v in f.verts) for f in bm.faces];bm.free();return mesh_object(name,verts,faces,mat)
    palm=loft('Palm',[(-.12,0,0),(.04,0,0),(.32,0,0),(.61,0,-.005),(.82,0,-.01),(.92,0,-.01)],[.17,.25,.34,.36,.33,.27],[.10,.125,.145,.14,.115,.09],skin)
    thenar=ellipsoid('Thenar',(.25,-.19,-.095),(.25,.17,.085),skin)
    for name,y,length,radius in [('Index',-.255,.64,.087),('Middle',-.078,.77,.093),('Ring',.112,.70,.089),('Little',.275,.52,.073)]:
        start=.75;tip=start+length
        loft(name,[(start,y,0),(.94,y,-.005),(tip-.16,y*.98,-.015),(tip-.055,y*.98,-.018),(tip,y*.98,-.018)],[radius*.95,radius,radius*.9,radius*.60,.012],[radius*.83,radius*.85,radius*.82,radius*.6,.012],skin)
        ellipsoid(name+'_Nail',(tip-.105,y*.98,.055),(.097,radius*.64,.014),nail)
    thumb=loft('Thumb',[(.11,-.20,-.035),(.20,-.38,-.04),(.37,-.55,-.025),(.57,-.64,.005),(.65,-.64,.008)],[.14,.14,.12,.09,.018],[.12,.12,.10,.08,.018],skin)
    ellipsoid('Thumb_Nail',(.565,-.64,.078),(.085,.056,.013),nail)
    loft('Wrist',[(-.53,0,0),(-.24,0,0),(.03,0,0)],[.175,.18,.205],[.105,.11,.115],skin)
    loft('Cuff',[(-.70,0,0),(-.57,0,0),(-.51,0,0)],[.22,.22,.22],[.15,.15,.15],coat)
    loft('CuffLining',[(-.53,0,0),(-.49,0,0)],[.21,.21],[.142,.142],lining)
    surfaces=[]
    for obj in [palm,thenar,thumb]:
        bm=bmesh.new();bm.from_mesh(obj.data);surfaces.append(BVHTree.FromBMesh(bm));bm.free()
    def surface_line(name,points):
        # Project onto actual palmar meshes, then put ink just outside them.
        dense=[]
        for i in range(len(points)-1):
            p0=Vector(points[max(0,i-1)]);p1=Vector(points[i]);p2=Vector(points[i+1]);p3=Vector(points[min(len(points)-1,i+2)])
            for k in range(12):
                t=k/12
                dense.append(tuple(.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t)))
        dense.append(points[-1])
        projected=[]
        for x,y in dense:
            hits=[]
            for surface in surfaces:
                loc,normal,index,distance=surface.ray_cast(Vector((x,y,-1)),Vector((0,0,1)))
                if loc is not None:hits.append(loc.z)
            if hits:projected.append((x,y,min(hits)-.006))
        if len(projected)<2:return
        curve=bpy.data.curves.new(scene.name+'_'+name,'CURVE');curve.dimensions='3D';curve.bevel_depth=.007;curve.bevel_resolution=2
        spline=curve.splines.new('POLY');spline.points.add(len(projected)-1)
        for bp,point in zip(spline.points,projected):bp.co=(*point,1)
        obj=bpy.data.objects.new(curve.name,curve);collection.objects.link(obj);obj.parent=root;curve.materials.append(crease);authored.append(obj)
    surface_line('ThumbRootCrease',[(.08,-.08),(.20,-.04),(.37,-.10),(.45,-.21),(.42,-.30)])
    surface_line('PalmFoldA',[(.31,.23),(.40,.13),(.47,.01),(.50,-.09)])
    surface_line('PalmFoldB',[(.62,.26),(.67,.13),(.70,0),(.69,-.15)])
    camera_data=bpy.data.cameras.new(scene.name+'_Camera');camera=bpy.data.objects.new(camera_data.name,camera_data);collection.objects.link(camera);camera.location=(.42,0,5);camera_data.type='ORTHO';camera_data.ortho_scale=3.;scene.camera=camera
    def light(name,location,power,size):
        data=bpy.data.lights.new(scene.name+'_'+name,'AREA');data.energy=power;data.shape='DISK';data.size=size
        obj=bpy.data.objects.new(data.name,data);collection.objects.link(obj);obj.location=location;obj.rotation_euler=(Vector((.4,0,0))-obj.location).to_track_quat('-Z','Y').to_euler()
    light('Key',(-2,-2,4),180,3);light('Fill',(2,2,3),100,3);light('Rim',(0,2,-3),130,2.5)
    world=bpy.data.worlds.new(scene.name+'_World');world.use_nodes=True;world.node_tree.nodes['Background'].inputs['Color'].default_value=(.55,.62,.75,1);world.node_tree.nodes['Background'].inputs['Strength'].default_value=.35;scene.world=world
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8;scene.cycles.use_denoising=True
    scene.render.resolution_x=640;scene.render.resolution_y=360;scene.render.resolution_percentage=100
    scene.render.threads_mode='FIXED';scene.render.threads=2;scene.render.film_transparent=True
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.color_depth='8'
    scene.view_settings.view_transform='Standard';scene.render.fps=24;scene.frame_start=1;scene.frame_end=24
    # Explicit integer-frame samples avoid depending on action/fcurve layout.
    for f in range(1,25):
        root.rotation_euler=(math.pi*(f-1)/23,0,0);root.keyframe_insert(data_path='rotation_euler',frame=f)
    scene.frame_set(1)
    metadata={'scene_name':scene.name,'width':640,'height':360,'fps':24,'frame_start':1,'frame_end':24}
    try:
        if bpy.context.window:bpy.context.window.scene=scene
        # Headless MCP has no Window; the JOB also explicitly selects this scene.
        with bpy.context.temp_override(scene=scene):
            bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'),copy=True)
    finally:
        if bpy.context.window:bpy.context.window.scene=original_scene
    # Export only this scene and its dependency closure for delivery.
    bpy.data.libraries.write(str(out/'hand-only.blend'),{scene},fake_user=True,compress=True)
    receipt={'blender_version':bpy.app.version_string,'metadata':metadata,'native_file':str(out/'scene.blend'),'mesh_count':len([o for o in authored if o.type=='MESH']),'curve_count':len([o for o in authored if o.type=='CURVE']),'root':root.name,'original_scene_restored':bpy.context.scene==original_scene,'rendered':False,'provenance':'Manually authored stylized hand, no external model/texture/font'}
    (out/'scene.json').write_text(json.dumps(metadata,indent=2)+'\n');(out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    import argparse,sys
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);print(json.dumps(build(args.output)))
