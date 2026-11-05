"""Package inspected transparent Blender JOB frames as a slow hand-turn preview."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from PIL import Image, ImageDraw, ImageFont


def png(image,path):
    buffer=io.BytesIO();image.save(buffer,format='PNG');path.write_bytes(buffer.getvalue())


def package(source,output):
    output.mkdir(exist_ok=False)
    with zipfile.ZipFile(source) as archive:
        archive.extractall(output/'native')
    with zipfile.ZipFile(output/'native/render-result.zip') as archive:
        archive.extractall(output/'render')
    job=json.loads((output/'render/job.json').read_text())
    frames=sorted((output/'render/frames').glob('*.png'))
    if len(frames)!=24:raise ValueError('Expected exactly 24 native frames')
    images=[];bounds=[]
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
    small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',13)
    for i,path in enumerate(frames):
        with Image.open(path) as src:
            src.load();rgba=src.convert('RGBA')
        if rgba.size!=(640,360):raise ValueError('Unexpected native dimensions')
        bbox=rgba.getchannel('A').getbbox()
        if not bbox:raise ValueError('Empty render')
        if min(bbox[0],bbox[1],640-bbox[2],360-bbox[3])<12:raise ValueError('Hand is clipped or too near frame edge')
        bounds.append(bbox)
        background=Image.new('RGBA',rgba.size,(241,242,246,255));background.alpha_composite(rgba)
        image=background.convert('RGB');draw=ImageDraw.Draw(image)
        draw.text((18,12),'BLENDER / HAND TURN',font=font,fill=(40,43,55))
        draw.text((18,333),f'BACK  >  EDGE  >  PALM     {i*180/23:.0f} deg',font=small,fill=(75,80,90))
        images.append(image)
    timeline=[0]*10+list(range(24))+[23]*10+list(range(22,0,-1))
    video=output/'preview-frames';video.mkdir()
    for n,i in enumerate(timeline):png(images[i],video/f'{n:04d}.png')
    with tempfile.TemporaryDirectory() as temp:
        dest=Path(temp)/'clip.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-n','-framerate','12','-i',str(video/'%04d.png'),'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(dest)],check=True)
        (output/'Akino-Blender-Hand-Turn.mp4').write_bytes(dest.read_bytes())
    palette=Image.new('RGB',(640,360*3))
    for n,i in enumerate([0,11,23]):palette.paste(images[i],(0,n*360))
    pal=palette.quantize(colors=128)
    gif=[images[i].quantize(palette=pal,dither=Image.Dither.NONE) for i in timeline]
    b=io.BytesIO();gif[0].save(b,format='GIF',save_all=True,append_images=gif[1:],duration=83,loop=0,optimize=False)
    (output/'Akino-Blender-Hand-Turn.gif').write_bytes(b.getvalue())
    strip=Image.new('RGB',(1440,270))
    for n,i in enumerate([0,11,23]):strip.paste(images[i].resize((480,270)),(480*n,0))
    png(strip,output/'Akino-Blender-Hand-Views.png')
    (output/'Akino-Blender-Hand.blend').write_bytes((output/'native/hand-only.blend').read_bytes())
    report={'native_frames':24,'native_fps':24,'preview_fps':12,'preview_frames':len(timeline),'image_size':[640,360],'bbox_first_middle_last':[bounds[i] for i in [0,11,23]],'source_transfer_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'job_id':job['job_id'],'provenance':'Blender Cycles CPU; manually authored geometry; no original-art texture; no external model'}
    (output/'acceptance.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args();print(json.dumps(package(args.source,args.output)))
