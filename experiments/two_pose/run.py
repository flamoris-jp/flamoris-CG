"""Offline two-key-pose mesh-warp experiment (not a production scene API).

Optional, explicitly installed research dependencies: numpy, scipy, Pillow.
No network, model inference, Blender mutation, or implicit dependency installs.
"""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import tempfile


def save_png(image, path):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(buffer.getvalue())
    temporary.replace(path)


def encode_mp4(directory, destination, fps):
    # Encode on the local temporary filesystem so the muxer's faststart seek
    # does not depend on workspace mount seek behavior. Install complete bytes.
    with tempfile.TemporaryDirectory() as td:
        temporary = Path(td)/'clip.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-n',
                        '-framerate',str(fps),'-i',str(directory/'%04d.png'),
                        '-c:v','libx264','-crf','18','-pix_fmt','yuv420p',
                        '-movflags','+faststart',str(temporary)],check=True)
        destination.write_bytes(temporary.read_bytes())


def load_landmarks(path):
    import numpy as np
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if set(data) != {'schema_version', 'annotation', 'size', 'points', 'bones'}:
        raise ValueError('Unknown or missing annotation fields')
    if data['schema_version'] != 1:
        raise ValueError('Unsupported annotation version')
    w, h = data['size']
    if any(type(v) is not int for v in [w, h]) or not (16 <= w <= 4096 and 16 <= h <= 4096):
        raise ValueError('Invalid image size')
    names = list(data['points'])
    if not 3 <= len(names) <= 256:
        raise ValueError('Expected 3..256 matching points')
    a, b = [], []
    for name, poses in data['points'].items():
        if set(poses) != {'a', 'b'}:
            raise ValueError('Each point needs exactly a and b')
        for key, dest in [('a', a), ('b', b)]:
            v = poses[key]
            if not isinstance(v, list) or len(v) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in v):
                raise ValueError('Coordinates must be finite pairs')
            if not (0 <= v[0] < w and 0 <= v[1] < h):
                raise ValueError('Point outside image')
            dest.append(v)
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    if len(np.unique(a, axis=0)) != len(a) or len(np.unique(b, axis=0)) != len(b):
        raise ValueError('Duplicate points')
    for chain in data['bones']:
        if not isinstance(chain, list) or len(chain) < 2 or any(n not in names for n in chain):
            raise ValueError('Unknown bone point')
    return data, names, a, b


def signed_areas(points, triangles):
    q = points[triangles]
    return (q[:, 1, 0]-q[:, 0, 0])*(q[:, 2, 1]-q[:, 0, 1]) - (q[:, 1, 1]-q[:, 0, 1])*(q[:, 2, 0]-q[:, 0, 0])


def warp(image, source, target, triangles, background=255.):
    """Inverse barycentric rasterization with bilinear RGB sampling.

    Destination triangles use shared vertices and inclusive edge coverage.
    Overlaps caused by folds are deliberately retained for diagnosis.
    """
    import numpy as np
    from scipy.ndimage import map_coordinates
    h, w = image.shape[:2]
    output = np.full((h, w, image.shape[2]), background, dtype=np.float32)
    coverage = np.zeros((h, w), dtype=np.uint8)
    for tri in triangles:
        s, d = source[tri], target[tri]
        mat = np.column_stack([d[1]-d[0], d[2]-d[0]])
        if abs(np.linalg.det(mat)) < 1e-7:
            continue
        lo = np.maximum(np.floor(d.min(axis=0)).astype(int), [0,0])
        hi = np.minimum(np.ceil(d.max(axis=0)).astype(int)+1, [w,h])
        if (hi <= lo).any():
            continue
        yy, xx = np.mgrid[lo[1]:hi[1], lo[0]:hi[0]]
        coords = np.stack([xx-d[0,0], yy-d[0,1]], axis=0).reshape(2,-1)
        uv = np.linalg.solve(mat, coords)
        valid = (uv[0] >= -1e-6) & (uv[1] >= -1e-6) & (uv.sum(axis=0) <= 1+1e-6)
        if not valid.any():
            continue
        pos = s[0,:,None] + np.column_stack([s[1]-s[0],s[2]-s[0]]) @ uv[:,valid]
        oy, ox = yy.ravel()[valid], xx.ravel()[valid]
        for c in range(image.shape[2]):
            output[oy,ox,c] = map_coordinates(image[:,:,c], [pos[1],pos[0]], order=1, mode='nearest')
        coverage[oy,ox] += 1
    return output, coverage


