"""Source-art sleeve and hand deformation on fixed Akino A.

Manual geometry/correspondences and source A/B textures; no generative redraw.
The hand uses authored dorsal/palmar view selection around an edge-on phase.
"""
import argparse
import io
import json
import hashlib
from pathlib import Path
import numpy as np
from scipy import ndimage
from scipy.interpolate import RBFInterpolator
from PIL import Image,ImageDraw
from layers_akino import LAYERS
from run_joint_arm import rotation,angular_lerp
from run import save_png,encode_mp4

PIVOT=np.array([642.,625.])
ELBOW=np.array([[714.,744.],[716.,668.]])
WRIST=np.array([[773.,833.],[785.,576.]])
HAND_WRIST=np.array([[773.,833.],[806.,522.]])
HAND_DIRECTION=np.array([[841.,851.],[899.,480.]])-HAND_WRIST
# The proximal cut follows the original shoulder seam; upper coat remains fixed.
SLEEVE=np.array([(640,582),(661,603),(678,648),(695,680),(716,703),(740,733),(762,757),(782,781),(799,800),(800,813),(782,838),(754,857),(736,857),(719,836),(696,810),(676,780),(654,744),(641,708),(635,668),(630,627)],float)
SIZE=(1122,1402)


def polygon_mask(points,size=SIZE):
    m=Image.new('L',size);ImageDraw.Draw(m).polygon([tuple(p) for p in points],fill=255);return np.asarray(m)>0


def joint_pose(t):
    if not np.isfinite(t) or not 0<=t<=1:raise ValueError('t must be finite in [0,1]')
    u=ELBOW-PIVOT;v=WRIST-ELBOW
    ua=np.arctan2(u[:,1],u[:,0]);va=np.arctan2(v[:,1],v[:,0])
    theta=angular_lerp(ua[0],ua[1],t);phi=angular_lerp(va[0],va[1],t)
    lu=(1-t)*np.linalg.norm(u[0])+t*np.linalg.norm(u[1]);lv=(1-t)*np.linalg.norm(v[0])+t*np.linalg.norm(v[1])
    e=PIVOT+lu*np.array([np.cos(theta),np.sin(theta)])
    w=e+lv*np.array([np.cos(phi),np.sin(phi)])
    return e,w,theta,phi,lu,lv


def move_cage(points,t):
    p=np.array(points,dtype=float);e,w,theta,phi,lu,lv=joint_pose(t)
    u0=ELBOW[0]-PIVOT;v0=WRIST[0]-ELBOW[0]
    a0=np.arctan2(u0[1],u0[0]);b0=np.arctan2(v0[1],v0[0])
    def transform(p,origin,target,old_angle,new_angle,ratio):
        q=(p-origin)@rotation(old_angle);q[:,0]*=ratio
        return q@rotation(new_angle).T+target
    upper=transform(p,PIVOT,PIVOT,a0,theta,lu/np.linalg.norm(u0))
    lower=transform(p,ELBOW[0],e,b0,phi,lv/np.linalg.norm(v0))
    along=(p-ELBOW[0])@(v0/np.linalg.norm(v0))
    weight=np.clip((along+25)/60,0,1)[:,None]
    target=(1-weight)*upper+weight*lower
    # Keep coat-cap points close to the corrected shoulder immobile.
    cap=np.clip((np.linalg.norm(p-PIVOT,axis=1)-22)/43,0,1)[:,None]
    return p+(target-p)*cap


def rgba_cut(source,points,margin=4,white_coat=False):
    region=ndimage.binary_dilation(polygon_mask(points),iterations=margin)
    rgb=np.asarray(source)
    foreground=np.min(rgb,axis=2)<247
    foreground=ndimage.binary_closing(foreground,iterations=1)
    # White coat interiors belong to the cutout; hand gaps remain background.
    if white_coat:foreground=ndimage.binary_fill_holes(foreground)
    alpha=region&foreground
    if white_coat:
        # Fill enclosed white fabric within the manually identified sleeve.
        alpha=region&ndimage.binary_fill_holes(ndimage.binary_closing(alpha,iterations=3))
    alpha=ndimage.binary_fill_holes(alpha)
    labels,count=ndimage.label(alpha)
    if not count:raise ValueError('Empty source-art cutout')
    sizes=np.bincount(labels.ravel());sizes[0]=0
    alpha=labels==np.argmax(sizes)
    out=np.zeros((*rgb.shape[:2],4),dtype=float);out[:,:,:3]=rgb;out[:,:,3]=alpha*255
    return out,alpha


