"""Stylized hand turn: explicit 3D depth for palm/thumb, 2D ink and paint.

A manually authored fixed-hand model, not anatomical reconstruction from images.
Keeps the prior arm motion and adds a chosen half-turn about the hand's long axis.
"""
import argparse
import io
import json
from pathlib import Path
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw
from run import save_png,encode_mp4
from run_joint_arm import geometry,rotation,angular_lerp,display,SIZE,SCALE,TIP,W,mask_for,STROKE

PALM=np.array([(0,-17),(36,-23),(72,-21),(89,-17),(91,-11),(98,-8),(106,-3),(106,3),(103,6),(105,10),(103,16),(97,20),(81,23),(49,24),(28,23),(0,18)],dtype=float)
THUMB=np.array([(18,13),(19,27),(28,43),(36,51),(48,52),(55,47),(55,40),(48,34),(39,31),(32,21),(29,13)],dtype=float)
SS=3


def extrude(poly,zbase,half):
    z=np.broadcast_to(zbase,len(poly))
    v=np.vstack([np.column_stack([poly,z-half]),np.column_stack([poly,z+half])])
    # A simple fan can cross concave outlines; use ear clipping per cap.
    def triangulate(q):
        order=list(range(len(q)));out=[]
        area=np.sum(q[:,0]*np.roll(q[:,1],-1)-np.roll(q[:,0],-1)*q[:,1])
        if area<0:order.reverse()
        def cross(a,b,c):
            u,v=b-a,c-a;return u[0]*v[1]-u[1]*v[0]
        while len(order)>3:
            found=False
            for k,j in enumerate(order):
                i,l=order[k-1],order[(k+1)%len(order)]
                if cross(q[i],q[j],q[l])<=1e-8:continue
                def inside(p):return min(cross(q[i],q[j],p),cross(q[j],q[l],p),cross(q[l],q[i],p))>=-1e-8
                if any(inside(q[n]) for n in order if n not in [i,j,l]):continue
                out.append([i,j,l]);order.pop(k);found=True;break
            if not found:raise ValueError('Non-simple polygon cap')
        return out+[order]
    n=len(poly);cap=triangulate(poly)
    faces=[f[::-1] for f in cap]+[[i+n for i in f] for f in cap]
    for i in range(n):
        j=(i+1)%n;faces.extend([[i,j,j+n],[i,j+n,i+n]])
    return v,np.array(faces)


def project(points,t,twist=None):
    q=np.array(points,dtype=float).copy()
    # Back (+Z) faces viewer at start, palm (-Z) faces viewer at finish.
    theta=np.pi*t if twist is None else twist
    y=q[:,1]*np.cos(theta)+q[:,2]*np.sin(theta)
    z=q[:,2]*np.cos(theta)-q[:,1]*np.sin(theta)
    q[:,1]=y
    q[:,:2]*=(1+.12*t)
    phi=np.arctan2((TIP-W)[:,1],(TIP-W)[:,0]);angle=angular_lerp(phi[0],phi[1],t)
    xy=q[:,:2]@rotation(angle).T+geometry(t)['wrist']
    return np.column_stack([display(xy),z])


def raster_hand(t,twist=None):
    h,w=SIZE[1]*SS,SIZE[0]*SS
    rgb=np.zeros((h,w,3),dtype=np.uint8);depth=np.full((h,w),-np.inf);labels=np.zeros((h,w),dtype=np.uint8)
    mesh=[extrude(PALM,0.,7.),extrude(THUMB,(THUMB[:,1]-13)*.20-4.,4.5)]
    for label,(vertices,faces) in enumerate(mesh,1):
        projected=project(vertices,t,twist);projected[:,:2]*=SS
        for face in faces:
            p=projected[face];matrix=np.column_stack([p[1,:2]-p[0,:2],p[2,:2]-p[0,:2]])
            if abs(np.linalg.det(matrix))<1e-6:continue
            lo=np.maximum(np.floor(p[:,:2].min(axis=0)).astype(int),[0,0]);hi=np.minimum(np.ceil(p[:,:2].max(axis=0)).astype(int)+1,[w,h])
            yy,xx=np.mgrid[lo[1]:hi[1],lo[0]:hi[0]]
            uv=np.linalg.solve(matrix,np.stack([xx-p[0,0],yy-p[0,1]],axis=0).reshape(2,-1))
            valid=(uv.min(axis=0)>=-1e-6)&(uv.sum(axis=0)<=1+1e-6)
            zz=p[0,2]+(p[1,2]-p[0,2])*uv[0]+(p[2,2]-p[0,2])*uv[1]
            yi,xi=yy.ravel(),xx.ravel();valid&=zz>depth[yi,xi]
            yi,xi,zz=yi[valid],xi[valid],zz[valid]
            # Flat colors by face orientation; no transparent skin or dissolve.
            a,b,c=vertices[face];normal=np.cross(b-a,c-a);normal/=np.linalg.norm(normal)
            shade=.87+.10*abs(normal[2])
            color=np.array([255,211,177] if label==1 else [248,194,155])*shade
            rgb[yi,xi]=color.astype('uint8');depth[yi,xi]=zz;labels[yi,xi]=label
    return rgb,depth,labels


