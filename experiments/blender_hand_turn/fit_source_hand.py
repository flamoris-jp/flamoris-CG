"""Author a closed, two-art-surface hand mesh from explicit source correspondences.
Depth is designed, not reconstructed anatomy. Requires numpy/scipy/Pillow offline.
"""
import argparse,base64,hashlib,io,json,math
from pathlib import Path
import numpy as np
from scipy.interpolate import CubicSpline
from PIL import Image,ImageDraw

# Same semantic arcs, non-thumb wrist -> four fingertip profiles -> thumb -> wrist.
ARCS_A=[[(785,815),(807,824),(829,829),(850,830)],
[(850,830),(858,830),(861,833),(860,837),(854,841),(844,843),(834,843)],
[(834,843),(846,847),(857,849),(861,852),(860,856),(855,859)],
[(855,859),(852,861),(849,862),(845,863),(841,863)],
[(841,863),(841,865),(838,867),(834,866),(831,865)],
[(831,865),(820,862),(807,857),(800,855),(796,855)],
[(796,855),(794,858),(797,866),(801,876),(802,881)],
[(802,881),(800,885),(796,887),(792,885),(786,878)],
[(786,878),(776,868),(766,861),(760,852),(758,846)],
[(758,846),(767,832),(777,821),(785,815)]]
ARCS_B=[[(815,535),(827,520),(851,512),(897,498)],
[(897,498),(905,495),(911,493),(912,491),(912,489)],
[(912,489),(918,488),(923,486),(924,484),(924,482)],
[(924,482),(926,481),(926,478),(923,475),(919,472)],
[(919,472),(917,469),(914,467),(908,464),(902,463)],
[(902,463),(891,462),(878,461),(855,462),(835,461)],
[(835,461),(838,453),(842,445),(842,439),(839,433)],
[(839,433),(836,430),(832,431),(829,437),(826,443)],
[(826,443),(818,455),(804,467),(798,481),(796,497)],
[(796,497),(794,506),(799,518),(806,527),(815,535)]]
SAMPLES=[12,12,10,12,10,12,12,12,14,12]
WRISTS=np.array([[773.,833.],[806.,522.]])
DIRECTIONS=np.array([[68.,18.],[93.,-42.]])
CROPS=[(750,807,871,897),(787,422,936,543)]


def cross(a,b):return a[0]*b[1]-a[1]*b[0]


def outline(arcs):
    chunks=[]
    for points,n in zip(arcs,SAMPLES):
        a=np.array(points,dtype=float);d=np.r_[0,np.cumsum(np.linalg.norm(np.diff(a,axis=0),axis=1))]
        chunks.append(CubicSpline(d,a,bc_type='natural')(np.linspace(0,d[-1],n,endpoint=False)))
    return np.concatenate(chunks)


def canonical(points,view):
    d=DIRECTIONS[view]/np.linalg.norm(DIRECTIONS[view]);q=points-WRISTS[view]
    x=q@d;y=(q@np.array([-d[1],d[0]]))*(-1 if view==0 else 1)
    return np.column_stack([x,y])/100


def contains(p,a,b,c,eps=1e-10):
    return cross(b-a,p-a)>eps and cross(c-b,p-b)>eps and cross(a-c,p-c)>eps


