import importlib.util
from pathlib import Path
import sys
import unittest
AVAILABLE=all(importlib.util.find_spec(m) for m in ['numpy','scipy','PIL'])
if AVAILABLE:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'/'two_pose'))
    import numpy as np
    from run_thumb_turn import project,render_turn,raster_hand,extrude,PALM,THUMB

@unittest.skipUnless(AVAILABLE,'Optional research dependencies unavailable')
class ThumbTurnTests(unittest.TestCase):
    def test_twist_preserves_projected_axis_and_reverses_cross_section(self):
        q=np.array([[0,0,0],[0,15,0],[0,-15,0]],float)
        a=project(q,.5,twist=0);b=project(q,.5,twist=np.pi)
        np.testing.assert_allclose(a[0],b[0],atol=1e-10)
        np.testing.assert_allclose(a[1,:2],b[2,:2],atol=1e-10)
    def test_hand_stays_opaque_and_attached_at_three_views(self):
        for t in [0,.5,1]:
            image,c=render_turn(t)
            self.assertEqual(c['holes'],0)
            self.assertEqual(c['components'],1)
            self.assertGreater(c['palm_pixels'],1000)
            self.assertGreater(c['thumb_pixels'],100)
            self.assertLessEqual(c['repaired_subpixel_samples'],16)
    def test_surface_details_are_not_drawn_through_edge_view(self):
        _,front=render_turn(0);_,side=render_turn(.5);_,palm=render_turn(1)
        self.assertGreater(front['visible_detail_pixels'],0)
        self.assertEqual(side['visible_detail_pixels'],0)
        self.assertGreater(palm['visible_detail_pixels'],0)
        self.assertGreater(palm['thumb_boundary_pixels'],0)
    def test_mesh_caps_cover_polygon_area_without_fan_overlap(self):
        for poly in [PALM,THUMB]:
            vertices,faces=extrude(poly,0,7)
            area=abs(np.sum(poly[:,0]*np.roll(poly[:,1],-1)-np.roll(poly[:,0],-1)*poly[:,1]))/2
            total=0
            for face in faces[:len(poly)-2]:
                a,b,c=vertices[face,:2];u,v=b-a,c-a
                total+=abs(u[0]*v[1]-u[1]*v[0])/2
            self.assertAlmostEqual(total,area)
