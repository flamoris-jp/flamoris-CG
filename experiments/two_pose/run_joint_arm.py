"""Manual single-arm redraw: shared contour for opaque paint and constant ink.

Uses measured 2D shoulder/elbow/wrist landmarks and hand contour annotations.
This is simplified re-authoring, not recovered hidden texture or a 3D rig.
"""
import argparse
import io
import json
import math
from pathlib import Path
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw, ImageFont
from layers_akino import LAYERS
from run import save_png,encode_mp4

S=np.array([[646.,590.],[663.,571.]])
E=np.array([[715.,743.],[737.,614.]])
W=np.array([[770.,831.],[806.,522.]])
TIP=np.array([[840.,850.],[895.,480.]])
HAND=next(x for x in LAYERS if x[0]=='hand_r')
SIZE=(480,640)
SCALE=1.05
ORIGIN=np.array([595.,380.])
OFFSET=np.array([40.,40.])
STROKE=2.8


def rotation(angle):
    c,s=np.cos(angle),np.sin(angle)
    return np.array([[c,-s],[s,c]])


def angular_lerp(a,b,t):return a+t*((b-a+np.pi)%(2*np.pi)-np.pi)


def geometry(t):
    if not 0<=t<=1:raise ValueError('t must be in [0,1]')
    upper=E-S;lower=W-E
    u=np.arctan2(upper[:,1],upper[:,0]);v=np.arctan2(lower[:,1],lower[:,0])
    a=angular_lerp(u[0],u[1],t);b=angular_lerp(v[0],v[1],t)
    lengths=(1-t)*np.array([np.linalg.norm(upper[0]),np.linalg.norm(lower[0])])+t*np.array([np.linalg.norm(upper[1]),np.linalg.norm(lower[1])])
    s=(1-t)*S[0]+t*S[1]
    d0=np.array([np.cos(a),np.sin(a)]);d1=np.array([np.cos(b),np.sin(b)])
    e=s+lengths[0]*d0;w=e+lengths[1]*d1
    n0=np.array([-d0[1],d0[0]]);n1=np.array([-d1[1],d1[0]])
    normal=(n0+n1)/np.linalg.norm(n0+n1)
    miter=normal*min(42.,31./max(.35,np.dot(normal,n0)))
    plus=[s+n0*32,(s+e)/2+n0*33,e+miter,(e+w)/2+n1*29,w+n1*25]
    minus=[s-n0*32,(s+e)/2-n0*33,e-miter,(e+w)/2-n1*29,w-n1*25]
    sleeve=np.array(plus+minus[::-1])
    phi=np.arctan2((TIP-W)[:,1],(TIP-W)[:,0])
    ph=angular_lerp(phi[0],phi[1],t)
    def deform(pa,pb):
        la=(np.array(pa)-W[0])@rotation(phi[0]);lb=(np.array(pb)-W[1])@rotation(phi[1])
        return ((1-t)*la+t*lb)@rotation(ph).T+w
    hand=deform(HAND[1],HAND[2])
    cuff=np.array([w+n1*25,w-d1*17+n1*27,w-d1*17-n1*27,w-n1*25])
    # A short connector lives behind sleeve and palm, covering the wrist join.
    from scipy.spatial import ConvexHull
    connector=np.vstack([cuff,hand[[0,1,2,-1,-2,-3]]])
    bridge=connector[ConvexHull(connector).vertices]
    creases=[deform([(785,855),(799,845),(818,845)],[(817,497),(835,485),(858,489)]),
             deform([(821,840),(839,841),(851,839)],[(865,476),(891,476),(914,480)]),
             deform([(824,853),(842,856),(854,854)],[(866,489),(887,487),(910,485)])]
    return {'shoulder':s,'elbow':e,'wrist':w,'sleeve':sleeve,'hand':hand,'cuff':cuff,'bridge':bridge,'creases':creases,'projected_lengths':lengths}


def display(q):return (np.asarray(q)-ORIGIN)*SCALE+OFFSET


def self_intersections(q):
    def cross(a,b,c):
        u,v=b-a,c-a
        return u[0]*v[1]-u[1]*v[0]
    result=0;n=len(q)
    for i in range(n):
        for j in range(i+1,n):
            if j==i+1 or (i==0 and j==n-1):continue
            a,b=q[i],q[(i+1)%n];c,d=q[j],q[(j+1)%n]
            if cross(a,b,c)*cross(a,b,d)<-1e-8 and cross(c,d,a)*cross(c,d,b)<-1e-8:result+=1
    return result


def mask_for(q,size=SIZE,ss=3):
    mask=Image.new('L',(size[0]*ss,size[1]*ss))
    ImageDraw.Draw(mask).polygon([tuple(v*ss) for v in display(q)],fill=255)
    return mask