def triangulate_pair(a,b):
    # Dynamic programming avoids a greedy ear blocking the other drawing.
    # Each face must preserve orientation throughout the shape-key interval.
    n=len(a);blend=[(1-t)*a+t*b for t in np.linspace(0,1,17)]
    valid=np.ones((n,n,n),dtype=bool)
    for p in blend:
        v=p[None,:,:]-p[:,None,:]
        areas=v[:,:,None,0]*v[:,None,:,1]-v[:,:,None,1]*v[:,None,:,0]
        valid &= areas>1e-12
    possible=np.zeros((n,n),dtype=bool);split={}
    for i in range(n-1):possible[i,i+1]=True
    for length in range(2,n):
        for i in range(n-length):
            j=i+length
            choices=[k for k in range(i+1,j) if possible[i,k] and possible[k,j] and valid[i,k,j]]
            if choices:
                k=max(choices,key=lambda k:min(cross(p[k]-p[i],p[j]-p[i]) for p in [a,b]))
                possible[i,j]=True;split[i,j]=k
    if not possible[0,n-1]:raise ValueError('No common positive triangulation')
    result=[]
    def emit(i,j):
        if j-i<2:return
        k=split[i,j];result.append((i,k,j));emit(i,k);emit(k,j)
    emit(0,n-1);return result


def distance_boundary(p,boundary):
    a=boundary;b=np.roll(a,-1,axis=0);d=b-a
    q=p[:,None,:]-a[None,:,:];t=np.clip(np.sum(q*d,axis=2)/np.sum(d*d,axis=1),0,1)
    return np.sqrt(np.min(np.sum((q-t[:,:,None]*d)**2,axis=2),axis=1))


