"""Manual layered smooth-warp follow-up to the full-image mesh baseline."""
import argparse
import io
import json
import hashlib
from pathlib import Path
import subprocess
import numpy as np
from scipy.spatial import Delaunay
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from run import load_landmarks, signed_areas, save_png, encode_mp4
from layers_akino import LAYERS


def prepare(image, polygon):
    mask = Image.new('L',image.size)
    ImageDraw.Draw(mask).polygon([tuple(p) for p in polygon],fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(.45))
    alpha = np.asarray(mask,dtype=float)/255
    rgb = np.asarray(image,dtype=float)
    return np.dstack([rgb*alpha[:,:,None],alpha*255]).astype(np.float32)


def build_layers(aimg,bimg,data,scale):
    layers=[]
    for name,pa,pb,inner in LAYERS:
        if len(pa)!=len(pb):
            raise ValueError(f'{name}: unmatched boundaries')
        # Store explicit triangles after triangulation for reproducible rendering.
        a=np.array(pa+[data['points'][n]['a'] for n in inner],dtype=float)*scale
        b=np.array(pb+[data['points'][n]['b'] for n in inner],dtype=float)*scale
        triangles=Delaunay((a+b)/2).simplices
        ra,rb=prepare(aimg,np.array(pa)*scale),prepare(bimg,np.array(pb)*scale)
        if name=='torso':
            # B's fist covers its coat in the source image. This deliberately
            # limited, flat patch is a declared manual disocclusion assumption.
            rgb=np.asarray(bimg).copy()
            patch=Image.fromarray(rgb)
            ImageDraw.Draw(patch).polygon([tuple(np.array(p)*scale) for p in [(495,589),(547,581),(569,618),(567,661),(547,685),(494,672)]],fill=(236,233,235))
            rb=prepare(patch,np.array(pb)*scale)
        ref=np.sign(signed_areas((a+b)/2,triangles))
        folds=[int(np.sum(signed_areas((1-t)*a+t*b,triangles)*ref<=1e-6)) for t in np.linspace(0,1,101)]
        layers.append(dict(name=name,a=a,b=b,triangles=triangles,ra=ra,rb=rb,linear_baseline_max_folds=max(folds)))
    return layers


def smooth_warp(image, source, target):
    from scipy.interpolate import RBFInterpolator
    from scipy.ndimage import map_coordinates
    h,w=image.shape[:2]
    output=np.zeros_like(image)
    lo=np.maximum(np.floor(target.min(axis=0)-12).astype(int),[0,0])
    hi=np.minimum(np.ceil(target.max(axis=0)+12).astype(int),[w,h])
    yy,xx=np.mgrid[lo[1]:hi[1],lo[0]:hi[0]]
    query=np.column_stack([xx.ravel(),yy.ravel()])
    # Smooth inverse displacement, with a normalized coordinate domain.
    field=RBFInterpolator(target/128,(source-target)/128,kernel='thin_plate_spline',smoothing=1e-7)
    samples=query+128*field(query/128)
    for c in range(image.shape[2]):
        output[lo[1]:hi[1],lo[0]:hi[0],c]=map_coordinates(image[:,:,c],[samples[:,1],samples[:,0]],order=1,mode='constant',cval=0).reshape(xx.shape)
    return output


