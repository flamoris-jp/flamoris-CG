"""Joint refinements: hand side volume, tapered wrist, and coat underarm gusset.

Original A/B surface artwork is retained. Unseen side and joint cloth are
explicitly authored completion assumptions, with colors/texture from originals.
"""
import argparse
import io
import json
from pathlib import Path
import numpy as np
from scipy import ndimage
from PIL import Image,ImageDraw
from run_original_art_arm import prepare as original_prepare,warp_sleeve,hand_layer as flat_hand,joint_pose,move_cage,polygon_mask,SIZE,HAND_DIRECTION,PIVOT
from run_joint_arm import rotation,angular_lerp
from run import save_png,encode_mp4

SEAM=np.array([(630,625),(639,675),(647,716),(656,752)],float)
INNER=np.array([(630,627),(635,668),(641,708),(654,744)],float)


def angle_at(t):
    phi=np.arctan2(HAND_DIRECTION[:,1],HAND_DIRECTION[:,0])
    return angular_lerp(phi[0],phi[1],t)


def prepare(a,b):
    p=original_prepare(a,b)
    # Remove the baked orange oval at the end of the original cuff. Preserve
    # fabric, cuff rim and black lining; a tapered wrist supplies the skin.
    rgba=p['sleeve'].copy();rgb=rgba[:,:,:3]
    yy,xx=np.mgrid[:SIZE[1],:SIZE[0]]
    skin=(rgb[:,:,0]>150)&(rgb[:,:,0]-rgb[:,:,1]>17)&(rgb[:,:,1]-rgb[:,:,2]>10)
    near=(xx-773)**2+(yy-833)**2<48**2
    removed=skin&near&(rgba[:,:,3]>0);rgba[removed,3]=0
    p['sleeve']=rgba;p['removed_wrist_oval_pixels']=int(removed.sum())
    # The old aperture is used only as hidden coverage, not as its photographed
    # circular skin/shadow face. It follows the same cuff warp as the fabric.
    aperture=np.zeros_like(rgba);aperture[:,:,:3]=[249,201,169];aperture[:,:,3]=removed*255
    p['wrist_aperture']=aperture
    p['cloth_source']=np.asarray(b).copy()
    return p


def hand_volume(p,t):
    im,view,width=flat_hand(p['hand_a'],p['hand_b'],t)
    arr=np.asarray(im);mask=arr[:,:,3]>32
    angle=angle_at(t);normal=np.array([-np.sin(angle),np.cos(angle)])
    # Finite physical thickness grows as the painted surface turns edge-on.
    depth=14*np.sin(np.pi*t)**2
    volume=mask.copy()
    for step in np.linspace(-depth/2,depth/2,13):
        volume|=ndimage.shift(mask.astype('uint8'),(normal[1]*step,normal[0]*step),order=0,mode='constant')>0
    volume=ndimage.binary_fill_holes(volume)
    source=p['hand_a'] if view==0 else p['hand_b'];rgb=source[:,:,:3]
    skin=rgb[(source[:,:,3]>128)&(rgb[:,:,0]>180)&(rgb[:,:,0]-rgb[:,:,1]>12)&(rgb[:,:,0]-rgb[:,:,2]>20)]
    base=np.median(skin,axis=0)
    result=np.zeros_like(arr)
    # Warm side shading makes the newly exposed thickness readable.
    result[volume,:3]=np.clip(base*np.array([.96,.90,.87]),0,255).astype('uint8');result[volume,3]=255
    result_image=Image.fromarray(result)
    # Surface plane on the upper side of the volume. At exact edge-on the
    # original remains only a thin highlight, while the shaded side stays solid.
    if np.sin(np.pi*t)**2>.80:
        # Near exact edge-on, the photographed face's compressed outer ink
        # would create parallel black rails inside the new side surface.
        # Keep its sampled color but suppress only those degenerate dark rails.
        face=np.array(im);dark=(face[:,:,:3].max(axis=2)<110)&(face[:,:,3]>0)
        face[dark,:3]=np.clip(base*np.array([1.,.97,.94]),0,255).astype('uint8')
        im=Image.fromarray(face)
    result_image=Image.alpha_composite(result_image,im)
    result=np.array(result_image)
    edge=ndimage.binary_dilation(volume,iterations=1)^ndimage.binary_erosion(volume,iterations=1)
    result[edge,:3]=[38,30,29];result[edge,3]=255
    return Image.fromarray(result),{'hand_added_depth':float(depth),'hand_side_pixels':int(np.sum(volume&~mask)),'hand_view':'back_A' if view==0 else 'palm_B'}


