"""Trusted local preparation of a packed native snapshot for ID registration.

Open only author-owned .blend files, using --disable-autoexec. The remote job
API cannot invoke this script or supply native file paths. Never renders.
"""
import argparse
import json
from pathlib import Path
import sys


def main():
    import bpy
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene',required=True)
    parser.add_argument('--output',required=True,help='NEW directory')
    parser.add_argument('--width',type=int,choices=[320,640,768,960,1280,1920],default=640)
    parser.add_argument('--samples',type=int,choices=range(1,65),default=8)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    scene=bpy.data.scenes.get(args.scene)
    if scene is None:raise ValueError('unknown native scene')
    if scene.render.engine!='CYCLES':raise ValueError('this preparation profile supports Cycles only')
    # Explicit tiny CPU profile; no GPU selection or saved user preferences.
    scene.cycles.device='CPU';scene.cycles.samples=args.samples
    scene.render.resolution_x=args.width;scene.render.resolution_y=args.width*9//16
    scene.render.resolution_percentage=100
    scene.render.threads_mode='FIXED';scene.render.threads=2
    scene.render.image_settings.file_format='PNG'
    bpy.context.window.scene=scene
    bpy.ops.file.pack_all()
    for image in bpy.data.images:
        if image.filepath and image.source=='FILE' and not image.packed_file:
            raise ValueError('native snapshot contains an unpacked image')
    root=Path(args.output).resolve();root.mkdir(parents=True,exist_ok=False)
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'scene.blend'),copy=True)
    metadata={'scene_name':scene.name,'width':args.width,'height':args.width*9//16,
              'fps':scene.render.fps/scene.render.fps_base,
              'frame_start':scene.frame_start,'frame_end':scene.frame_end}
    (root/'scene.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print('PREPARED_NATIVE_JOB',json.dumps(metadata),flush=True)


if __name__=='__main__':main()
