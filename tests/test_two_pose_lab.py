"""Optional research-dependency tests; default CG installations stay unchanged."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import shutil
import subprocess
import unittest

LAB = Path(__file__).resolve().parents[1] / 'experiments' / 'two_pose'
AVAILABLE = all(importlib.util.find_spec(m) for m in ['numpy','scipy','PIL'])
if AVAILABLE:
    sys.path.insert(0,str(LAB))
    import numpy as np
    from run import load_landmarks, warp, make_frame, save_png
    from run_layered import smooth_warp
    from PIL import Image

@unittest.skipUnless(AVAILABLE,'Optional numpy/scipy/Pillow research dependencies unavailable')
class TwoPoseTests(unittest.TestCase):
    def setUp(self):
        self.points=np.array([[0,0],[15,0],[15,15],[0,15]],dtype=float)
        self.tri=np.array([[0,1,2],[0,2,3]])
        self.rgb=np.full((16,16,3),255,dtype='uint8')
        self.rgb[5:10,4:8]=[210,20,30]

    def test_identity_mesh_has_no_cracks(self):
        result,coverage=warp(self.rgb,self.points,self.points,self.tri)
        np.testing.assert_array_equal(result,self.rgb)
        self.assertTrue((coverage>0).all())

    def test_translated_patch_moves_without_stationary_ghost(self):
        result,_=warp(self.rgb,self.points,self.points+[4,0],self.tri)
        np.testing.assert_array_equal(result[6,9],[210,20,30])
        np.testing.assert_array_equal(result[6,4],[255,255,255])

    def test_both_endpoints_are_exact(self):
        b=255-self.rgb
        np.testing.assert_array_equal(make_frame(self.rgb,b,self.points,self.points,self.tri,0),self.rgb)
        np.testing.assert_array_equal(make_frame(self.rgb,b,self.points,self.points,self.tri,1),b)

    def test_smooth_translation_preserves_premultiplied_alpha(self):
        rgba=np.zeros((16,16,4),dtype='float32');rgba[5:10,4:8]=[210,20,30,255]
        moved=smooth_warp(rgba,self.points,self.points+[4,0])
        np.testing.assert_allclose(moved[6,9],[210,20,30,255],atol=1e-4)
        np.testing.assert_allclose(moved[6,4],[0,0,0,0],atol=1e-4)

    def test_rejects_nonfinite_and_unknown_fields(self):
        data=json.loads((LAB/'akino_landmarks.json').read_text())
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bad.json'
            data['points']['eye_l']['a'][0]=float('nan')
            p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):load_landmarks(p)
            data['execute']='anything';p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):load_landmarks(p)

    def test_annotation_bounds_and_duplicate_detection(self):
        data=json.loads((LAB/'akino_landmarks.json').read_text())
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bad.json'
            data['points']['eye_l']['a']=data['points']['eye_r']['a']
            p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):load_landmarks(p)

    def test_png_serialization_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'frame.png';save_png(Image.fromarray(self.rgb),p)
            with Image.open(p) as im:np.testing.assert_array_equal(np.asarray(im),self.rgb)

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg needed for CLI smoke test')
    def test_complete_cli_writes_readable_media_and_report_without_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            source=root/'source.png'
            Image.new('RGB',(1122,1402),'white').save(source)
            output=root/'new-run'
            command=[sys.executable,str(LAB/'run_layered.py'),'--a',str(source),
                     '--b',str(source),'--landmarks',str(LAB/'akino_landmarks.json'),
                     '--output',str(output),'--frames','2','--width','128']
            result=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads((output/'report.json').read_text())
            self.assertEqual(report['frames'],2)
            self.assertEqual(len(report['layers']),8)
            self.assertTrue(all('linear_baseline_max_folds' in x for x in report['layers']))
            for name in ['Akino-2Pose-24frames.mp4','Akino-2Pose-Comparison.mp4']:
                subprocess.run(['ffmpeg','-v','error','-i',str(output/name),'-f','null','-'],check=True,capture_output=True,timeout=10)
            before=(output/'report.json').read_bytes()
            retry=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertNotEqual(retry.returncode,0)
            self.assertEqual((output/'report.json').read_bytes(),before)

if __name__=='__main__':unittest.main()