def wrist_shape(t):
    e,w,_,phi,_,_=joint_pose(t)
    d=np.array([np.cos(phi),np.sin(phi)]);n=np.array([-d[1],d[0]])
    a=angle_at(t);hd=np.array([np.cos(a),np.sin(a)]);hn=np.array([-hd[1],hd[0]])
    # The cross-section narrows toward the hand; no disk or constant-width
    # orange rectangle is placed over the cuff opening.
    root=w-d*35;middle=w+hd*3;tip=w+hd*29
    end_radius=11+5*abs(np.cos(np.pi*t))
    return np.array([root+n*30,middle+hn*18,tip+hn*end_radius,tip-hn*end_radius,middle-hn*18,root-n*30])


def cloth_joint(p,t):
    moving=move_cage(INNER,t)
    # Slight overlap under both source coat and warped sleeve prevents a
    # background slit between two individually closed painted components.
    poly=np.vstack([SEAM+[-5,0],(moving+[8,0])[::-1]])
    mask=polygon_mask(poly)
    y,x=np.nonzero(mask)
    # Sample a visible, unmarked B coat strip; this is donor fabric, not white
    # background infill or inferred hidden embroidery.
    u=np.clip((x-625)/100,0,1);v=np.clip((y-625)/140,0,1)
    sx=682+u*18;sy=714+v*52
    out=np.zeros((SIZE[1],SIZE[0],4),dtype='uint8')
    for c in range(3):out[y,x,c]=ndimage.map_coordinates(p['cloth_source'][:,:,c].astype(float),[sy,sx],order=1,mode='nearest').astype('uint8')
    out[y,x,3]=255
    # Exterior continuation of the coat's underarm edge. Inner edges stay
    # under the original coat and the sleeve rather than being double-inked.
    im=Image.fromarray(out);d=ImageDraw.Draw(im)
    d.line([tuple(SEAM[-1]),tuple(moving[-1]+[8,0])],fill=(50,43,44,255),width=2)
    return im,mask,poly


