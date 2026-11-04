import importlib.util
from pathlib import Path
import sys
import unittest
AVAILABLE=all(importlib.util.find_spec(m) for m in ['numpy','scipy','PIL'])
if AVAILABLE:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'/'two_pose'))
    import numpy as np
    from scipy import ndimage
    from run_joint_arm import geometry,audit,render,S,E,W,SIZE,STROKE

@unittest.skipUnless(AVAILABLE,'Optional research dependencies unavailable')
class JointArmTests(unittest.TestCase):
    def test_measured_joint_endpoints(self):
        for t,i in [(0,0),(1,1)]:
            g=geometry(t)
            for n,expected in [('shoulder',S),('elbow',E),('wrist',W)]:
                np.testing.assert_allclose(g[n],expected[i],atol=1e-10)
    def test_intermediate_motion_uses_rotating_bones(self):
        g=geometry(.5)
        self.assertGreater(np.linalg.norm(g['wrist']-(W[0]+W[1])/2),10)
        lengths=[np.linalg.norm(g['elbow']-g['shoulder']),np.linalg.norm(g['wrist']-g['elbow'])]
        np.testing.assert_allclose(lengths,g['projected_lengths'])
    def test_sampled_geometry_has_connected_paint_without_holes_or_crossings(self):
        for t in np.linspace(0,1,49):
            check=audit(geometry(float(t)))
            self.assertEqual(check['components'],1)
            self.assertEqual(check['holes'],0)
            self.assertEqual(check['self_intersections'],0)
            self.assertGreater(check['sleeve_hand_overlap_pixels'],0)
    def test_paint_interior_is_opaque_at_endpoints_and_midpoint(self):
        for t in [0,.5,1]:
            image,mask=render(geometry(t));rgb=np.asarray(image)
            # Coverage is measured on the same supersampled geometry; inspect
            # pixels safely inside the combined painted area after downsampling.
            from PIL import Image
            coverage=np.asarray(mask.resize(SIZE,Image.Resampling.NEAREST))>0
            interior=ndimage.binary_erosion(coverage,iterations=4)
            background=np.array([231,237,243])
            self.assertFalse(np.any(np.all(rgb[interior]==background,axis=1)))
            self.assertGreater(np.sum(np.all(rgb<90,axis=2)),200)
