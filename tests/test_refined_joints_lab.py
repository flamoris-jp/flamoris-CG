import importlib.util
from pathlib import Path
import sys
import unittest
AVAILABLE=all(importlib.util.find_spec(m) for m in ['numpy','scipy','PIL'])
if AVAILABLE:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'/'two_pose'))
    import numpy as np
    from PIL import Image,ImageDraw
    from refine_original_art_joints import prepare,hand_volume,wrist_shape,cloth_joint,render,SIZE
    from run_original_art_arm import SLEEVE
    from run_joint_arm import self_intersections
    from layers_akino import LAYERS

@unittest.skipUnless(AVAILABLE,'Optional research dependencies unavailable')
class RefinedJointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        a=Image.new('RGB',SIZE,'white');b=Image.new('RGB',SIZE,'white')
        for im,pose in [(a,1),(b,2)]:
            d=ImageDraw.Draw(im);d.rectangle((450,540,630,1050),fill=(225,220,230))
            if pose==1:d.polygon([tuple(q) for q in SLEEVE],fill=(232,231,238),outline=(35,35,40),width=3)
            d.polygon(next(l for l in LAYERS if l[0]=='hand_r')[pose],fill=(248,190,148),outline=(35,29,28),width=2)
        cls.p=prepare(a,b)
    def test_edge_on_hand_has_exposed_side_volume(self):
        _,back=hand_volume(self.p,0);_,edge=hand_volume(self.p,.5);_,palm=hand_volume(self.p,1)
        self.assertAlmostEqual(edge['hand_added_depth'],14)
        self.assertAlmostEqual(back['hand_added_depth'],0)
        self.assertAlmostEqual(palm['hand_added_depth'],0)
        self.assertGreater(edge['hand_side_pixels'],1000)
    def test_wrist_is_tapered_without_self_crossing(self):
        for t in np.linspace(0,1,25):
            q=wrist_shape(float(t))
            self.assertEqual(self_intersections(q),0)
            self.assertGreater(np.linalg.norm(q[0]-q[-1]),1.5*np.linalg.norm(q[2]-q[3]))
    def test_cloth_strip_is_opaque_and_tracks_arm(self):
        before,mask0,q0=cloth_joint(self.p,0);after,mask1,q1=cloth_joint(self.p,1)
        self.assertGreater(int(mask1.sum()),int(mask0.sum()))
        self.assertGreater(np.linalg.norm(q1-q0),10)
        self.assertTrue(np.all(np.asarray(after.getchannel('A'))[mask1]==255))
    def test_joint_coverage_and_source_preservation(self):
        self.assertGreater(self.p['removed_wrist_oval_pixels'],0)
        for t in [0,.25,.5,.75,1]:
            im,c=render(self.p,t)
            self.assertEqual(c['joint_band_unpainted'],0)
            self.assertEqual(c['remaining_arm_holes'],0)
            self.assertEqual(c['head_changed_pixels'],0)
            self.assertEqual(c['outside_edit_pixels'],0)
