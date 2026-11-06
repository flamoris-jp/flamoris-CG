"""Attach the existing simplified arm to a fixed original Akino illustration.

Manual original-arm removal and a declared shoulder patch, with original head
restored in front. No automatic segmentation, texture recovery or body turn.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import numpy as np
from scipy import ndimage
from PIL import Image,ImageDraw
from layers_akino import LAYERS
from run import save_png,encode_mp4
from run_joint_arm import geometry,S,ORIGIN,OFFSET,SCALE
from run_thumb_turn import render_turn

CAP=[(610,565),(641,569),(666,590),(670,632),(645,665),(633,630),(618,605)]


def polygon_mask(size,points):
    m=Image.new('L',size);ImageDraw.Draw(m).polygon([tuple(p) for p in points],fill=255);return m


def prepare_body(source):
    if source.size!=(1122,1402):raise ValueError('Expected original 1122x1402 illustration')
    erase=np.zeros((1402,1122),dtype=bool)
    for name in ['arm_r','hand_r']:
        points=next(l for l in LAYERS if l[0]==name)[1]
        erase|=np.asarray(polygon_mask(source.size,points))>0
    erase=ndimage.binary_dilation(erase,iterations=7)
    cleaned=source.copy();cleaned.paste('white',(0,0,*source.size),Image.fromarray(erase.astype('uint8')*255))
    # The original sleeve covers this shoulder area; reconstruct only a simple
    # white coat cap, not the original hidden texture or emblem.
    cap=polygon_mask(source.size,CAP);cleaned.paste('#f5f3f9',(0,0,*source.size),cap)
    head=polygon_mask(source.size,next(l for l in LAYERS if l[0]=='head')[1])
    return cleaned,head,erase|(np.asarray(cap)>0)


def place_arm(arm,t,size):
    delta=S[0]-geometry(t)['shoulder']
    # Inverse of display(world) with a translation pinning S(t) to S(0).
    matrix=(SCALE,0,OFFSET[0]-SCALE*(ORIGIN[0]+delta[0]),0,SCALE,OFFSET[1]-SCALE*(ORIGIN[1]+delta[1]))
    return arm.transform(size,Image.Transform.AFFINE,matrix,resample=Image.Resampling.BICUBIC)


def compose(source,body,head,editmask,arm,t):
    layer=place_arm(arm,t,source.size)
    frame=Image.alpha_composite(body.convert('RGBA'),layer).convert('RGB')
    # Hair and face occlude the shoulder if the rendered sleeve passes behind.
    frame.paste(source,(0,0),head)
    allowed=editmask|(np.asarray(layer.getchannel('A'))>0)
    changes=np.any(np.asarray(frame)!=np.asarray(source),axis=2)
    outside=int(np.sum(changes&~allowed))
    protected=np.asarray(head)>0
    head_changes=int(np.sum(changes&protected))
    # Original-resolution shoulder coverage probe, inside the new root cross-section.
    x,y=np.rint(S[0]).astype(int)
    alpha=np.asarray(layer.getchannel('A'))
    return frame,{'outside_edit_pixels':outside,'head_changed_pixels':head_changes,'shoulder_center_alpha':int(alpha[y,x]),'pinned_shoulder':S[0].tolist()}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    with Image.open(args.source) as im:source=im.convert('RGB')
    body,head,editmask=prepare_body(source)
    args.output.mkdir(parents=True,exist_ok=False)
    for name in ['frames','loop','comparison']:(args.output/name).mkdir()
    frames=[];panels=[];checks=[]
    for i,v in enumerate(np.linspace(0,1,48)):
        t=float(v*v*(3-2*v))
        arm,armcheck=render_turn(t,transparent=True,open_shoulder=True)
        frame,c=compose(source,body,head,editmask,arm,t);c['arm_holes']=armcheck['holes'];checks.append(c)
        small=frame.resize((560,700),Image.Resampling.LANCZOS);frames.append(small)
        save_png(small,args.output/'frames'/f'{i:04}.png')
        panel=Image.new('RGB',(1120,740),'#162231');panel.paste(source.resize((560,700),Image.Resampling.LANCZOS),(0,40));panel.paste(small,(560,40))
        d=ImageDraw.Draw(panel);d.text((14,12),'ORIGINAL A',fill='white');d.text((574,12),'FIXED BODY + TURNING ARM',fill='white');panels.append(panel)
        print(f'attached {i+1}/48',flush=True)
    seq=[0]*12+list(range(48))+[47]*12+list(range(46,0,-1))
    for i,j in enumerate(seq):save_png(frames[j],args.output/'loop'/f'{i:04}.png');save_png(panels[j],args.output/'comparison'/f'{i:04}.png')
    encode_mp4(args.output/'loop',args.output/'Akino-Attached-Arm.mp4',24);encode_mp4(args.output/'comparison',args.output/'Akino-Attached-Arm-Comparison.mp4',24)
    buf=io.BytesIO();frames[0].save(buf,format='GIF',save_all=True,append_images=[frames[j] for j in seq[1:]],duration=42,loop=0);(args.output/'Akino-Attached-Arm.gif').write_bytes(buf.getvalue())
    sheet=Image.new('RGB',(2800,700),'white')
    for col,j in enumerate([0,12,24,35,47]):sheet.paste(frames[j],(col*560,0))
    save_png(sheet,args.output/'Akino-Attached-Arm-Contact.png')
    report={'method':'fixed original body + manually removed original right-image arm + simplified turning arm pinned at shoulder + original head foreground','source_sha256':hashlib.sha256(args.source.read_bytes()).hexdigest(),'frames':48,'fps':24,'size':[560,700],'max_outside_edit_pixels':max(c['outside_edit_pixels'] for c in checks),'max_head_changed_pixels':max(c['head_changed_pixels'] for c in checks),'min_shoulder_center_alpha':min(c['shoulder_center_alpha'] for c in checks),'max_arm_holes':max(c['arm_holes'] for c in checks),'checks':checks,'limitations':['Only image-right arm animates; body, face, hair and other arm are fixed','Original sleeve is removed using manual masks and white background fill','Shoulder coat cap is manually patched; original sleeve emblem and texture are omitted','Simplified arm differs in paint style from the original; shoulder seam needs artistic review','Head overlap is a fixed manual mask, not general occlusion reasoning','No original B/full-body endpoint match or inferred anatomy/3D motion']}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print({k:v for k,v in report.items() if k!='checks'})

if __name__=='__main__':main()