def make_frame(aimg, bimg, a, b, triangles, t):
    import numpy as np
    # Preserve both unmodified endpoint RGB images exactly.
    if t == 0:
        return aimg.copy()
    if t == 1:
        return bimg.copy()
    p = (1-t)*a + t*b
    wa, _ = warp(aimg, a, p, triangles)
    wb, _ = warp(bimg, b, p, triangles)
    return np.clip(np.rint((1-t)*wa+t*wb),0,255).astype(np.uint8)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--a', required=True, type=Path)
    parser.add_argument('--b', required=True, type=Path)
    parser.add_argument('--landmarks', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--frames', type=int, default=24)
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--fps', type=int, default=24)
    args = parser.parse_args()
    if not (2 <= args.frames <= 120 and 128 <= args.width <= 1122 and 1 <= args.fps <= 60):
        parser.error('Bounded experiment: 2..120 frames, 128..1122 width, 1..60 fps')
    import numpy as np
    import scipy
    from scipy.spatial import Delaunay
    from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version
    data, names, a, b = load_landmarks(args.landmarks)
    original_a, original_b = Image.open(args.a).convert('RGB'), Image.open(args.b).convert('RGB')
    if original_a.size != tuple(data['size']) or original_b.size != original_a.size:
        raise ValueError('Both input sizes must match the annotation; no silent alignment')
    width = args.width
    height = round(width*data['size'][1]/data['size'][0]/2)*2
    aimg = np.asarray(original_a.resize((width,height),Image.Resampling.LANCZOS))
    bimg = np.asarray(original_b.resize((width,height),Image.Resampling.LANCZOS))
    scale = np.array([(width-1)/(data['size'][0]-1),(height-1)/(data['size'][1]-1)])
    a, b = a*scale, b*scale
    # Freeze triangulation once. Retriangulating each frame would cause popping.
    triangles = Delaunay((a+b)/2).simplices
    mid_sign = np.sign(signed_areas((a+b)/2,triangles))
    audit = []
    for t in np.linspace(0,1,101):
        areas = signed_areas((1-t)*a+t*b,triangles)
        bad = np.flatnonzero((areas*mid_sign <= 1e-6))
        audit.append({'t':round(float(t),2),'folded_or_degenerate':len(bad)})
    args.output.mkdir(parents=True, exist_ok=False)
    for directory in ['mesh','fade','diagnostic']:
        (args.output/directory).mkdir()
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',16) if Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf').exists() else ImageFont.load_default()
    frames = []
    for i,t in enumerate(np.linspace(0,1,args.frames)):
        t = float(t)
        rgb = make_frame(aimg,bimg,a,b,triangles,t)
        frame = Image.fromarray(rgb)
        save_png(frame,args.output/'mesh'/f'{i:04}.png')
        fade = Image.fromarray(np.rint((1-t)*aimg.astype(float)+t*bimg).astype('uint8'))
        save_png(fade,args.output/'fade'/f'{i:04}.png')
        diag = Image.new('RGB',(width,height),'#f3f5f8')
        draw = ImageDraw.Draw(diag)
        p = (1-t)*a+t*b
        for tri in triangles:
            draw.line([tuple(p[j]) for j in [*tri,tri[0]]],fill='#c2cbd7',width=1)
        for bone in data['bones']:
            draw.line([tuple(p[names.index(n)]) for n in bone],fill='#d64b7d',width=3)
        for name in names:
            if name.startswith('border_'): continue
            x,y = p[names.index(name)]
            draw.ellipse((x-2,y-2,x+2,y+2),fill='#097f91')
        save_png(diag,args.output/'diagnostic'/f'{i:04}.png')
        frames.append(frame)
        print(f'frame {i+1}/{args.frames}',flush=True)
    # A/B ping-pong with endpoint holds, pure mesh clip separately retained.
    sequence = [0]*12 + list(range(args.frames)) + [args.frames-1]*12 + list(range(args.frames-2,0,-1))
    movie_dir = args.output/'loop'
    movie_dir.mkdir()
    for i,idx in enumerate(sequence):
        panel = Image.new('RGB',(width*3,height+56),'#162231')
        for col,(folder,label) in enumerate([('fade','FADE BASELINE'),('mesh','LANDMARK MESH'),('diagnostic','CONTROL POINTS')]):
            panel.paste(Image.open(args.output/folder/f'{idx:04}.png'),(col*width,56))
            ImageDraw.Draw(panel).text((col*width+18,17),label,font=font,fill='white')
        save_png(panel,movie_dir/f'{i:04}.png')
    for directory, filename in [('mesh','akino-mesh-24f.mp4'),('loop','akino-two-pose-comparison.mp4')]:
        encode_mp4(args.output/directory,args.output/filename,args.fps)
    indices = [0,round((args.frames-1)*.25),round((args.frames-1)*.5),round((args.frames-1)*.75),args.frames-1]
    sheet = Image.new('RGB',(width*5,height+56),'white')
    for col,idx in enumerate(indices):
        sheet.paste(frames[idx],(col*width,56))
        ImageDraw.Draw(sheet).text((col*width+18,17),f'{idx/(args.frames-1):.0%}',font=font,fill='#162231')
    save_png(sheet,args.output/'akino-inbetween-contact.png')
    report = {'method':'manual matching + fixed midpoint Delaunay + inverse barycentric warp + aligned texture blend', 'automatic_detection':False, 'line_redraw':False,'blender_render':False, 'size':[width,height], 'frames':args.frames,'fps':args.fps,'point_count':len(names),'triangle_count':len(triangles), 'mesh':triangles.tolist(), 'fold_audit':audit, 'max_folded_triangles':max(x['folded_or_degenerate'] for x in audit), 'endpoint_pixels_exact':bool(np.array_equal(np.asarray(frames[0]),aimg) and np.array_equal(np.asarray(frames[-1]),bimg)), 'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.a,args.b,args.landmarks]}, 'environment':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__,'pillow':pillow_version}, 'command':sys.argv, 'landmark_displacements_pixels_original':{n:(np.asarray(data['points'][n]['b'])-data['points'][n]['a']).tolist() for n in names if not n.startswith('border_')}, 'limitations':['Manual annotations, not automatic pose recognition','2D screen-space motion, no recovered 3D rotation','Unconstrained mesh can fold around arms and occlusions','Texture blending can soften lines, badges and fingers','No missing surface reconstruction; no line vectorization']}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['point_count','triangle_count','max_folded_triangles','endpoint_pixels_exact']}))

if __name__=='__main__':
    main()