def sleeve_cage():
    return np.vstack([SLEEVE,PIVOT,ELBOW[0],WRIST[0],(PIVOT+ELBOW[0])/2,(ELBOW[0]+WRIST[0])/2])


def warp_sleeve(rgba,t):
    a=sleeve_cage();b=move_cage(a,t)
    # Crop evaluation to this sleeve's destination region, not the whole canvas.
    lo=np.maximum(np.floor(b.min(axis=0)-10).astype(int),[0,0]);hi=np.minimum(np.ceil(b.max(axis=0)+10).astype(int),SIZE)
    yy,xx=np.mgrid[lo[1]:hi[1],lo[0]:hi[0]];query=np.column_stack([xx.ravel(),yy.ravel()])
    inverse=RBFInterpolator(b/128,(a-b)/128,kernel='thin_plate_spline',smoothing=1e-8)
    src=query+128*inverse(query/128)
    alpha=rgba[:,:,3]/255
    out=np.zeros((SIZE[1],SIZE[0],4),dtype='uint8')
    sampled_alpha=ndimage.map_coordinates(alpha,[src[:,1],src[:,0]],order=1,mode='constant').reshape(xx.shape)
    for c in range(3):
        values=ndimage.map_coordinates(rgba[:,:,c]*alpha,[src[:,1],src[:,0]],order=1,mode='constant').reshape(xx.shape)
        out[lo[1]:hi[1],lo[0]:hi[0],c]=np.rint(np.divide(values,sampled_alpha,out=np.zeros_like(values),where=sampled_alpha>1e-5)).astype('uint8')
    out[lo[1]:hi[1],lo[0]:hi[0],3]=np.rint(sampled_alpha*255).astype('uint8')
    return Image.fromarray(out),b


def hand_layer(hand_a,hand_b,t):
    # Rotate the selected original view into its own source hand coordinates.
    # At the thin edge the surface changes from dorsal A to palmar B; no fade.
    view=0 if t<=.5 else 1
    source=[hand_a,hand_b][view]
    source_angle=np.arctan2(HAND_DIRECTION[view,1],HAND_DIRECTION[view,0])
    angle=angular_lerp(np.arctan2(HAND_DIRECTION[0,1],HAND_DIRECTION[0,0]),np.arctan2(HAND_DIRECTION[1,1],HAND_DIRECTION[1,0]),t)
    _,w,*_=joint_pose(t)
    width=max(.16,abs(np.cos(np.pi*t)))
    # No mirroring of the source drawings: B already depicts the palmar view.
    extents=[]
    for n,rgba in enumerate([hand_a,hand_b]):
        y,x=np.nonzero(rgba[:,:,3]>128)
        xy=np.column_stack([x,y])-HAND_WRIST[n]
        ph=np.arctan2(HAND_DIRECTION[n,1],HAND_DIRECTION[n,0])
        extents.append(float(np.max((xy@rotation(ph))[:,0])))
    desired=(1-t)*extents[0]+t*extents[1]
    length_scale=desired/extents[view]
    mat=rotation(angle)@np.diag([length_scale,width])@rotation(source_angle).T
    inv=np.linalg.inv(mat);offset=HAND_WRIST[view]-inv@w
    coeff=(inv[0,0],inv[0,1],offset[0],inv[1,0],inv[1,1],offset[1])
    im=Image.fromarray(source.astype('uint8'),'RGBA').transform(SIZE,Image.Transform.AFFINE,coeff,resample=Image.Resampling.BICUBIC)
    arr=np.array(im);paint=arr[:,:,3]>32
    # A nearly edge-on hand needs a continuous thickness profile. Its contour
    # comes from the projected original, and new interior uses sampled skin.
    mask=paint.copy()
    if width<.30:
        from scipy.spatial import ConvexHull
        y,x=np.nonzero(paint);q=np.column_stack([x,y]);hull=q[ConvexHull(q).vertices]
        mask=polygon_mask(hull)
    mask=ndimage.binary_fill_holes(mask)
    skin=source[:,:,:3][(source[:,:,3]>128)&(source[:,:,0]>180)&(source[:,:,0]-source[:,:,1]>12)&(source[:,:,0]-source[:,:,2]>20)]
    color=np.median(skin,axis=0).astype('uint8')
    arr[mask&~paint,:3]=color;arr[mask,3]=255
    edge=ndimage.binary_dilation(mask,iterations=1)^ndimage.binary_erosion(mask,iterations=1)
    arr[edge,:3]=[37,30,29];arr[edge,3]=255
    return Image.fromarray(arr),view,width


