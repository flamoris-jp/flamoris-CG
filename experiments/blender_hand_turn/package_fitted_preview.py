"""Presentation of real Blender frames; constant-width 2D silhouette ink pass."""
import argparse,io,json,subprocess,tempfile,zipfile
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageFilter,ImageChops


def png(image,path):
    b=io.BytesIO();image.save(b,format='PNG');path.write_bytes(b.getvalue())


def ink(rgba):
    alpha=rgba.getchannel('A');expanded=alpha.filter(ImageFilter.MaxFilter(5))
    edge=Image.new('RGBA',rgba.size,(39,29,28,0));edge.putalpha(expanded);edge.alpha_composite(rgba);return edge


def package(source,output):
    output.mkdir(exist_ok=False)
    with zipfile.ZipFile(source) as z:z.extractall(output/'native')
    with zipfile.ZipFile(output/'native/render-result.zip') as z:z.extractall(output/'render')
    job=json.loads((output/'render/job.json').read_text());frames=sorted((output/'render/frames').glob('*.png'))
    if len(frames)!=32 or [int(p.stem) for p in frames]!=list(range(1,33)):raise ValueError('Expected 32 consecutive native frames')
    images=[];boxes=[];font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',20);small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',15)
    (output/'inked-frames').mkdir();(output/'preview-frames').mkdir()
    for n,p in enumerate(frames):
        with Image.open(p) as f:f.load();rgba=f.convert('RGBA')
        if rgba.size!=(800,600):raise ValueError('Dimensions differ')
        box=rgba.getchannel('A').getbbox()
        if not box or min(box[0],box[1],800-box[2],600-box[3])<16:raise ValueError('Empty or clipped hand')
        boxes.append(box);rgba=ink(rgba);png(rgba,output/'inked-frames'/p.name)
        bg=Image.new('RGBA',rgba.size,(241,242,246,255));bg.alpha_composite(rgba);im=bg.convert('RGB');d=ImageDraw.Draw(im)
        d.text((20,15),'SOURCE ART x BLENDER VOLUME',font=font,fill=(40,43,55));d.text((20,573),'THUMB TOWARDS VIEWER / FIXED FRONT CAMERA',font=small,fill=(75,80,90));images.append(im)
    timeline=[0]*8+list(range(32))+[31]*8+list(range(30,0,-1))
    for n,i in enumerate(timeline):png(images[i],output/'preview-frames'/f'{n:04d}.png')
    with tempfile.TemporaryDirectory() as temp:
        dest=Path(temp)/'clip.mp4';subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-n','-framerate','16','-i',str(output/'preview-frames/%04d.png'),'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(dest)],check=True);(output/'Akino-Source-Matched-Hand.mp4').write_bytes(dest.read_bytes())
    palette=Image.new('RGB',(800,1800))
    for n,i in enumerate([0,15,31]):palette.paste(images[i],(0,n*600))
    pal=palette.quantize(colors=160);gif=[images[i].quantize(palette=pal,dither=Image.Dither.NONE) for i in timeline];b=io.BytesIO();gif[0].save(b,format='GIF',save_all=True,append_images=gif[1:],duration=62,loop=0,optimize=False);(output/'Akino-Source-Matched-Hand.gif').write_bytes(b.getvalue())
    strip=Image.new('RGB',(1200,300))
    for n,i in enumerate([0,15,31]):strip.paste(images[i].resize((400,300)),(400*n,0))
    png(strip,output/'Akino-Source-Matched-Hand-Views.png')
    (output/'Akino-Source-Matched-Hand.blend').write_bytes((output/'native/hand.blend').read_bytes())
    receipt=json.loads((output/'native/build-receipt.json').read_text());report={'job_id':job['job_id'],'status':job['status'],'native_frames':32,'native_fps':24,'preview_fps':16,'preview_frames':len(timeline),'size':[800,600],'bbox_first_edge_last':[boxes[i] for i in [0,15,31]],'nonmanifold_edges':receipt['nonmanifold_edges'],'source_hashes':receipt['source_hashes'],'outline_pass':'2 pixels alpha dilation under real RGBA render; raw and inked frames kept','limitations':receipt['limitations']}
    (output/'acceptance.json').write_text(json.dumps(report,indent=2)+'\n');return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);args=p.parse_args();print(json.dumps(package(args.source,args.output)))
