"""Authored 2.5D clip experiment, not a screenplay/planning engine.

blender -b --threads 2 --python-exit-code 1 --python examples/pudding_defense.py -- \
  --assets /path/to/three/pngs --output /path/to/NEW/output [--sequence]

Requires akino.png, misaki.png, chipsy.png supplied by the author. No artwork
or fonts are distributed in this repository. Output contains packed native
Blender scene, three previews, a static background and optional PNG sequence.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "blender")]
from flamoris_cg.assets import resolve_png
from sprites import create_sprite


def build(assets, width=960, samples=8):
    import bpy
    from mathutils import Vector
    scene = bpy.data.scenes.new("Pudding_Defense_25D")
    bpy.context.window.scene = scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 3
    scene.cycles.transparent_max_bounces = 8
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 2
    scene.render.resolution_x = width
    scene.render.resolution_y = width * 9 // 16
    scene.render.resolution_percentage = 100
    scene.render.fps = 12
    scene.frame_start, scene.frame_end = 1, 180
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Standard"
    scene.world = bpy.data.worlds.new("Pudding_Studio_World")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.65,.75,.85,1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = .6

    def material(name, color, glow=0):
        m = bpy.data.materials.new("Pudding_" + name)
        m.diffuse_color = (*color,1)
        m.use_nodes = True
        shader = m.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value = (*color,1)
        shader.inputs['Roughness'].default_value = .8
        shader.inputs['Emission Color'].default_value = (*color,1)
        shader.inputs['Emission Strength'].default_value = glow
        return m

    cream = material('Warm_Plaster',(.77,.83,.78),.15)
    trim = material('Ink_Teal',(.045,.15,.18),.15)
    wood = material('Honey_Wood',(.53,.30,.14),.1)
    floor = material('Pale_Wood',(.70,.58,.40),.1)
    mint = material('Mint',(.24,.62,.59),.15)
    pink = material('Coral',(.9,.37,.29),.15)
    white = material('Porcelain',(.93,.90,.76),.1)
    blue = material('Blue_Blanket',(.16,.36,.48),.1)
    gold = material('Pudding_Custard',(.98,.65,.13),.2)
    caramel = material('Caramel',(.38,.12,.035),.1)
    sky = material('Window_Glow',(.99,.62,.35),.8)
    dark = material('Screen',(.025,.055,.075),.15)
    cyan = material('Screen_Light',(.09,.80,.77),1)

    def box(name, location, size, mat, bevel=.025):
        bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        o=bpy.context.object; o.name='Pudding_'+name
        o.dimensions=size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        o.data.materials.append(mat)
        if bevel:
            b=o.modifiers.new('Soft ink edges','BEVEL'); b.width=bevel; b.segments=1
            o.modifiers.new('Weighted corner normals','WEIGHTED_NORMAL')
        return o

    def sphere(name, pos, size, mat):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, location=pos)
        o=bpy.context.object; o.name='Pudding_'+name; o.scale=size
        o.data.materials.append(mat)
        for p in o.data.polygons: p.use_smooth=True
        return o

    def cylinder(name, pos, radius, depth, mat, top=None):
        bpy.ops.mesh.primitive_cone_add(vertices=40, radius1=radius,
            radius2=radius if top is None else top, depth=depth, location=pos)
        o=bpy.context.object; o.name='Pudding_'+name; o.data.materials.append(mat)
        b=o.modifiers.new('Tiny rim','BEVEL'); b.width=.018; b.segments=2
        o.modifiers.new('Normals','WEIGHTED_NORMAL')
        return o

    def text(name, content, pos, size, mat):
        data=bpy.data.curves.new('Pudding_'+name,'FONT'); data.body=content
        data.size=size; data.align_x='CENTER'; data.extrude=.0008
        o=bpy.data.objects.new(data.name,data); scene.collection.objects.link(o)
        o.location=pos; o.rotation_euler=(math.pi/2,0,0); data.materials.append(mat)
        return o

    box('Floor',(0,.4,-.10),(10.8,8,.18),floor)
    for i in range(14):
        box('Floor_Seam_%02d'%i,(0,-3.35+i*.56,.003),(10.7,.012,.008),wood,0)
    box('Back_Wall',(0,4.25,2.65),(10.8,.18,5.5),cream,0)
    box('Skirting',(0,4.08,.15),(10.8,.08,.30),trim,.01)
    box('Dado',(0,4.11,1.42),(10.8,.035,.04),mint,0)
    box('Window_Frame',(-3.35,4.08,3.20),(2.65,.10,2.25),trim)
    box('Sunset_Window',(-3.35,4.01,3.20),(2.46,.05,2.06),sky,0)
    for x in [-3.95,-3.35,-2.75]:
        box('City', (x,3.97,2.72),(.35,.02,.85 if x!=-3.35 else 1.2),blue,0)
    box('Window_Mullion',(-3.35,3.92,3.2),(.065,.08,2.1),white,0)
    box('Window_Midbar',(-3.35,3.91,3.2),(2.46,.08,.065),white,0)
    box('Sill',(-3.35,3.87,2.1),(2.9,.46,.12),white)
    box('Lab_Sign',(0,4.03,3.65),(2.65,.1,1.0),trim)
    text('FLAMORIS','FLAMORIS',(0,3.96,3.68),.32,white)
    text('Lab','GOOTARA LAB',(0,3.96,3.39),.16,mint)
    # Bed, pillow and blanket remain editable 3D objects.
    box('Bed_Frame',(-3.6,1.45,.37),(2.0,3.4,.48),wood)
    box('Mattress',(-3.6,1.43,.67),(1.94,3.3,.32),white,.08)
    box('Duvet',(-3.6,.95,.87),(1.99,2.2,.18),blue,.08)
    box('Headboard',(-3.6,3.17,.95),(2.15,.13,1.4),trim)
    sphere('Pillow',(-3.6,2.62,.91),(.74,.39,.17),white)
    # Work desk, screen and one tiny luminous GPU tower.
    box('Desk_Top',(3.14,2.88,1.16),(3.05,1.0,.13),wood)
    for x in [1.85,4.43]:
        box('Desk_Leg',(x,2.88,.57),(.10,.72,1.14),trim)
    box('Monitor',(3.10,3.05,1.85),(1.30,.13,.83),trim)
    box('Monitor_Glass',(3.10,2.97,1.85),(1.15,.012,.68),dark,0)
    for i in range(4):
        box('Code_Line',(3.0,2.95,1.65+i*.12),(.70 if i%2 else .9,.01,.025),cyan,0)
    box('Monitor_Stem',(3.10,3.08,1.35),(.1,.1,.36),trim)
    box('Keyboard',(3.1,2.57,1.25),(1.15,.27,.055),trim)
    box('GPU_Tower',(4.25,3.04,1.58),(.45,.6,.72),trim)
    for z in [1.40,1.73]:
        fan=cylinder('GPU_Fan',(4.25,2.725,z),.11,.018,cyan)
        fan.rotation_euler=(math.pi/2,0,0)
    # Shelf with books and a potted plant.
    box('Shelf',(3.0,4.0,3.25),(3.2,.45,.10),wood)
    for i, mat in enumerate([mint,pink,blue,white,gold]):
        box('Book_%d'%i,(1.8+i*.22,3.95,3.53),(.15,.27,.46+(i%2)*.10),mat,.008)
    cylinder('Plant_Pot',(4.05,3.96,3.43),.17,.29,pink,top=.21)
    for dx,dz in [(-.18,.2),(.10,.35),(.22,.15)]:
        leaf=sphere('Plant_Leaf',(4.05+dx,3.96,3.67+dz),(.12,.06,.25),mint)
        leaf.rotation_euler[1]=dx*3
    rug=cylinder('Rug',(0,-.1,.018),2.2,.025,mint); rug.scale.y=.62
    # Coffee table, plate and the contested pudding.
    table=cylinder('Table',(-1.45,-.40,.86),.78,.10,wood)
    cylinder('Table_Stem',(-1.45,-.40,.43),.075,.85,trim)
    cylinder('Table_Base',(-1.45,-.40,.055),.42,.06,trim)
    plate=cylinder('Plate',(-1.45,-.40,.94),.34,.045,white)
    pudding=cylinder('Custard',(-1.45,-.40,1.105),.235,.29,gold,top=.18)
    cap=cylinder('Caramel_Top',(-1.45,-.40,1.258),.182,.025,caramel)
    spoon=box('Spoon_Handle',(-1.03,-.48,.99),(.28,.035,.018),white,.008)
    sphere('Spoon_Bowl',(-.87,-.48,.99),(.07,.05,.015),white)

    actors={}
    for name,x,y,h in [('akino',-1.55,.45,2.65),('misaki',3.2,1.45,2.65),('chipsy',.80,-.22,1.32)]:
        image=bpy.data.images.load(str(assets[name]),check_existing=True)
        w=h*image.size[0]/image.size[1]
        obj=create_sprite('Pudding_Actor_'+name,assets[name],w,h)
        obj.location=(x,y,.025)
        actors[name]=obj
    # Subtle contact disks avoid a floating-card look. These are authored,
    # flattened meshes, not physical character shadows or a rig.
    shadows={}
    shadowmat=material('Contact_Shadow',(.14,.23,.21),.1)
    for name,actor in actors.items():
        shadows[name]=sphere('Contact_'+name,(actor.location.x,actor.location.y,.03),(.38,.12,.018),shadowmat)

    camera_data=bpy.data.cameras.new('Pudding_Camera'); camera_data.type='ORTHO'
    camera=bpy.data.objects.new('Pudding_Camera',camera_data)
    scene.collection.objects.link(camera); scene.camera=camera
    camera_data.clip_end=100
    keydata=bpy.data.lights.new('Pudding_Key','AREA'); keydata.energy=500
    keydata.shape='DISK'; keydata.size=7
    key=bpy.data.objects.new(keydata.name,keydata); scene.collection.objects.link(key)
    key.location=(-3,-4,8)
    key.rotation_euler=(Vector((0,1,0))-key.location).to_track_quat('-Z','Y').to_euler()

    for frame in range(1,181):
        t=(frame-1)/12
        if t<5:
            target=Vector((0,.9,1.75)); ortho=11.5-.04*t
        elif t<9:
            target=Vector((.4,.55,1.48)); ortho=7.3-.035*(t-5)
        else:
            target=Vector((.3,.75,1.6)); ortho=11.3
        camera.location=target+Vector((0,-14,4.3))
        camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
        camera_data.ortho_scale=ortho
        camera.keyframe_insert('location',frame=frame)
        camera.keyframe_insert('rotation_euler',frame=frame)
        camera_data.keyframe_insert('ortho_scale',frame=frame)
        # Misaki approaches, settles, then both actors jump in surprise.
        move=max(0,min(1,(t-3.5)/2.5))
        actors['misaki'].location.x=3.2-2.35*move
        actors['misaki'].location.y=1.45-.78*move
        actors['misaki'].location.z=.025+(.045*abs(math.sin(t*13)) if 0<move<1 else .007*math.sin(t*2))
        actors['misaki'].rotation_euler[1]=.022*math.sin(t*13) if 0<move<1 else 0
        actors['akino'].location.z=.025+.009*math.sin(t*2.4)
        # Robot creeps toward the table, jumps up, steals the plate, escapes.
        creep=max(0,min(1,(t-1.0)/7.5))
        robot=actors['chipsy']
        robot.location=(.8-1.6*creep,-.80,.025+.025*abs(math.sin(t*8)))
        if 9<=t<9.8:
            q=(t-9)/.8
            robot.location=(-.8-.65*q,-.80,.025+.82*math.sin(math.pi*q/2))
        if t>=9.8:
            q=t-9.8
            robot.location=(-1.45+2.05*q,-.95,.12+.15*abs(math.sin(q*12)))
            robot.rotation_euler[1]=.10*math.sin(q*12)
            for prop,offset in [(plate,0),(pudding,.165),(cap,.318)]:
                prop.location=(robot.location.x,robot.location.y-.08,1.45+robot.location.z+offset)
                prop.keyframe_insert('location',frame=frame)
        else:
            for prop in [plate,pudding,cap]: prop.keyframe_insert('location',frame=frame)
        if 10.0<t<10.7:
            jump=.22*math.sin((t-10)/.7*math.pi)
            for name in ['akino','misaki']: actors[name].location.z+=jump
        if t>=11:
            chase=max(0,t-11)
            actors['akino'].location.x=-1.55+chase*1.60
            actors['misaki'].location.x=.85+chase*1.55
            for name in ['akino','misaki']:
                actors[name].location.z+=.075*abs(math.sin(chase*13))
                actors[name].rotation_euler[1]=.045*math.sin(chase*13)
        for name,actor in actors.items():
            actor.keyframe_insert('location',frame=frame)
            actor.keyframe_insert('rotation_euler',frame=frame)
            shadows[name].location.x=actor.location.x
            shadows[name].location.y=actor.location.y
            shadows[name].keyframe_insert('location',frame=frame)
    # Dense samples use linear interpolation, camera shot changes stay stepped.
    for datablock in list(actors.values())+list(shadows.values())+[camera,camera_data,plate,pudding,cap]:
        anim=datablock.animation_data
        if anim and anim.action:
            for layer in anim.action.layers:
                for strip in layer.strips:
                    for bag in strip.channelbags:
                        for curve in bag.fcurves:
                            for point in curve.keyframe_points: point.interpolation='CONSTANT'
    scene.frame_set(1)
    return scene,actors,shadows


def main():
    import bpy
    parser=argparse.ArgumentParser()
    parser.add_argument('--assets',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--sequence',action='store_true')
    parser.add_argument('--width',type=int,choices=[640,768,960,1280],default=960)
    parser.add_argument('--samples',type=int,choices=range(1,65),default=8)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    assets={name:resolve_png(args.assets,name) for name in ['akino','misaki','chipsy']}
    output=Path(args.output).resolve(); output.mkdir(parents=True,exist_ok=False)
    scene,actors,shadows=build(assets,args.width,args.samples)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'pudding-defense.blend'))
    receipt={'experiment':'pudding-defense-2.5d','blender':bpy.app.version_string,
             'engine':scene.render.engine,'device':scene.cycles.device,'fps':12,
             'frames':180,'resolution':[scene.render.resolution_x,scene.render.resolution_y],
             'samples':scene.cycles.samples,
             'assets':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in assets.items()},
             'limitations':['whole-body sprites','authored bobbing, no skeletal walking',
                            'no expression changes or lip sync','no audio or final editing'],
             'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    for frame in [1,78,126]:
        scene.frame_set(frame); scene.render.filepath=str(output/f'preview-{frame:03d}.png')
        bpy.ops.render.render(write_still=True)
    for obj in list(actors.values())+list(shadows.values()): obj.hide_render=True
    scene.frame_set(1); scene.render.filepath=str(output/'background.png')
    bpy.ops.render.render(write_still=True)
    for obj in list(actors.values())+list(shadows.values()): obj.hide_render=False
    if args.sequence:
        frames=output/'frames'; frames.mkdir()
        scene.render.filepath=str(frames/'frame_')
        bpy.ops.render.render(animation=True)
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('PUDDING_DEFENSE_OK',output,flush=True)


if __name__=='__main__':
    main()