def prepare(source_a,source_b):
    if source_a.size!=SIZE or source_b.size!=SIZE:raise ValueError('Both originals must be 1122x1402')
    sleeve,sm=rgba_cut(source_a,SLEEVE,margin=4,white_coat=True)
    ha,ma=rgba_cut(source_a,next(l for l in LAYERS if l[0]=='hand_r')[1],margin=5)
    hb,mb=rgba_cut(source_b,next(l for l in LAYERS if l[0]=='hand_r')[2],margin=5)
    erase=ndimage.binary_dilation(polygon_mask(SLEEVE)|polygon_mask(next(l for l in LAYERS if l[0]=='hand_r')[1]),iterations=11)
    body=source_a.copy();body.paste('white',(0,0,*SIZE),Image.fromarray(erase.astype('uint8')*255))
    # Reuse B's visible coat only in the narrow under-arm clothing gap.
    aa=np.array([(646,590),(643,705),(671,824),(725,976),(600,1020),(523,850),(553,755)],float)
    bb=np.array([(663,571),(682,635),(739,800),(795,908),(720,969),(613,816),(664,705)],float)
    torso=polygon_mask(next(l for l in LAYERS if l[0]=='torso')[1])
    yy,xx=np.mgrid[:SIZE[1],:SIZE[0]]
    donor_mask=erase&torso&(yy>680)&(xx>625)
    py,px=np.nonzero(donor_mask)
    donor=RBFInterpolator(aa/128,(bb-aa)/128,kernel='thin_plate_spline',smoothing=1e-7)
    q=np.column_stack([px,py]);coords=q+128*donor(q/128)
    body_rgb=np.asarray(body).copy();b=np.asarray(source_b)
    for c in range(3):body_rgb[py,px,c]=ndimage.map_coordinates(b[:,:,c].astype(float),[coords[:,1],coords[:,0]],order=1,mode='nearest').astype('uint8')
    body=Image.fromarray(body_rgb)
    head=polygon_mask(next(l for l in LAYERS if l[0]=='head')[1])
    cap=polygon_mask([(612,565),(642,577),(661,608),(666,631),(651,646),(633,640),(624,611)])
    return {'sleeve':sleeve,'hand_a':ha,'hand_b':hb,'body':body,'head':head,'cap':cap,'erase':erase,'donor':donor_mask,'source':source_a}


