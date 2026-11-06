"""Trace the actual foreground silhouette and morph its vector coordinates.

No pixel dissolve: one closed, constant-width stroke is redrawn each frame.
The silhouette cannot retain internal/occluded hands or interior details.
"""
import argparse
import io
import json
from pathlib import Path
import numpy as np
from scipy import ndimage
import contourpy
from PIL import Image, ImageDraw
from run import save_png, encode_mp4


def trace(image):
    rgb=np.asarray(image.convert('RGB'))
    seed=np.min(rgb,axis=2)<220
    seed=ndimage.binary_closing(seed,iterations=2)
    labels,count=ndimage.label(ndimage.binary_fill_holes(seed))
    if not count:raise ValueError('No foreground outline')
    sizes=np.bincount(labels.ravel());sizes[0]=0
    mask=labels==np.argmax(sizes)
    paths=contourpy.contour_generator(z=np.pad(mask.astype(float),1)).lines(.5)
    def area(q):return np.sum(q[:-1,0]*q[1:,1]-q[1:,0]*q[:-1,1])/2
    q=max(paths,key=lambda q:abs(area(q)))-1
    if area(q)<0:q=q[::-1]
    return q[:-1]


def resample(q,n):
    closed=np.vstack([q,q[0]])
    distance=np.r_[0,np.cumsum(np.linalg.norm(np.diff(closed,axis=0),axis=1))]
    t=np.linspace(0,distance[-1],n,endpoint=False)
    return np.column_stack([np.interp(t,distance,closed[:,c]) for c in [0,1]])


def match(a,b,n=1200):
    # Orientation is fixed by trace(). Start at the topmost hair contour point.
    a=np.roll(a,-np.argmin(a[:,1]),axis=0)
    b=np.roll(b,-np.argmin(b[:,1]),axis=0)
    a,b=resample(a,n),resample(b,n)
    # Common exposed outline anchors, in clockwise traversal order. A closed
    # silhouette has no semantic access to B's fist over its torso.
    anchors=[((846,445),(793,410)),((860,850),(925,482)),
             ((720,976),(795,910)),((665,1320),(622,1297)),
             ((468,1350),(411,1318)),((305,945),(358,903)),
             ((270,445),(243,455))]
    ia=[0];ib=[0]
    for pa,pb in anchors:
        i=int(np.argmin(np.linalg.norm(a-np.array(pa),axis=1)))
        j=int(np.argmin(np.linalg.norm(b-np.array(pb),axis=1)))
        if i<=ia[-1] or j<=ib[-1]:raise ValueError('Ambiguous contour anchor order')
        ia.append(i);ib.append(j)
    ia.append(n);ib.append(n)
    outa=[];outb=[]
    for k in range(len(ia)-1):
        qa=np.vstack([a,a[0]])[ia[k]:ia[k+1]+1]
        qb=np.vstack([b,b[0]])[ib[k]:ib[k+1]+1]
        # Open segments: preserve both matching anchors, omit duplicate end.
        length=max(16,round(n*(ia[k+1]-ia[k]+ib[k+1]-ib[k])/(2*n)))
        def sample_open(q):
            d=np.r_[0,np.cumsum(np.linalg.norm(np.diff(q,axis=0),axis=1))]
            t=np.linspace(0,d[-1],length,endpoint=False)
            return np.column_stack([np.interp(t,d,q[:,c]) for c in [0,1]])
        outa.extend(sample_open(qa));outb.extend(sample_open(qb))
    return np.array(outa),np.array(outb)


def draw(q,size):
    supersample=3
    im=Image.new('RGB',(size[0]*supersample,size[1]*supersample),'white')
    pts=[tuple(p*supersample) for p in q]
    ImageDraw.Draw(im).line(pts+[pts[0]],fill='#202025',width=5,joint='curve')
    return im.resize(size,Image.Resampling.LANCZOS)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--a',required=True,type=Path);p.add_argument('--b',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    with Image.open(args.a) as im:
        if im.size!=(1122,1402):raise ValueError('This annotated experiment requires 1122x1402 inputs')
        a=trace(im)
    with Image.open(args.b) as im:
        if im.size!=(1122,1402):raise ValueError('This annotated experiment requires 1122x1402 inputs')
        b=trace(im)
    a,b=match(a,b)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'frames').mkdir();(args.output/'loop').mkdir()
    size=(480,600);scale=np.array([480/1122,600/1402])
    frames=[]
    for i,t in enumerate(np.linspace(0,1,24)):
        q=((1-t)*a+t*b)*scale
        frame=draw(q,size);frames.append(frame)
        save_png(frame,args.output/'frames'/f'{i:04}.png')
        # Exact vector output is retained for inspection and later editing.
        coords=' '.join(f'{x:.3f},{y:.3f}' for x,y in q)
        (args.output/f'outline-{i:02}.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 600"><rect width="480" height="600" fill="white"/><polygon points="{coords}" fill="none" stroke="#202025" stroke-width="1.667" stroke-linejoin="round"/></svg>')
    sequence=[0]*12+list(range(24))+[23]*12+list(range(22,0,-1))
    for i,j in enumerate(sequence):save_png(frames[j],args.output/'loop'/f'{i:04}.png')
    encode_mp4(args.output/'loop',args.output/'Akino-Outline-Morph.mp4',24)
    buf=io.BytesIO()
    frames[0].save(buf,format='GIF',save_all=True,append_images=[frames[j] for j in sequence[1:]],duration=42,loop=0)
    (args.output/'Akino-Outline-Morph.gif').write_bytes(buf.getvalue())
    sheet=Image.new('RGB',(480*5,600),'white')
    for col,i in enumerate([0,6,12,17,23]):sheet.paste(frames[i],(col*480,0))
    save_png(sheet,args.output/'Akino-Outline-Contact.png')
    (args.output/'report.json').write_text(json.dumps({'method':'threshold/close/fill/largest-component silhouette tracing; manually anchored arc-length correspondence; linear vector coordinate interpolation; constant-width stroke redraw','frames':24,'points_per_contour':len(a),'stroke_width':5/3,'pixel_dissolve':False,'manual_outline_anchors':7,'limitations':['Outer silhouette only; no facial/clothing interior lines','Hidden hand and overlapping contours cannot be represented by a single outline','Linear contour interpolation does not preserve limb lengths or guarantee no self intersections','Fine fingers can be simplified by threshold and contour correspondence']},indent=2))
    print('Finished',len(a),'vector points')

if __name__=='__main__':main()
