"""Pure geometry regressions; actual Blender acceptance is separate."""
import sys,unittest,importlib.util
from pathlib import Path
AVAILABLE=all(importlib.util.find_spec(m) for m in ['numpy','scipy','PIL'])
if AVAILABLE:
    import numpy as np
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments/blender_hand_turn'))
    from fit_source_hand import ARCS_A,ARCS_B,outline,canonical,triangulate_pair,cross


@unittest.skipUnless(AVAILABLE,'Optional fitting dependencies unavailable')
class FittedHandTests(unittest.TestCase):
    def test_common_topology_stays_positive_through_turn(self):
        a,b=[canonical(outline(arcs),i)[::-1] for i,arcs in enumerate([ARCS_A,ARCS_B])]
        triangles=np.array(triangulate_pair(a,b))
        for t in np.linspace(0,1,101):
            p=(1-t)*a+t*b;u=p[triangles[:,1]]-p[triangles[:,0]];v=p[triangles[:,2]]-p[triangles[:,0]]
            self.assertTrue(np.all(u[:,0]*v[:,1]-u[:,1]*v[:,0]>0))

    def test_thumb_passes_towards_camera(self):
        # At a -90 degree roll, thumb's local negative Y becomes positive Z.
        thumb_y=canonical(np.array([[796.,882.]]),0)[0,1]
        self.assertLess(thumb_y,0);self.assertGreater(-thumb_y,0)

    def test_endpoint_geometry_recovers_unmirrored_source(self):
        import math
        from fit_source_hand import WRISTS,DIRECTIONS
        for view,arcs in enumerate([ARCS_A,ARCS_B]):
            source=outline(arcs);local=canonical(source,view)
            if view:local[:,1]*=-1
            angle=-math.atan2(DIRECTIONS[view,1],DIRECTIONS[view,0]);c,s=math.cos(angle),math.sin(angle)
            world=local@np.array([[c,s],[-s,c]])
            target=(source-WRISTS[view])/100;target[:,1]*=-1
            np.testing.assert_allclose(world,target,atol=1e-12)
