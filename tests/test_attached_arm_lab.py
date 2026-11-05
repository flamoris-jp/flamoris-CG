import importlib.util
from pathlib import Path
import sys
import unittest
AVAILABLE=all(importlib.util.find_spec(m) for m in ['numpy','scipy','PIL'])
if AVAILABLE:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'/'two_pose'))
    import numpy as np
    from PIL import Image,ImageDraw
    from run_attached_arm import prepare_body,place_arm,compose,render_turn,geometry,S
    from run_joint_arm import display,SIZE

@unittest.skipUnless(AVAILABLE,'Optional research dependencies unavailable')
class AttachedArmTests(unittest.TestCase):
    def test_source_size_guard(self):
        with self.assertRaises(ValueError):prepare_body(Image.new('RGB',(64,64)))
    def test_root_is_pinned_when_source_shoulder_moves(self):
        for t in [0,.5,1]:
            p=display(geometry(t)['shoulder'])
            im=Image.new('RGBA',SIZE)
            ImageDraw.Draw(im).ellipse((p[0]-3,p[1]-3,p[0]+3,p[1]+3),fill='white')
            result=place_arm(im,t,(1122,1402))
            y,x=np.nonzero(np.asarray(result.getchannel('A'))>128)
            np.testing.assert_allclose([x.mean(),y.mean()],S[0],atol=1.5)
    def test_export_alpha_does_not_include_background(self):
        image,_=render_turn(.5,transparent=True,open_shoulder=True)
        self.assertEqual(image.mode,'RGBA')
        alpha=np.asarray(image.getchannel('A'))
        self.assertEqual(alpha[0,0],0)
        self.assertEqual(int(alpha.max()),255)
        self.assertGreater(np.sum(alpha==255),10000)
    def test_original_pixels_and_head_are_preserved_outside_arm(self):
        yy,xx=np.mgrid[:1402,:1122]
        rgb=np.stack([xx%251,yy%249,(xx+yy)%247],axis=2).astype('uint8')
        source=Image.fromarray(rgb);body,head,edit=prepare_body(source)
        for t in [0,1]:
            arm,_=render_turn(t,transparent=True,open_shoulder=True)
            result,c=compose(source,body,head,edit,arm,t)
            self.assertEqual(c['outside_edit_pixels'],0)
            self.assertEqual(c['head_changed_pixels'],0)
            self.assertEqual(c['shoulder_center_alpha'],255)
            self.assertGreater(np.sum(np.any(np.asarray(result)!=rgb,axis=2)),1000)
