"""Bounds and portability checks independent of Blender."""
import copy
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from flamoris_cg.spec import load_scene, validate_scene
from flamoris_cg.assets import resolve_png


class SpriteContractTests(unittest.TestCase):
    def setUp(self):
        self.spec = load_scene(ROOT / 'examples/hello_motion.json')
        self.sprite = copy.deepcopy(self.spec['objects'][0])
        self.sprite.update(primitive='sprite', asset='akino')
        self.spec['objects'][0] = self.sprite

    def test_sprite_and_orthographic_camera(self):
        self.spec['camera'].update(projection='orthographic', ortho_scale=8)
        self.assertIs(validate_scene(self.spec), self.spec)

    def test_asset_id_cannot_embed_paths(self):
        for asset in ['../secret', '/tmp/image', 'https://example.com/a', None, 'a.png']:
            with self.subTest(asset=asset), self.assertRaises(ValueError):
                self.sprite['asset'] = asset
                validate_scene(self.spec)

    def test_non_sprite_rejects_asset(self):
        self.sprite['primitive']='cube'
        with self.assertRaises(ValueError): validate_scene(self.spec)

    def test_camera_scale_is_bounded_and_requires_orthographic(self):
        for projection,scale in [('perspective',8),('orthographic',float('inf')),
                                 ('orthographic',True),('orthographic',0)]:
            with self.subTest(projection=projection,scale=scale), self.assertRaises(ValueError):
                self.spec['camera'].update(projection=projection,ortho_scale=scale)
                validate_scene(self.spec)

    def test_asset_header_limits_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); assets=root/'assets'; assets.mkdir()
            path=assets/'akino.png'
            path.write_bytes(b'not a PNG')
            with self.assertRaises(ValueError): resolve_png(assets,'akino')
            path.write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'+struct.pack('>II',4097,100)+b'\0'*9)
            with self.assertRaises(ValueError): resolve_png(assets,'akino')
            with self.assertRaises(ValueError): resolve_png(None,'akino')
            outside=root/'outside.png'; outside.write_bytes(path.read_bytes())
            path.unlink()
            try: path.symlink_to(outside)
            except (OSError,NotImplementedError): self.skipTest('symlinks unavailable')
            with self.assertRaises(ValueError): resolve_png(assets,'akino')


if __name__=='__main__': unittest.main()
