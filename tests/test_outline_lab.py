import importlib.util
from pathlib import Path
import sys
import unittest
AVAILABLE=all(importlib.util.find_spec(m) for m in ['numpy','scipy','PIL','contourpy'])
if AVAILABLE:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'/'two_pose'))
    import numpy as np
    from PIL import Image,ImageDraw
    from run_outline import trace,resample,draw

@unittest.skipUnless(AVAILABLE,'Optional outline dependencies unavailable')
class OutlineTests(unittest.TestCase):
    def test_blank_input_rejected(self):
        with self.assertRaises(ValueError):trace(Image.new('RGB',(64,64),'white'))
    def test_white_interior_is_preserved_in_foreground_silhouette(self):
        im=Image.new('RGB',(64,64),'white')
        ImageDraw.Draw(im).rectangle((10,10,50,50),outline='black',width=2)
        q=trace(im)
        self.assertTrue(np.all(q.min(axis=0)<11))
        self.assertTrue(np.all(q.max(axis=0)>49))
    def test_closed_arclength_resampling(self):
        q=np.array([[0,0],[10,0],[10,10],[0,10]],dtype=float)
        r=resample(q,8)
        np.testing.assert_allclose(r[[0,2,4,6]],q)
        np.testing.assert_allclose(np.linalg.norm(np.diff(np.vstack([r,r[0]]),axis=0),axis=1),5)
    def test_redraw_is_unfilled_and_fully_dark(self):
        a=np.array([[10,10],[30,10],[30,30],[10,30]],dtype=float)
        b=a+[20,0]
        im=np.asarray(draw((a+b)/2,(64,64)))
        self.assertTrue(np.all(im[20,30]>250))
        self.assertLess(im[10,30].mean(),90)
        self.assertTrue(np.all(im[10,10]>250))