def render(g,ink=True):
    ss=3;size=(SIZE[0]*ss,SIZE[1]*ss)
    canvas=Image.new('RGB',size,'#e7edf3')
    union=Image.new('L',size)
    # All paint is opaque. Shading is clipped by the same mask as its outline.
    for name,base in [('bridge',(247,199,166)),('hand',(255,216,186)),('sleeve',(248,247,252)),('cuff',(42,44,52))]:
        q=g[name];mask=mask_for(q)
        yy,xx=np.mgrid[:size[1],:size[0]]
        shade=(xx/size[0]*.05+yy/size[1]*.025)
        rgb=np.clip(np.array(base)[None,None,:]*(1-shade[:,:,None]),0,255).astype('uint8')
        canvas.paste(Image.fromarray(rgb),(0,0),mask)
        union=Image.fromarray(np.maximum(np.asarray(union),np.asarray(mask)))
        if ink and name!='bridge':
            pts=[tuple(p*ss) for p in display(q)]
            ImageDraw.Draw(canvas).line(pts+[pts[0]],fill='#25252d',width=round(STROKE*ss),joint='curve')
    if ink:
        crease_layer=Image.new('RGBA',size)
        d=ImageDraw.Draw(crease_layer)
        for q in g['creases']:d.line([tuple(p*ss) for p in display(q)],fill='#ad7761',width=4,joint='curve')
        # Restrict detail strokes to the palm's fill region.
        alpha=np.minimum(np.asarray(crease_layer.getchannel('A')),np.asarray(mask_for(g['hand'])))
        crease_layer.putalpha(Image.fromarray(alpha))
        canvas.paste(crease_layer,(0,0),crease_layer)
    return canvas.resize(SIZE,Image.Resampling.LANCZOS),union


def audit(g):
    masks={n:np.asarray(mask_for(g[n],ss=1))>0 for n in ['hand','sleeve','bridge','cuff']}
    union=np.logical_or.reduce(list(masks.values()))
    holes=ndimage.binary_fill_holes(union)&~union
    _,components=ndimage.label(union)
    return {'components':int(components),'holes':int(holes.sum()),'sleeve_hand_overlap_pixels':int(np.sum(masks['hand']&masks['sleeve'])),'self_intersections':sum(self_intersections(g[n]) for n in ['sleeve','hand','cuff','bridge'])}


def svg(g):
    parts=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 640">','<rect width="480" height="640" fill="#e7edf3"/>']
    for name,color in [('bridge','#f7c7a6'),('hand','#ffd8ba'),('sleeve','#f8f7fc'),('cuff','#2a2c34')]:
        coords=' '.join(f'{x:.3f},{y:.3f}' for x,y in display(g[name]))
        parts.append(f'<polygon points="{coords}" fill="{color}" stroke="{color if name=="bridge" else "#25252d"}" stroke-width="{0 if name=="bridge" else STROKE}" stroke-linejoin="round"/>')
    return ''.join(parts)+'</svg>'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    for n in ['frames','loop','comparison']:(args.output/n).mkdir()
    frames=[];panels=[];checks=[]
    for i,t in enumerate(np.linspace(0,1,48)):
        # Smooth timing with exact endpoints; geometry still driven by angles.
        t=float(t*t*(3-2*t));g=geometry(t);frame,_=render(g);frames.append(frame);checks.append(audit(g))
        save_png(frame,args.output/'frames'/f'{i:04}.png')
        (args.output/f'arm-{i:02}.svg').write_text(svg(g))
        diagnostic=Image.new('RGB',SIZE,'#f4f6fa');d=ImageDraw.Draw(diagnostic)
        joints=[display(g[n]) for n in ['shoulder','elbow','wrist']]
        d.line([tuple(q) for q in joints],fill='#ce527b',width=4)
        for q in joints:d.ellipse((q[0]-5,q[1]-5,q[0]+5,q[1]+5),fill='#087f94')
        panel=Image.new('RGB',(960,684),'#162231')
        panel.paste(frame,(0,44));panel.paste(diagnostic,(480,44))
        d=ImageDraw.Draw(panel);d.text((16,12),'SHARED STROKE + FILL',fill='white');d.text((496,12),'2D JOINT ROTATION',fill='white');panels.append(panel)
    seq=[0]*12+list(range(48))+[47]*12+list(range(46,0,-1))
    for i,j in enumerate(seq):
        save_png(frames[j],args.output/'loop'/f'{i:04}.png');save_png(panels[j],args.output/'comparison'/f'{i:04}.png')
    encode_mp4(args.output/'loop',args.output/'Akino-Joint-Arm.mp4',24)
    encode_mp4(args.output/'comparison',args.output/'Akino-Joint-Arm-Controls.mp4',24)
    buf=io.BytesIO();frames[0].save(buf,format='GIF',save_all=True,append_images=[frames[j] for j in seq[1:]],duration=42,loop=0)
    (args.output/'Akino-Joint-Arm.gif').write_bytes(buf.getvalue())
    sheet=Image.new('RGB',(480*5,640),'#e7edf3')
    for col,j in enumerate([0,12,24,35,47]):sheet.paste(frames[j],(col*480,0))
    save_png(sheet,args.output/'Akino-Joint-Arm-Contact.png')
    report={'method':'manual 2D joint angles and projected lengths; hand-local contour morph; shared contour stroke/fill','frames':48,'fps':24,'stroke_width_px':STROKE,'max_components':max(c['components'] for c in checks),'max_hole_pixels':max(c['holes'] for c in checks),'max_self_intersections':max(c['self_intersections'] for c in checks),'min_sleeve_hand_overlap_pixels':min(c['sleeve_hand_overlap_pixels'] for c in checks),'checks':checks,'limitations':['Single image-right arm only, detached from body','Manually simplified sleeve and hand; flat clipped shading replaces original texture','2D projected bone lengths interpolate; no recovered 3D rotation','No automatic part extraction or full-character acceptance','SVG retains geometry/base colors; PNG includes extra shading and palm crease strokes']}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='checks'}))

if __name__=='__main__':main()