def draw_details(rgb,depth,labels,t,twist=None,enabled=True):
    if not enabled:return rgb,{'thumb_boundary_pixels':0,'visible_detail_pixels':0}
    visible=labels>0
    outer=ndimage.binary_dilation(visible,iterations=4)^ndimage.binary_erosion(visible,iterations=4)
    thumb=labels==2
    seam=ndimage.binary_dilation(thumb,iterations=3)&(labels==1)
    rgb[outer|seam]=[35,34,40]
    def stroke(local,color,width=2):
        p=project(local,t,twist);p[:,:2]*=SS;count=0
        for a,b in zip(p[:-1],p[1:]):
            n=max(2,int(np.linalg.norm(b[:2]-a[:2])*1.5))
            points=np.linspace(a,b,n)
            for x,y,z in points:
                ix,iy=int(round(x)),int(round(y))
                if 0<=iy<labels.shape[0] and 0<=ix<labels.shape[1] and labels[iy,ix]>0 and z>=depth[iy,ix]-1.0:
                    rr=width;rgb[max(0,iy-rr):iy+rr+1,max(0,ix-rr):ix+rr+1]=color;count+=1
        return count
    theta=np.pi*t if twist is None else twist
    count=0
    if np.cos(theta)>0.03:
        # Dorsal thumb root and thumbnail; palm creases stay on the far side.
        count+=stroke([(26,26,4),(31,34,7),(41,40,10)],(51,42,40),3)
        count+=stroke([(41,42,10),(47,44,10),(50,42,10)],(139,94,76),2)
        for y,x in [(-15,83),(-5,95),(5,96),(16,87)]:
            count+=stroke([(x-5,y-2,7.3),(x+2,y-2,7.3),(x+4,y+2,7.3)],(151,104,85),1)
    if np.cos(theta)<-0.03:
        # Thenar arc and two selected palm folds, at the palmar face.
        count+=stroke([(9,12,-7.3),(16,6,-7.3),(26,5,-7.3),(33,11,-7.3),(35,20,-7.3)],(63,43,39),2)
        count+=stroke([(29,-15,-7.3),(43,-9,-7.3),(54,0,-7.3),(58,13,-7.3)],(150,91,71),2)
        count+=stroke([(55,-17,-7.3),(63,-9,-7.3),(67,1,-7.3),(68,13,-7.3)],(150,91,71),2)
    return rgb,{'thumb_boundary_pixels':int(seam.sum()),'visible_detail_pixels':count}


