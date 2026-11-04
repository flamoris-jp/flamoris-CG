"""Composite the two existing experiments at matching frame indices.

No registration or new warp: multiply the white-backed outline over the
colored render so the two methods' shape disagreements remain inspectable.
"""
import argparse
import io
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from run import save_png, encode_mp4


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--color',type=Path,required=True)
    parser.add_argument('--outline',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    color=sorted(args.color.glob('*.png'));outline=sorted(args.outline.glob('*.png'))
    if len(color)!=24 or len(outline)!=24 or [p.name for p in color]!=[p.name for p in outline]:
        raise ValueError('Expected the two matching 24-frame experiments')
    args.output.mkdir(parents=True,exist_ok=False)
    for name in ['frames','loop','comparison']:(args.output/name).mkdir()
    frames=[];panels=[]
    font=ImageFont.load_default(size=18)
    for i,(c,l) in enumerate(zip(color,outline)):
        with Image.open(c) as im:rgb=np.array(im.convert('RGB'),dtype=float)
        with Image.open(l) as im:ink=np.array(im.convert('RGB'),dtype=float)
        if rgb.shape!=ink.shape:raise ValueError('Frame size mismatch')
        composite=Image.fromarray(np.rint(rgb*ink/255).astype('uint8'))
        frames.append(composite)
        save_png(composite,args.output/'frames'/f'{i:04}.png')
        height,width=rgb.shape[:2]
        panel=Image.new('RGB',(width*2,height+42),'#162231')
        panel.paste(Image.fromarray(rgb.astype('uint8')),(0,42));panel.paste(composite,(width,42))
        d=ImageDraw.Draw(panel)
        d.text((16,10),'COLOR WARP',font=font,fill='white')
        d.text((width+16,10),'COLOR + OUTLINE',font=font,fill='white')
        panels.append(panel)
    sequence=[0]*12+list(range(24))+[23]*12+list(range(22,0,-1))
    for i,j in enumerate(sequence):
        save_png(frames[j],args.output/'loop'/f'{i:04}.png')
        save_png(panels[j],args.output/'comparison'/f'{i:04}.png')
    encode_mp4(args.output/'loop',args.output/'Akino-Color-Outline.mp4',24)
    encode_mp4(args.output/'comparison',args.output/'Akino-Color-Outline-Comparison.mp4',24)
    buf=io.BytesIO()
    frames[0].save(buf,format='GIF',save_all=True,append_images=[frames[j] for j in sequence[1:]],duration=42,loop=0)
    (args.output/'Akino-Color-Outline.gif').write_bytes(buf.getvalue())
    save_png(panels[12],args.output/'Akino-Color-Outline-Midpoint.png')
    (args.output/'report.json').write_text(json.dumps({'operation':'RGB multiply of same-index frames','frames':24,'fps':24,'loop_frames':len(sequence),'new_registration_or_warp':False,'limitations':['Color and outline use different correspondence methods, so their silhouettes can disagree','Original internal double lines remain; this only overlays the exterior stroke']},indent=2)+'\n')
    print('24 matching frames composited')

if __name__=='__main__':main()