def render(layers,t,size):
    w,h=size
    out=np.full((h,w,3),255.,dtype=np.float32)
    for layer in layers:
        a,b=layer['a'],layer['b']
        p=(1-t)*a+t*b
        wa=smooth_warp(layer['ra'],a,p)
        wb=smooth_warp(layer['rb'],b,p)
        rgba=(1-t)*wa+t*wb
        alpha=np.clip(rgba[:,:,3:4]/255,0,1)
        out=rgba[:,:,:3]+out*(1-alpha)
    return Image.fromarray(np.clip(np.rint(out),0,255).astype('uint8'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--a',required=True,type=Path);p.add_argument('--b',required=True,type=Path)
    p.add_argument('--landmarks',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--width',type=int,default=480);p.add_argument('--frames',type=int,default=24)
    p.add_argument('--midpoint-only',action='store_true')
    args=p.parse_args()
    if not (128<=args.width<=1122 and 2<=args.frames<=120):p.error('width 128..1122, frames 2..120')
    data,names,a,b=load_landmarks(args.landmarks)
    width=args.width;height=round(width*data['size'][1]/data['size'][0]/2)*2
    original_a,original_b=Image.open(args.a).convert('RGB'),Image.open(args.b).convert('RGB')
    if original_a.size!=tuple(data['size']) or original_b.size!=original_a.size:raise ValueError('Image size mismatch')
    size=(width,height)
    aimg,bimg=[im.resize(size,Image.Resampling.LANCZOS) for im in [original_a,original_b]]
    scale=np.array([(width-1)/(data['size'][0]-1),(height-1)/(data['size'][1]-1)])
    layers=build_layers(aimg,bimg,data,scale)
    args.output.mkdir(parents=True,exist_ok=False)
    if args.midpoint_only:
        save_png(render(layers,.5,size),args.output/'midpoint.png')
        print([{k:l[k] for k in ['name','linear_baseline_max_folds']} for l in layers]);return
    for folder in ['layered','comparison','loop']:(args.output/folder).mkdir()
    font_path=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    font=ImageFont.truetype(str(font_path),16) if font_path.exists() else ImageFont.load_default()
    images=[]
    for i,t in enumerate(np.linspace(0,1,args.frames)):
        # Endpoint originals are exact; separate seam errors below measure the
        # actual layered reconstruction without this endpoint override.
        frame=aimg.copy() if i==0 else bimg.copy() if i==args.frames-1 else render(layers,float(t),size)
        images.append(frame)
        save_png(frame,args.output/'layered'/f'{i:04}.png')
        fade=Image.blend(aimg,bimg,float(t))
        diag=Image.new('RGB',size,'#eef2f6');d=ImageDraw.Draw(diag)
        pts=(1-t)*a*scale+t*b*scale
        for layer in layers:
            lp=(1-t)*layer['a']+t*layer['b']
            for tri in layer['triangles']:
                d.line([tuple(lp[j]) for j in [*tri,tri[0]]],fill='#c4cfd8',width=1)
        for chain in data['bones']:
            d.line([tuple(pts[names.index(n)]) for n in chain],fill='#cc4672',width=3)
        for n in ['eye_l','eye_r','neck','shoulder_l','shoulder_r','elbow_l','elbow_r','wrist_l','wrist_r','waist','knee_l','knee_r','ankle_l','ankle_r']:
            x,y=pts[names.index(n)];d.ellipse((x-3,y-3,x+3,y+3),fill='#0a8491')
        panel=Image.new('RGB',(3*width,height+56),'#162231')
        for col,(im,label) in enumerate([(fade,'FADE BASELINE'),(frame,'LAYERED TPS WARP'),(diag,'MANUAL CONTROLS')]):
            panel.paste(im,(col*width,56));ImageDraw.Draw(panel).text((col*width+18,17),label,font=font,fill='white')
        save_png(panel,args.output/'comparison'/f'{i:04}.png')
        print(f'layered {i+1}/{args.frames}',flush=True)
    seq=[0]*12+list(range(args.frames))+[args.frames-1]*12+list(range(args.frames-2,0,-1))
    for i,j in enumerate(seq):
        (args.output/'loop'/f'{i:04}.png').write_bytes((args.output/'comparison'/f'{j:04}.png').read_bytes())
    for folder,name in [('layered','Akino-2Pose-24frames.mp4'),('loop','Akino-2Pose-Comparison.mp4')]:
        encode_mp4(args.output/folder,args.output/name,24)
    # A compact repeated motion preview with original endpoint holds.
    loopframes=[images[j] for j in seq]
    gif_buffer=io.BytesIO()
    loopframes[0].save(gif_buffer,format='GIF',save_all=True,append_images=loopframes[1:],duration=42,loop=0)
    (args.output/'Akino-2Pose-Preview.gif').write_bytes(gif_buffer.getvalue())
    sheet=Image.new('RGB',(width*5,height+56),'white')
    for col,idx in enumerate([0,6,12,17,23] if args.frames==24 else [round(v*(args.frames-1)) for v in [0,.25,.5,.75,1]]):
        sheet.paste(images[idx],(col*width,56));ImageDraw.Draw(sheet).text((col*width+18,17),f'{idx/(args.frames-1):.0%}',font=font,fill='#162231')
    save_png(sheet,args.output/'Akino-2Pose-Contact.png')
    seams=[]
    for t,original in [(0,aimg),(1,bimg)]:
        rr=np.asarray(render(layers,t,size),dtype=float)
        seams.append(float(np.abs(rr-np.asarray(original)).mean()))
    report={'method':'manual semantic layers + inverse thin-plate-spline displacement + premultiplied alpha composite', 'points_manual':len(names),'layers':[{k:l[k] for k in ['name','linear_baseline_max_folds']} for l in layers], 'layered_endpoint_reconstruction_mae_rgb':seams, 'endpoint_override':True,'automatic_detection':False,'line_redraw':False,'recovered_3d_rotation':False,'blender_render':False,'size':list(size),'frames':args.frames,'fps':24,'manual_occlusion_assumptions':['Fixed leg/torso/arm/hand/head layer order','Flat coat-color patch beneath pose B left fist; no inferred hidden texture'], 'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.a,args.b,args.landmarks]},'limitations':['Masks are manually approximated and leave white edge fringes','Triangle counts describe discarded linear baseline; smooth warp is not proven fold-free','Fingers blend between different gestures; not redrawn','Coat patch and fixed stacking can be visible','2D motion does not establish a physical 3D body turn']}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
