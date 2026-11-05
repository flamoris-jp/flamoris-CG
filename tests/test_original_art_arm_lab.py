import importlib.util
from pathlib import Path
import sys
import unittest
AVAILABLE=all(importlib.util.find_spec(m) for m in ['numpy','scipy','PIL'])
if AVAILABLE:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'/'two_pose'))
    import numpy as np
    from PIL import Image,ImageDraw
    from run_original_art_arm import prepare,render,move_cage,joint_pose,warp_sleeve,hand_layer,PIVOT,SLEEVE,SIZE
    from layers_akino import LAYERS

@unittest.skipUnless(AVAILABLE,'Optional research dependencies unavailable')
class OriginalArtArmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=Image.new('RGB',SIZE,'white');cls.b=Image.new('RGB',SIZE,'white')
        for image,pose,color in [(cls.a,1,(245,185,142)),(cls.b,2,(255,205,166))]:
            d=ImageDraw.Draw(image)
            d.rectangle((450,540,630,1050),fill=(210,218,229))
            if pose==1:
                d.polygon([tuple(p) for p in SLEEVE],fill=(225,224,230),outline=(35,35,40),width=3)
                d.rectangle((669,669,686,687),fill=(205,32,55))
            points=next(l for l in LAYERS if l[0]=='hand_r')[pose]
            d.polygon(points,fill=color,outline=(35,29,28),width=2)
        cls.prepared=prepare(cls.a,cls.b)
    def test_source_and_time_guards(self):
        with self.assertRaises(ValueError):prepare(Image.new('RGB',(64,64)),self.b)
        for t in [float('nan'),-0.01,1.01]:
            with self.assertRaises(ValueError):joint_pose(t)
    def test_source_cage_identity_and_corrected_pivot(self):
        np.testing.assert_allclose(move_cage(SLEEVE,0),SLEEVE,atol=1e-10)
        for t in np.linspace(0,1,11):
            np.testing.assert_allclose(move_cage(np.array([PIVOT]),float(t))[0],PIVOT,atol=1e-10)
    def test_identity_warp_retains_original_pixel_colors(self):
        rgba=self.prepared['sleeve'];image,_=warp_sleeve(rgba,0);out=np.asarray(image)
        interior=rgba[:,:,3]>254
        self.assertGreater(interior.sum(),1000)
        np.testing.assert_array_equal(out[interior,:3],rgba[interior,:3].astype('uint8'))
    def test_hand_surfaces_use_distinct_originals_without_dissolve(self):
        for t,expected in [(0,0),(.49,0),(.51,1),(1,1)]:
            image,view,width=hand_layer(self.prepared['hand_a'],self.prepared['hand_b'],t)
            self.assertEqual(view,expected);self.assertGreaterEqual(width,.16)
            alpha=np.asarray(image.getchannel('A'))
            self.assertGreater((alpha==255).sum(),100)
    def test_composite_preserves_protected_pixels_and_connected_paint(self):
        for t in [0,.5,1]:
            image,c=render(self.prepared,t)
            self.assertEqual(c['outside_edit_pixels'],0)
            self.assertEqual(c['head_changed_pixels'],0)
            self.assertEqual(c['arm_hole_pixels'],0)
            self.assertEqual(c['arm_components'],1)
            self.assertGreater(c['donor_coat_pixels'],0)