def render_turn(t,twist=None,details=True,transparent=False,open_shoulder=False):
    g=geometry(t);rgb,depth,labels=raster_hand(t,twist)
    rgb,checks=draw_details(rgb,depth,labels,t,twist,details)
    h,w=labels.shape;canvas=Image.new('RGB',(w,h),'#e7edf3')
    # Connector between actual projected palm root and cuff; opaque behind hand.
    from scipy.spatial import ConvexHull
    root=project(np.array([[0,-17,-7],[0,18,-7],[0,18,7],[0,-17,7]],float),t,twist)[:,:2]
    cuff=display(g['cuff']);points=np.vstack([root,cuff]);bridge=points[ConvexHull(points).vertices]
    d=ImageDraw.Draw(canvas);d.polygon([tuple(v*SS) for v in bridge],fill='#efbc98')
    mask=Image.fromarray((labels>0).astype('uint8')*255)
    # Include silhouette ink beyond paint coverage in the paste mask.
    ink=np.all(rgb==[35,34,40],axis=2);alpha=(labels>0)|ink
    canvas.paste(Image.fromarray(rgb),(0,0),Image.fromarray(alpha.astype('uint8')*255))
    coverage=np.asarray(mask)>0
    bridgemask=Image.new('L',(w,h));ImageDraw.Draw(bridgemask).polygon([tuple(v*SS) for v in bridge],fill=255)
    coverage|=np.asarray(bridgemask)>0
    for name,color in [('sleeve','#f5f3f9'),('cuff','#2a2c34')]:
        q=g[name];m=mask_for(q);canvas.paste(color,(0,0,w,h),m);coverage|=np.asarray(m)>0
        pts=[tuple(p*SS) for p in display(q)]
        path=pts if open_shoulder and name=='sleeve' else pts+[pts[0]]
        ImageDraw.Draw(canvas).line(path,fill='#25252d',width=round(STROKE*SS),joint='curve')
    # Crop detailed ink to projected painted area; no detail enters background.
    pinholes=ndimage.binary_fill_holes(coverage)&~coverage
    repair_count=int(pinholes.sum())
    if repair_count>16:raise ValueError('Large coverage hole: inspect geometry instead of repairing')
    if repair_count:
        pixels=np.array(canvas);pixels[pinholes]=[245,199,163];canvas=Image.fromarray(pixels);coverage|=pinholes
    _,components=ndimage.label(coverage)
    checks.update(components=int(components),holes=int((ndimage.binary_fill_holes(coverage)&~coverage).sum()),repaired_subpixel_samples=repair_count,thumb_pixels=int((labels==2).sum()),palm_pixels=int((labels==1).sum()))
    if transparent:
        alpha=(np.any(np.asarray(canvas)!=[231,237,243],axis=2).astype('uint8')*255)
        canvas=canvas.convert('RGBA');canvas.putalpha(Image.fromarray(alpha))
    return canvas.resize(SIZE,Image.Resampling.LANCZOS),checks


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    for n in ['frames','loop','comparison']:(args.output/n).mkdir()
    frames=[];panels=[];checks=[]
    for i,v in enumerate(np.linspace(0,1,48)):
        t=float(v*v*(3-2*v));im,c=render_turn(t);frames.append(im);checks.append(c)
        save_png(im,args.output/'frames'/f'{i:04}.png')
        control,_=render_turn(t,twist=0,details=False)
        panel=Image.new('RGB',(960,684),'#162231');panel.paste(control,(0,44));panel.paste(im,(480,44))
        d=ImageDraw.Draw(panel);d.text((16,12),'FIXED BACK VIEW / NO DETAILS',fill='white');d.text((496,12),'TURN + THUMB OVERLAP',fill='white');panels.append(panel)
        print(f'frame {i+1}/48',flush=True)
    seq=[0]*12+list(range(48))+[47]*12+list(range(46,0,-1))
    for i,j in enumerate(seq):save_png(frames[j],args.output/'loop'/f'{i:04}.png');save_png(panels[j],args.output/'comparison'/f'{i:04}.png')
    encode_mp4(args.output/'loop',args.output/'Akino-Thumb-Turn.mp4',24);encode_mp4(args.output/'comparison',args.output/'Akino-Thumb-Turn-Comparison.mp4',24)
    buf=io.BytesIO();frames[0].save(buf,format='GIF',save_all=True,append_images=[frames[j] for j in seq[1:]],duration=42,loop=0);(args.output/'Akino-Thumb-Turn.gif').write_bytes(buf.getvalue())
    sheet=Image.new('RGB',(2400,640),'#e7edf3')
    for col,j in enumerate([0,12,24,35,47]):sheet.paste(frames[j],(col*480,0))
    save_png(sheet,args.output/'Akino-Thumb-Turn-Contact.png')
    report={'method':'manually authored thick palm and separate thumb; chosen 180-degree axial turn; triangle depth buffer; visible outline/root and dorsal/palmar detail strokes','frames':48,'max_holes':max(c['holes'] for c in checks),'max_components':max(c['components'] for c in checks),'max_repaired_subpixel_samples':max(c['repaired_subpixel_samples'] for c in checks),'checks':checks,'limitations':['Stylized hand; proportions, depth and rotation are authored, not estimated from the source drawings','Single arm only; not anatomical/3D reconstruction acceptance','Comparison changes both depth rotation and detail strokes, not a single-variable ablation','Depth-tested details and discrete face visibility can still produce popping']}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print({k:v for k,v in report.items() if k!='checks'})

if __name__=='__main__':main()