def prepare(a_path,b_path,output):
    output.mkdir(exist_ok=False)
    pixel=[outline(ARCS_A),outline(ARCS_B)];xy=[canonical(p,i) for i,p in enumerate(pixel)]
    # Reverse both together if necessary; correspondence stays intact.
    if sum(cross(xy[0][i],xy[0][(i+1)%len(xy[0])]) for i in range(len(xy[0])))<0:
        xy=[p[::-1] for p in xy];pixel=[p[::-1] for p in pixel]
    faces=triangulate_pair(*xy);boundary_count=len(xy[0]);print('base',boundary_count,len(faces))
    # Shared midpoint refinement produces matching interior vertices for both keys.
    coords=[p.tolist() for p in xy];pix=[p.tolist() for p in pixel]
    for _ in range(2):
        edge={};new=[]
        def midpoint(i,j):
            key=tuple(sorted((i,j)))
            if key not in edge:
                edge[key]=len(coords[0])
                for dest in [coords,pix]:
                    for view in [0,1]:dest[view].append(((np.array(dest[view][i])+dest[view][j])/2).tolist())
            return edge[key]
        for i,j,k in faces:
            ij=midpoint(i,j);jk=midpoint(j,k);ki=midpoint(k,i)
            new.extend([(i,ij,ki),(ij,j,jk),(ki,jk,k),(ij,jk,ki)])
        faces=new
    coords=[np.array(p) for p in coords];pix=[np.array(p) for p in pix]
    # Identify refined boundary edges, not only original control points.
    counts={}
    for f in faces:
        for i,j in zip(f,np.roll(f,-1)):
            key=tuple(sorted((int(i),int(j))));counts[key]=counts.get(key,0)+1
    boundary=sorted({v for e,n in counts.items() if n==1 for v in e});boundary_set=set(boundary)
    # Interior chords between two rim vertices need a raised midpoint. Sharing
    # those chords across both sides would otherwise create four-face edges.
    split_edges={}
    coords=[p.tolist() for p in coords];pix=[p.tolist() for p in pix]
    for (i,j),count in counts.items():
        if count==2 and i in boundary_set and j in boundary_set:
            split_edges[i,j]=len(coords[0])
            for dest in [coords,pix]:
                for view in [0,1]:dest[view].append(((np.array(dest[view][i])+dest[view][j])/2).tolist())
    new=[]
    for f in faces:
        polygon=[]
        for i,j in zip(f,np.roll(f,-1)):
            polygon.append(int(i));key=tuple(sorted((int(i),int(j))))
            if key in split_edges:polygon.append(split_edges[key])
        if len(polygon)==3:new.append(tuple(polygon));continue
        center=len(coords[0])
        for dest in [coords,pix]:
            for view in [0,1]:dest[view].append(np.mean(np.array(dest[view])[polygon],axis=0).tolist())
        new.extend((polygon[i],polygon[(i+1)%len(polygon)],center) for i in range(len(polygon)))
    faces=new;coords=[np.array(p) for p in coords];pix=[np.array(p) for p in pix]
    surfaces=[]
    for view,p in enumerate(coords):
        dist=distance_boundary(p,xy[view]);depth=.075*np.sqrt(np.clip(dist/.10,0,1))
        depth[boundary]=0
        # Wrist and fingertip thickness vary smoothly with the traced drawing.
        surfaces.append(np.column_stack([p,depth]))
    # Front and back share their perimeter: one watertight mesh, no finger seams.
    n=len(coords[0]);back_map={i:(i if i in boundary_set else n+sum(j not in boundary_set for j in range(i))) for i in range(n)}
    keys=[]
    for surface in surfaces:
        vertices=surface.tolist()+[[*surface[i,:2],-surface[i,2]] for i in range(n) if i not in boundary_set];keys.append(vertices)
    polygons=[list(f) for f in faces]+[[back_map[i] for i in reversed(f)] for f in faces]
    uv=[]
    for view in [0,1]:
        x0,y0,x1,y1=CROPS[view]
        for f in faces:
            indices=f if view==0 else list(reversed(f))
            uv.append([[(pix[view][i,0]-x0)/(x1-x0),1-(pix[view][i,1]-y0)/(y1-y0)] for i in indices])
    textures=[]
    for view,path in enumerate([a_path,b_path]):
        im=Image.open(path).convert('RGBA').crop(CROPS[view]).resize(((CROPS[view][2]-CROPS[view][0])*4,(CROPS[view][3]-CROPS[view][1])*4),Image.Resampling.LANCZOS)
        buffer=io.BytesIO();im.save(buffer,format='PNG');raw=buffer.getvalue();(output/f'art-{view}.png').write_bytes(raw);textures.append(base64.b64encode(raw).decode())
    angles=[-math.atan2(d[1],d[0]) for d in DIRECTIONS]
    payload={'schema_version':1,'keys':keys,'faces':polygons,'uv':uv,'front_faces':len(faces),'angles':angles,'textures':textures,'source_hashes':[hashlib.sha256(p.read_bytes()).hexdigest() for p in [a_path,b_path]],'crop_rects':CROPS,'canonical_scale_pixels':100,'twist_degrees':-180,'depth_design':{'max_half_thickness':.075,'edge_transition':.10},'limitations':['Authored silhouette correspondence and thickness; not anatomical 3D reconstruction','Shape keys interpolate between two inconsistent drawn views','Forearm and sleeve are not modeled']}
    (output/'mesh.json').write_text(json.dumps(payload,separators=(',',':')))
    # Compare traced contour against original before Blender.
    board=Image.new('RGB',(1000,460),'#eeeef2');draw=ImageDraw.Draw(board)
    for view,path in enumerate([a_path,b_path]):
        im=Image.open(path).convert('RGB');x0,y0,x1,y1=CROPS[view];im=im.crop(CROPS[view]).resize((480,390));board.paste(im,(view*500,35))
        pts=[((p[0]-x0)/(x1-x0)*480+view*500,(p[1]-y0)/(y1-y0)*390+35) for p in pixel[view]]
        draw.line(pts+[pts[0]],fill=(40,110,220),width=2);draw.text((view*500+10,10),['A / BACK','B / PALM'][view],fill='black')
    b=io.BytesIO();board.save(b,format='PNG');(output/'contour-check.png').write_bytes(b.getvalue())
    print(json.dumps({'vertices':len(keys[0]),'faces':len(polygons),'boundary':len(boundary),'json_bytes':(output/'mesh.json').stat().st_size}))
    return payload

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('a',type=Path);p.add_argument('b',type=Path);p.add_argument('output',type=Path);args=p.parse_args();prepare(args.a,args.b,args.output)