def render(prepared,t):
    sleeve,cage=warp_sleeve(prepared['sleeve'],t)
    hand,view,width=hand_layer(prepared['hand_a'],prepared['hand_b'],t)
    # A concealed skin connector keeps wrist coverage under the original cuff.
    e,w,_,phi,_,_=joint_pose(t);d=np.array([np.cos(phi),np.sin(phi)]);n=np.array([-d[1],d[0]])
    bridge=np.array([w-d*10+n*15,w+d*17+n*15,w+d*17-n*15,w-d*10-n*15])
    layer=Image.new('RGBA',SIZE);ImageDraw.Draw(layer).polygon([tuple(p) for p in bridge],fill=(249,200,167,255))
    layer=Image.alpha_composite(layer,hand);layer=Image.alpha_composite(layer,sleeve)
    rgba=np.array(layer);binary=rgba[:,:,3]>32
    labels,count=ndimage.label(binary)
    sizes=np.bincount(labels.ravel());sizes[0]=0
    main=labels==np.argmax(sizes)
    keep=ndimage.binary_dilation(main,iterations=2)
    rgba[~keep,3]=0
    rgba[(labels!=np.argmax(sizes))&(rgba[:,:,3]>32),3]=0
    raw_holes=ndimage.binary_fill_holes(main)&~main
    repaired=int(raw_holes.sum())
    if repaired>32:raise ValueError('Large arm hole requires geometry correction')
    if repaired:
        _,nearest=ndimage.distance_transform_edt(~main,return_indices=True)
        rgba[raw_holes]=rgba[nearest[0][raw_holes],nearest[1][raw_holes]]
        rgba[raw_holes,3]=255
    layer=Image.fromarray(rgba)
    frame=Image.alpha_composite(prepared['body'].convert('RGBA'),layer).convert('RGB')
    hm=Image.fromarray((prepared['head']|prepared['cap']).astype('uint8')*255);frame.paste(prepared['source'],(0,0),hm)
    alpha=np.asarray(layer.getchannel('A'))
    allowed=prepared['erase']|(alpha>0)
    changed=np.any(np.asarray(frame)!=np.asarray(prepared['source']),axis=2)
    # Probe a local band around the elbow/wrist; body alone is not a coverage test.
    coverage=alpha>32
    holes=ndimage.binary_fill_holes(coverage)&~coverage
    _,components=ndimage.label(coverage)
    return frame,{'view':'back_A' if view==0 else 'palm_B','hand_width_factor':width,'outside_edit_pixels':int(np.sum(changed&~allowed)),'head_changed_pixels':int(np.sum(changed&prepared['head'])),'repaired_pixels':repaired,'arm_components':int(components),'arm_hole_pixels':int(holes.sum()),'donor_coat_pixels':int(prepared['donor'].sum())}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--a',required=True,type=Path);p.add_argument('--b',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--preview-only',action='store_true');args=p.parse_args()
    with Image.open(args.a) as im:a=im.convert('RGB')
    with Image.open(args.b) as im:b=im.convert('RGB')
    prepared=prepare(a,b);args.output.mkdir(parents=True,exist_ok=False)
    if args.preview_only:
        for t in [0,.25,.5,.75,1]:
            im,c=render(prepared,t);save_png(im.resize((560,700),Image.Resampling.LANCZOS),args.output/f'pose-{t}.png');print(t,c,flush=True)
        return
    for n in ['frames','loop','comparison']:(args.output/n).mkdir()
    frames=[];panels=[];checks=[]
    for i,v in enumerate(np.linspace(0,1,48)):
        t=float(v*v*(3-2*v));im,c=render(prepared,t);checks.append(c);small=im.resize((720,900),Image.Resampling.LANCZOS);frames.append(small)
        save_png(small,args.output/'frames'/f'{i:04}.png')
        panel=Image.new('RGB',(1440,940),'#162231');panel.paste(a.resize((720,900),Image.Resampling.LANCZOS),(0,40));panel.paste(small,(720,40));d=ImageDraw.Draw(panel);d.text((14,12),'ORIGINAL A',fill='white');d.text((734,12),'SOURCE-ART ARM',fill='white');panels.append(panel)
        print(f'original art {i+1}/48',flush=True)
    seq=[0]*12+list(range(48))+[47]*12+list(range(46,0,-1))
    for i,j in enumerate(seq):save_png(frames[j],args.output/'loop'/f'{i:04}.png');save_png(panels[j],args.output/'comparison'/f'{i:04}.png')
    encode_mp4(args.output/'loop',args.output/'Akino-Original-Art-Arm.mp4',24);encode_mp4(args.output/'comparison',args.output/'Akino-Original-Art-Arm-Comparison.mp4',24)
    # Reuse a single palette and disable GIF optimization for predictable encoding cost.
    gif_frames=[f.resize((560,700),Image.Resampling.LANCZOS) for f in frames]
    palette=Image.fromarray(np.vstack([np.asarray(gif_frames[0]),np.asarray(gif_frames[-1])])).quantize(colors=256)
    gif=[gif_frames[j].quantize(palette=palette,dither=Image.Dither.NONE) for j in seq]
    buf=io.BytesIO();gif[0].save(buf,format='GIF',save_all=True,append_images=gif[1:],duration=42,loop=0,optimize=False);(args.output/'Akino-Original-Art-Arm.gif').write_bytes(buf.getvalue())
    sheet=Image.new('RGB',(3600,900),'white')
    for col,j in enumerate([0,12,24,35,47]):sheet.paste(frames[j],(col*720,0))
    save_png(sheet,args.output/'Akino-Original-Art-Arm-Contact.png')
    report={'method':'source A sleeve TPS deformation; source A/B hand affine surface views; shoulder-cap anchoring; B coat donor patch','frames':48,'fps':24,'size':[720,900],'pivot':PIVOT.tolist(),'max_outside_edit_pixels':max(c['outside_edit_pixels'] for c in checks),'max_head_changed_pixels':max(c['head_changed_pixels'] for c in checks),'max_arm_holes':max(c['arm_hole_pixels'] for c in checks),'max_arm_components':max(c['arm_components'] for c in checks),'max_repaired_pixels':max(c['repaired_pixels'] for c in checks),'inputs':{str(p.name):hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.a,args.b]},'checks':checks,'limitations':['One arm only; body and other arm fixed','Manual shoulder/cutout/donor correspondences','Hand surfaces switch near edge-on; compression floor is authored, not recovered 3D; narrow profiles use a hull and source-sampled skin fill','Hidden sleeve backside uses A artwork; coat donor B is warped and may need retouching','A hidden wrist connector is flat skin color; source-view details still change at the edge, though projected hand length is matched continuously']}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print({k:v for k,v in report.items() if k!='checks'})

if __name__=='__main__':main()