def render(p,t):
    sleeve,_=warp_sleeve(p['sleeve'],t)
    aperture,_=warp_sleeve(p['wrist_aperture'],t)
    hand,hcheck=hand_volume(p,t)
    wrist=wrist_shape(t)
    # Skin colors sampled from the original hand; a gentle directional
    # shade distinguishes the underside of the wrist without a circular face.
    source=p['hand_a'] if t<=.5 else p['hand_b'];rgb=source[:,:,:3]
    samples=rgb[(source[:,:,3]>128)&(rgb[:,:,0]>180)&(rgb[:,:,0]-rgb[:,:,1]>12)&(rgb[:,:,0]-rgb[:,:,2]>20)]
    color=tuple(np.rint(np.median(samples,axis=0)).astype('uint8'))+(255,)
    skin=Image.new('RGBA',SIZE);ImageDraw.Draw(skin).polygon([tuple(q) for q in wrist],fill=color)
    # Hand is placed after the wrist so its original contour covers the joint;
    # original cuff is placed last and naturally hides the inner wrist edge.
    arm=Image.alpha_composite(aperture,skin);arm=Image.alpha_composite(arm,hand);arm=Image.alpha_composite(arm,sleeve)
    gusset,gap,poly=cloth_joint(p,t)
    clothing=Image.alpha_composite(p['body'].convert('RGBA'),gusset)
    rgba=np.array(arm);alpha=rgba[:,:,3]>32
    labels,count=ndimage.label(alpha);sizes=np.bincount(labels.ravel());sizes[0]=0
    main=labels==np.argmax(sizes)
    keep=ndimage.binary_dilation(main,iterations=2)
    rgba[~keep,3]=0;rgba[(labels!=np.argmax(sizes))&(rgba[:,:,3]>32),3]=0
    holes=ndimage.binary_fill_holes(main)&~main
    repair=int(holes.sum())
    if repair>32:raise ValueError('Large joint hole requires correction')
    if repair:
        _,near=ndimage.distance_transform_edt(~main,return_indices=True)
        rgba[holes]=rgba[near[0][holes],near[1][holes]];rgba[holes,3]=255
    arm=Image.fromarray(rgba);alpha=rgba[:,:,3]>32
    remaining=int((ndimage.binary_fill_holes(alpha)&~alpha).sum())
    frame=Image.alpha_composite(clothing,arm).convert('RGB')
    protect=p['head']|p['cap'];frame.paste(p['source'],(0,0),Image.fromarray(protect.astype('uint8')*255))
    changed=np.any(np.asarray(frame)!=np.asarray(p['source']),axis=2)
    allowed=p['erase']|(np.asarray(gusset.getchannel('A'))>0)|(np.asarray(arm.getchannel('A'))>0)|holes
    # This band is the newly covered underarm seam, a distinct coverage check
    # from the closed-contour hole test used in earlier iterations.
    combined=(np.asarray(gusset.getchannel('A'))>0)|alpha
    return frame,{**hcheck,'wrist_kind':'tapered six-point connector','removed_baked_wrist_skin':p['removed_wrist_oval_pixels'],'joint_band_unpainted':int(np.sum(gap&~combined)),'joint_band_pixels':int(gap.sum()),'repaired_pixels':repair,'remaining_arm_holes':remaining,'outside_edit_pixels':int(np.sum(changed&~allowed)),'head_changed_pixels':int(np.sum(changed&p['head']))}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--a',required=True,type=Path);parser.add_argument('--b',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--preview-only',action='store_true');args=parser.parse_args()
    a=Image.open(args.a).convert('RGB');b=Image.open(args.b).convert('RGB');p=prepare(a,b)
    args.output.mkdir(parents=True,exist_ok=False)
    if args.preview_only:
        for t in [0,.25,.5,.75,1]:
            im,c=render(p,t);save_png(im.resize((560,700),Image.Resampling.LANCZOS),args.output/f'pose-{t}.png');print(t,c,flush=True)
        return
    for n in ['frames','loop','comparison']:(args.output/n).mkdir()
    frames=[];panels=[];checks=[]
    for i,v in enumerate(np.linspace(0,1,48)):
        t=float(v*v*(3-2*v));im,c=render(p,t);small=im.resize((720,900),Image.Resampling.LANCZOS);frames.append(small);checks.append(c);save_png(small,args.output/'frames'/f'{i:04}.png')
        # A source reference beside the revised result keeps the deliverable
        # reproducible without requiring artifacts from an earlier run.
        panel=Image.new('RGB',(1440,940),'#162231');panel.paste(a.resize((720,900),Image.Resampling.LANCZOS),(0,40));panel.paste(small,(720,40));d=ImageDraw.Draw(panel);d.text((14,12),'ORIGINAL A',fill='white');d.text((734,12),'VOLUME + WRIST + COAT JOINT',fill='white');panels.append(panel)
        print(f'joint refinement {i+1}/48',flush=True)
    seq=[0]*12+list(range(48))+[47]*12+list(range(46,0,-1))
    for i,j in enumerate(seq):save_png(frames[j],args.output/'loop'/f'{i:04}.png');save_png(panels[j],args.output/'comparison'/f'{i:04}.png')
    encode_mp4(args.output/'loop',args.output/'Akino-Arm-Joint-Refined.mp4',24);encode_mp4(args.output/'comparison',args.output/'Akino-Arm-Joint-Refined-Comparison.mp4',24)
    previews=[f.resize((560,700),Image.Resampling.LANCZOS) for f in frames];palette=Image.fromarray(np.vstack([np.asarray(previews[0]),np.asarray(previews[-1])])).quantize(colors=256);gif=[previews[j].quantize(palette=palette,dither=Image.Dither.NONE) for j in seq]
    buf=io.BytesIO();gif[0].save(buf,format='GIF',save_all=True,append_images=gif[1:],duration=42,loop=0,optimize=False);(args.output/'Akino-Arm-Joint-Refined.gif').write_bytes(buf.getvalue())
    sheet=Image.new('RGB',(3600,900),'white')
    for col,j in enumerate([0,12,24,35,47]):sheet.paste(frames[j],(col*720,0))
    save_png(sheet,args.output/'Akino-Arm-Joint-Refined-Contact.png')
    report={'method':'source-art arm with authored hand side volume, tapered wrist and donor-textured dynamic underarm cloth bridge','frames':48,'fps':24,'size':[720,900],'max_added_depth':max(c['hand_added_depth'] for c in checks),'max_joint_band_unpainted':max(c['joint_band_unpainted'] for c in checks),'max_remaining_holes':max(c['remaining_arm_holes'] for c in checks),'max_outside_edit_pixels':max(c['outside_edit_pixels'] for c in checks),'max_head_changed_pixels':max(c['head_changed_pixels'] for c in checks),'checks':checks,'limitations':['Single arm and fixed body; corrections are manually authored, not inferred anatomy','Side shading and wrist are painted from sampled source colors, not original unseen textures','Underarm cloth reuses a chosen B fabric strip and may need artistic seam retouching','Original cuff rim remains, but its baked skin oval is removed and replaced by a tapered wrist','Hand surfaces still change at edge-on; this is not full 3D reconstruction']}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print({k:v for k,v in report.items() if k!='checks'})

if __name__=='__main__':main()
